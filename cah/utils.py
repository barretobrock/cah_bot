#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import json
import time
import logging
import traceback
import pandas as pd
import numpy as np
from random import randrange
from datetime import datetime
from dateutil.relativedelta import relativedelta as reldelta
from slacktools import SlackTools, GracefulKiller
from kavalkilu import Keys, Log, DateTools
from .cards import Decks
from .players import Players
from .games import Game


help_txt = """
Hi! I'm Wizzy and I help you play shitty games!
*Command Prefix*
 - `c!` or `cah`: Use this before any of the below commands (e.g., `c! pick 1`)
*Basic Commands*:
 - `new game [OPTIONS]`: start a new CAH game
    optional flags:
        - `-(set|s) <card-set-name>`: choose a specific card set (standard, indeed) default: *standard*
        - `-p @player1 @player2 ...`: tag a subset of the channel as current players (space-separated)
 - `(points|score|scores)`: show points/score of all players
 - `status`: get the current status of the game
 - `toggle jping`: Toggles whether or not the judge is pinged after all selections are made (default: off)
 - `toggle dm`: Toggles whether or not you receive cards as a DM from Wizzy (default: off)
 - `cahds now`: Send cards immediately without toggling DM
 - `end game`: end the current game
 - `show decks`: shows the deck names available
 - `refresh sheets`: refreshes the GSheets that contain the card sets. Can only be done outside a game.
 - `show link`: shows the link to the GSheets where Wizzy reads in cards. helpful if you want to contribute
*Card selection*:
 - `(p|pick) <card-num>[<next-card>]`: pick your card for the round (index starts at 1, cards in order)
 - `randpick [<@other_player>]`: randomly select your card when you just can't decide
*Judge-only commands*:
 - `(c|choose) <index>`: used when selecting the :q:best:q: card from picks (index starts at 1)
"""


