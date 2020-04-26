#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import string
import random
import pandas as pd
import numpy as np
from typing import List, Optional, Union
from random import randrange
from slacktools import SlackBotBase, BlockKitBuilder
from .cards import Decks, Deck
from .players import Players, Player
from .games import Game
from ._version import get_versions


class CAHBot:
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, log_name: str, xoxb_token: str, xoxp_token: str, debug: bool = False):
        """
        Args:
            log_name: str, name of the kavalkilu.Log object to retrieve
            xoxb_token: str, bot token to use
            xoxp_token: str, user token to use
            debug: bool, if True, will use a different set of triggers for testing purposes
        """
        self.bot_name = f'Wizzy {"Debugus" if debug else "Prodspero"}'
        self.triggers = ['cah', 'c!'] if not debug else ['decah', 'dc!']
        self.channel_id = 'CMPV3K8AE' if not debug else 'CQ1DG4WB1'  # cah or cah-test
        self.admin_user = ['UM35HE6R5']
        # We'll need this to avoid overwriting actual scores
        self.debug = debug
        self.bkb = BlockKitBuilder()

        # Bot version stuff
        version_dict = get_versions()
        self.version = version_dict['version']
        self.update_date = pd.to_datetime(version_dict['date']).strftime('%F %T')
        self.bootup_msg = [self.bkb.make_context_section([
            f"*{self.bot_name}* *`{self.version}`* booted up at `{pd.datetime.now():%F %T}`!",
            f"(updated {self.update_date})"
        ])]

        # GSheets setup stuff
        self.cah_gsheet_key = '1IVYlID7N-eGiBrmew4vgE7FgcVaGJ2PwyncPjfBHx-M'
        self.cah_sheets = {}

        # Generate score wipe confirmation key
        self.confirm_wipe = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))

        intro = f"Hi! I'm *{self.bot_name}* and I help you play Cards Against Humanity! \n" \
                f"Be sure to call my attention first with *`{'`* or *`'.join(self.triggers)}`*\n " \
                f"Example: *`c! new game -set standard`*\nHere's what I can do:"
        avi_url = "https://avatars.slack-edge.com/2020-01-28/925065624848_3efb45d2ac590a466dbd_512.png"
        avi_alt = 'dat me'
        # Command categories
        cat_basic = 'basic'
        cat_debug = 'debug'
        cat_settings = 'settings'
        cat_player = 'player'
        cat_judge = 'judge'
        cmd_categories = [cat_basic, cat_settings, cat_player, cat_judge, cat_debug]

        commands = {
            r'^help': {
                'pattern': 'help',
                'cat': cat_basic,
                'desc': 'Description of all the commands I respond to!',
                'value': '',
            },
            r'^about$': {
                'pattern': 'about',
                'cat': cat_basic,
                'desc': 'Bootup time, version and last update date',
                'value': self.bootup_msg,
            },
            r'^test\s?run': {
                'pattern': 'test run',
                'cat': cat_debug,
                'desc': 'Starts a new test game in #cah-test. Not for use outside of debug mode',
                'value': [self.test_run]
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
                        'pattern': '-skip @p1 @p2 ...',
                        'desc': 'skips players in the channel but not playing'
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
                'desc': 'Toggles whether or not the judge is pinged after all selections are made. default: `True`',
                'value': [self.toggle_judge_ping]
            },
            r'^toggle announcements': {
                'pattern': 'toggle announcements',
                'cat': cat_settings,
                'desc': 'Toggles whether or not pick announcements are made. default: `True`',
                'value': [self.toggle_announce_picks]
            },
            r'^toggle (winner\s?|w)ping': {
                'pattern': 'toggle (winner|w)ping',
                'cat': cat_settings,
                'desc': 'Toggles whether or not the winner is pinged when they win a round. default: `True`',
                'value': [self.toggle_winner_ping]
            },
            r'^toggle voting': {
                'pattern': 'toggle voting',
                'cat': cat_settings,
                'desc': 'Toggles whether or not players can vote on their favorite picks. default: `True`',
                'value': [self.toggle_pick_voting]
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
            r'^refresh sheets': {
                'pattern': 'refresh sheets',
                'cat': cat_basic,
                'desc': 'Refreshes the GSheet database that contains the card sets. '
                        'Can only be done outside a game.',
                'value': [self.handle_refresh_decks]
            },
            r'^(gsheets?|show) link': {
                'pattern': '(show|gsheet[s]?) link',
                'cat': cat_basic,
                'desc': 'Shows the link to the GSheets database whence Wizzy reads cards. '
                        'Helpful for contributing.',
                'value': f'https://docs.google.com/spreadsheets/d/{self.cah_gsheet_key}/'
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
                        '_NOTE: If your randpicked card is chosen, you\'ll get 1:diddlecoin: deducted :hr-smile:_',
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
            },
            r'^wipe score[s]?$': {
                'pattern': 'wipe score',
                'cat': cat_basic,
                'desc': 'Wipe scores (with confirmation before)',
                'value': f'Are you sure you want to wipe scores? '
                         f'Reply with `wipe scores {self.confirm_wipe}` to confirm'
            },
            r'^wipe score[s]? [\w\d]+': {
                'pattern': 'wipe score <confirmation-code>',
                'cat': cat_basic,
                'desc': 'Definitely wipe scores',
                'value': [self.handle_wipe_scores, 'message']
            }
        }
        # Initate the bot, which comes with common tools for interacting with Slack's API
        self.st = SlackBotBase(log_name, triggers=self.triggers, team='orbitalkettlerelay',
                               main_channel=self.channel_id, xoxp_token=xoxp_token, xoxb_token=xoxb_token,
                               commands=commands, cmd_categories=cmd_categories)
        self.bot_id = self.st.bot_id
        self.user_id = self.st.user_id
        self.bot = self.st.bot

        # Reading in GSheets
        self._refresh_sheets()
        # Score sheet name
        self.score_sheet_name = 'x_scores' if not debug else 'x_test_scores'
        # Game info (players, rounds, etc)
        self.game_info_sheet_name = 'x_game_info' if not debug else 'x_test_game_info'
        self.game_info_df = self.cah_sheets[self.game_info_sheet_name].set_index('index')

        # Build the help text based on the commands above and insert back into the commands dict
        commands[r'^help']['value'] = self.st.build_help_block(intro, avi_url, avi_alt)
        # Update the command dict in SlackBotBase
        self.st.update_commands(commands)

        # More game environment-specific initialization stuff
        # Read in decks
        self.decks = None
        self.refresh_decks()
        # Build out players
        self.players = Players(self._build_players())
        self.game = None

        self.st.message_main_channel(blocks=self.bootup_msg)

        # Check for preserved scores
        self.read_score()

    def cleanup(self, *args):
        """Runs just before instance is destroyed"""
        notify_block = [
            self.bkb.make_context_section(f'{self.bot_name} died. :death-drops::party-dead::death-drops:'),
            self.bkb.make_context_section(self.st.build_phrase('pour one out'))
        ]
        self.st.message_main_channel(blocks=notify_block)
        sys.exit(0)

    def test_run(self) -> Optional[str]:
        """Bypass for running a test game in #cah-test with just myself and a test account"""
        # Toggle arp with these player ids and turn off card dming
        arp_players = ['UM8N2JZE3', 'UM3AP9RQT', 'UMRJKAC2W']  # pip, weezy, testhuman

        if self.debug:
            for player in self.players.player_list:
                if player.player_id in arp_players:
                    player.auto_randpick = True
                    player.dm_cards = False
                self.players.update_player(player)
            self.new_game(message='new game -s techindeed')
            self.game.ping_winner = False
        else:
            return 'No.'

    def _build_players(self) -> List[Player]:
        """
        Collects list of users in channel, sets basic, game-related details and
            returns a list of dicts for each human player
        """
        players = []
        for user in self.st.get_channel_members(self.channel_id, humans_only=True):
            # Make sure display name is not empty
            dis_name = user['display_name'].lower() if user['display_name'] != '' else user['name'].lower()
            uid = user['id']
            players.append(Player(uid, dis_name))
        return players

    def show_decks(self) -> str:
        """Returns the deck names currently available"""
        return f'`{",".join(self.decks.deck_names)}`'

    def handle_refresh_decks(self) -> str:
        """Handles top-level checking of game status before refreshing sheets"""
        if self.game is None:
            self.refresh_decks()
            response = f'Sheets have been refreshed! New decks: `{",".join(self.decks.deck_names)}`'
        elif self.game.status not in [self.game.gs.stahted, self.game.gs.ended]:
            response = 'Please end the game before refreshing. THANKSSSS :))))))'
        else:
            self.refresh_decks()
            response = f'Sheets have been refreshed! New decks: `{",".join(self.decks.deck_names)}`'
        return response

    def handle_wipe_scores(self, message: str) -> str:
        """Handles determining if a wipe score command is valid"""
        if self.confirm_wipe in message:
            self.wipe_score()
        else:
            return "Score wipe aborted. Missing confirmation code."

    def _determine_players(self, message: str) -> str:
        """Determines the players for the game"""
        # Parse flags from command
        skip_players = self.st.get_flag_from_command(message, ['skip'], None)
        specific_players = self.st.get_flag_from_command(message, ['p'], None)

        def get_ids_from_msg(raw_ids: str) -> List[str]:
            specific_player_ids = [x for x in raw_ids.split() if '<@' in x]
            # Collect specific player ids
            pids = []
            for p in specific_player_ids:
                # Extract user id
                uid = self.st.parse_tag_from_text(p)
                if uid is None:
                    # Failed at parsing
                    raise ValueError(f'Failed to parse a user id for `{p}`. Game cannot proceed.')
                else:
                    pids.append(uid)
            return pids

        if skip_players is not None or specific_players is not None:
            if skip_players is not None:
                player_ids = get_ids_from_msg(skip_players)
                self.players.skip_players_in_list(player_ids)

            elif specific_players is not None:
                player_ids = get_ids_from_msg(specific_players)
                self.players.skip_players_not_in_list(player_ids)

            # Build the notification message
            notify_msg = 'Skipping: `{}`'.format('`,`'.join(
                [x.display_name for x in self.players.player_list if x.skip]))
        else:
            notify_msg = 'Playing with everyone :you-better-smirk:.'
        return notify_msg

    def _read_in_cards(self, card_set: str = 'standard') -> Deck:
        """Reads in the cards"""
        deck = self.decks.get_deck_by_name(card_set)
        if deck is None:
            raise ValueError(f'The card set `{card_set}` was not found. '
                             f'Possible sets: `{",".join(self.decks.deck_names)}`.')
        return deck

    def new_game(self, message: str) -> Optional:
        """Begins a new game"""
        if self.game is not None:
            if self.game.status != self.game.gs.ended:
                self.st.message_main_channel('Looks like you haven\'t ended the current game yet. '
                                             'Do that and then start a new game.')
                return None

        response_list = []

        # Determine card set to use
        card_set = self.st.get_flag_from_command(message, ['set', 's'], 'standard')
        response_list.append(f'Using `{card_set}` deck')

        # Refresh the players' names, get response from build function
        self.players.load_players_in_channel(self._build_players(), refresh=True)
        response_list.append(self._determine_players(message))

        # Read in card deck
        deck = self._read_in_cards(card_set)

        # Set eligible players, set the game, add players, shuffle the players
        self.players.set_eligible_players()
        self.game = Game(self.st, self.players.eligible_players, deck, trigger_msg=message)
        # Get order of judges
        response_list.append(self.game.judge_order)
        # Kick off the new round, message details to the group
        self.new_round(notifications=response_list, save=False)

    def toggle_judge_ping(self) -> Optional:
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_judge_ping()
        self.st.message_main_channel(f'Judge pinging set to: `{self.game.ping_judge}`')

    def toggle_announce_picks(self) -> Optional:
        """Toggles whether or not to post when a player has made a pick"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_announce_picked()
        self.st.message_main_channel(f'Pick announcements set to: `{self.game.announce_picked}`')

    def toggle_winner_ping(self) -> Optional:
        """Toggles whether or not to ping the winner when they've won a round"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_winner_ping()
        self.st.message_main_channel(f'Weiner pinging set to: `{self.game.ping_winner}`')

    def toggle_pick_voting(self) -> Optional:
        """Toggles whether or not to ping the winner when they've won a round"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_pick_voting()
        self.st.message_main_channel(f'Pick voting set to: `{self.game.pick_voting}`')

    def toggle_card_dm(self, user_id: str, channel: str):
        """Toggles card dming"""
        if self.game is None:
            # Set the player object outside of the game
            player = self.players.get_player_by_id(user_id)
        else:
            player = self.game.players.get_player_by_id(user_id)
        player.dm_cards = not player.dm_cards
        msg = f'Card DMing for player `{player.display_name}` set to `{player.dm_cards}`'
        self.st.send_message(channel, msg)
        if self.game is not None:
            # Send cards to user if the status shows we're currently in a game
            if self.game.status == self.game.gs.players_decision and player.dm_cards:
                self.dm_cards_now(user_id)
            self.game.players.update_player(player)
        else:
            self.players.update_player(player)

    def toggle_auto_pick_or_choose(self, user_id: str, channel: str, message: str, pick_or_choose: str) -> str:
        """Toggles card dming"""
        msg_split = message.split()
        if self.game is None:
            # Set the player object outside of the game
            player = self.players.get_player_by_id(user_id)
        else:
            player = self.game.players.get_player_by_id(user_id)

        # Set the player as the user first, but see if the user is actually picking for someone else
        if any(['<@' in x for x in msg_split]):
            # Player has tagged someone. See if they tagged themselves or another person
            if not any([player.player_tag in x for x in msg_split]):
                # Tagged someone else. Get that other tag & use it to change the player.
                ptag = next((x for x in msg_split if '<@' in x))
                player = self.game.players.get_player_by_tag(ptag.upper())

        is_randpick = pick_or_choose == 'randpick'

        if is_randpick:
            player.auto_randpick = not player.auto_randpick
            resp_msg = f'Auto randpick for player `{player.display_name}` set to `{player.auto_randpick}`'
            if self.game is not None:
                self.game.players.update_player(player)
                if all([self.game.status == self.game.gs.players_decision,
                        player.player_id != self.game.judge.player_id,
                        player.auto_randpick,
                        not player.hand.pick.is_empty()]):
                    # randpick for the player immediately
                    self.process_picks(player.player_id, 'randpick')
            else:
                self.players.update_player(player)
        else:
            # Auto randchoose
            player.auto_randchoose = not player.auto_randchoose
            resp_msg = f'Auto randchoose for player `{player.display_name}` set to `{player.auto_randchoose}`'
            if self.game is not None:
                self.game.players.update_player(player)
                if all([self.game.status == self.game.gs.judge_decision,
                        player.player_id == self.game.judge.player_id,
                        player.auto_randchoose]):
                    self.choose_card(player.player_id, 'randchoose')
            else:
                self.players.update_player(player)

        return resp_msg

    def dm_cards_now(self, user_id: str) -> Optional:
        """DMs current card set to user"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        player = self.game.players.get_player_by_id(user_id)

        # Send cards to user if the status shows we're currently in a game
        if len(player.hand.cards) == 0:
            msg_txt = "You have no cards to send. This likely means you're not a current player"
            self.st.private_message(player.player_id, msg_txt)
        elif self.game.status == self.game.gs.players_decision:
            question_block = self.make_question_block()
            cards_block = player.hand.render_hand()
            self.st.private_message(player.player_id, message='', blocks=question_block + cards_block)
        else:
            msg_txt = f"The game's current status (`{self.game.status}`) doesn't allow for card DMing"
            self.st.private_message(player.player_id, msg_txt)

    def make_question_block(self) -> List[dict]:
        """Generates the question block for the current round"""
        # Determine honorific for judge
        honorifics = [
            'lackey', 'intern', 'young padawan', 'master apprentice', 'honorable', 'respected and just',
            'cold and yet still fair', 'worthy inheriter of daddy\'s millions', 'mother of dragons', 'excellent',
            'elder', 'ruler of the lower cards', 'most fair dictator of difficult choices',
            'benevolent and omniscient chief of dutiful diddling', 'supreme high chancellor of card justice'
        ]
        judge_pts = self.game.judge.points
        honorific = f'the {honorifics[-1] if judge_pts > len(honorifics) - 1 else honorifics[judge_pts]}'
        # Assign this to the judge so we can refer to it in other areas.
        self.game.judge.honorific = honorific.title()

        return [
            self.bkb.make_block_section(f'Round *`{self.game.rounds}`* - *{self.game.judge.honorific} '
                                        f'Judge {self.game.judge.display_name.title()}* presiding.'),
            self.bkb.make_block_section(f'*:regional_indicator_q:: {self.game.current_question_card.txt}*'),
            self.bkb.make_block_divider()
        ]

    def process_incoming_action(self, user: str, channel: str, action: dict) -> Optional:
        """Handles an incoming action (e.g., when a button is clicked)"""
        if action['type'] == 'multi_static_select':
            # Multiselect
            selections = action['selected_options']
            parsed_command = ''
            for selection in selections:
                value = selection['value'].replace('-', ' ')
                if 'all' in value:
                    # Only used for randpick/choose. Results in just the command 'rand(pick|choose)'
                    #   If we're selecting all, we don't need to know any of the other selections.
                    parsed_command = f'{value.split()[0]}'
                    break
                if parsed_command == '':
                    # Put the entire first value into the parsed command (e.g., 'pick 1'
                    parsed_command = f'{value}'
                else:
                    # Build on the already-made command by concatenating the number to the end
                    #   e.g. 'pick 1' => 'pick 12'
                    parsed_command += value.split()[1]

        elif action['type'] == 'button':
            # Normal button clicks just send a 'value' key in the payload dict
            parsed_command = action['value'].replace('-', ' ')
        else:
            # Probably should notify the user, but I'm not sure if Slack will attempt
            #   to send requests multiple times if it doesn't get a response in time.
            return None

        if 'pick' in parsed_command:
            # Handle pick/randpick
            self.process_picks(user, parsed_command)
        elif 'choose' in parsed_command:
            # handle choose/randchoose
            self.choose_card(user, parsed_command)

    def new_round(self, notifications: List[str] = None, save: bool = True) -> Optional:
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        :param save: bool, save the points of the previous round
        """
        if save:
            # Preserve points of last round
            self.save_score()

        # Refresh the players' names, get response from build function
        self.players.load_players_in_channel(self._build_players(), refresh=True, names_only=True)

        # Leverage Block Kit to make notifications fancier
        notification_block = []

        if notifications is not None:
            # Process incoming notifications into the block
            notification_block.append(self.bkb.make_block_section(notifications, join_str='\n'))

        self.game.new_round()
        if self.game.status == self.game.gs.ended:
            # Game ended because we ran out of questions
            self.st.message_main_channel(blocks=notification_block)
            self.end_game()
            return None

        question_block = self.make_question_block()
        notification_block += question_block
        self.st.message_main_channel(blocks=notification_block)

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
                    player.current_blocks[dm_chan] = ts
                pchan_ts = self.st.private_channel_message(player.player_id, self.channel_id, ret_ts=True,
                                                           message='', blocks=cards_block)
                player.current_blocks[self.channel_id] = pchan_ts
                if player.auto_randpick:
                    # Player has elected to automatically pick their cards
                    self.process_picks(player.player_id, 'randpick')
                    self.st.private_message(player.player_id, 'Your pick was handled automatically, '
                                                              'as you have `auto randpick` enabled.')
                self.game.players.update_player(player)
            # Increment rounds played by this player by 1
            self.game.players.player_list[i].rounds_played += 1

    def decknuke(self, user: str):
        """Deals the user a new hand while randpicking one of the cards from their current deck.
        The card that's picked will have a negative point value
        """
        # Randpick a card for this user
        self.process_picks(user, 'randpick')
        # Replace all remaining cards in hand
        player = self.game.players.get_player_by_id(user)
        # Remove all cards form their hand
        player.hand.burn_cards()
        player.nuked_hand = True
        # Deal the player the unused new cards the number of cards played will be replaced after the round ends.
        self.game._card_dealer(player, self.game.DECK_SIZE - self.game.current_question_card.required_answers)

    def process_picks(self, user: str, message: str) -> Optional:
        """Processes the card selection made by the user"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        if self.game.status != self.game.gs.players_decision:
            # Prevent this method from being called outside of the player's decision stage
            self.st.message_main_channel(f'<@{user}> You cannot make selections '
                                         f'in the current status of this game: `{self.game.status}`.')
            return None

        # We're in the right status and the user isn't a judge. Let's break this down further
        card_subset = None  # For when player wants to pick from a subset
        msg_split = message.split()

        # Set the player as the user first, but see if the user is actually picking for someone else
        player = self.game.players.get_player_by_id(user)
        if any(['<@' in x for x in msg_split]):
            # Player has tagged someone. See if they tagged themselves or another person
            if not any([player.player_tag in x for x in msg_split]):
                # Tagged someone else. Get that other tag & use it to change the player.
                ptag = next((x for x in msg_split if '<@' in x))
                player = self.game.players.get_player_by_tag(ptag.upper())

        # Make sure the player referenced isn't the judge
        if player.player_id == self.game.judge.player_id:
            self.st.message_main_channel(f'{player.player_tag} is the judge this round. Judges can\'t pick!')
            return None

        # Player is set, now determine what we need to do
        if 'randpick' in message:
            # Random picking section
            n_cards = len(player.hand.cards)
            req_ans = self.game.current_question_card.required_answers
            if len(msg_split) > 1:
                # Randpick possibly includes further instructions
                after_randpick = msg_split[1]
                if '<@' not in after_randpick:
                    # This was not a tag;
                    if after_randpick.isnumeric():
                        card_subset = list(map(int, list(after_randpick)))
                    elif ',' in after_randpick:
                        card_subset = list(map(int, after_randpick.split(',')))
                    else:
                        # Pick not understood; doesn't match expected syntax
                        self.st.message_main_channel(
                            f'<@{user}> I didn\'t understand your randpick message (`{message}`). Pick voided.')
                        return None
                else:
                    # Was a tag. We've already applied the tag earlier
                    pass
            else:
                # Just 'randpick'
                pass
            # Determine how we're gonna randpick
            if card_subset is not None:
                # Player wants to randomly choose from a subset of cards
                # Check that the subset is at least the same number as the required cards
                if len(card_subset) >= req_ans:
                    picks = [x - 1 for x in np.random.choice(card_subset, req_ans, False).tolist()]
                else:
                    self.st.message_main_channel(f'<@{user}> your subset of picks is too small. '
                                                 f'At least (`{req_ans}`) picks required. Pick voided.')
                    return None
            else:
                # Randomly choose over all of the player's cards
                picks = np.random.choice(n_cards, req_ans, False).tolist()

        else:
            # Performing a standard pick; process the pick from the message
            picks = self._get_pick(user, message)

        if picks is None:
            return None
        elif any([x > len(player.hand.cards) - 1 or x < 0 for x in picks]):
            self.st.message_main_channel(f'<@{user}> I think you picked outside the range of suggestions. '
                                         f'Your picks: `{picks}`.')
            return None
        messages = [self.game.assign_player_pick(player.player_id, picks)]

        if player.dm_cards and 'randpick' in message:
            # Ping player their randomly selected picks if they've chosen to be DMed cards
            self.st.private_message(player.player_id, f'Your randomly selected pick(s): '
                                                      f'`{"` | `".join([player.hand.pick.pick_txt_list])}`')

        # See who else has yet to decide
        remaining = self.game.players_left_to_decide()
        if len(remaining) == 0:
            messages.append('All players have made their picks.')
            if self.game.ping_judge:
                judge_msg = f'{self.game.judge.player_tag} to judge.'
            else:
                judge_msg = f'`{self.game.judge.display_name.title()}` to judge.'
            messages.append(judge_msg)
            self.game.status = self.game.gs.judge_decision

            self._display_picks(notifications=messages)
        else:
            # Make the remaining players more visible
            remaining_txt = ' '.join([f'`{x}`' for x in remaining])
            messages.append(f'*`{len(remaining)}`* players remaining to decide: {remaining_txt}')
            msg_block = [self.bkb.make_context_section(messages)]
            if self.game.round_ts is None:
                # Announcing the picks for the first time; capture the timestamp so
                #   we can update that same message later
                self.game.round_ts = self.st.send_message(self.channel_id, message='', ret_ts=True,
                                                          blocks=msg_block)
            else:
                # Update the message we've already got
                self.st.update_message(self.channel_id, self.game.round_ts, blocks=msg_block)

    def _get_pick(self, user: str, message: str, judge_decide: bool = False) -> Union[int, Optional[List[int]]]:
        """Processes a number from a message"""

        def isolate_pick(pick_txt: str) -> Optional[List[int]]:
            if ',' in pick_txt:
                return [int(x) for x in pick_txt.split(',') if x.isnumeric()]
            elif pick_txt.isnumeric():
                return [int(x) for x in list(pick_txt)]
            return None

        # Process the message
        msg_split = message.split()
        picks = None
        if len(msg_split) == 2:
            # Our pick was something like 'pick 4', 'pick 42' or 'pick 3,2'
            pick_part = msg_split[1]
            picks = isolate_pick(pick_part)
        elif len(msg_split) > 2:
            # Our pick was something like 'pick 4 2' or 'pick 3, 2'
            pick_part = ''.join(msg_split[1:])
            picks = isolate_pick(pick_part)

        if picks is None:
            self.st.message_main_channel(f'<@{user}> - I didn\'t understand your pick. You entered: `{message}` \n'
                                         f'Try something like `p 12` or `pick 2`')
        elif judge_decide:
            if len(picks) == 1:
                # Expected number of picks for judge
                return picks[0] - 1
            else:
                self.st.message_main_channel(f'<@{user}> - You\'re the judge. '
                                             f'You should be choosing only one set. Try again!')
        else:
            # Confirm that the number of picks matches the required number of answers
            req_ans = self.game.current_question_card.required_answers
            if len(set(picks)) == req_ans:
                # Set picks to 0-based index and send onward
                return [x - 1 for x in picks]
            else:
                self.st.message_main_channel(f'<@{user}> - You chose {len(picks)} things, '
                                             f'but the current question requires {req_ans}.')
        return None

    def _display_picks(self, notifications: List[str] = None):
        """Shows a random order of the picks"""
        if notifications is not None:
            public_response_block = [
                self.bkb.make_context_section(notifications),
                self.bkb.make_block_divider()
            ]
        else:
            public_response_block = []
        question_block = self.make_question_block()
        public_choices, private_choices = self.game.display_picks()
        public_response_block += question_block + public_choices
        private_response_block = question_block + private_choices
        # Show everyone's picks to the group, but only send the choice buttons to the judge
        self.st.message_main_channel(blocks=public_response_block)
        if self.game.pick_voting:
            ids_to_send_to = [x.player_id for x in self.game.players.player_list]
        else:
            ids_to_send_to = [self.game.judge.player_id]

        for p_id in ids_to_send_to:
            # send as private in-channel message (though this sometimes goes unrendered)
            self.st.private_channel_message(p_id, self.channel_id,
                                            message='', blocks=private_response_block)
            if self.game.players.get_player_by_id(p_id).dm_cards:
                # DM choices to player if they have card dming enabled
                self.st.private_message(p_id, message='', blocks=private_response_block)

    def _randchoose_handling(self, message: str) -> Optional[int]:
        """Contains all the logic for handling a randchoose command"""
        if len(message.split(' ')) > 1:
            randchoose_instructions = message.split(' ')[1]
            # Use a subset of choices
            card_subset = None
            if randchoose_instructions.isnumeric():
                card_subset = list(map(int, list(randchoose_instructions)))
            elif ',' in randchoose_instructions:
                card_subset = list(map(int, randchoose_instructions.split(',')))
            if card_subset is not None:
                # Pick from the card subset and subtract by 1 to bring it in line with 0-based index
                pick = list(np.random.choice(card_subset, 1))[0] - 1
            else:
                # Card subset wasn't able to be parsed
                self.st.message_main_channel('I wasn\'t able to parse the card subset you entered. '
                                             'Try again!')
                return None
        else:
            # Randomly choose from all cards
            # available choices = total number of players - (judge + len factor)
            available_choices = len(self.game.players.player_list) - 2
            if available_choices == 0:
                pick = 0
            else:
                pick = list(np.random.choice(available_choices, 1))[0]
        return pick

    def choose_card(self, user: str, message: str) -> Optional:
        """For the judge to choose the winning card and
        for other players to vote on the card they think should win"""
        if self.game is None:
            self.st.message_main_channel('Start a game first, then tell me to do that.')
            return None

        if self.game.status != self.game.gs.judge_decision:
            # Prevent this method from being called outside of the judge's decision stage
            self.st.message_main_channel(f'Not the right status for this command: `{self.game.status}`')
            return None

        if user in self.admin_user and 'blueberry pie' in message:
            # Overrides the block below to allow admin to make a choice during testing or special circumstances
            user = self.game.judge.player_id
            message = 'randchoose'

        used_randchoose = 'randchoose' in message

        if used_randchoose:
            pick = self._randchoose_handling(message)
            if pick is None:
                # The randchoose method wasn't able to parse anything useful from the message
                return None
        else:
            pick = self._get_pick(user, message, judge_decide=True)

        if pick > len(self.game.players.player_list) - 2 or pick < 0:
            # Pick is rendered as an array index here.
            # Pick can either be:
            #   -less than total players minus judge, minus 1 more to account for array
            #   -greater than -1
            self.st.message_main_channel(f'I think you picked outside the range of suggestions. '
                                         f'Your pick: {pick}')
            return None
        else:
            if user == self.game.judge.player_id:
                # Record the judge's pick
                if self.game.judge.pick_idx is None:
                    self.game.judge.pick_idx = pick
                else:
                    self.st.message_main_channel('Judge\'s pick voided. You\'ve already picked this round.')
            else:
                player = self.game.players.get_player_by_id(user)
                if not player.voted:
                    # Record the player's vote
                    self.game.round_picks[pick].add_vote()
                    player.voted = True
                    self.game.players.update_player(player)
                else:
                    self.st.message_main_channel('Player\'s pick voided. You\'ve already voted this round.')

        if self.game.pick_voting:
            # We're allowing people to vote
            if self.game.players.have_all_players_voted() and self.game.judge.pick_idx is not None:
                # We're ready to wrap up the round
                self._round_wrap_up()
        else:
            if self.game.judge.pick_idx is not None:
                self._round_wrap_up()

    def _round_wrap_up(self):
        """Coordinates end-of-round logic (tallying votes, picking winner, etc.)"""
        # Make sure all users have votes and judge has made decision before wrapping up the round
        # Handle the announcement of winner and distribution of points
        self.st.message_main_channel(blocks=self._winner_selection())
        self.game.status = self.game.gs.end_round
        # Start new round
        self.new_round()

    def _points_redistributer(self, penalty: int) -> str:
        """Handles the logic covering redistribution of wealth among players"""
        # Deduct points from the judge, give randomly to others
        point_receivers = {}  # Store 'name' (of player) and 'points' (distributed)
        # Determine the eligible receivers of the extra points
        player_points_list = [x.points for x in self.game.players if not x.is_judge]
        if sum(player_points_list) == 0:
            # No one has made any points yet - everyone's eligible
            eligible_receivers = [x for x in self.game.players if not x.is_judge]
        else:
            # Some people have earned points already. Make sure those with the highest points aren't eligible
            max_points = max(player_points_list)
            eligible_receivers = [x for x in self.game.players if not x.is_judge and x.points < max_points]
        for pt in range(0, penalty * -1):
            if len(eligible_receivers) > 1:
                player = list(np.random.choice(eligible_receivers, 1))[0]
            else:
                # In case everyone has the max score except for one person
                player = eligible_receivers[0]
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
        point_receivers_txt = ','.join([f'`{v["name"]}`: *`{v["points"]}`* :diddlecoin:'
                                        for k, v in point_receivers.items()])
        return point_receivers_txt

    def _show_votes(self) -> List[str]:
        """Will show the round's votes for analysis"""
        if not self.game.pick_voting:
            return []
        selections = []
        for i, pick in enumerate(self.game.round_picks):
            num_votes = pick.votes
            vote_txt = ':heavy_check_mark:' * num_votes
            selections.append(f'*{i + 1}*: {"|".join(pick.pick_txt_list)}{vote_txt}')
        # Add the judge's icon to whatever index they chose
        selections[self.game.judge.pick_idx] += ':gavel:'
        return selections

    def _winner_selection(self) -> List[dict]:
        """Contains the logic that determines point distributions upon selection of a winner"""
        # Get the list of cards picked by each player
        rps = self.game.round_picks
        winning_pick = rps[self.game.judge.pick_idx]
        if self.game.pick_voting:
            # Vote logic
            # The judge needs to have _manually_ selected a card that has at least
            # 1/3 of the votes from other players. If judge is ARCing, threshold is set at 0
            if self.game.judge.auto_randchoose:
                vote_threshold = 0
            else:
                vote_threshold = round(1/3 * (len(self.game.players) - 1))
            judge_penalty = -2
            if winning_pick.votes >= vote_threshold:
                vote_txt = 'Judge has wisely selected according to the demands of the masses.'
            else:
                point_receivers_txt = self._points_redistributer(judge_penalty)
                vote_txt = f'Judge has chosen... _poorly_.\n' \
                           f'The Judge\'s choice had *`{winning_pick.votes}`* votes, ' \
                           f'missing the required {vote_threshold} votes for this game. Thus, Judge takes ' \
                           f'a penalty of *`{judge_penalty}`* :diddlecoin:, which was redistributed ' \
                           f'to the following manner: {point_receivers_txt} '
        else:
            vote_txt = ''

        # Winner selection
        decknuke_penalty = -2
        winner = self.game.players.get_player_by_id(winning_pick.id)
        # If decknuke occurred, distribute the points to others randomly
        if winner.nuked_hand:
            point_receivers_txt = self._points_redistributer(decknuke_penalty)
            points_won = decknuke_penalty
            decknuke_txt = f'\n:impact::impact::impact::impact:LOL HOW DAT DECKNUKE WORK FOR YA NOW??\n' \
                           f'Your points were redistributed such: {point_receivers_txt}'
        else:
            points_won = 1
            decknuke_txt = ''

        winner.add_points(points_won)
        self.game.players.update_player(winner)
        winner_details = winner.player_tag if self.game.ping_winner \
            else f'*`{winner.display_name.title()}`*'
        winner_txt_blob = [
            f":regional_indicator_q: *{self.game.current_question_card.txt}*",
            f":tada:Winning card: `{','.join([winner.hand.pick.pick_txt_list])}`",
            f"*`{points_won:+}`* :diddlecoin: to {winner_details}! "
            f"New score: *`{winner.points}`* :diddlecoin: "
            f"({winner.get_grand_score() + winner.points} total){decknuke_txt}\n{vote_txt}"
        ]

        message_block = [
            self.bkb.make_block_section(winner_txt_blob),
            self.bkb.make_block_divider(),
            self.bkb.make_context_section(self._show_votes() + ['Round ended.'])
        ]
        return message_block

    def end_game(self) -> Optional:
        """Ends the current game"""
        if self.game is None:
            self.st.message_main_channel('You have to start a game before you can end it...????')
            return None
        if self.game.status != self.game.gs.ended:
            # Check if game was not already ended automatically
            self.game.end_game()
        # Save score history to file
        self.display_points()
        self.save_score(ended=True)
        self.st.message_main_channel('The game has ended. :died:')

    def save_score(self, ended: bool = False):
        """Saves the score to directory"""
        # First, save general game stats
        game_df = pd.DataFrame({
            'game_start': self.game.game_start_time.strftime('%F %T'),
            'rounds': self.game.rounds,
            'elapsed_time': self.st.get_time_elapsed(self.game.game_start_time),
            'trigger_msg': self.game.trigger_msg,
            'ended': ended
        }, index=[self.game.game_id])
        # Merge existing games from the gsheet
        self.game_info_df = self.game_info_df.append(game_df)
        self.game_info_df = self.game_info_df.loc[~self.game_info_df.index.duplicated(keep='last')]
        self.st.write_sheet(self.cah_gsheet_key, self.game_info_sheet_name, self.game_info_df.reset_index())

        scores_df = pd.DataFrame()
        for player in self.players.player_list:
            df = pd.DataFrame({
                'player_id': player.player_id,
                'name': player.display_name,
                'current': player.points,
                'final': sum(player.final_scores),
                'rounds_played': player.rounds_played
            }, index=[0])
            scores_df = scores_df.append(df)

        self.st.write_sheet(self.cah_gsheet_key, self.score_sheet_name, scores_df)

    def read_score(self):
        """Reads in score from directory"""
        if self.score_sheet_name in self.cah_sheets.keys():
            scores_df = self.cah_sheets[self.score_sheet_name]
            for i, row in scores_df.iterrows():
                player_id = row['player_id']
                player = self.players.get_player_by_id(player_id)
                if player is not None:
                    try:
                        player.points = row['current']
                        player.final_scores = [row['final']]
                        player.rounds_played = row['rounds_played']
                    except KeyError:
                        player.points = 0
                        player.final_scores = list()
                        player.rounds_played = 0
                    self.players.update_player(player)
            self.st.message_main_channel('Preserved scores have been read in from gsheets.')
        else:
            self.st.message_main_channel('Scores file was empty. No scores will be updated.')

    def wipe_score(self):
        """Resets all player's score history"""
        for player in self.game.players.player_list:
            # For in the current game
            player.final_scores = list()
            player.points = 0
            player.rounds_played = 0
            self.game.players.update_player(player)
        for player in self.players.player_list:
            # For in the whole channel
            player.final_scores = list()
            player.points = 0
            player.rounds_played = 0
            self.players.update_player(player)
        self.save_score()
        self.st.message_main_channel('All scores have been erased.')

    def display_points(self) -> List[dict]:
        """Displays points for all players"""

        if self.game is None:
            plist = self.players.player_list
        else:
            plist = self.game.players.player_list

        points_df = pd.DataFrame()
        for player in plist:
            row = {
                'name': player.display_name,
                'diddles': player.points,
                'overall': player.get_grand_score()
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
            self.bkb.make_context_section('*Current Scores*'),
            self.bkb.make_block_divider(),
            self.bkb.make_block_section(scores_list)
        ]

    def display_status(self) -> Optional[List[dict]]:
        """Displays status of the game"""

        if self.game is None:
            self.st.message_main_channel('I just stahted this wicked pissa game, go grab me some dunkies.')
            return None

        status_block = [
            self.bkb.make_block_section('*Game Info*')
        ]

        if self.game.status not in [self.game.gs.ended, self.game.gs.stahted]:
            # Players that have card DMing enabled
            dm_players = [f"`{x.display_name}`" for x in self.game.players.player_list if x.dm_cards]
            # Players that have auto randpick enabled
            arp_players = [f"`{x.display_name}`" for x in self.game.players.player_list if x.auto_randpick]

            status_block += [
                self.bkb.make_context_section([
                    f':gavel: *Judge*: *`{self.game.judge.display_name.title()}`*'
                ]),
                self.bkb.make_block_divider(),
                self.bkb.make_context_section([
                    f'*Status*: *`{self.game.status.replace("_", " ").title()}`*\n'
                    f'*Judge Ping*: `{self.game.ping_judge}`\t\t*Weiner Ping*: `{self.game.ping_winner}`\n'
                    f':orange_check: *DM Cards*: {" ".join(dm_players)}\n'
                    f':orange_check: *ARP*: {" ".join(arp_players)}\n'
                ]),
                self.bkb.make_block_divider(),
                self.bkb.make_context_section([
                    f':stopwatch: *Round `{self.game.rounds}`*: '
                    f'{self.st.get_time_elapsed(self.game.round_start_time)}\t\t'
                    f'*Game*: {self.st.get_time_elapsed(self.game.game_start_time)}\n',
                    f':stack-of-cards: *Deck*: `{self.game.deck.name}` - '
                    f'`{len(self.game.deck.questions_card_list)}` question &'
                    f' `{len(self.game.deck.answers_card_list)}` answer cards remain',
                    f':conga_parrot: *Player Order*: '
                    f'{" ".join([f"`{x.display_name}`" for x in self.game.players.player_list])}'
                ])
            ]

        if self.game.status in [self.game.gs.players_decision, self.game.gs.judge_decision]:
            picks_needed = ['`{}`'.format(x) for x in self.game.players_left_to_decide()]
            pickle_txt = '' if len(picks_needed) == 0 else f'\n:pickle-sword: ' \
                                                           f'*Pickles Needed*: {" ".join(picks_needed)}'
            status_block = status_block[:1] + [
                self.bkb.make_block_section(f':regional_indicator_q: `{self.game.current_question_card.txt}`'),
                self.bkb.make_context_section([
                    f':gavel: *Judge*: *`{self.game.judge.display_name.title()}`*{pickle_txt}'
                ])
            ] + status_block[2:]  # Skip over the previous judge block

        return status_block

    def _refresh_sheets(self):
        """Refreshes the GSheet containing the Q&A cards & other info"""
        self.cah_sheets = self.st.read_in_sheets(self.cah_gsheet_key)

    def refresh_decks(self):
        """Refreshes the GSheet containing the Q&A cards"""
        self._refresh_sheets()

        possible_decks = self.cah_sheets.copy()
        # Pop out any item that has a key starting with 'x_'
        keys = list(possible_decks.keys())
        for k in keys:
            if k.startswith('x_'):
                _ = possible_decks.pop(k)

        self.decks = Decks(possible_decks)
