#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from datetime import datetime
import sys
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from loguru import logger
import numpy as np
import pandas as pd
from slacktools import SlackBotBase
from slacktools.block_kit.base import BlocksType
from slacktools.block_kit.blocks import (
    ContextBlock,
    DividerBlock,
    MarkdownContextBlock,
    MarkdownSectionBlock,
)
from slacktools.block_kit.elements.display import (
    ImageElement,
    MarkdownTextElement,
)
from slacktools.block_kit.elements.formatters import (
    DateFormatter,
    DateFormatType,
)
from slacktools.tools import build_commands

from cah import ROOT_PATH
from cah.core.common_methods import refresh_players_in_channel
from cah.core.deck import Deck
from cah.core.games import (
    Game,
    GameStatus,
)
from cah.db_eng import WizzyPSQLClient
from cah.forms import Forms
from cah.model import (
    SettingType,
    TableAnswerCard,
    TableDeck,
    TableGame,
    TablePlayer,
    TablePlayerRound,
    TableQuestionCard,
)
from cah.queries.bot_queries import BotQueries

if TYPE_CHECKING:
    from cah.core.players import Player
    from cah.settings import (
        Development,
        Production,
    )


class CAHBot(Forms):
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, eng: WizzyPSQLClient, props: Dict, parent_log: logger,
                 config: Union['Development', 'Production']):
        """
        Args:

        """
        self.bot_name = f'{config.BOT_FIRST_NAME} {config.BOT_LAST_NAME}'
        self.log = parent_log.bind(child_name=self.__class__.__name__)
        self.eng = eng
        self.config = config
        self.triggers = config.TRIGGERS
        self.channel_id = config.MAIN_CHANNEL  # cah or cah-test
        self.admins = config.ADMINS
        self.version = config.VERSION
        self.update_date = config.UPDATE_DATE

        # Begin loading and organizing commands
        self.commands = build_commands(self, cmd_yaml_path=ROOT_PATH.parent.joinpath('commands.yaml'),
                                       log=self.log)
        # Initate the bot, which comes with common tools for interacting with Slack's API
        self.is_post_exceptions = self.eng.get_setting(SettingType.IS_POST_ERR_TRACEBACK)
        self.st = SlackBotBase(props=props, triggers=self.triggers, main_channel=self.channel_id,
                               admins=self.admins, is_post_exceptions=self.is_post_exceptions,
                               debug=False, use_session=False)
        # Pass in commands to SlackBotBase, where task delegation occurs
        self.log.debug('Patching in commands to SBB...')
        self.st.update_commands(commands=self.commands)
        self.bot_id = self.st.bot_id
        self.user_id = self.st.user_id
        self.bot = self.st.bot
        self.generate_intro()

        super().__init__(st=self.st, eng=self.eng)

        # More game environment-specific initialization stuff
        self.current_game = None        # type: Optional[Game]
        self.bq = BotQueries(eng=eng, log=self.log)

        if self.eng.get_setting(SettingType.IS_ANNOUNCE_STARTUP):
            self.log.debug('IS_ANNOUNCE_STARTUP was enabled, so sending message to main channel')
            self.st.message_main_channel(blocks=self.get_bootup_msg())

        if self.eng.get_setting(SettingType.IS_LOOK_FOR_ONGOING_GAMES):
            self.log.debug('Checking for an ongoing game...')
            self.check_for_ongoing_game()

        # Store for state across UI responses (thanks Slack for not supporting multi-user selects!)
        self.state_store = {
            'decks': ['cahbase']
        }

    def check_for_ongoing_game(self):
        """Determines if the last game in the db was ended properly.
        If not, it assumes that game will need to be started up"""
        with self.eng.session_mgr() as session:
            last_game: TableGame
            last_game = session.query(TableGame).order_by(TableGame.created_date.desc()).limit(1).one_or_none()
            if last_game is not None and last_game.status != GameStatus.ENDED:
                self.log.debug(f'Game id {last_game.game_id} was not ended. Reloading...')
                self.reinstate_game(game_id=last_game.game_id)

    def get_bootup_msg(self) -> BlocksType:
        now = datetime.now()
        bootup_time_txt = f"{DateFormatType.date_short_pretty.value} at {DateFormatType.time_secs.value}"
        formatted_bootup_date = DateFormatter.localize_dates(now, bootup_time_txt)

        update_dtt = datetime.strptime(self.update_date, '%Y-%m-%d_%H:%M:%S')
        update_time_txt = f"{DateFormatType.date_short_pretty.value} at {DateFormatType.time_secs.value}"
        formatted_update_date = DateFormatter.localize_dates(update_dtt, update_time_txt)
        return [
            MarkdownContextBlock([
                f"*{self.bot_name}* *`{self.version}`* booted up {formatted_bootup_date}",
                f"(updated `{formatted_update_date}`)"
            ])
        ]

    def search_help_block(self, message: str) -> Union[BlocksType, str]:
        """Takes in a message and filters command descriptions for output
        """
        self.log.debug(f'Got help search command: {message}')
        return self.st.search_help_block(message=message)

    def generate_intro(self) -> BlocksType:
        """Generates the intro message and feeds it in to the 'help' command"""
        intro = f"Hi! I'm *{self.bot_name}* and I help you play Cards Against Humanity! \n" \
                f"Be sure to call my attention first with *`{'`* or *`'.join(self.triggers)}`*\n " \
                f"Example: *`c! new game -set standard`*\nHere's what I can do:"
        avi_url = "https://avatars.slack-edge.com/2020-01-28/925065624848_3efb45d2ac590a466dbd_512.png"
        avi_alt = 'dat me'
        # Build the help text based on the commands above and insert back into the commands dict
        return self.st.build_help_block(intro, avi_url, avi_alt)

    def cleanup(self, *args):
        """Runs just before instance is destroyed"""
        _ = args
        notify_block = [
            MarkdownContextBlock(f'{self.bot_name} died. Pour one out `010100100100100101010000`').asdict()
        ]
        if self.eng.get_setting(SettingType.IS_ANNOUNCE_SHUTDOWN):
            self.st.message_main_channel(blocks=notify_block)
        self.log.info('Bot shutting down...')
        sys.exit(0)

    def process_slash_command(self, event_dict: Dict):
        """Hands off the slash command processing while also refreshing the session"""
        self.st.parse_slash_command(event_dict)

    def process_event(self, event_dict: Dict):
        """Hands off the event data while also refreshing the session"""
        self.st.parse_message_event(event_dict)

    def process_incoming_action(self, user: str, channel: str, action_dict: Dict, event_dict: Dict) -> Optional:
        """Handles an incoming action (e.g., when a button is clicked)"""
        action_id = action_dict.get('action_id')
        action_value = action_dict.get('value')
        msg = event_dict.get('message', {})
        thread_ts = msg.get('thread_ts')
        self.log.debug(f'Receiving action_id: {action_id} and value: {action_value} from user: {user} in '
                       f'channel: {channel}')

        if action_id.startswith('game-'):
            # Special in-game commands like pick & choose
            parsed_command = ''
            if action_dict['type'] == 'multi_static_select':
                # Multiselect
                selections = action_dict['selected_options']
                for selection in selections:
                    selection_value = selection['value'].replace('-', ' ')
                    if 'all' in selection_value:
                        # Only used for randpick/choose. Results in just the command 'rand(pick|choose)'
                        #   If we're selecting all, we don't need to know any of the other selections.
                        parsed_command = f'{selection_value.split()[0]}'
                        break
                    if parsed_command == '':
                        # Put the entire first value into the parsed command (e.g., 'pick 1'
                        parsed_command = f'{selection_value}'
                    else:
                        # Build on the already-made command by concatenating the number to the end
                        #   e.g. 'pick 1' => 'pick 12'
                        parsed_command += selection_value.split()[1]

            elif action_dict['type'] == 'button':
                # Normal button clicks just send a 'value' key in the payload dict
                parsed_command = action_value.replace('-', ' ')

            if 'pick' in parsed_command:
                # Handle pick/randpick
                self.log.debug(f'Processed "pick" command to: {parsed_command}')
                self.process_picks(user, parsed_command)
            elif 'choose' in parsed_command:
                # handle choose/randchoose
                self.log.debug(f'Processed "choose" command to: {parsed_command}')
                self.choose_card(user, parsed_command)
        elif action_id == 'new-game-start':
            # Kicks off the new game form process
            if self.current_game is not None and self.current_game.status != GameStatus.ENDED:
                self.st.send_message(channel=channel, message=f'Dear <@{user}>, one must end the game '
                                                              f'before one can start a game anew :meditation-fart:')
                return None
            # First ask for the deck
            self.st.send_message(channel=channel, message=f'Looks like <@{user}>, is starting a game. '
                                                          f'Might take a few seconds while they select stuff...')
            with self.eng.session_mgr() as session:
                deck_objs = session.query(TableDeck).order_by(TableDeck.n_answers.desc()).all()
                decks = [(f'{x.name[:25]:.<30}..a{x.n_answers:_>4}..q{x.n_questions:_>4}', x.name) for x in deck_objs]
            formp1 = self.build_new_game_form_p1(decks)
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p1',
                                                blocks=formp1)
        elif action_id == 'new-game-deck':
            # Set the deck for the new game and then send the second form
            self.log.debug('Processing second part of new game process.')
            deck_names = [x['value'].replace('deck_', '') for x in action_dict['selected_options']]
            self.log.debug(f'Extracted these deck names: {deck_names}')
            self.state_store['decks'] = deck_names
            formp2 = self.build_new_game_form_p2(decks_list=deck_names)
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p2',
                                                blocks=formp2)
        elif action_id == 'game-stats':
            # TODO: Build out game stats
            #   number of rounds, avg round time, decknukes, caught decknukes,
            self.st.send_message(channel=channel, message='Game stats is currently in development! '
                                                          'Check back later.', thread_ts=thread_ts)
        elif action_id in ['my-stats', 'player-stats']:
            # TODO: Build out player stats (see my-settings to borrow)
            self.st.send_message(channel=channel, message='My/Player stats is currently in development! '
                                                          'Check back later.', thread_ts=thread_ts)
        elif action_id == 'arparc-player':
            # TODO: Build out arp/arc of other player
            self.st.send_message(channel=channel, message='ARPARC player is currently in development! '
                                                          'Check back later.', thread_ts=thread_ts)
        elif action_id == 'my-cards':
            user_player_obj: Player
            user_player_obj = self.current_game.players.player_dict[user.upper()]
            cards_block = user_player_obj.render_hand()
            self.st.private_channel_message(user_id=user, channel=channel, message='Your cahds', blocks=cards_block)
        elif action_id == 'new-game-users':
            self.new_game(deck_names=self.state_store['decks'], player_hashes=action_dict['selected_users'])
        elif action_id == 'status':
            status_block = self.display_status()
            if status_block is not None:
                self.st.send_message(channel=channel, message='Game status', blocks=status_block,
                                     thread_ts=thread_ts)
        elif action_id == 'modify-question-form':
            qmod_form = self.modify_question_form(original_value=self.current_game.current_question_card.card_text)
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='Modify question form',
                                                blocks=qmod_form)
        elif action_id == 'modify-question':
            # Response from modify question form
            self.current_game.current_question_card.modify_text(eng=self.eng, new_text=action_value)
            self.st.message_main_channel(f'Question updated: *{self.current_game.current_question_card.card_text}*'
                                         f' by <@{user}>')
        elif action_id == 'my-settings':
            self.get_my_settings(user=user, channel=channel)
        elif action_id == 'add-player':
            add_user = self.build_add_user_form()
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='Add player form',
                                                blocks=add_user)
        elif action_id == 'add-player-done':
            if self.current_game is not None:
                add_user = action_dict.get('selected_user')
                self.current_game.players.add_player_to_game(add_user, game_id=self.current_game.game_id,
                                                             game_round_id=self.current_game.game_round_id)
        elif action_id == 'remove-player':
            rem_user = self.build_remove_user_form()
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='Remove player form',
                                                blocks=rem_user)
        elif action_id == 'remove-player-done':
            if self.current_game is not None:
                rem_user = action_dict.get('selected_user')
                self.current_game.players.remove_player_from_game(rem_user)
        elif action_id == 'decknuke':
            if self.current_game is not None:
                self.current_game.decknuke(user)
        elif action_id.startswith('toggle-'):
            action_msg = action_id.replace('-', ' ')
            if action_id == 'toggle-auto-randpick':
                self.toggle_auto_pick_or_choose(user_hash=user, channel=channel, message=action_msg,
                                                pick_or_choose='randpick')
            elif action_id == 'toggle-auto-randchoose':
                self.toggle_auto_pick_or_choose(user_hash=user, channel=channel, message=action_msg,
                                                pick_or_choose='randchoose')
            elif action_id == 'toggle-arparca':
                self.toggle_auto_pick_or_choose(user_hash=user, channel=channel, message=action_msg,
                                                pick_or_choose='both')
            elif action_id == 'toggle-card-dm':
                self.toggle_card_dm(user_hash=user, channel=channel)
        elif action_id == 'score':
            score_block = self.display_points()
            if score_block is not None:
                self.st.send_message(channel=channel, message='Scores', blocks=score_block)
        elif action_id == 'ping':
            ping_txt = self.ping_players_left_to_pick()
            self.st.send_message(channel=channel, message=ping_txt)
        elif action_id == 'end-game':
            self.end_game()
        else:
            # Probably should notify the user, but I'm not sure if Slack will attempt
            #   to send requests multiple times if it doesn't get a response in time.
            return None

    def get_my_settings(self, user: str, channel: str):
        settings_form = self.build_my_settings_form(eng=self.eng, user_id=user)
        _ = self.st.private_channel_message(user_id=user, channel=channel, message='Settings form',
                                            blocks=settings_form)

    def prebuild_main_menu(self, user_hash: str, channel: str):
        """Encapsulates required objects for building and sending the main menu form"""
        self.build_main_menu(game_obj=self.current_game, user=user_hash, channel=channel)

    def new_game(self, deck_names: List[str], player_hashes: List[str] = None, message: str = None):
        """Begins a new game

        Args:
            deck_names: the list of names of the decks to use for this game
            player_hashes: list of the slack hashes assigned to each player
            message: optional, the message used to spin up the game. originally used to orchestrate things,
                but now is somewhat vestigial
        """
        _ = message
        if self.current_game is not None:
            if self.current_game.status != GameStatus.ENDED:
                self.st.message_main_channel('Looks like you haven\'t ended the current game yet. '
                                             'Do that and then start a new game.')
                return None

        response_list = [f'Using decks: `{deck_names}` deck']

        # Read in card deck to use with this game
        self.log.debug('Reading in deck...')
        deck = self._read_in_cards(deck_names)

        # Load the game, add players, shuffle the players
        self.log.debug('Instantiating game object')
        self.current_game = Game(player_hashes=player_hashes, deck=deck, st=self.st, eng=self.eng,
                                 parent_log=self.log, config=self.config)
        # Get order of judges
        self.log.debug('Getting judge order')
        response_list.append(f'Judge order: {self.current_game.get_judge_order()}')
        # Kick off the new round, message details to the group
        self.log.debug('Beginning new round')
        self.new_round(notifications=response_list)

    def refresh_players(self) -> str:
        """Refresh all channel members' details, including the players' names.
        While doing so, make sure they're members of the channel."""
        refresh_players_in_channel(channel='CMPV3K8AE', eng=self.eng, st=self.st, log=self.log)
        if self.current_game is not None:
            self.log.debug('After refresh, syncing display names for current game\'s player objects...')
            with self.eng.session_mgr() as session:
                for uid, player in self.current_game.players.player_dict.items():
                    dname = session.query(TablePlayer.display_name).filter(
                        TablePlayer.slack_user_hash == uid).one().display_name
                    self.current_game.players.player_dict[uid].display_name = dname
        return 'Players refreshed o7'

    def decknuke(self, user: str):
        """Deals the user a new hand while randpicking one of the cards from their current deck.
        The card that's picked will have a negative point value
        """
        if self.current_game is None or self.current_game.status not in [GameStatus.PLAYER_DECISION]:
            return 'Here\'s a nuke for ya :fart:'
        self.current_game.decknuke(player_hash=user)

    def show_decks(self) -> str:
        """Returns the deck names currently available"""
        with self.eng.session_mgr() as session:
            deck_names = [f'`{x.name}`' for x in session.query(TableDeck).all()]
        return ",".join(deck_names)

    def _read_in_cards(self, card_sets: List[str]) -> 'Deck':
        """Reads in the cards"""
        self.log.debug(f'Reading in decks: {card_sets}')
        with self.eng.session_mgr() as session:
            decks: List[TableDeck]
            decks = session.query(TableDeck).filter(TableDeck.name.in_(card_sets)).all()
            if len(decks) == 0:
                possible_decks = [x.name for x in session.query(TableDeck).all()]
                raise ValueError(f'The card sets `{card_sets}` were not found. '
                                 f'Possible deck to combine: `{",".join(possible_decks)}`.')
            deck_combo = []
            for deck in decks:
                deck.times_used += 1
                deck = self.eng.refresh_table_object(tbl_obj=deck, session=session)
                deck_combo.append(deck.name)
        self.log.debug(f'Returned: {deck_combo}. Building card lists from this...')
        return Deck(deck_combo=deck_combo, eng=self.eng)

    def _toggle_bool_setting(self, setting: SettingType):
        # Map of setting attribute names to their toggle methods
        setting_map = {
            setting.IS_PING_JUDGE: {'method': 'toggle_judge_ping', 'attr': 'is_ping_judge'},
            setting.IS_PING_WINNER: {'method': 'toggle_winner_ping', 'attr': 'is_ping_winner'},
        }
        if self.current_game is not None:
            self.log.debug('Toggling setting inside of active game.')
            if setting in setting_map.keys():
                method = setting_map[setting]['method']
                attr = setting_map[setting]['attr']
                getattr(self.current_game, method)()
                new_val = getattr(self.current_game, attr)
            else:
                self.log.error(f'Unable to find setting ({setting}) in setting map. Returning None')
                return None
        else:
            self.log.debug(f'Toggling setting ({setting}) outside of game...')
            old_val = self.eng.get_setting(setting)
            new_val = not old_val
            self.eng.set_setting(setting, setting_val=new_val)
        self.st.message_main_channel(f'`{setting.name}` set to: `{new_val}`')

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        self._toggle_bool_setting(SettingType.IS_PING_JUDGE)

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        self._toggle_bool_setting(SettingType.IS_PING_WINNER)

    def toggle_auto_pick_or_choose(self, user_hash: str, channel: str, message: str, pick_or_choose: str) -> str:
        """Toggles ARP/ARC for player"""
        _ = channel
        msg_split = message.split()
        is_randpick = pick_or_choose == 'randpick'
        is_both = pick_or_choose == 'both'

        if self.current_game is None:
            player = self.eng.get_player_from_hash(user_hash=user_hash)  # type: TablePlayer
        else:
            player = self.current_game.players.player_dict[user_hash]  # type: 'Player'

            # Set the player as the user first, but see if the user is actually picking for someone else
            if any(['<@' in x for x in msg_split]):
                # Player has tagged someone. See if they tagged themselves or another person
                if not any([player.player_tag in x for x in msg_split]):
                    # Tagged someone else. Get that other tag & use it to change the player.
                    ptag = next((x for x in msg_split if '<@' in x))
                    # Clean tag markup, if any
                    ptag = ptag.replace('<@', '').replace('>', '')
                    player = self.current_game.players.player_dict[ptag.upper()]  # type: 'Player'

        resp_msg = []

        if is_randpick or is_both:
            # Auto randpick
            if isinstance(player, TablePlayer):
                player.is_auto_randpick = not player.is_auto_randpick
                resp_msg.append(f'Auto randpick for player `{player.display_name}` set to '
                                f'`{player.is_auto_randpick}`')
            else:
                player.toggle_arp()
                resp_msg.append(f'Auto randpick for player `{player.display_name}` set to '
                                f'`{player.is_arp}`')
            if self.current_game is not None:
                if all([self.current_game.status == GameStatus.PLAYER_DECISION,
                        player.player_hash != self.current_game.judge.player_hash,
                        player.is_arp,
                        not player.is_picked]):
                    # randpick for the player immediately if:
                    #   - game active
                    #   - players' decision status
                    #   - player not judge
                    #   - autorandpick was turned on
                    #   - player picks are empty
                    resp_msg.append('THIS IS TO CONFIRM THAT YOUR RANDPICK HAS BEEN AUTOMATHICALLY '
                                    'HANDLED THIS ROUND, ASSHOLE!!!!')
                    rand_roll = np.random.random()
                    if rand_roll <= 0.10:
                        self.decknuke(player.player_hash)
                    else:
                        self.process_picks(player.player_hash, 'randpick')

        if any([not is_randpick, is_both]):
            # Auto randchoose
            if isinstance(player, TablePlayer):
                player.is_auto_randchoose = not player.is_auto_randchoose
                resp_msg.append(f'Auto randchoose for player `{player.display_name}` set to '
                                f'`{player.is_auto_randchoose}`')
            else:
                player.toggle_arc()
                resp_msg.append(f'Auto randchoose for player `{player.display_name}` set to '
                                f'`{player.is_arc}`')
            if self.current_game is not None:
                if all([self.current_game.status == GameStatus.JUDGE_DECISION,
                        player.player_hash == self.current_game.judge.player_hash,
                        player.is_arc,
                        self.current_game.judge.selected_choice_idx is None]):
                    # randchoose for the player immediately if:
                    #   - game active
                    #   - judge's decision status
                    #   - player is judge
                    #   - autorandchoose was turned on
                    #   - judge picks are empty
                    self.choose_card(player.player_hash, 'randchoose')
        if isinstance(player, TablePlayer):
            # Apply changes to table
            self.eng.refresh_table_object(tbl_obj=player)

        return '\n'.join(resp_msg)

    def toggle_card_dm(self, user_hash: str, channel: str):
        """Toggles card dming"""
        if self.current_game is not None:
            player = self.current_game.players.player_dict[user_hash]
            player.toggle_cards_dm()
            # Send cards to user if the status shows we're currently in a game
            if self.current_game.status == GameStatus.PLAYER_DECISION and player.is_dm_cards:
                self.dm_cards_now(user_hash)
        else:
            player = self.eng.get_player_from_hash(user_hash=user_hash)
            player.is_dm_cards = not player.is_dm_cards
            self.eng.refresh_table_object(tbl_obj=player)

        msg = f'Card DMing for player `{player.display_name}` set to `{player.is_dm_cards}`'
        self.st.send_message(channel, msg)

    def dm_cards_now(self, user_hash: str) -> Optional:
        """DMs current card set to user"""
        if self.current_game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None
        player = self.current_game.players.player_dict[user_hash]

        # Send cards to user if the status shows we're currently in a game
        if player.get_nonreplaceable_cards() == 0:
            msg_txt = "You have no cards to send. This likely means you've recently nuked your deck, " \
                      "or you're not a current player"
            self.st.private_message(player.player_hash, msg_txt)
        elif self.current_game.status == GameStatus.PLAYER_DECISION:
            question_block = self.current_game.make_question_block()
            cards_block = player.render_hand(
                max_selected=self.current_game.current_question_card.responses_required)
            self.st.private_message(player.player_hash, message='Your cards have arrived',
                                    blocks=question_block + cards_block)
        else:
            msg_txt = f"The game's current status (`{self.current_game.status.name}`) doesn't allow for card DMing"
            self.st.private_message(player.player_hash, msg_txt)

    def reinstate_game(self, game_id: int):
        """Reinstates a game after a reboot"""
        # We're binding to a preexisting game
        with self.eng.session_mgr() as session:
            # Find deck combo
            game: TableGame
            game = session.query(TableGame).filter(
                TableGame.game_id == game_id
            ).one_or_none()
            deck = Deck(game.deck_combo.split(','), eng=self.eng, game_id=game_id)
            # Build list of players who played last
            players = session.query(TablePlayer). \
                join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayerRound.game_key == game_id
            ).group_by(TablePlayer.player_id).all()
            player_hashes = [x.slack_user_hash for x in players]
        self.current_game = Game(player_hashes=player_hashes, deck=deck, st=self.st, eng=self.eng,
                                 parent_log=self.log, config=self.config, game_id=game_id)
        self.current_game.reinstate_round()

    def new_round(self, notifications: List[str] = None) -> Optional:
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        """

        # Leverage Block Kit to make notifications fancier
        notification_block = []

        if notifications is not None:
            # Process incoming notifications into the block
            notification_block.append(
                MarkdownContextBlock([x for x in notifications]).asdict()
            )

        if self.current_game.status == GameStatus.ENDED:
            # Game ended because we ran out of questions
            self.st.message_main_channel(blocks=notification_block)
            self.end_game()
            return None

        self.current_game.new_round(notification_block=notification_block)

    def process_picks(self, user_hash: str, message: str) -> Optional:
        """Processes the card selection made by the user"""
        if self.current_game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        if self.current_game.status != GameStatus.PLAYER_DECISION:
            # Prevent this method from being called outside of the player's decision stage
            self.st.message_main_channel(f'<@{user_hash}> You cannot make selections '
                                         f'in the current status of this game: `{self.current_game.status.name}`.')
            return None

        self.current_game.process_picks(player_hash=user_hash, message=message)

    def choose_card(self, user_hash: str, message: str) -> Optional:
        """For the judge to choose the winning card and
        for other players to vote on the card they think should win"""
        if self.current_game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        if self.current_game.status != GameStatus.JUDGE_DECISION:
            # Prevent this method from being called outside of the judge's decision stage
            self.st.message_main_channel(f'Not the right status for this command: '
                                         f'`{self.current_game.status.name}`')
            return None

        self.current_game.choose_card(player_hash=user_hash, message=message)
        if self.current_game.judge.selected_choice_idx is not None:
            self.current_game.round_wrap_up()

    def end_game(self) -> Optional:
        """Ends the current game"""
        if self.current_game is None:
            self.st.message_main_channel('You have to start a game before you can end it...????')
            return None
        if self.current_game.status != GameStatus.ENDED:
            # Check if game was not already ended automatically
            self.current_game.end_game()
        # Save score history to file
        self.display_points()
        self.current_game = None
        self.st.message_main_channel('The game has ended. :died:')

    def get_score(self, in_game: bool = True) -> pd.DataFrame:
        """Queries db for players' scores"""
        # Get overall score
        is_current_game = in_game and self.current_game is not None
        score_df = self.bq.get_overall_score()

        if is_current_game:
            current_df = self.bq.get_score_data_for_display_points(game_id=self.current_game.game_id,
                                                                   game_round_id=self.current_game.game_round_id)
            score_df = score_df.merge(current_df, on=['player_id', 'display_name'], how='left')

            # Determine rank trajectory
            self.log.debug('Determining rank and trajectory...')
            for stage in ['current', 'prev']:
                score_df[f'{stage}_rank'] = score_df[[stage, f'overall_{stage}']].apply(tuple, axis=1).\
                    rank(ascending=False, method='first')
            score_df['rank_chg'] = score_df['prev_rank'] - score_df['current_rank']
            score_df['rank_chg_emoji'] = score_df['rank_chg'].apply(
                lambda x: ':green-triangle-up:' if x > 0 else ':red-triangle-down:' if x < 0 else ':blank:')
        else:
            score_df['rank_chg_emoji'] = ':blank:'
            score_df['current'] = 0
            score_df['current_rank'] = score_df['overall'].rank(ascending=False, method='first')

        return score_df

    def determine_streak(self) -> Tuple[Optional[int], int]:
        self.log.debug('Determining if there\'s currently a streak')
        rounds_df = self.bq.get_player_rounds_in_game(game_id=self.current_game.game_id)
        self.log.debug(f'Pulled {rounds_df.shape[0]} rows of data for current game.')
        # Get previous round, determine who won
        n_streak = 0
        streaker_id = None
        if rounds_df.shape[0] == 0:
            return streaker_id, n_streak
        for r in range(self.current_game.game_round_id - 1, rounds_df.game_round_key.min() - 1, -1):
            self.log.debug(f'Working round {r}...')
            # Determine if round had a caught nuke
            caught_nukes_df = rounds_df.loc[(rounds_df.game_round_key == r) & rounds_df.is_nuked_hand_caught, :]
            if not caught_nukes_df.empty:
                self.log.debug(f'Stopping at round {r} - detected caught decknuke')
                break
            winner = rounds_df.loc[(rounds_df.game_round_key == r) & (rounds_df.score > 0), 'player_id']
            if winner.empty:
                self.log.debug('Result: No winner was found (empty result)')
                break
            if streaker_id is None:
                streaker_id = winner.item()
            elif winner.item() == streaker_id:
                self.log.debug('Same winner found as previously. Incrementing streak.')
                # Same streaker
                n_streak += 1
            elif winner.item() != streaker_id:
                # Check if streaker was judge for this round
                self.log.debug('Winner was not the same. Checking if judge.')
                res = rounds_df.loc[(rounds_df.game_round_key == r) &
                                    (rounds_df.player_id == streaker_id), 'score']
                if pd.isna(res.item()):
                    # They were the judge. Continue, as they might have scored in the round
                    # before to preserve their streak
                    self.log.debug('Streaker was judge this round. Continuing streak count.')
                    continue
                else:
                    # They weren't the judge, so this ends their streak. Break out of the loop
                    self.log.debug('Streaker was not the judge this round. Breaking out of loop.')
                    break
        return streaker_id, n_streak

    def display_points(self) -> BlocksType:
        """Displays points for all players"""
        self.log.debug('Generating scores...')
        score_df = self.get_score(in_game=True)  # type: pd.DataFrame
        self.log.debug(f'Retrieved {score_df.shape[0]} players\' scores')
        if score_df.shape[0] == 0:
            return [
                MarkdownSectionBlock('No one has scored yet. Check back later!')
            ]
        score_df.loc[:, 'rank_emoji'] = [':blank:' for _ in range(score_df.shape[0])]
        if score_df['current'].sum() != 0:
            # Determine the emojis for 1st, 2nd and 3rd place
            is_zero = (score_df.current == 0)
            for r in range(1, 6):
                score_df.loc[(score_df.current_rank == r) & (~is_zero), 'rank_emoji'] = f':cah-rank-{r}:'
        # Determine if the recent winner is on a streak
        score_df['streak'] = ''
        if self.current_game is not None:
            player_id, n_streak = self.determine_streak()
            if n_streak > 0:
                # Streak!
                score_df.loc[score_df.player_id == player_id, 'streak'] = ':steak:' * n_streak
        # Set order of the columns
        score_df = score_df[['rank_chg_emoji', 'rank_emoji', 'current_rank', 'display_name',
                             'current', 'overall', 'streak']]
        score_df = score_df.sort_values('current_rank', ascending=True)

        scores_list = []
        for i, r in score_df.iterrows():
            dname = f"{r['display_name'][:14].title():_<15}"
            emos = f"{r['rank_chg_emoji'] + r['rank_emoji']}"
            c_rank = f"{r['current_rank']:>2.0f}"
            scores = f"*`{r['current']:>4.0f}`*`({r['overall']:>4.0f})`"
            streak = f"{r['streak']}"
            line = f"{emos}*`{c_rank}`*` {dname}`:diddlecoin:{scores}{streak}"
            scores_list.append(line)

        return [
            MarkdownContextBlock('*Current Scores*'),
            DividerBlock(),
            MarkdownSectionBlock(scores_list)
        ]

    def ping_players_left_to_pick(self) -> str:
        """Generates a string to tag any players that have yet to pick"""
        if self.current_game is None:
            return 'I can\'t really do this outside of a game WHAT DO YOU WANT FROM ME?!?!?!?!??!'
        elif self.current_game.status == GameStatus.PLAYER_DECISION:
            self.log.debug('Determining players that haven\'t yet picked for pinging...')
            remaining = self.current_game.players_left_to_pick(as_name=False)
            if len(remaining) > 0:
                tagged = ' and '.join([f'<@{x}>' for x in remaining])
                return f'Hey {tagged} - get out there and make pickles! :pickle-sword::pickle-sword::pickle-sword:'
        elif self.current_game.status == GameStatus.JUDGE_DECISION:
            self.log.debug('Pinging judge to make a choice')
            return f'Hey <@{self.current_game.judge.player_hash}> time to wake up and do your CAHvic doodie'
        else:
            self.log.debug(f'Status wasn\'t right for pinging: {self.current_game.status}.')
            return 'IDK - looks like the wrong status for a ping, bucko.'

    @staticmethod
    def _generate_avi_context_section(players: List['Player'],
                                      pretext: str) -> List[Union[MarkdownTextElement, ImageElement]]:
        """Generates a context section with players' avatars rendered"""
        sect_list = [MarkdownTextElement(pretext)]
        if len(players) == 0:
            return sect_list
        player_list = [ImageElement(x.avi_url, x.display_name) for x in players]
        if len(sect_list + player_list) > 10:
            # Only 10 elements are allowed in a context block at a given time
            player_list = player_list[:9]
        return sect_list + player_list

    def modify_question_text(self, new_text: str):
        """Modifies the question text"""
        # TODO: MAke sure the question id is passed in the form to modify in case the modification
        #  happens into the following round
        with self.eng.session_mgr() as session:
            session.query(TableQuestionCard).filter(
                TableQuestionCard.question_card_id == self.current_game.current_question_card.question_card_id
            ).update({
                TableQuestionCard.card_text: new_text
            })

    def modify_answer_text(self, answer_card_id: int, new_text: str):
        """Modifies the question text"""
        with self.eng.session_mgr() as session:
            session.query(TableAnswerCard).filter(TableAnswerCard.answer_card_id == answer_card_id).update({
                TableAnswerCard.card_text: new_text
            })

    def display_status(self, hide_identities: bool = True) -> Optional[BlocksType]:
        """Displays status of the game"""

        if self.current_game is None:
            self.st.message_main_channel('I just stahted this wicked pissa game, go grab me some dunkies.')
            return None

        status_block = [
            MarkdownSectionBlock('*Game Info*')
        ]

        if self.current_game.status not in [GameStatus.ENDED, GameStatus.INITIATED]:
            icon = ':orange_check:'

            dmers = self.current_game.players.get_players_with_dm_cards(name_only=False)
            arpers = self.current_game.players.get_players_with_arp(name_only=False)
            arcers = self.current_game.players.get_players_with_arc(name_only=False)

            # Players that have card DMing enabled
            dm_section = self._generate_avi_context_section(dmers, f'{icon} *DM Cards*: ')

            if hide_identities:
                arp_section = f'{icon} *ARP*: {len(arpers)}'
                arc_section = f'{icon} *ARC*: {len(arcers)}'
            else:
                # Players that have auto randpick enabled
                arp_section = self._generate_avi_context_section(arpers, f'{icon} *ARP*: ')
                # Players that have auto randchoose enabled
                arc_section = self._generate_avi_context_section(arcers, f'{icon} *ARC*: ')

            status_section = f'*Status*: *`{self.current_game.status.name.replace("_", " ").title()}`*\n' \
                             f'*Judge Ping*: `{self.current_game.is_ping_judge}`\t\t' \
                             f'*Weiner Ping*: `{self.current_game.is_ping_winner}`\n'
            game_section = f':stopwatch: *Round `{self.current_game.game_round_number}`*: ' \
                           f'{self.st.get_time_elapsed(self.current_game.game_round_tbl.start_time)}\t\t' \
                           f'*Game*: {self.st.get_time_elapsed(self.current_game.game_start_time)}\n' \
                           f':stack-of-cards: *Deck*: `{self.current_game.deck.deck_combo}` - ' \
                           f'`{len(self.current_game.deck.questions_card_list)}` question & ' \
                           f'`{len(self.current_game.deck.answers_card_list)}` answer cards remain\n' \
                           f':conga_parrot: *Judge Order*: {self.current_game.get_judge_order()}'

            status_block += [
                MarkdownContextBlock(f':gavel: *Judge*: *`{self.current_game.judge.get_full_name()}`*'),
                DividerBlock(),
                MarkdownContextBlock(status_section),
                ContextBlock(dm_section),
                MarkdownContextBlock(arp_section),
                MarkdownContextBlock(arc_section),
                DividerBlock(),
                MarkdownContextBlock(game_section)
            ]

        if self.current_game.status in [GameStatus.PLAYER_DECISION, GameStatus.JUDGE_DECISION]:
            picks_needed = ['`{}`'.format(x) for x in self.current_game.players_left_to_pick()]
            pickle_txt = '' if len(picks_needed) == 0 else f'\n:pickle-sword: ' \
                                                           f'*Pickles Needed*: {" ".join(picks_needed)}'
            status_block = status_block[:1] + [
                MarkdownSectionBlock(f':regional_indicator_q: `{self.current_game.current_question_card.card_text}`'),
                MarkdownContextBlock(f':gavel: *Judge*: *`{self.current_game.judge.get_full_name()}` *{pickle_txt}'),
            ] + status_block[2:]  # Skip over the previous judge block

        return status_block
