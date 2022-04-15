#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from datetime import datetime
from typing import (
    List,
    Optional,
    Dict,
    Union,
    TYPE_CHECKING
)
from types import SimpleNamespace
from random import randrange
from sqlalchemy.sql import (
    func,
)
import pandas as pd
from slacktools import (
    SlackBotBase,
    BlockKitBuilder as BKitB
)
from slacktools.tools import build_commands
from loguru import logger
from cah import ROOT_PATH
from cah.model import (
    SettingType,
    TableDeck,
    TablePlayer,
    TablePlayerRound
)
from cah.settings import auto_config
from cah.forms import Forms
from cah.db_eng import WizzyPSQLClient
from cah.core.games import (
    Game,
    GameStatus
)
from cah.core.deck import Deck
from cah.core.common_methods import refresh_players_in_channel
if TYPE_CHECKING:
    from cah.core.players import Player


class CAHBot(Forms):
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, eng: WizzyPSQLClient, bot_cred_entry: SimpleNamespace, parent_log: logger):
        """
        Args:

        """
        self.bot_name = f'{auto_config.BOT_FIRST_NAME} {auto_config.BOT_LAST_NAME}'
        self.log = parent_log.bind(child_name=self.__class__.__name__)
        self.eng = eng
        self.triggers = auto_config.TRIGGERS
        self.channel_id = auto_config.MAIN_CHANNEL  # cah or cah-test
        self.admin_user = auto_config.ADMINS
        self.version = auto_config.VERSION
        self.update_date = auto_config.UPDATE_DATE

        # Begin loading and organizing commands
        self.commands = build_commands(self, cmd_yaml_path=ROOT_PATH.parent.joinpath('commands.yaml'),
                                       log=self.log)
        # Initate the bot, which comes with common tools for interacting with Slack's API
        self.st = SlackBotBase(bot_cred_entry=bot_cred_entry, triggers=self.triggers, main_channel=self.channel_id,
                               parent_log=self.log, debug=True, use_session=False)
        # Pass in commands to SlackBotBase, where task delegation occurs
        self.log.debug('Patching in commands to SBB...')
        self.st.update_commands(commands=self.commands)
        self.bot_id = self.st.bot_id
        self.user_id = self.st.user_id
        self.bot = self.st.bot
        self.generate_intro()

        super().__init__(st=self.st, eng=self.eng, parent_log=self.log)

        # More game environment-specific initialization stuff
        self.current_game = None        # type: Optional[Game]

        if self.eng.get_setting(SettingType.IS_ANNOUNCE_STARTUP):
            self.log.debug('IS_ANNOUNCE_STARTUP was enabled, so sending message to main channel')
            self.st.message_main_channel(blocks=self.get_bootup_msg())

        # Store for state across UI responses (thanks Slack for not supporting multi-user selects!)
        self.state_store = {
            'deck': 'standard'
        }

    def get_bootup_msg(self) -> List[Dict]:
        return [BKitB.make_context_section([
            BKitB.markdown_section(f"*{self.bot_name}* *`{self.version}`* booted up at `{datetime.now():%F %T}`!"),
            BKitB.markdown_section(f"(updated {self.update_date})")
        ])]

    def search_help_block(self, message: str):
        """Takes in a message and filters command descriptions for output
        """
        self.log.debug(f'Got help search command: {message}')
        return self.st.search_help_block(message=message)

    def generate_intro(self):
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
        if self.current_game is not None:
            self.current_game.end_game()
        notify_block = [
            BKitB.make_context_section([BKitB.markdown_section(f'{self.bot_name} died. '
                                                               f':death-drops::party-dead::death-drops:')])
        ]
        if self.eng.get_setting(SettingType.IS_ANNOUNCE_SHUTDOWN):
            self.st.message_main_channel(blocks=notify_block)
        self.log.info('Bot shutting down...')
        sys.exit(0)

    def process_slash_command(self, event_dict: Dict):
        """Hands off the slash command processing while also refreshing the session"""
        # TODO: Log slash
        self.st.parse_slash_command(event_dict)

    def process_event(self, event_dict: Dict):
        """Hands off the event data while also refreshing the session"""
        self.st.parse_event(event_data=event_dict)

    def process_incoming_action(self, user: str, channel: str, action_dict: Dict, event_dict: Dict,
                                ) -> Optional:
        """Handles an incoming action (e.g., when a button is clicked)"""
        _ = event_dict
        action_id = action_dict.get('action_id')
        action_value = action_dict.get('value')
        self.log.debug(f'Receiving action_id: {action_id} and value: {action_value}')

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
            # First ask for the deck
            self.st.send_message(channel=channel, message=f'Looks like <@{user}>, is starting a game. '
                                                          f'Might take a few seconds while they select stuff...')
            with self.eng.session_mgr() as session:
                deck_names = [x.name for x in session.query(TableDeck).all()]
            formp1 = self.build_new_game_form_p1(deck_names)
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p1',
                                                blocks=formp1)

        elif action_id == 'new-game-deck':
            # Set the deck for the new game and then send the second form
            self.log.debug('Processing second part of new game process.')
            deck_name = action_dict['selected_option']['value'].replace('deck_', '')
            self.log.debug(f'Processed deck name to {deck_name}')
            self.state_store['deck'] = deck_name
            formp2 = self.build_new_game_form_p2()
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p2',
                                                blocks=formp2)
        elif action_id == 'new-game-users':
            self.new_game(deck=self.state_store['deck'], player_hashes=action_dict['selected_users'])
        elif action_id == 'status':
            status_block = self.display_status()
            if status_block is not None:
                self.st.send_message(channel=channel, message='Game status', blocks=status_block)
        elif action_id == 'modify-question-form':
            qmod_form = self.modify_question_form(original_value=self.current_game.current_question_card.txt)
            _ = self.st.private_channel_message(user_id=user, channel=channel, message='Modify question form',
                                                blocks=qmod_form)
        elif action_id == 'modify-question':
            # Response from modify question form
            self.current_game.current_question_card.modify_text(eng=self.eng, new_text=action_value)
            self.st.message_main_channel(f'Question updated: *{self.current_game.current_question_card.txt}*'
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
            if self.current_game is not None:
                if self.current_game.status == GameStatus.PLAYER_DECISION:
                    ping_txt = self.ping_players_left_to_pick()
                elif self.current_game.status == GameStatus.JUDGE_DECISION:
                    ping_txt = f'Hey <@{self.current_game.judge.player_hash}> time to do your doodie'
                else:
                    ping_txt = 'Wrong status for a ping, bucko.'
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

    def new_game(self, deck: str = 'standard', player_hashes: List[str] = None, message: str = None):
        """Begins a new game"""
        _ = message
        if self.current_game is not None:
            if self.current_game.status != GameStatus.ENDED:
                self.st.message_main_channel('Looks like you haven\'t ended the current game yet. '
                                             'Do that and then start a new game.')
                return None

        response_list = [f'Using `{deck}` deck']

        # Read in card deck to use with this game
        self.log.debug('Reading in deck...')
        deck = self._read_in_cards(deck)

        # Load the game, add players, shuffle the players
        self.log.debug('Instantiating game object')
        self.current_game = Game(player_hashes=player_hashes, deck=deck, st=self.st, eng=self.eng,
                                 parent_log=self.log)
        # Get order of judges
        self.log.debug('Getting judge order')
        response_list.append(self.current_game.get_judge_order())
        # Kick off the new round, message details to the group
        self.log.debug('Beginning new round')
        self.new_round(notifications=response_list)

    def refresh_players_in_channel(self):
        """Refresh all channel members' details, including the players' names.
        While doing so, make sure they're members of the channel."""
        refresh_players_in_channel(channel=auto_config.MAIN_CHANNEL, eng=self.eng, st=self.st, log=self.log)
        return 'Players refreshed o7'

    def decknuke(self, user: str):
        """Deals the user a new hand while randpicking one of the cards from their current deck.
        The card that's picked will have a negative point value
        """
        if self.current_game is None or self.current_game.status not in [GameStatus.PLAYER_DECISION]:
            return 'Here\'s a nuke for ya :walkfart:'
        self.current_game.decknuke(player_hash=user)

    def show_decks(self) -> str:
        """Returns the deck names currently available"""
        with self.eng.session_mgr() as session:
            deck_names = [f'`{x.name}`' for x in session.query(TableDeck).all()]
        return ",".join(deck_names)

    def _read_in_cards(self, card_set: str = 'standard') -> 'Deck':
        """Reads in the cards"""
        self.log.debug(f'Reading in deck with name: {card_set}')
        with self.eng.session_mgr() as session:
            deck: TableDeck
            deck = session.query(TableDeck).filter(TableDeck.name == card_set).one_or_none()
            if deck is None:
                possible_decks = [x.name for x in session.query(TableDeck).all()]
                raise ValueError(f'The card set `{card_set}` was not found. '
                                 f'Possible sets: `{",".join(possible_decks)}`.')
            deck.times_used += 1
            deck = self.eng.refresh_table_object(tbl_obj=deck, session=session)
        self.log.debug(f'Returned: {deck}. Building card lists from this...')
        return Deck(name=deck.name, eng=self.eng)

    def _toggle_bool_setting(self, setting: SettingType):
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
        """Toggles card dming"""
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
                        player.hand.pick.is_empty()]):
                    # randpick for the player immediately if:
                    #   - game active
                    #   - players' decision status
                    #   - player not judge
                    #   - autorandpick was turned on
                    #   - player picks are empty
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
                        self.current_game.judge.pick_idx is None]):
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
        if len(player.hand.cards) == 0:
            msg_txt = "You have no cards to send. This likely means you're not a current player"
            self.st.private_message(player.player_hash, msg_txt)
        elif self.current_game.status == GameStatus.PLAYER_DECISION:
            question_block = self.current_game.make_question_block()
            cards_block = player.hand.render_hand()
            self.st.private_message(player.player_hash, message='Your cards have arrived',
                                    blocks=question_block + cards_block)
        else:
            msg_txt = f"The game's current status (`{self.current_game.status.name}`) doesn't allow for card DMing"
            self.st.private_message(player.player_hash, msg_txt)

    def new_round(self, notifications: List[str] = None) -> Optional:
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        """

        # Leverage Block Kit to make notifications fancier
        notification_block = []

        if notifications is not None:
            # Process incoming notifications into the block
            notification_block.append(BKitB.make_context_section([BKitB.markdown_section(x)
                                                                  for x in notifications]))

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
        if self.current_game.judge.pick_idx is not None:
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

    def get_score(self, in_game: bool = True) -> List[Dict[str, Union[str, int]]]:
        """Queries db for players' scores"""
        # Get overall score
        is_current_game = in_game and self.current_game is not None
        scores = []
        with self.eng.session_mgr() as session:
            if is_current_game:
                result = session.query(
                    TablePlayer.player_id,
                    TablePlayer.display_name,
                    func.sum(TablePlayerRound.score).label('diddles'),
                    TablePlayer.total_score
                ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                    TablePlayerRound.game_key == self.current_game.game_id
                ).group_by(TablePlayer.player_id).all()
            else:
                result = session.query(
                    TablePlayer.player_id,
                    TablePlayer.display_name,
                    TablePlayer.total_score
                ).filter(TablePlayer.is_active).group_by(TablePlayer.player_id).all()
            for p in result:
                diddles = p.diddles if is_current_game else 0
                score_dict = {
                    'name': p.display_name,
                    'diddles': diddles,
                    'overall': p.total_score
                }
                scores.append(score_dict)

        return scores

    def display_points(self) -> List[dict]:
        """Displays points for all players"""
        self.log.debug('Generating scores...')
        scores = self.get_score(in_game=True)  # type: List[Dict[str, Union[str, int]]]
        points_df = pd.DataFrame(scores)
        self.log.debug(f'Retrieved {points_df.shape[0]} players\' scores')
        if points_df.shape[0] == 0:
            return [
                BKitB.make_block_section('No one has scored yet. Check back later!')
            ]
        # Apply fun emojis
        poops = ['poop_wtf', 'poop', 'poop_ugh', 'poop_tugh', 'poopfire', 'poopstar']

        if points_df['diddles'].sum() == 0:
            points_df.loc[:, 'rank'] = [f':{poops[randrange(0, len(poops))]}:' for _ in range(points_df.shape[0])]
        else:
            # Start off with the basics
            points_df.loc[:, 'rank'] = [f':{poops[randrange(0, len(poops))]}:' for _ in range(points_df.shape[0])]
            points_df['points_rank'] = points_df.diddles.rank(method='dense', ascending=False)
            first_place = points_df['points_rank'].min()
            second_place = first_place + 1
            third_place = second_place + 1
            is_zero = (points_df.diddles == 0)
            points_df.loc[(points_df.points_rank == first_place) & (~is_zero), 'rank'] = ':first_place_medal:'
            points_df.loc[(points_df.points_rank == second_place) & (~is_zero), 'rank'] = ':second_place_medal:'
            points_df.loc[(points_df.points_rank == third_place) & (~is_zero), 'rank'] = ':third_place_medal:'

        # Set order of the columns
        points_df = points_df[['rank', 'name', 'diddles', 'overall']]
        points_df = points_df.sort_values(['diddles', 'overall'], ascending=False)

        scores_list = []
        for i, r in points_df.iterrows():
            line = f"{r['rank']} `{r['name'][:20].title():_<25}`:diddlecoin:`" \
                   f"{r['diddles']:<3} ({r['overall']:<4}overall)`"
            scores_list.append(line)
        return [
            BKitB.make_context_section([BKitB.markdown_section('*Current Scores*')]),
            BKitB.make_block_divider(),
            BKitB.make_block_section(scores_list)
        ]

    def ping_players_left_to_pick(self) -> str:
        """Generates a string to tag any players that have yet to pick"""
        if self.current_game is None:
            return 'I can\'t really do this outside of a game WHAT DO YOU WANT FROM ME?!?!?!?!??!'
        self.log.debug('Determining players that haven\'t yet picked for pinging...')
        remaining = []
        for p_hash, p_obj in self.current_game.players.player_dict.items():
            if p_obj.hand.pick.is_empty() and p_hash != self.current_game.judge.player_hash:
                remaining.append(p_hash)
        if len(remaining) > 0:
            tagged = ' and '.join([f'<@{x}>' for x in remaining])
            return f'Hey {tagged} - get out there and make pickles! :pickle-sword::pickle-sword::pickle-sword:'
        return 'Looks like everyone\'s made picks?'

    @staticmethod
    def _generate_avi_context_section(players: List['Player'], pretext: str):
        """Generates a context section with players' avatars rendered"""
        sect_list = [BKitB.markdown_section(pretext)]
        if len(players) == 0:
            return sect_list
        player_list = [BKitB.make_image_element(x.avi_url, x.display_name) for x in players]
        if len(sect_list + player_list) > 10:
            # Only 10 elements are allowed in a context block at a given time
            player_list = player_list[:9]
        return sect_list + player_list

    def display_status(self) -> Optional[List[dict]]:
        """Displays status of the game"""

        if self.current_game is None:
            self.st.message_main_channel('I just stahted this wicked pissa game, go grab me some dunkies.')
            return None

        status_block = [
            BKitB.make_block_section('*Game Info*')
        ]

        if self.current_game.status not in [GameStatus.ENDED, GameStatus.INITIATED]:
            icon = ':orange_check:'
            # Players that have card DMing enabled
            dm_section = self._generate_avi_context_section(
                self.current_game.players.get_players_with_dm_cards(name_only=False), f'{icon} *DM Cards*: ')
            # Players that have auto randpick enabled
            arp_section = self._generate_avi_context_section(
                self.current_game.players.get_players_with_arp(name_only=False), f'{icon} *ARP*: ')
            # Players that have auto randchoose enabled
            arc_section = self._generate_avi_context_section(
                self.current_game.players.get_players_with_arc(name_only=False), f'{icon} *ARC*: ')

            status_section = f'*Status*: *`{self.current_game.status.name.replace("_", " ").title()}`*\n' \
                             f'*Judge Ping*: `{self.current_game.is_ping_judge}`\t\t' \
                             f'*Weiner Ping*: `{self.current_game.is_ping_winner}`\n'
            game_section = f':stopwatch: *Round `{self.current_game.round_number}`*: ' \
                           f'{self.st.get_time_elapsed(self.current_game.round_start_time)}\t\t' \
                           f'*Game*: {self.st.get_time_elapsed(self.current_game.game_start_time)}\n' \
                           f':stack-of-cards: *Deck*: `{self.current_game.deck.name}` - ' \
                           f'`{len(self.current_game.deck.questions_card_list)}` question & ' \
                           f'`{len(self.current_game.deck.answers_card_list)}` answer cards remain\n' \
                           f':conga_parrot: *Player Order*: ' \
                           f'{" ".join(self.current_game.players.get_player_names(monospace=True))}'

            status_block += [
                BKitB.make_context_section([
                    BKitB.markdown_section(f':gavel: *Judge*: *`{self.current_game.judge.get_full_name()}`*')
                ]),
                BKitB.make_block_divider(),
                BKitB.make_context_section([
                    BKitB.markdown_section(status_section)
                ]),
                BKitB.make_context_section(dm_section),
                BKitB.make_context_section(arp_section),
                BKitB.make_context_section(arc_section),
                BKitB.make_block_divider(),
                BKitB.make_context_section([
                    BKitB.markdown_section(game_section)
                ])
            ]

        if self.current_game.status in [GameStatus.PLAYER_DECISION, GameStatus.JUDGE_DECISION]:
            picks_needed = ['`{}`'.format(x) for x in self.current_game.players_left_to_pick()]
            pickle_txt = '' if len(picks_needed) == 0 else f'\n:pickle-sword: ' \
                                                           f'*Pickles Needed*: {" ".join(picks_needed)}'
            status_block = status_block[:1] + [
                BKitB.make_block_section(f':regional_indicator_q: '
                                         f'`{self.current_game.current_question_card.txt}`'),
                BKitB.make_context_section([
                    BKitB.markdown_section(f':gavel: *Judge*: *`{self.current_game.judge.get_full_name()}`'
                                           f'*{pickle_txt}')
                ])
            ] + status_block[2:]  # Skip over the previous judge block

        return status_block
