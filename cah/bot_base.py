#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Optional,Dict
from random import randrange, choice
from sqlalchemy.sql import func
from slacktools import SlackBotBase, BlockKitBuilder as bkb
from easylogger import Log
import cah.app as cah_app
import cah.cards as cahds
import cah.games as cah_game
from .players import Players
from .model import TablePlayers, TableDecks, TablePlayerRounds


class CAHBot:
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, parent_log: Log = None):
        """
        Args:

        """
        self.bot_name = f'{cah_app.auto_config.BOT_FIRST_NAME} {cah_app.auto_config.BOT_LAST_NAME}'
        self.log = Log(parent_log, child_name='cah_bot')
        self.triggers = cah_app.auto_config.TRIGGERS
        self.channel_id = cah_app.auto_config.MAIN_CHANNEL  # cah or cah-test
        self.admin_user = cah_app.auto_config.ADMINS
        self.version = cah_app.auto_config.VERSION
        self.update_date = cah_app.auto_config.UPDATE_DATE

        # Begin loading and organizing commands
        # Command categories
        cat_basic = 'basic'
        cat_debug = 'debug'
        cat_settings = 'settings'
        cat_player = 'player'
        cat_judge = 'judge'
        cmd_categories = [cat_basic, cat_settings, cat_player, cat_judge, cat_debug]
        self.commands = {
            r'^help': {
                'pattern': 'help',
                'cat': cat_basic,
                'desc': 'Description of all the commands I respond to!',
                'value': [],
            },
            r'^about$': {
                'pattern': 'about',
                'cat': cat_basic,
                'desc': 'Bootup time, version and last update date',
                'value': self.get_bootup_msg,
            },
            r'^m(ain\s?menu|m)': {
                'pattern': 'main menu|mm',
                'cat': cat_basic,
                'desc': 'Access CAH main menu',
                'value': [self.build_main_menu, 'user', 'channel'],
            },
            r'^new game': {
                'pattern': 'new game [FLAGS]',
                'cat': cat_basic,
                'desc': 'Start a new CAH game',
                'value': [self.new_game, 'message'],
                'flags': [
                    {
                        'pattern': '-(set|s) <card-set-name>',
                        'desc': 'Choose a specific card set (e.g., standard, indeed) default: `standard`',
                    }, {
                        'pattern': '-p @p1 @p2 ...',
                        'desc': 'select the specific players in the channel to play with'
                    }
                ]
            },
            r'^new round': {
                'pattern': 'new round',
                'cat': cat_basic,
                'desc': 'For manually transitioning to another round when Wizzy fails to.',
                'value': [self.new_round]
            },
            r'^(points|score[s]?)': {
                'pattern': '(points|score[s]?)',
                'cat': cat_basic,
                'desc': 'Show points / score of all players',
                'value': [self.display_points]
            },
            r'^status': {
                'pattern': 'status',
                'cat': cat_basic,
                'desc': 'Get current status of the game and other metadata',
                'value': [self.display_status]
            },
            r'^toggle (judge\s?|j)ping': {
                'pattern': 'toggle (judge|j)ping',
                'cat': cat_settings,
                'desc': 'Toggles whether or not the judge is pinged after all selections are made. '
                        'default: `True`',
                'value': [self.toggle_judge_ping]
            },
            r'^toggle (winner\s?|w)ping': {
                'pattern': 'toggle (winner|w)ping',
                'cat': cat_settings,
                'desc': 'Toggles whether or not the winner is pinged when they win a round. default: `True`',
                'value': [self.toggle_winner_ping]
            },
            r'^toggle (auto\s?randpick|arp)': {
                'pattern': 'toggle (auto randpick|arp) [-u <user>]',
                'cat': cat_settings,
                'desc': 'Toggles automated randpicking. default: `False`',
                'value': [self.toggle_auto_pick_or_choose, 'user', 'channel', 'message', 'randpick']
            },
            r'^toggle (auto\s?randchoose|arc)': {
                'pattern': 'toggle (auto randchoose|arc) [-u <user>]',
                'cat': cat_settings,
                'desc': 'Toggles automated randchoose (i.e., arp for judges). default: `False`',
                'value': [self.toggle_auto_pick_or_choose, 'user', 'channel', 'message', 'randchoose']
            },
            r'^toggle arparca': {
                'pattern': 'toggle arparca [-u <user>]',
                'cat': cat_settings,
                'desc': 'Toggles both automated randpicking and automated randchoose (i.e., arp for judges).',
                'value': [self.toggle_auto_pick_or_choose, 'user', 'channel', 'message', 'both']
            },
            r'^toggle (card\s?)?dm': {
                'pattern': 'toggle (dm|card dm)',
                'cat': cat_settings,
                'desc': 'Toggles whether or not you receive cards as a DM from Wizzy. default: `True`',
                'value': [self.toggle_card_dm, 'user', 'channel']
            },
            r'^cahds now': {
                'pattern': 'cahds now',
                'cat': cat_player,
                'desc': 'Toggles whether or not you receive cards as a DM from Wizzy. default: `True`',
                'value': [self.dm_cards_now, 'user']
            },
            r'^end game': {
                'pattern': 'end game',
                'cat': cat_basic,
                'desc': 'Ends the current game and saves scores',
                'value': [self.end_game]
            },
            r'^show decks': {
                'pattern': 'show decks',
                'cat': cat_basic,
                'desc': 'Shows the decks currently available',
                'value': [self.show_decks]
            },
            r'^(gsheets?|show) link': {
                'pattern': '(show|gsheet[s]?) link',
                'cat': cat_basic,
                'desc': 'Shows the link to the GSheets database whence Wizzy reads cards. '
                        'Helpful for contributing.',
                'value': self.show_gsheets_link
            },
            r'^p(ick)? \d[\d,]*': {
                'pattern': '(p|pick) <card-num>[<next-card>]',
                'cat': cat_player,
                'desc': 'Pick your card(s) for the round',
                'value': [self.process_picks, 'user', 'message']
            },
            r'^decknuke': {
                'pattern': 'decknuke',
                'cat': cat_player,
                'desc': 'Don\'t like any of your cards? Use this and one card will get randpicked from your '
                        'current deck. The other will be shuffled out and replaced with new cards \n\t\t'
                        f'_NOTE: If your randpicked card is chosen, you\'ll get PENALIZED',
                'value': [self.decknuke, 'user']
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
                'value': [self.process_picks, 'user', 'message']
            },
            r'^c(hoose)? \d': {
                'pattern': '(c|choose) <card-num>',
                'cat': cat_judge,
                'desc': 'Used by the judge to select the :Q:best:Q: card from the picks.',
                'value': [self.choose_card, 'user', 'message']
            },
            r'^randchoose': {
                'pattern': 'randchoose [FLAGS]',
                'cat': cat_judge,
                'desc': 'Randomly choose the best card from all the cards or a subset.',
                'value': [self.choose_card, 'user', 'message'],
                'flags': [
                    {
                        'pattern': '234` or `2,3,4',
                        'desc': 'Choose randomly from a subset'
                    }
                ]
            }
        }
        # Initate the bot, which comes with common tools for interacting with Slack's API
        self.st = SlackBotBase(triggers=self.triggers, credstore=cah_app.credstore,
                               test_channel=self.channel_id, commands=self.commands,
                               cmd_categories=cmd_categories, slack_cred_name=cah_app.auto_config.BOT_NICKNAME,
                               parent_log=self.log)
        self.bot_id = self.st.bot_id
        self.user_id = self.st.user_id
        self.bot = self.st.bot
        self.generate_intro()

        # More game environment-specific initialization stuff
        # Read in decks
        self.decks = None       # type: Optional['Decks']
        # Build out all possible players (for possibly applying settings outside of a game)
        self.potential_players = Players([x.slack_id for x in cah_app.session.query(TablePlayers).all()],
                                         cah_app.session, slack_api=self.st, parent_log=self.log)  # type: Players
        self.game = None        # type: Optional[cah_game.Game]

        self.st.message_test_channel(blocks=self.get_bootup_msg())

        # Store for state across UI responses (thanks Slack for not supporting multi-user selects!)
        self.state_store = {}

    def get_bootup_msg(self) -> List[Dict]:
        return [bkb.make_context_section([
            f"*{self.bot_name}* *`{self.version}`* booted up at `{datetime.now():%F %T}`!",
            f"(updated {self.update_date})"
        ])]

    def generate_intro(self):
        """Generates the intro message and feeds it in to the 'help' command"""
        intro = f"Hi! I'm *{self.bot_name}* and I help you play Cards Against Humanity! \n" \
                f"Be sure to call my attention first with *`{'`* or *`'.join(self.triggers)}`*\n " \
                f"Example: *`c! new game -set standard`*\nHere's what I can do:"
        avi_url = "https://avatars.slack-edge.com/2020-01-28/925065624848_3efb45d2ac590a466dbd_512.png"
        avi_alt = 'dat me'
        # Build the help text based on the commands above and insert back into the commands dict
        self.commands[r'^help']['value'] = self.st.build_help_block(intro, avi_url, avi_alt)
        # Update the command dict in SlackBotBase
        self.st.update_commands(self.commands)

    def cleanup(self, *args):
        """Runs just before instance is destroyed"""
        notify_block = [
            bkb.make_context_section(f'{self.bot_name} died. :death-drops::party-dead::death-drops:')
        ]
        self.st.message_test_channel(blocks=notify_block)
        sys.exit(0)

    def decknuke(self, user: str):
        """Deals the user a new hand while randpicking one of the cards from their current deck.
        The card that's picked will have a negative point value
        """
        self.game.decknuke(player_id=user)

    @staticmethod
    def show_decks() -> str:
        """Returns the deck names currently available"""
        deck_list = [x.name for x in cah_app.session.query(TableDecks).all()]
        return f'`{",".join(deck_list)}`'

    @staticmethod
    def show_gsheets_link():
        return f'https://docs.google.com/spreadsheets/d/{cah_app.cah_creds.spreadsheet_key}/'

    def _read_in_cards(self, card_set: str = 'standard') -> cahds.Deck:
        """Reads in the cards"""
        deck = cah_app.session.query(TableDecks).filter_by(name=card_set).one_or_none()
        if deck is None:
            raise ValueError(f'The card set `{card_set}` was not found. '
                             f'Possible sets: `{",".join(self.decks.deck_names)}`.')
        return cahds.Deck(name=deck.name, session=cah_app.session)

    def new_game(self, deck: str = 'standard', player_ids: List[str] = None, message: str = None):
        """Begins a new game"""
        if self.game is not None:
            if self.game.game_tbl.status != cah_game.GameStatuses.ended:
                self.st.message_test_channel('Looks like you haven\'t ended the current game yet. '
                                             'Do that and then start a new game.')
                return None

        response_list = [f'Using `{deck}` deck']

        # TODO Refresh all channel members' details, including the players' names.
        #  While doing so, make sure they're members of the channel.
        #  If not, invite them?

        # Read in card deck to use with this game
        deck = self._read_in_cards(deck)

        # Load the game, add players, shuffle the players
        self.game = cah_game.Game(player_ids, deck, parent_log=self.log)
        # Get order of judges
        response_list.append(self.game.judge_order)
        # Kick off the new round, message details to the group
        self.new_round(notifications=response_list)

    def toggle_judge_ping(self) -> Optional:
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_judge_ping()
        self.st.message_test_channel(f'Judge pinging set to: `{self.game.game_settings_tbl.is_ping_judge}`')

    def toggle_winner_ping(self) -> Optional:
        """Toggles whether or not to ping the winner when they've won a round"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_winner_ping()
        self.st.message_test_channel(f'Weiner pinging set to: `{self.game.game_settings_tbl.is_ping_winner}`')

    def toggle_card_dm(self, user_id: str, channel: str):
        """Toggles card dming"""
        if self.game is None:
            # Set the player object outside of the game
            player = self.potential_players.get_player(player_attr=user_id, attr_name='player_id')
        else:
            player = self.game.players.get_player(player_attr=user_id, attr_name='player_id')
        player.toggle_cards_dm()
        msg = f'Card DMing for player `{player.display_name}` set to `{player.player_table.is_dm_cards}`'
        self.st.send_message(channel, msg)
        if self.game is not None:
            # Send cards to user if the status shows we're currently in a game
            if self.game.game_tbl.status == cah_game.GameStatuses.players_decision and \
                    player.player_table.is_dm_cards:
                self.dm_cards_now(user_id)
            self.game.players.update_player(player)

    def toggle_auto_pick_or_choose(self, user_id: str, channel: str, message: str, pick_or_choose: str) -> str:
        """Toggles card dming"""
        msg_split = message.split()
        if self.game is None:
            # Set the player object outside of the game
            player = self.potential_players.get_player(player_attr=user_id, attr_name='player_id')
        else:
            player = self.game.players.get_player_by_id(user_id)

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
                            f'`{player.player_table.is_auto_randpick}`')
            if self.game is not None:
                if all([self.game.game_tbl.status == cah_game.GameStatuses.players_decision,
                        player.player_id != self.game.judge.player_id,
                        player.auto_randpick,
                        not player.hand.pick.is_empty()]):
                    # randpick for the player immediately
                    self.process_picks(player.player_id, 'randpick')

        if any([not is_randpick, is_both]):
            # Auto randchoose
            player.toggle_arc()
            resp_msg.append(f'Auto randchoose for player `{player.display_name}` set to '
                            f'`{player.player_table.is_auto_randchoose}`')
            if self.game is not None:
                self.game.players.update_player(player)
                if all([self.game.game_tbl.status == cah_game.GameStatuses.judge_decision,
                        player.player_table.is_auto_randchoose]):
                    self.choose_card(player.player_id, 'randchoose')
            cah_app.session.commit()

        return '\n'.join(resp_msg)

    def dm_cards_now(self, user_id: str) -> Optional:
        """DMs current card set to user"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        player = self.game.players.get_player_by_id(user_id)

        # Send cards to user if the status shows we're currently in a game
        if len(player.hand.cards) == 0:
            msg_txt = "You have no cards to send. This likely means you're not a current player"
            self.st.private_message(player.player_id, msg_txt)
        elif self.game.game_tbl.status == cah_game.GameStatuses.players_decision:
            question_block = self.game.make_question_block()
            cards_block = player.hand.render_hand()
            self.st.private_message(player.player_id, message='', blocks=question_block + cards_block)
        else:
            msg_txt = f"The game's current status (`{self.game.game_tbl.status}`) doesn't allow for card DMing"
            self.st.private_message(player.player_id, msg_txt)

    def build_main_menu(self, user: str, channel: str):
        """Generates and sends a main menu"""
        links = [
            'https://picard.ytmnd.com/',
            'https://darthno.ytmnd.com/',
            'https://christmaschebacca.ytmnd.com/',
            'https://leekspin.ytmnd.com/'
        ]
        button_list = [
            bkb.make_action_button('Status', value='status', action_id='status'),
            bkb.make_action_button('Scores', value='score', action_id='score'),
            bkb.make_action_button('My Details', value='my-details', action_id='my-details', url=choice(links)),
            bkb.make_action_button('New Game', value='newgame', action_id='new-game-start', danger_style=False),
            bkb.make_action_button('Kick/Add to Game', value='kick-add', action_id='kick-add',
                                   url=choice(links)),
        ]
        if self.game is not None and self.game.game_tbl.status not in [cah_game.GameStatuses.ended]:
            button_list.append(
                bkb.make_action_button('End Game', value='end-game', action_id='end-game', danger_style=True,
                                       incl_confirm=True, confirm_title='Really end game?',
                                       confirm_text='Are you sure you want to end the game?', ok_text='Ya',
                                       deny_text='Na')
            )
        blocks = [
            bkb.make_header('CAH International Main Menu'),
            bkb.make_action_button_group(button_list)
        ]
        self.st.private_channel_message(user_id=user, channel=channel,
                                        message='Welcome to the CAH Global Incorporated main menu!',
                                        blocks=blocks)

    def build_new_game_form_p1(self) -> List[Dict]:
        """Builds a new game form with Block Kit"""
        decks = self.decks.deck_names
        decks_list = [{'txt': x, 'value': f'deck_{x}'} for x in decks]

        return [bkb.make_static_select('Select a deck', option_list=decks_list, action_id='new-game-deck')]

    @staticmethod
    def build_new_game_form_p2(user_id: str) -> List[Dict]:
        """Builds the second part to the new game form with Block Kit"""
        return [bkb.make_multi_user_select('Select the players', initial_users=[user_id],
                                           action_id='new-game-users')]

    def process_incoming_action(self, user: str, channel: str, action_dict: Dict, event_dict: Dict) -> Optional:
        """Handles an incoming action (e.g., when a button is clicked)"""
        action_id = action_dict.get('action_id')
        action_value = action_dict.get('value')

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
            formp1 = self.build_new_game_form_p1()
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p1',
                                                   blocks=formp1)
        elif action_id == 'new-game-deck':
            # Set the deck for the new game and then send the second form
            self.state_store['deck'] = action_dict['selected_option']['value'].replace('deck_', '')
            formp2 = self.build_new_game_form_p2(user_id=user)
            resp = self.st.private_channel_message(user_id=user, channel=channel, message='New game form, p2',
                                                   blocks=formp2)
        elif action_id == 'new-game-users':
            self.new_game(deck=self.state_store['deck'], player_ids=action_dict['selected_users'])
        elif action_id == 'status':
            status_block = self.display_status()
            if status_block is not None:
                self.st.send_message(channel=channel, message='Game status', blocks=status_block)
        elif action_id == 'my-details':
            pass
            # TODO: make a show-my-details method that takes in a user and outputs privately all their info
        elif action_id == 'score':
            score_block = self.display_points()
            if score_block is not None:
                self.st.send_message(channel=channel, message='Scores', blocks=score_block)
        elif action_id == 'end-game':
            self.end_game()
        else:
            # Probably should notify the user, but I'm not sure if Slack will attempt
            #   to send requests multiple times if it doesn't get a response in time.
            return None

    def new_round(self, notifications: List[str] = None) -> Optional:
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        """

        # Leverage Block Kit to make notifications fancier
        notification_block = []

        if notifications is not None:
            # Process incoming notifications into the block
            notification_block.append(bkb.make_context_section(notifications))

        self.game.new_round()
        if self.game.game_tbl.status == cah_game.GameStatuses.ended:
            # Game ended because we ran out of questions
            self.st.message_test_channel(blocks=notification_block)
            self.end_game()
            return None

        question_block = self.game.make_question_block()
        notification_block += question_block
        self.st.message_test_channel(blocks=notification_block)

        # Get the required number of answers for the current question
        req_ans = self.game.current_question_card.required_answers

        self.st.private_channel_message(self.game.judge.player_id, self.channel_id, "You're the judge this round!")
        for i, player in enumerate(self.game.players.player_list):
            if player.player_id != self.game.judge.player_id:
                cards_block = player.hand.render_hand(max_selected=req_ans)  # Returns list of blocks
                if player.dm_cards:
                    msg_block = question_block + cards_block
                    dm_chan, ts = self.st.private_message(player.player_id, message='', ret_ts=True,
                                                          blocks=msg_block)
                    player.pick_blocks[dm_chan] = ts
                pchan_ts = self.st.private_channel_message(player.player_id, self.channel_id, ret_ts=True,
                                                           message='', blocks=cards_block)
                player.pick_blocks[self.channel_id] = pchan_ts
                if player.auto_randpick:
                    # Player has elected to automatically pick their cards
                    self.process_picks(player.player_id, 'randpick')
                    if player.dm_cards:
                        self.st.private_message(player.player_id, 'Your pick was handled automatically, '
                                                                  'as you have `auto randpick` enabled.')
                self.game.players.update_player(player)
            # Increment rounds played by this player by 1
            self.game.players.player_list[i].rounds_played += 1

    def process_picks(self, user: str, message: str) -> Optional:
        """Processes the card selection made by the user"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        if self.game.game_tbl.status != cah_game.GameStatuses.players_decision:
            # Prevent this method from being called outside of the player's decision stage
            self.st.message_test_channel(f'<@{user}> You cannot make selections '
                                         f'in the current status of this game: `{self.game.game_tbl.status}`.')
            return None

        self.game.process_picks(user=user, message=message)

    def choose_card(self, user: str, message: str) -> Optional:
        """For the judge to choose the winning card and
        for other players to vote on the card they think should win"""
        if self.game is None:
            self.st.message_test_channel('Start a game first, then tell me to do that.')
            return None

        if self.game.game_tbl.status != cah_game.GameStatuses.judge_decision:
            # Prevent this method from being called outside of the judge's decision stage
            self.st.message_test_channel(f'Not the right status for this command: `{self.game.game_tbl.status}`')
            return None

        self.game.choose_card(user=user, message=message)
        if self.game.judge.pick_idx is not None:
            self._round_wrap_up()

    def _round_wrap_up(self):
        """Coordinates end-of-round logic (tallying votes, picking winner, etc.)"""
        # Make sure all users have votes and judge has made decision before wrapping up the round
        # Handle the announcement of winner and distribution of points
        self.st.message_test_channel(blocks=self._winner_selection())
        self.game.game_tbl.status = cah_game.GameStatuses.end_round
        # Start new round
        self.new_round()

    def _points_redistributer(self, penalty: int) -> str:
        """Handles the logic covering redistribution of wealth among players"""
        # Deduct points from the judge, give randomly to others
        point_receivers = {}  # Store 'name' (of player) and 'points' (distributed)
        # Determine the eligible receivers of the extra points
        nonjudge_players = [x for x in self.game.players.player_list if not x.is_judge]
        player_points_list = [x.points for x in nonjudge_players]
        if sum(player_points_list) == 0:
            # No one has made any points yet - everyone's eligible
            eligible_receivers = [x for x in nonjudge_players]
        else:
            # Some people have earned points already. Make sure those with the highest points aren't eligible
            max_points = max(player_points_list)
            eligible_receivers = [x for x in nonjudge_players if x.points < max_points]
        for pt in range(0, penalty * -1):
            if len(eligible_receivers) > 1:
                player = list(np.random.choice(eligible_receivers, 1))[0]
            elif len(eligible_receivers) == 1:
                # In case everyone has the max score except for one person
                player = eligible_receivers[0]
            else:
                # Everyone has the same score lol. Just pick a random player
                player = list(np.random.choice(nonjudge_players, 1))[0]

            player.add_points(1)
            if player.player_id in point_receivers.keys():
                # Add another point
                point_receivers[player.player_id]['points'] += 1
            else:
                point_receivers[player.player_id] = {
                    'name': player.display_name,
                    'points': 1
                }
            self.game.players.update_player(player)
        point_receivers_txt = '\n'.join([f'`{v["name"]}`: *`{v["points"]}`* :diddlecoin:'
                                         for k, v in point_receivers.items()])
        return point_receivers_txt

    def _winner_selection(self) -> List[dict]:
        """Contains the logic that determines point distributions upon selection of a winner"""
        # Get the list of cards picked by each player
        rps = self.game.round_picks
        winning_pick = rps[self.game.judge.pick_idx]

        # Winner selection
        winner = self.game.players.get_player(winning_pick.id)
        # If decknuke occurred, distribute the points to others randomly
        if winner.nuked_hand:
            penalty = self.game.game_settings_tbl.decknuke_penalty
            point_receivers_txt = self._points_redistributer(penalty)
            points_won = penalty
            decknuke_txt = f'\n:impact::impact::impact::impact:LOLOLOLOLOL HOW DAT DECKNUKE WORK FOR YA NOW??\n' \
                           f'Your points were redistributed such: {point_receivers_txt}'
        else:
            points_won = 1
            decknuke_txt = ''

        winner.add_points(points_won)
        self.game.players.update_player(winner)
        winner_details = winner.player_tag if self.game.game_settings_tbl.is_ping_winner \
            else f'*`{winner.display_name.title()}`*'
        winner_txt_blob = [
            f":regional_indicator_q: *{self.game.current_question_card.txt}*",
            f":tada:Winning card: {winner.hand.pick.render_pick_list_as_str()}",
            f"*`{points_won:+}`* :diddlecoin: to {winner_details}! "
            f"New score: *`{winner.points}`* :diddlecoin: "
            f"({winner.get_grand_score() + winner.points} total){decknuke_txt}\n"
        ]
        last_section = [
            bkb.make_context_section(f'Round ended. Nice going, {self.game.judge.display_name}.')
        ]

        message_block = [
            bkb.make_block_section(winner_txt_blob),
            bkb.make_block_divider(),
        ]
        return message_block + last_section

    def end_game(self) -> Optional:
        """Ends the current game"""
        if self.game is None:
            self.st.message_test_channel('You have to start a game before you can end it...????')
            return None
        if self.game.game_tbl.status != cah_game.GameStatuses.ended:
            # Check if game was not already ended automatically
            self.game.end_game()
        # Save score history to file
        self.display_points()
        self.st.message_test_channel('The game has ended. :died:')

    def display_points(self) -> List[dict]:
        """Displays points for all players"""
        if self.game is None:
            plist = cah_app.session.query(TablePlayers, func.sum(TablePlayerRounds.score).label('game_score'))\
                .join(TablePlayerRounds).all()
        else:
            plist = cah_app.session.query(TablePlayers, func.sum(TablePlayerRounds.score).label('game_score'))\
                .join(TablePlayerRounds)\
                .filter(TablePlayerRounds.game_id == self.game.game_tbl.id).all()

        points_df = pd.DataFrame()
        for player in plist:
            row = {
                'name': player.name,
                'diddles': player.game_score
            }
            points_df = points_df.append(pd.DataFrame(row, index=[0]))

        points_df = points_df.reset_index(drop=True)
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
        points_df['overall'] = points_df['diddles'] + points_df['overall']
        points_df = points_df.sort_values('diddles', ascending=False)

        scores_list = []
        for i, r in points_df.iterrows():
            line = f"{r['rank']} `{r['name'][:20].title():.<30}` " \
                   f"{r['diddles']:<3} :diddlecoin: ({r['overall']:<4}total)"
            scores_list.append(line)
        return [
            bkb.make_context_section('*Current Scores*'),
            bkb.make_block_divider(),
            bkb.make_block_section(scores_list)
        ]

    def display_status(self) -> Optional[List[dict]]:
        """Displays status of the game"""

        if self.game is None:
            self.st.message_test_channel('I just stahted this wicked pissa game, go grab me some dunkies.')
            return None

        status_block = [
            bkb.make_block_section('*Game Info*')
        ]

        if self.game.game_tbl.status not in [cah_game.GameStatuses.ended, cah_game.GameStatuses.initiated]:
            # Players that have card DMing enabled
            dm_players = [f"`{x.display_name}`" for x in self.game.players.player_list if x.dm_cards]
            # Players that have auto randpick enabled
            arp_players = [f"`{x.display_name}`" for x in self.game.players.player_list if x.auto_randpick]
            arc_players = [f"`{x.display_name}`" for x in self.game.players.player_list if x.auto_randchoose]

            status_block += [
                bkb.make_context_section([
                    f':gavel: *Judge*: *`{self.game.judge.display_name.title()}`*'
                ]),
                bkb.make_block_divider(),
                bkb.make_context_section([
                    f'*Status*: *`{self.game.game_tbl.status.replace("_", " ").title()}`*\n'
                    f'*Judge Ping*: `{self.game.game_settings_tbl.is_ping_judge}`\t\t'
                    f'*Weiner Ping*: `{self.game.game_settings_tbl.is_ping_winner}`\n'
                    f':orange_check: *DM Cards*: {" ".join(dm_players)}\n'
                    f':orange_check: *ARP*: {" ".join(arp_players)}\n'
                    f':orange_check: *ARC*: {" ".join(arc_players)}\n'
                ]),
                bkb.make_block_divider(),
                bkb.make_context_section([
                    f':stopwatch: *Round `{self.game.game_tbl.rounds}`*: '
                    f'{self.st.get_time_elapsed(self.game.round_start_time)}\t\t'
                    f'*Game*: {self.st.get_time_elapsed(self.game.game_start_time)}\n',
                    f':stack-of-cards: *Deck*: `{self.game.deck.name}` - '
                    f'`{len(self.game.deck.questions_card_list)}` question &'
                    f' `{len(self.game.deck.answers_card_list)}` answer cards remain',
                    f':conga_parrot: *Player Order*: '
                    f'{" ".join([f"`{x.display_name}`" for x in self.game.players.player_list])}'
                ])
            ]

        if self.game.game_tbl.status in [cah_game.GameStatuses.players_decision,
                                         cah_game.GameStatuses.judge_decision]:
            picks_needed = ['`{}`'.format(x) for x in self.game.players_left_to_pick()]
            pickle_txt = '' if len(picks_needed) == 0 else f'\n:pickle-sword: ' \
                                                           f'*Pickles Needed*: {" ".join(picks_needed)}'
            status_block = status_block[:1] + [
                bkb.make_block_section(f':regional_indicator_q: `{self.game.current_question_card.txt}`'),
                bkb.make_context_section([
                    f':gavel: *Judge*: *`{self.game.judge.display_name.title()}`*{pickle_txt}'
                ])
            ] + status_block[2:]  # Skip over the previous judge block

        return status_block
