#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import pandas as pd
from datetime import datetime
from typing import List, Optional, Dict, Union
from random import randrange
from slacktools import SlackBotBase, BlockKitBuilder as bkb
from easylogger import Log
import cah.app as cah_app
import cah.cards as cahds
import cah.games as cah_game
from .players import Players, Player
from .model import TablePlayers, TableDecks, TableGameSettings, TableGames, TableGameRounds, TableAnswerCards,\
    TableQuestionCards, TablePlayerRounds
from .settings import auto_config
from .forms import Forms


class CAHBot:
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, parent_log: Log):
        """
        Args:

        """
        self.bot_name = f'{auto_config.BOT_FIRST_NAME} {auto_config.BOT_LAST_NAME}'
        self.log = Log(parent_log, child_name='cah_bot')
        self.triggers = auto_config.TRIGGERS
        self.channel_id = auto_config.MAIN_CHANNEL  # cah or cah-test
        self.admin_user = auto_config.ADMINS
        self.version = auto_config.VERSION
        self.update_date = auto_config.UPDATE_DATE

        # Begin loading and organizing commands
        # Command categories
        cat_basic = 'basic'
        cat_settings = 'settings'
        cat_player = 'player'
        cat_judge = 'judge'
        cmd_categories = [cat_basic, cat_settings, cat_player, cat_judge]
        self.commands = {
            r'^help': {
                'pattern': 'help',
                'cat': cat_basic,
                'desc': 'Description of all the commands I respond to!',
                'response': [],
            },
            r'^about$': {
                'pattern': 'about',
                'cat': cat_basic,
                'desc': 'Bootup time, version and last update date',
                'response': [self.get_bootup_msg],
            },
            r'^m(ain\s?menu|m)': {
                'pattern': 'main menu|mm',
                'cat': cat_basic,
                'desc': 'Access CAH main menu',
                'response': [self.prebuild_main_menu, 'user', 'channel'],
            },
            r'^new round': {
                'pattern': 'new round',
                'cat': cat_basic,
                'desc': 'For manually transitioning to another round when Wizzy fails to.',
                'response': [self.new_round]
            },
            r'^(points|score[s]?)': {
                'pattern': '(points|score[s]?)',
                'cat': cat_basic,
                'desc': 'Show points / score of all players',
                'response': [self.display_points]
            },
            r'^status': {
                'pattern': 'status',
                'cat': cat_basic,
                'desc': 'Get current status of the game and other metadata',
                'response': [self.display_status]
            },
            r'^toggle (judge\s?|j)ping': {
                'pattern': 'toggle (judge|j)ping',
                'cat': cat_settings,
                'desc': 'Toggles whether or not the judge is pinged after all selections are made. '
                        'default: `True`',
                'response': [self.toggle_judge_ping]
            },
            r'^toggle (winner\s?|w)ping': {
                'pattern': 'toggle (winner|w)ping',
                'cat': cat_settings,
                'desc': 'Toggles whether or not the winner is pinged when they win a round. default: `True`',
                'response': [self.toggle_winner_ping]
            },
            r'^toggle (auto\s?randpick|arp\s)': {
                'pattern': 'toggle (auto randpick|arp) [-u <user>]',
                'cat': cat_settings,
                'desc': 'Toggles automated randpicking. default: `False`',
                'response': [self.toggle_auto_pick_or_choose, 'user', 'channel', 'message', 'randpick']
            },
            r'^toggle (auto\s?randchoose|arc)': {
                'pattern': 'toggle (auto randchoose|arc) [-u <user>]',
                'cat': cat_settings,
                'desc': 'Toggles automated randchoose (i.e., arp for judges). default: `False`',
                'response': [self.toggle_auto_pick_or_choose, 'user', 'channel', 'message', 'randchoose']
            },
            r'^toggle arparca': {
                'pattern': 'toggle arparca [-u <user>]',
                'cat': cat_settings,
                'desc': 'Toggles both automated randpicking and automated randchoose (i.e., arp for judges).',
                'response': [self.toggle_auto_pick_or_choose, 'user', 'channel', 'message', 'both']
            },
            r'^toggle (cards?\s?)?dm': {
                'pattern': 'toggle (dm|card dm)',
                'cat': cat_settings,
                'desc': 'Toggles whether or not you receive cards as a DM from Wizzy. default: `True`',
                'response': [self.toggle_card_dm, 'user', 'channel']
            },
            r'^cahds now': {
                'pattern': 'cahds now',
                'cat': cat_player,
                'desc': 'Toggles whether or not you receive cards as a DM from Wizzy. default: `True`',
                'response': [self.dm_cards_now, 'user']
            },
            r'^end game': {
                'pattern': 'end game',
                'cat': cat_basic,
                'desc': 'Ends the current game and saves scores',
                'response': [self.end_game]
            },
            r'^show decks': {
                'pattern': 'show decks',
                'cat': cat_basic,
                'desc': 'Shows the decks currently available',
                'response': [self.show_decks]
            },
            r'^(gsheets?|show) link': {
                'pattern': '(show|gsheet[s]?) link',
                'cat': cat_basic,
                'desc': 'Shows the link to the GSheets database whence Wizzy reads cards. '
                        'Helpful for contributing.',
                'response': self.show_gsheets_link
            },
            r'^p(ick)? \d[\d,]*': {
                'pattern': '(p|pick) <card-num>[<next-card>]',
                'cat': cat_player,
                'desc': 'Pick your card(s) for the round',
                'response': [self.process_picks, 'user', 'message']
            },
            r'^decknuke': {
                'pattern': 'decknuke',
                'cat': cat_player,
                'desc': 'Don\'t like any of your cards? Use this and one card will get randpicked from your '
                        'current deck. The other will be shuffled out and replaced with new cards \n\t\t'
                        f'_NOTE: If your randpicked card is chosen, you\'ll get PENALIZED',
                'response': [self.decknuke, 'user']
            },
            r'^randpick': {
                'pattern': 'randpick [FLAGS]',
                'cat': cat_player,
                'desc': 'Randomly select your card when you just can\'t decide.',
                'flags': [
                    {
                        'pattern': '@other_player',
                        'desc': 'Randomly select for another player'
                    }, {
                        'pattern': '1234` or `1,2,3,4',
                        'desc': 'Randomly select from a subset of your cards'
                    }
                ],
                'response': [self.process_picks, 'user', 'message']
            },
            r'^c(hoose)? \d': {
                'pattern': '(c|choose) <card-num>',
                'cat': cat_judge,
                'desc': 'Used by the judge to select the :Q:best:Q: card from the picks.',
                'response': [self.choose_card, 'user', 'message']
            },
            r'^randchoose': {
                'pattern': 'randchoose [FLAGS]',
                'cat': cat_judge,
                'desc': 'Randomly choose the best card from all the cards or a subset.',
                'response': [self.choose_card, 'user', 'message'],
                'flags': [
                    {
                        'pattern': '234` or `2,3,4',
                        'desc': 'Choose randomly from a subset'
                    }
                ]
            },
            r'^ping ppl': {
                'pattern': 'ping ppl',
                'cat': cat_basic,
                'desc': 'Ping players who haven\'t yet picked',
                'response': [self.ping_players_left_to_pick]
            },
        }
        # Initate the bot, which comes with common tools for interacting with Slack's API
        self.st = SlackBotBase(triggers=self.triggers, credstore=cah_app.credstore,
                               test_channel=self.channel_id, commands=self.commands,
                               cmd_categories=cmd_categories, slack_cred_name=auto_config.BOT_NICKNAME,
                               parent_log=self.log)
        self.bot_id = self.st.bot_id
        self.user_id = self.st.user_id
        self.bot = self.st.bot
        self.generate_intro()

        # More game environment-specific initialization stuff
        # Read in decks
        self.decks = cahds.Decks()       # type: Optional['Decks']
        # Build out all possible players (for possibly applying settings outside of a game)
        all_player_ids = [x.slack_id for x in cah_app.db.session.query(TablePlayers.slack_id).all()]
        self.potential_players = Players(player_id_list=all_player_ids, slack_api=self.st,
                                         parent_log=self.log, is_global=True)  # type: Optional[Players]
        self.global_game_settings_tbl = cah_app.db.session.query(TableGameSettings).one_or_none()
        cah_app.db.session.commit()
        self.game = None        # type: Optional[cah_game.Game]

        if not auto_config.DEBUG:
            self.st.message_test_channel(blocks=self.get_bootup_msg())

        # Store for state across UI responses (thanks Slack for not supporting multi-user selects!)
        self.state_store = {}

    def get_bootup_msg(self) -> List[Dict]:
        return [bkb.make_context_section([
            bkb.markdown_section(f"*{self.bot_name}* *`{self.version}`* booted up at `{datetime.now():%F %T}`!"),
            bkb.markdown_section(f"(updated {self.update_date})")
        ])]

    def generate_intro(self):
        """Generates the intro message and feeds it in to the 'help' command"""
        intro = f"Hi! I'm *{self.bot_name}* and I help you play Cards Against Humanity! \n" \
                f"Be sure to call my attention first with *`{'`* or *`'.join(self.triggers)}`*\n " \
                f"Example: *`c! new game -set standard`*\nHere's what I can do:"
        avi_url = "https://avatars.slack-edge.com/2020-01-28/925065624848_3efb45d2ac590a466dbd_512.png"
        avi_alt = 'dat me'
        # Build the help text based on the commands above and insert back into the commands dict
        self.commands[r'^help']['response'] = self.st.build_help_block(intro, avi_url, avi_alt)
        # Update the command dict in SlackBotBase
        self.st.update_commands(self.commands)

    def cleanup(self, *args):
        """Runs just before instance is destroyed"""
        if self.game is not None:
            self.game.end_game()
        notify_block = [
            bkb.make_context_section([bkb.markdown_section(f'{self.bot_name} died. '
                                                           f':death-drops::party-dead::death-drops:')])
        ]
        self.st.message_test_channel(blocks=notify_block)
        self.log.info('Bot shutting down...')
        self.log.close()
        sys.exit(0)

    def process_slash_command(self, event_dict: Dict):
        """Hands off the slash command processing while also refeshing the session"""

        self.st.parse_slash_command(event_dict)

    def process_event(self, event_dict: Dict):
        """Hands off the event data while also refreshing the session"""
        self.st.parse_event(event_data=event_dict)

    def process_incoming_action(self, user: str, channel: str, action_dict: Dict, event_dict: Dict,
                                ) -> Optional:
        """Handles an incoming action (e.g., when a button is clicked)"""

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
                self.process_picks(user, parsed_command)
            elif 'choose' in parsed_command:
                # handle choose/randchoose
                self.choose_card(user, parsed_command)
        elif action_id == 'new-game-start':
            # Kicks off the new game form process
            # First ask for the deck
            self.st.send_message(channel=channel, message=f'Looks like <@{user}>, is starting a game. '
                                                          f'Might take a few seconds while they select stuff...')
            formp1 = Forms.build_new_game_form_p1(self.decks.deck_list)
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p1',
                                                   blocks=formp1)

        elif action_id == 'new-game-deck':
            # Set the deck for the new game and then send the second form
            self.state_store['deck'] = action_dict['selected_option']['value'].replace('deck_', '')
            formp2 = Forms.build_new_game_form_p2(user_id=user)
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p2',
                                                   blocks=formp2)
        elif action_id == 'new-game-users':
            self.new_game(deck=self.state_store['deck'], player_ids=action_dict['selected_users'])
        elif action_id == 'status':
            status_block = self.display_status()
            if status_block is not None:
                self.st.send_message(channel=channel, message='Game status', blocks=status_block)
        elif action_id == 'my-settings':
            settings_form = Forms.build_my_settings_form(session_object=cah_app.db.session, user_id=user)
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='Settings form',
                                                   blocks=settings_form)
        elif action_id == 'add-player':
            add_user = Forms.build_add_user_form()
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='Add player form',
                                                   blocks=add_user)
        elif action_id == 'add-player-done':
            if self.game is not None:
                add_user = action_dict.get('selected_user')
                self.game.players.add_player_to_game(add_user, game_id=self.game.game_id,
                                                     round_id=self.game.gameround_id)
        elif action_id == 'remove-player':
            rem_user = Forms.build_remove_user_form()
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='Remove player form',
                                                   blocks=rem_user)
        elif action_id == 'remove-player-done':
            if self.game is not None:
                rem_user = action_dict.get('selected_user')
                self.game.players.remove_player_from_game(rem_user)
        elif action_id.startswith('toggle-'):
            if action_id == 'toggle-auto-randpick':
                self.toggle_auto_pick_or_choose(user_id=user, channel=channel, message=action_id.replace('-', ' '),
                                                pick_or_choose='randpick')
            elif action_id == 'toggle-auto-randchoose':
                self.toggle_auto_pick_or_choose(user_id=user, channel=channel, message=action_id.replace('-', ' '),
                                                pick_or_choose='randchoose')
            elif action_id == 'toggle-arparca':
                self.toggle_auto_pick_or_choose(user_id=user, channel=channel, message=action_id.replace('-', ' '),
                                                pick_or_choose='both')
            elif action_id == 'toggle-card-dm':
                self.toggle_card_dm(user_id=user, channel=channel)
        elif action_id == 'score':
            score_block = self.display_points()
            if score_block is not None:
                self.st.send_message(channel=channel, message='Scores', blocks=score_block)
        elif action_id == 'ping':
            if self.game is not None:
                if self.game.status == cah_game.GameStatuses.players_decision:
                    ping_txt = self.ping_players_left_to_pick()
                elif self.game.status == cah_game.GameStatuses.judge_decision:
                    ping_txt = f'Hey <@{self.game.judge.player_id}> time to do your doodie'
                else:
                    ping_txt = 'Wrong status for a ping, bucko.'
                self.st.send_message(channel=channel, message=ping_txt)
        elif action_id == 'end-game':
            self.end_game()
        else:
            # Probably should notify the user, but I'm not sure if Slack will attempt
            #   to send requests multiple times if it doesn't get a response in time.
            return None

    def prebuild_main_menu(self, user_id: str, channel: str):
        """Encapsulates required objects for building and sending the main menu form"""
        Forms.build_main_menu(game_obj=self.game, slack_api=self.st, user=user_id, channel=channel)

    def new_game(self, deck: str = 'standard', player_ids: List[str] = None, message: str = None):
        """Begins a new game"""
        if self.game is not None:
            if self.game.status != cah_game.GameStatuses.ended:
                self.st.message_test_channel('Looks like you haven\'t ended the current game yet. '
                                             'Do that and then start a new game.')
                return None

        response_list = [f'Using `{deck}` deck']

        # TODO Refresh all channel members' details, including the players' names.
        #  While doing so, make sure they're members of the channel.

        # Read in card deck to use with this game
        deck = self._read_in_cards(deck)

        # Load the game, add players, shuffle the players
        self.game = cah_game.Game(player_ids, deck, parent_log=self.log)
        # Get order of judges
        response_list.append(self.game.judge_order)
        # Kick off the new round, message details to the group
        self.new_round(notifications=response_list)

    def decknuke(self, user: str):
        """Deals the user a new hand while randpicking one of the cards from their current deck.
        The card that's picked will have a negative point value
        """
        self.game.decknuke(player_id=user)

    def show_decks(self) -> str:
        """Returns the deck names currently available"""
        return f'`{",".join(self.decks.deck_list)}`'

    def game_stats(self):
        return
        # General game stats
        #   - Number of games
        #   - median duration
        #   - longest game
        #   - shortest game - decknukes per game
        games_result = cah_app.db.session.query(TableGames.start_time, TableGames.end_time)
        games_df = pd.DataFrame(games_result.all(), columns=[column['name']
                                                             for column in games_result.column_descriptions])
        n_games = games_df.shape[0]
        # Filter out games that don't have an end date
        games_df = games_df[~games_df['end_time'].isnull()]
        games_df['duration'] = games_df['end_time'] - games_df['start_time']
        median_duration = games_df['duration'].median()
        max_duration = games_df['duration'].max()

        # Round statsfra
        #   - Median number of rounds per game
        #   - most rounds per game
        #   - longest shortest median round
        rounds_result = cah_app.db.session.query(
            TableGameRounds.start_time, TableGameRounds.end_time, TableGameRounds.game_id)
        gamerounds_df = pd.DataFrame(rounds_result.all(), columns=[column['name']
                                                                   for column in rounds_result.column_descriptions])
        n_rounds = gamerounds_df.shape[0]
        # Filter out gamerounds that don't have an end date
        gamerounds_df = gamerounds_df[~gamerounds_df['end_time'].isnull()]
        gamerounds_df['duration'] = gamerounds_df['end_time'] - gamerounds_df['start_time']
        median_round = gamerounds_df['duration'].median()
        max_round = gamerounds_df['duration'].max()
        min_round = gamerounds_df['duration'].min()

        # Card stats
        #   - most chosen
        a_cards_result = cah_app.db.session.query(
            TableAnswerCards.card_text,
            TableAnswerCards.times_chosen,
            TableAnswerCards.times_burned,
            TableAnswerCards.times_picked,
        )
        a_cards_df = pd.DataFrame(a_cards_result.all(),
                                  columns=[column['name'] for column in a_cards_result.column_descriptions])
        n_cards = a_cards_df.shape[0]
        most_chosen = a_cards_df.loc[a_cards_df['times_chosen'].idxmax()]
        most_chosen_text = most_chosen.card_text
        most_chosen_val = most_chosen.times_chosen
        # Player stats
        #   - least/most likely to have caught a decknuke

    @staticmethod
    def show_gsheets_link():
        return f'https://docs.google.com/spreadsheets/d/{cah_app.cah_creds.spreadsheet_key}/'

    def _read_in_cards(self, card_set: str = 'standard') -> cahds.Deck:
        """Reads in the cards"""
        deck = cah_app.db.session.query(TableDecks).filter_by(name=card_set).one_or_none()
        if deck is None:
            raise ValueError(f'The card set `{card_set}` was not found. '
                             f'Possible sets: `{",".join(self.decks.deck_names)}`.')
        return cahds.Deck(name=deck.name)

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        if self.game is None:
            # Apply changes to game settings through the global table
            self.global_game_settings_tbl.is_ping_judge = not self.global_game_settings_tbl.is_ping_judge
            cah_app.db.session.commit()
            new_val = self.global_game_settings_tbl.is_ping_judge
        else:
            self.game.toggle_judge_ping()
            new_val = self.game.is_ping_judge
        self.st.message_test_channel(f'Judge pinging set to: `{new_val}`')

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        if self.game is None:
            # Apply changes to game settings through the global table
            self.global_game_settings_tbl.is_ping_winner = not self.global_game_settings_tbl.is_ping_winner
            cah_app.db.session.commit()
            new_val = self.global_game_settings_tbl.is_ping_winner
        else:
            self.game.toggle_winner_ping()
            new_val = self.game.is_ping_winner
        self.st.message_test_channel(f'Weiner pinging set to: `{new_val}`')

    def toggle_auto_pick_or_choose(self, user_id: str, channel: str, message: str, pick_or_choose: str) -> str:
        """Toggles card dming"""
        msg_split = message.split()
        player = self._get_player_in_or_out_of_game(user_id=user_id)

        # Set the player as the user first, but see if the user is actually picking for someone else
        if any(['<@' in x for x in msg_split]):
            # Player has tagged someone. See if they tagged themselves or another person
            if not any([player.player_tag in x for x in msg_split]):
                # Tagged someone else. Get that other tag & use it to change the player.
                ptag = next((x for x in msg_split if '<@' in x))
                player = self.game.players.get_player(player_attr=ptag.upper(), attr_name='player_tag')

        is_randpick = pick_or_choose == 'randpick'
        is_both = pick_or_choose == 'both'

        resp_msg = []

        if is_randpick or is_both:
            player.toggle_arp()
            resp_msg.append(f'Auto randpick for player `{player.display_name}` set to '
                            f'`{player.is_arp}`')
            if self.game is not None:
                if all([self.game.status == cah_game.GameStatuses.players_decision,
                        player.player_id != self.game.judge.player_id,
                        player.is_arp,
                        player.hand.pick.is_empty()]):
                    # randpick for the player immediately if:
                    #   - game active
                    #   - players' decision status
                    #   - player not judge
                    #   - autorandpick was turned on
                    #   - player picks are empty
                    self.process_picks(player.player_id, 'randpick')

        if any([not is_randpick, is_both]):
            # Auto randchoose
            player.toggle_arc()
            resp_msg.append(f'Auto randchoose for player `{player.display_name}` set to '
                            f'`{player.is_arc}`')
            if self.game is not None:
                if all([self.game.status == cah_game.GameStatuses.judge_decision,
                        player.player_id == self.game.judge.player_id,
                        player.is_arc,
                        self.game.judge.pick_idx is None]):
                    # randchoose for the player immediately if:
                    #   - game active
                    #   - judge's decision status
                    #   - player is judge
                    #   - autorandchoose was turned on
                    #   - judge picks are empty
                    self.choose_card(player.player_id, 'randchoose')

        return '\n'.join(resp_msg)

    def toggle_card_dm(self, user_id: str, channel: str):
        """Toggles card dming"""
        player = self._get_player_in_or_out_of_game(user_id=user_id)
        player.toggle_cards_dm()
        msg = f'Card DMing for player `{player.display_name}` set to `{player.is_dm_cards}`'
        self.st.send_message(channel, msg)
        if self.game is not None:
            # Send cards to user if the status shows we're currently in a game
            if self.game.status == cah_game.GameStatuses.players_decision and \
                    player.is_dm_cards:
                self.dm_cards_now(user_id)

    def _get_player_in_or_out_of_game(self, user_id: str) -> Player:
        """Attempts to retrieve the player object from and existing game if possible, and then falling back to
        A general list of all workspace members if no game currently exists
        """
        if self.game is None:
            # Set the player object outside of the game
            player_retrieval_func = self.potential_players.get_player
        else:
            player_retrieval_func = self.game.players.get_player
        return player_retrieval_func(player_attr=user_id, attr_name='player_id')

    def dm_cards_now(self, user_id: str) -> Optional:
        """DMs current card set to user"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        player = self.game.players.get_player(user_id)

        # Send cards to user if the status shows we're currently in a game
        if len(player.hand.cards) == 0:
            msg_txt = "You have no cards to send. This likely means you're not a current player"
            self.st.private_message(player.player_id, msg_txt)
        elif self.game.status == cah_game.GameStatuses.players_decision:
            question_block = self.game.make_question_block()
            cards_block = player.hand.render_hand()
            self.st.private_message(player.player_id, message='', blocks=question_block + cards_block)
        else:
            msg_txt = f"The game's current status (`{self.game.status.name}`) doesn't allow for card DMing"
            self.st.private_message(player.player_id, msg_txt)

    def new_round(self, notifications: List[str] = None) -> Optional:
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        """

        # Leverage Block Kit to make notifications fancier
        notification_block = []

        if notifications is not None:
            # Process incoming notifications into the block
            notification_block.append(bkb.make_context_section([bkb.markdown_section(x) for x in notifications]))

        if self.game.status == cah_game.GameStatuses.ended:
            # Game ended because we ran out of questions
            self.st.message_test_channel(blocks=notification_block)
            self.end_game()
            return None

        self.game.new_round(notification_block=notification_block)

    def process_picks(self, user: str, message: str) -> Optional:
        """Processes the card selection made by the user"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        if self.game.status != cah_game.GameStatuses.players_decision:
            # Prevent this method from being called outside of the player's decision stage
            self.st.message_test_channel(f'<@{user}> You cannot make selections '
                                         f'in the current status of this game: `{self.game.status.name}`.')
            return None

        self.game.process_picks(user=user, message=message)

    def choose_card(self, user: str, message: str) -> Optional:
        """For the judge to choose the winning card and
        for other players to vote on the card they think should win"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        if self.game.status != cah_game.GameStatuses.judge_decision:
            # Prevent this method from being called outside of the judge's decision stage
            self.st.message_test_channel(f'Not the right status for this command: `{self.game.status.name}`')
            return None

        self.game.choose_card(user=user, message=message)
        if self.game.judge.pick_idx is not None:
            self.game.round_wrap_up()

    def end_game(self) -> Optional:
        """Ends the current game"""
        if self.game is None:
            self.st.message_test_channel('You have to start a game before you can end it...????')
            return None
        if self.game.status != cah_game.GameStatuses.ended:
            # Check if game was not already ended automatically
            self.game.end_game()
        # Save score history to file
        self.display_points()
        self.game = None
        self.st.message_test_channel('The game has ended. :died:')

    def get_score(self, in_game: bool = True) -> List[Dict[str, Union[str, int]]]:
        """Queries db for players' scores"""
        # Get overall score
        overall = cah_app.db.session.query(
            TablePlayers.id,
            TablePlayers.name,
            TablePlayers.total_score
        ).group_by(TablePlayers.id).all()
        current = []
        if in_game and self.game is not None:
            # Calculate in-game score
            current = self.game.get_current_scores()
        cah_app.db.session.commit()
        # Loop through results, build out a usable dictionary
        scores = []
        for player in overall:
            current_results = next(iter([x for x in current if x.id == player.id]), None)
            scores.append({
                'name': player.name,
                'diddles': current_results.diddles if current_results is not None else 0,
                'overall': player.total_score,
                'is_playing': current_results is not None or player.total_score > 0
            })
        return scores

    def display_points(self) -> List[dict]:
        """Displays points for all players"""
        self.log.debug('Generating scores...')
        scores = self.get_score(in_game=True)  # type: List[Dict[str, Union[str, int]]]
        points_df = pd.DataFrame(scores)
        self.log.debug(f'Retrieved {points_df.shape[0]} players\' scores')
        points_df = points_df.loc[points_df['is_playing']].copy()
        self.log.debug(f'Filtered to {points_df.shape[0]} players\' scores')
        if points_df.shape[0] == 0:
            return [
                bkb.make_block_section('No one has scored yet. Check back later!')
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
            bkb.make_context_section([bkb.markdown_section('*Current Scores*')]),
            bkb.make_block_divider(),
            bkb.make_block_section(scores_list)
        ]

    def ping_players_left_to_pick(self) -> str:
        """Generates a string to tag any players that have yet to pick"""
        if self.game is None:
            return 'I can\'t really do this outside of a game WHAT DO YOU WANT FROM ME?!?!?!?!??!'
        self.log.debug('Determining players that haven\'t yet picked for pinging...')
        remaining = []
        for player in self.game.players.player_list:
            if player.hand.pick.is_empty() and player.player_id != self.game.judge.player_id:
                remaining.append(player.player_id)
        if len(remaining) > 0:
            tagged = ' and '.join([f'<@{x}>' for x in remaining])
            return f'Hey {tagged} - get out there and make pickles!'
        return 'Looks like everyone\'s made picks?'

    @staticmethod
    def _generate_avi_context_section(players: List[Player], pretext: str):
        """Generates a context section with players' avatars rendered"""
        sect_list = [bkb.markdown_section(pretext)]
        if len(players) == 0:
            return sect_list
        player_list = [bkb.make_image_element(x.avi_url, x.display_name) for x in players]
        if len(sect_list + player_list) > 10:
            # Only 10 elements are allowed in a context block at a given time
            player_list = player_list[:9]
        return sect_list + player_list

    def display_status(self) -> Optional[List[dict]]:
        """Displays status of the game"""

        if self.game is None:
            self.st.message_test_channel('I just stahted this wicked pissa game, go grab me some dunkies.')
            return None

        status_block = [
            bkb.make_block_section('*Game Info*')
        ]

        if self.game.status not in [cah_game.GameStatuses.ended, cah_game.GameStatuses.initiated]:

            # Players that have card DMing enabled
            dm_section = self._generate_avi_context_section(
                self.game.players.get_players_with_dm_cards(name_only=False), ':orange_check: *DM Cards*: ')
            # Players that have auto randpick enabled
            arp_section = self._generate_avi_context_section(
                self.game.players.get_players_with_arp(name_only=False), ':orange_check: *ARP*: ')
            # Players that have auto randchoose enabled
            arc_section = self._generate_avi_context_section(
                self.game.players.get_players_with_arc(name_only=False), ':orange_check: *ARC*: ')

            status_section = f'*Status*: *`{self.game.status.name.replace("_", " ").title()}`*\n' \
                             f'*Judge Ping*: `{self.game.is_ping_judge}`\t\t' \
                             f'*Weiner Ping*: `{self.game.is_ping_winner}`\n'
            game_section = f':stopwatch: *Round `{self.game.round_number}`*: ' \
                           f'{self.st.get_time_elapsed(self.game.round_start_time)}\t\t' \
                           f'*Game*: {self.st.get_time_elapsed(self.game.game_start_time)}\n' \
                           f':stack-of-cards: *Deck*: `{self.game.deck.name}` - ' \
                           f'`{len(self.game.deck.questions_card_list)}` question & ' \
                           f'`{len(self.game.deck.answers_card_list)}` answer cards remain\n:conga_parrot: ' \
                           f'*Player Order*: {" ".join(self.game.players.get_player_names(monospace=True))}'

            status_block += [
                bkb.make_context_section([
                    bkb.markdown_section(f':gavel: *Judge*: *`{self.game.judge.get_full_name()}`*')
                ]),
                bkb.make_block_divider(),
                bkb.make_context_section([
                    bkb.markdown_section(status_section)
                ]),
                bkb.make_context_section(dm_section),
                bkb.make_context_section(arp_section),
                bkb.make_context_section(arc_section),
                bkb.make_block_divider(),
                bkb.make_context_section([
                    bkb.markdown_section(game_section)
                ])
            ]

        if self.game.status in [cah_game.GameStatuses.players_decision,
                                cah_game.GameStatuses.judge_decision]:
            picks_needed = ['`{}`'.format(x) for x in self.game.players_left_to_pick()]
            pickle_txt = '' if len(picks_needed) == 0 else f'\n:pickle-sword: ' \
                                                           f'*Pickles Needed*: {" ".join(picks_needed)}'
            status_block = status_block[:1] + [
                bkb.make_block_section(f':regional_indicator_q: `{self.game.current_question_card.txt}`'),
                bkb.make_context_section([
                    bkb.markdown_section(f':gavel: *Judge*: *`{self.game.judge.get_full_name()}`'
                                         f'*{pickle_txt}')
                ])
            ] + status_block[2:]  # Skip over the previous judge block

        return status_block