class CAHBot:
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, log_name, debug=False):
        """
        :param log_name: str, name of the log to retrieve
        :param debug: bool,
        """
        self.log = Log(log_name, child_name='brain')
        self.bot_name = 'Wizzy'
        self.triggers = ['cah', 'c!'] if not debug else ['decah', 'dc!']
        self.channel_id = 'CMPV3K8AE' if not debug else 'CQ1DG4WB1'  # cah or cah-test
        # Read in common tools for interacting with Slack's API
        k = Keys()
        self.st = SlackTools(self.log.log_name, triggers=self.triggers, team=k.get_key('okr-name'),
                             xoxp_token=k.get_key('wizzy-token'), xoxb_token=k.get_key('wizzy-bot-user-token'))
        # Two types of API interaction: bot-level, user-level
        self.bot = self.st.bot
        self.user = self.st.user
        self.bot_id = self.bot.api_call('auth.test')['user_id']
        self.RTM_READ_DELAY = 1

        # For storing game info
        self.cah_gsheet = k.get_key('cah_sheet')
        # Read in decks
        self.decks = None
        self.refresh_sheets()
        # Build out players
        self.players = Players(self._build_players())
        self.game = None
        self.dt = DateTools()
        self.score_path = os.path.join(os.path.abspath('/home/bobrock/data'), 'scores.json')
        game_info = self.read_score()
        if game_info is not None:
            # Previous game was run and probably shut down improperly
            # Start new game, populate the rounds and start times
            if all([x in game_info.keys() for x in ['trigger_msg', 'game_start', 'round_start']]):
                self.message_grp('Previous game instance detected. Setting round and elapsed times back')
                self.new_game(game_info['trigger_msg'])
                self.game.rounds = game_info['round']
                self.game.game_start_time = datetime.strptime(game_info['game_start'], '%Y-%m-%d %H:%M:%S')
                self.game.round_start_time = datetime.strptime(game_info['round_start'], '%Y-%m-%d %H:%M:%S')

    def run_rtm(self, startup_msg, terminated_msg):
        """Initiate real-time messaging"""
        killer = GracefulKiller()
        if self.bot.rtm_connect(with_team_state=False):
            self.log.debug('{} is running.'.format(self.bot_name))
            self.st.send_message(self.channel_id, startup_msg)
            while not killer.kill_now:
                try:
                    msg_packet = self.st.parse_bot_commands(self.bot.rtm_read())
                    if msg_packet is not None:
                        try:
                            self.handle_command(**msg_packet)
                        except Exception as e:
                            traceback_msg = '\n'.join(traceback.format_tb(e.__traceback__))
                            exception_msg = '{}: {}'.format(e.__class__.__name__, e)
                            self.log.error(exception_msg)
                            self.st.send_message(msg_packet['channel'],
                                                 "Exception occurred: \n```{}\n{}```".format(traceback_msg,
                                                                                             exception_msg))
                    time.sleep(self.RTM_READ_DELAY)
                except Exception as e:
                    self.log.debug('Reconnecting...')
                    self.bot.rtm_connect(with_team_state=False)
            # Upon SIGTERM, message channel
            self.st.send_message(self.channel_id, terminated_msg)
        else:
            self.log.error('Connection failed.')

    def handle_command(self, channel, message, user, raw_message):
        """Handles a bot command if it's known"""
        response = None
        if message == 'help':
            response = help_txt
        elif message.startswith('new game'):
            self.new_game(message)
        elif message == 'end game':
            self.end_game()
        elif message.startswith('pick') or message.split()[0] == 'p':
            self.process_picks(user, message)
        elif message.startswith('choose') or message.split()[0] == 'c':
            self.choose_card(user, message)
        elif message.startswith('randpick'):
            self.process_picks(user, message, is_random=True)
        elif message in ['points', 'score', 'scores']:
            self.display_points()
        elif message == 'toggle jping':
            self.toggle_judge_ping()
        elif message == 'toggle dm':
            self.toggle_card_dm(user)
        elif message == 'cahds now':
            self.dm_cards_now(user)
        elif message == 'show decks':
            response = '`{}`'.format(','.join(self.decks.deck_names))
        elif message == 'show link':
            response = 'https://docs.google.com/spreadsheets/d/{}/'.format(self.cah_gsheet)
        elif message == 'status':
            self.display_status()
        elif message == 'refresh sheets':
            if self.game is None:
                self.refresh_sheets()
                response = 'Sheets have been refreshed! New decks: `{}`'.format(','.join(self.decks.deck_names))
            elif self.game.status not in [self.game.gs.stahted, self.game.gs.ended]:
                response = 'Please end the game before refreshing. THANKSSSS :))))))'
            else:
                self.refresh_sheets()
                response = 'Sheets have been refreshed! New decks: `{}`'.format(','.join(self.decks.deck_names))
        elif message != '':
            response = "I didn't understand this: `{}`\n " \
                       "Use `cah help` to get a list of my commands.".format(message)

        if response is not None:
            resp_dict = {
                'user': user
            }
            self.st.send_message(channel, response.format(**resp_dict))

    def message_grp(self, message):
        """Wrapper to send message to whole channel"""
        self.st.send_message(self.channel_id, message)

    def _get_text_after_flag(self, flags, msg, default=None):
        """Retrieves text after a flag beginning with '-' or '--'.
            Can detect other flags after the text.
         :param flags: list of str, flags to look for
         :param msg: str, the message to examine
         :param default: str, the default value to use if flag is not found or misused
        """
        msg_split = msg.split()
        if not any([x in msg_split for x in flags]):
            # No matching flags found
            return default
        # Determine which flag is used
        idx = None
        for flag in flags:
            try:
                idx = msg_split.index(flag)
                break
            except ValueError:
                continue
        # We have the index where the flag starts.
        # Now work through the rest of the message to find another flag or the end of the message
        end_pos = None
        for chunk in msg_split[idx + 1:]:
            if re.match(r'^-+', chunk):
                # Found a matching flag
                end_pos = msg_split.index(chunk)
                break
        if end_pos is not None:
            txt_list = msg_split[idx + 1:end_pos]
        else:
            txt_list = msg_split[idx + 1:]
        return ' '.join(txt_list) if len(txt_list) > 0 else default

    def _build_players(self):
        """
        Collects list of users in channel, sets basic, game-related details and
            returns a list of dicts for each human player
        """
        players = []
        for user in self.st.get_channel_members(self.channel_id, humans_only=True):
            user_cleaned = {
                'id': user['id'],
                'display_name': user['display_name'].lower(),
                'real_name': user['name'],
            }
            # Make sure display name is not empty
            if user_cleaned['display_name'] == '':
                user_cleaned['display_name'] = user_cleaned['real_name']
            players.append(user_cleaned)
        return players

    def _determine_players(self, message):
        """Determines the players for the game"""
        specific_players = self._get_text_after_flag(['-p'], message)
        if specific_players is not None:
            specific_player_ids = [x for x in specific_players.split() if '<@' in x]
            # This game is set with specific players
            player_ids = []
            for p in specific_player_ids:
                # Extract user id
                uid = self.st.parse_tag_from_text(p)
                if uid is None:
                    # Failed at parsing
                    raise ValueError('Failed to parse a user id for `{}`. Game cannot proceed.'.format(p))
                else:
                    player_ids.append(uid)
            self.players.skip_players_not_in_list(player_ids)

            # Build the notification message
            notify_msg = 'Skipping: `{}`'.format('`,`'.join(
                [x.display_name for x in self.players.player_list if x.skip]))
        else:
            notify_msg = 'Playing with everyone :you-better-smirk:.'
        return notify_msg

    def _read_in_cards(self, card_set='standard'):
        """Reads in the cards"""
        deck = self.decks.get_deck_by_name(card_set)
        if deck is None:
            raise ValueError('The card set `{}` was not found. '
                             'Possible sets: `{}`.'.format(card_set, ','.join(self.decks.deck_names)))
        return deck

    def new_game(self, message):
        """Begins a new game"""
        response_list = []

        # Determine card set to use
        card_set = self._get_text_after_flag(['-set', '-s'], message, 'standard')
        response_list.append('Using `{}` card set'.format(card_set))

        # Refresh the players' names, get response from build function
        self.players.load_players_in_channel(self._build_players(), refresh=True)
        response_list.append(self._determine_players(message))

        # Refresh our decks, read in card deck
        self.refresh_sheets()
        deck = self._read_in_cards(card_set)

        # Set eligible players, set the game, add players, shuffle the players
        self.players.set_eligible_players()
        self.game = Game(self.players.eligible_players, deck, trigger_msg=message)
        # Get order of judges
        response_list.append(self.game.judge_order)
        # Kick off the new round, message details to the group
        self.new_round(notifications=response_list, save=False)

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_judge_ping()
        self.message_grp('Judge pinging set to: {}'.format(self.game.ping_judge))

    def toggle_card_dm(self, user_id):
        """Toggles card dming"""
        if self.game is None:
            # Set the player object outside of the game
            player = self.players.get_player_by_id(user_id)
        else:
            player = self.game.players.get_player_by_id(user_id)
        player.dm_cards = not player.dm_cards
        self.message_grp('Card DMing for player `{}` set to `{}`'.format(player.display_name, player.dm_cards))
        if self.game is not None:
            # Send cards to user if the status shows we're currently in a game
            if self.game.status == self.game.gs.players_decision and player.dm_cards:
                self.dm_cards_now(user_id)
            self.game.players.update_player(player)
        else:
            self.players.update_player(player)

    def dm_cards_now(self, user_id):
        """DMs current card set to user"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        player = self.game.players.get_player_by_id(user_id)

        # Send cards to user if the status shows we're currently in a game
        if len(player.hand.cards) == 0:
            msg_txt = "You have no cards to send. This likely means you're not a current player"
        elif self.game.status == self.game.gs.players_decision:
            question = 'Current Question:\n`{}`'.format(self.game.current_question_card)
            cards_msg = player.hand.render_hand()
            msg_txt = '{}\nYour cards:\n{}'.format(question, cards_msg)
        else:
            msg_txt = "The game's current status (`{}`) doesn't allow for card DMing".format(self.game.status)
        self.st.private_message(player.player_id, msg_txt)

    def new_round(self, notifications=None, save=True):
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        :param save: bool, save the points of the previous round
        """
        if save:
            # Preserve points of last round
            self.save_score()

        # Refresh the players' names, get response from build function
        self.players.load_players_in_channel(self._build_players(), refresh=True, names_only=True)

        if notifications is None:
            notifications = []
        notifications += self.game.new_round()
        if self.game.status == self.game.gs.ended:
            # Game ended because we ran out of questions
            self.message_grp('\n'.join(notifications))
            self.end_game()
            return None

        self.message_grp('\n'.join(notifications))

        self.st.private_channel_message(self.game.judge.player_id, self.channel_id, "You're the judge this round!")
        for player in self.game.players.player_list:
            if player.player_id != self.game.judge.player_id:
                if player.dm_cards:
                    question = 'Current Question:\n`{}`'.format(self.game.current_question_card)
                    cards_msg = player.hand.render_hand()
                    msg_txt = '{}\nYour cards:\n{}'.format(question, cards_msg)
                    self.st.private_message(player.player_id, msg_txt)
                self.st.private_channel_message(player.player_id, self.channel_id, player.hand.render_hand())

    def process_picks(self, user, message, is_random=False):
        """Processes the card selection made by the user"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        if self.game.status != self.game.gs.players_decision:
            # Prevent this method from being called outside of the player's decision stage
            self.message_grp('<@{}> You cannot make selections '
                             'in the current status of this game: `{}`.'.format(user, self.game.status))
            return None

        if user == self.game.judge.player_id:
            self.message_grp('<@{}> You\'re the judge. You can\'t pick!'.format(user))
            return None

        if is_random:
            picks = None
            # Randomly assign a pick to the user based on size of hand
            msg_split = message.split()
            player_id = player = None
            if message == 'randpick':
                # Pick random for user
                player_id = user
                player = self.game.players.get_player_by_id(player_id)
            elif len(msg_split) > 1:
                ptag = msg_split[1].upper()
                # Player mentioned
                player = self.game.players.get_player_by_tag(ptag)
                if player is None:
                    self.message_grp('Player id not found: `{}`'.format(ptag))
                else:
                    user = player.player_id
            if player is not None:
                n_cards = len(player.hand.cards)
                req_ans = self.game.current_question_card.required_answers
                picks = np.random.choice(n_cards, req_ans, False).tolist()
        else:
            # Process the pick from the message
            picks = self._get_pick(user, message)
        if picks is None:
            return None
        elif any([x > self.game.DECK_SIZE - 1 or x < 0 for x in picks]):
            self.message_grp('<@{}> I think you picked outside '
                             'the range of suggestions: `{}`.'.format(user, ','.join([x - 1 for x in picks])))
            return None
        messages = [self.game.assign_player_pick(user, picks)]

        # See who else has yet to decide
        remaining = self.game.players_left_to_decide()
        if len(remaining) == 0:
            messages.append('All players have made their picks.')
            if self.game.ping_judge:
                judge_msg = '{} to judge.'.format(self.game.judge.player_tag)
            else:
                judge_msg = '`{}` to judge.'.format(self.game.judge.display_name)
            messages.append(judge_msg)
            self.game.status = self.game.gs.judge_decision
            self._display_picks()
        else:
            messages.append('`{}` players remaining to decide: {}'.format(len(remaining), ', '.join(remaining)))
        self.message_grp('\n'.join(messages))

    def _get_pick(self, user, message, judge_decide=False):
        """Processes a number from a message"""

        def isolate_pick(pick_txt):
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
            self.message_grp('<@{}> - I didn\'t understand your pick. You entered: `{}` \n'
                             'Try something like `p 12` or `pick 2`'.format(user, message))
        elif judge_decide:
            if len(picks) == 1:
                # Expected number of picks for judge
                return picks[0] - 1
            else:
                self.message_grp('<@{}> - You\'re the judge. You should be choosing only one set. Try again!')
        else:
            # Confirm that the number of picks matches the required number of answers
            req_ans = self.game.current_question_card.required_answers
            if len(set(picks)) == req_ans:
                # Set picks to 0-based index and send onward
                return [x - 1 for x in picks]
            else:
                self.message_grp('<@{}> - You chose {} things, but the '
                                 'current question requires {}.'.format(user, len(picks), req_ans))
        return None

    def _display_picks(self):
        """Shows a random order of the picks"""
        self.message_grp('Q: `{}`\n\n{}'.format(self.game.current_question_card.txt, self.game.display_picks()))

    def choose_card(self, user, message):
        """For the judge to choose the winning card"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        if self.game.status != self.game.gs.judge_decision:
            # Prevent this method from being called outside of the judge's decision stage
            self.message_grp('Not the right status for this command: `{}`'.format(self.game.status))
            return None

        if user == self.game.judge.player_id:
            pick = self._get_pick(user, message, judge_decide=True)
            if pick > len(self.game.players.player_list) - 2 or pick < 0:
                # Pick is rendered as an array index here.
                # Pick can either be:
                #   -less than total players minus judge, minus 1 more to account for array
                #   -greater than -1
                self.message_grp('I think you picked outside the range of suggestions.')
                return None
            else:
                # Get the list of cards picked by each player
                picks = self.game.picks
                winning_pick = picks[pick]
                winner = self.game.players.get_player_by_id(winning_pick['id'])
                # chosen_cards = self.game_dict['chosen_cards']
                winner.points += 1
                self.game.players.update_player(winner)
                self.message_grp("Winning card: `{}`\n\t`{}`, new score: *{}* diddles ({} total)".format(
                    ','.join([x.txt for x in winner.hand.picks]), winner.display_name, winner.points,
                    winner.get_grand_score() + winner.points))
                self.game.status = self.game.gs.end_round
                self.message_grp('Round ended.')
                # Start new round
                self.new_round()
        else:
            self.message_grp("Get yo _stanky_ ass outta here, you ain't the judge")

    def end_game(self):
        """Ends the current game"""
        if self.game is None:
            self.message_grp('You have to start a game before you can end it...????')
            return None
        if self.game.status != self.game.gs.ended:
            # Check if game was not already ended automatically
            self.game.end_game()
        # Save score history to file
        self.display_points()
        self.save_score()
        self.message_grp('The game has ended. :died:')

    def save_score(self):
        """Saves the score to directory"""
        # First, save general game stats
        scores_dict = {
            'game': {
                'round': self.game.rounds,
                'game_start': self.game.game_start_time.strftime('%F %T'),
                'round_start': self.game.round_start_time.strftime('%F %T'),
                'trigger_msg': self.game.trigger_msg
            }
        }
        for player in self.game.players.player_list:
            scores_dict[player.player_id] = {
                'current': player.points,
                'final': player.final_scores
            }
        with open(self.score_path, 'w') as f:
            f.write(json.dumps(scores_dict))

    def read_score(self):
        """Reads in score from directory"""
        if os.path.exists(self.score_path):
            with open(self.score_path, 'r') as f:
                contents = f.read()
                if contents.replace(' ', '') != '':
                    scores_dict = json.loads(contents)
                else:
                    self.message_grp('Scores file was empty. No scores will be updated.')
                    return None
            # Extract previous game's info
            game_info = scores_dict.pop('game', None)

            for player_id, score_dict in scores_dict.items():
                player = self.players.get_player_by_id(player_id)
                try:
                    player.points = score_dict['current']
                    player.final_scores = score_dict['final']
                except KeyError:
                    player.points = 0
                    player.final_scores = list()

                self.players.update_player(player)
            return game_info
        return None

    def wipe_score(self):
        """Resets all player's score history"""
        for player in self.game.players.player_list:
            # For in the current game
            player.final_scores = list()
            player.points = 0
            self.game.players.update_player(player)
        for player in self.players.player_list:
            # For in the whole channel
            player.final_scores = list()
            player.points = 0
            self.players.update_player(player)
        self.message_grp('All scores have been erased.')

    def display_points(self):
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
            points_df.loc[:, 'rank'] = [':{}:'.format(poops[randrange(0, len(poops))]) for x in
                                        range(points_df.shape[0])]
        else:
            # Start off with the basics
            points_df.loc[:, 'rank'] = [':{}:'.format(poops[randrange(0, len(poops))]) for x in
                                        range(points_df.shape[0])]
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
            line = '{} `{:.<30}` {} diddles ({} overall)'.format(r['rank'], r['name'][:20],
                                                                 r['diddles'], r['overall'])
            scores_list.append(line)

        self.message_grp('*Current Scores*:\n{}'.format('\n'.join(scores_list)))

    def get_time_elapsed(self, st_dt):
        """Gets elapsed time between two datetimes"""
        datediff = reldelta(datetime.now(), st_dt)
        return self.dt.human_readable(datediff)

    def display_status(self):
        """Displays status of the game"""

        if self.game is None:
            self.message_grp('I just stahted this wicked pissa game, go grab me some dunkies.')
            return None

        status_list = [
            'current game status: `{}`'.format(self.game.status),
        ]

        if self.game.status not in [self.game.gs.ended, self.game.gs.stahted]:
            status_list += [
                'players this game: {}'.format(','.join(['`{}`'.format(x.display_name)
                                                         for x in self.game.players.player_list])),
                'current judge: `{}`'.format(self.game.judge.display_name),
                'current round: `{}`'.format(self.game.rounds),
                'elapsed round time: `{}`'.format(self.get_time_elapsed(self.game.round_start_time)),
                'remaining black cards: `{}`'.format(len(self.game.deck.questions_card_list)),
                'remaining white cards: `{}`'.format(len(self.game.deck.answers_card_list)),
                'elapsed game time: `{}`'.format(self.get_time_elapsed(self.game.game_start_time)),
            ]

        if self.game.status in [self.game.gs.players_decision, self.game.gs.judge_decision]:
            status_list += [
                'current q: `{}`'.format(self.game.current_question_card),
                'awaiting pickles: {}'.format(
                    ','.join(['`{}`'.format(x) for x in self.game.players_left_to_decide()])),
            ]

        status_message = '\n'.join(status_list)
        self.message_grp(status_message)

    def refresh_sheets(self):
        """Refreshes the GSheet containing the Q&A cards"""
        self.decks = Decks(self.st.read_in_sheets(self.cah_gsheet))
