#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import json
import time
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
 - `toggle jping`: Toggles whether or not the judge is pinged after all selections are made (default: on)
 - `toggle wping`: Toggles whether or not the winner is pinged when they win a round (default: on)
 - `toggle dm`: Toggles whether or not you receive cards as a DM from Wizzy (default: on)
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
            self.log.debug(f'{self.bot_name} is running.')
            self.st.send_message(self.channel_id, startup_msg)
            while not killer.kill_now:
                try:
                    msg_packet = self.st.parse_bot_commands(self.bot.rtm_read())
                    if msg_packet is not None:
                        try:
                            self.handle_command(**msg_packet)
                        except Exception as e:
                            traceback_msg = '\n'.join(traceback.format_tb(e.__traceback__))
                            exception_msg = f'{e.__class__.__name__}: {e}'
                            self.log.error(exception_msg)
                            self.st.send_message(msg_packet['channel'],
                                                 f"Exception occurred: \n```{traceback_msg}\n{exception_msg}```")
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
        elif message == 'toggle wping':
            self.toggle_winner_ping()
        elif message == 'toggle dm':
            self.toggle_card_dm(user)
        elif message == 'cahds now':
            self.dm_cards_now(user)
        elif message == 'show decks':
            response = f'`{",".join(self.decks.deck_names)}`'
        elif message == 'show link':
            response = f'https://docs.google.com/spreadsheets/d/{self.cah_gsheet}/'
        elif message == 'status':
            self.display_status()
        elif message == 'refresh sheets':
            if self.game is None:
                self.refresh_sheets()
                response = f'Sheets have been refreshed! New decks: `{",".join(self.decks.deck_names)}`'
            elif self.game.status not in [self.game.gs.stahted, self.game.gs.ended]:
                response = 'Please end the game before refreshing. THANKSSSS :))))))'
            else:
                self.refresh_sheets()
                response = f'Sheets have been refreshed! New decks: `{",".join(self.decks.deck_names)}`'
        elif message != '':
            response = f"I didn't understand this: `{message}`\n " \
                       "Use `cah help` to get a list of my commands."

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
                    raise ValueError(f'Failed to parse a user id for `{p}`. Game cannot proceed.')
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
            raise ValueError(f'The card set `{card_set}` was not found. '
                             f'Possible sets: `{",".join(self.decks.deck_names)}`.')
        return deck

    def new_game(self, message):
        """Begins a new game"""
        response_list = []

        # Determine card set to use
        card_set = self._get_text_after_flag(['-set', '-s'], message, 'standard')
        response_list.append(f'Using `{card_set}` card set')

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
        self.message_grp(f'Judge pinging set to: `{self.game.ping_judge}`')

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        self.game.toggle_winner_ping()
        self.message_grp(f'Weiner pinging set to: `{self.game.ping_winner}`')

    def toggle_card_dm(self, user_id):
        """Toggles card dming"""
        if self.game is None:
            # Set the player object outside of the game
            player = self.players.get_player_by_id(user_id)
        else:
            player = self.game.players.get_player_by_id(user_id)
        player.dm_cards = not player.dm_cards
        self.message_grp(f'Card DMing for player `{player.display_name}` set to `{player.dm_cards}`')
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
            question = f'Current Question:\n`{self.game.current_question_card}`'
            cards_msg = player.hand.render_hand()
            msg_txt = f'{question}\nJudge: `{self.game.judge.display_name}`\nYour cards:\n{cards_msg}'
        else:
            msg_txt = f"The game's current status (`{self.game.status}`) doesn't allow for card DMing"
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
                    question = f'Current Question:\n`{self.game.current_question_card}`'
                    cards_msg = player.hand.render_hand()
                    msg_txt = f'{question}\nJudge: `{self.game.judge.display_name}`\nYour cards:\n{cards_msg}'
                    self.st.private_message(player.player_id, msg_txt)
                self.st.private_channel_message(player.player_id, self.channel_id, player.hand.render_hand())

    def process_picks(self, user, message, is_random=False):
        """Processes the card selection made by the user"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        if self.game.status != self.game.gs.players_decision:
            # Prevent this method from being called outside of the player's decision stage
            self.message_grp(f'<@{user}> You cannot make selections '
                             f'in the current status of this game: `{self.game.status}`.')
            return None

        if user == self.game.judge.player_id and not is_random:
            self.message_grp(f'<@{user}> You\'re the judge. You can\'t pick!')
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
                    self.message_grp(f'Player id not found: `{ptag}`')
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
            self.message_grp(f'<@{user}> I think you picked outside the range of suggestions: `{message}`.')
            return None
        messages = [self.game.assign_player_pick(user, picks)]

        # See who else has yet to decide
        remaining = self.game.players_left_to_decide()
        if len(remaining) == 0:
            messages.append('All players have made their picks.')
            if self.game.ping_judge:
                judge_msg = f'{self.game.judge.player_tag} to judge.'
            else:
                judge_msg = f'`{self.game.judge.display_name}` to judge.'
            messages.append(judge_msg)
            self.game.status = self.game.gs.judge_decision
            self._display_picks()
        else:
            messages.append(f'`{len(remaining)}` players remaining to decide: {", ".join(remaining)}')
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
            self.message_grp(f'<@{user}> - I didn\'t understand your pick. You entered: `{message}` \n'
                             'Try something like `p 12` or `pick 2`')
        elif judge_decide:
            if len(picks) == 1:
                # Expected number of picks for judge
                return picks[0] - 1
            else:
                self.message_grp(f'<@{user}> - You\'re the judge. You should be choosing only one set. Try again!')
        else:
            # Confirm that the number of picks matches the required number of answers
            req_ans = self.game.current_question_card.required_answers
            if len(set(picks)) == req_ans:
                # Set picks to 0-based index and send onward
                return [x - 1 for x in picks]
            else:
                self.message_grp(f'<@{user}> - You chose {len(picks)} things, '
                                 f'but the current question requires {req_ans}.')
        return None

    def _display_picks(self):
        """Shows a random order of the picks"""
        self.message_grp(f'Q: `{self.game.current_question_card.txt}`\n\n{self.game.display_picks()}')

    def choose_card(self, user, message):
        """For the judge to choose the winning card"""
        if self.game is None:
            self.message_grp('Start a game first, then tell me to do that.')
            return None

        if self.game.status != self.game.gs.judge_decision:
            # Prevent this method from being called outside of the judge's decision stage
            self.message_grp(f'Not the right status for this command: `{self.game.status}`')
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
                winner_details = winner.player_tag if self.game.ping_winner else f'`{winner.display_name}`'
                self.message_grp(f"Winning card: `{','.join([x.txt for x in winner.hand.picks])}`\n"
                                 f"\t({winner_details}) new score: *{winner.points}* diddles "
                                 f"({winner.get_grand_score() + winner.points} total)")
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
            points_df.loc[:, 'rank'] = [f':{poops[randrange(0, len(poops))]}:' for x in range(points_df.shape[0])]
        else:
            # Start off with the basics
            points_df.loc[:, 'rank'] = [f':{poops[randrange(0, len(poops))]}:' for x in range(points_df.shape[0])]
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
            line = f"{r['rank']} `{r['name'][:20]:.<30}` {r['diddles']} diddles ({r['overall']} overall)"
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
            '\n*Current Game Shit*',
            f'Status: `{self.game.status}`',
        ]

        if self.game.status not in [self.game.gs.ended, self.game.gs.stahted]:
            status_list += [
                f'Judge: `{self.game.judge.display_name}`',
                'Players: {}'.format(','.join(['`{}`'.format(x.display_name)
                                                         for x in self.game.players.player_list])),
                f'Round: `{self.game.rounds}`',
                f'Judge Ping: `{self.game.ping_judge}`',
                f'Weiner Ping: `{self.game.ping_winner}`',
                'DM Cards: {}'.format(",".join(
                    ["`{}`".format(x.display_name) for x in self.game.players.player_list if x.dm_cards])),
                '\n*Timing*',
                f'Elapsed Round Time: `{self.get_time_elapsed(self.game.round_start_time)}`',
                f'Elapsed Game Time: `{self.get_time_elapsed(self.game.game_start_time)}`',
                '\n*Metadootie*',
                f'Black Cards Left: `{len(self.game.deck.questions_card_list)}`',
                f'White Cards Left: `{len(self.game.deck.answers_card_list)}`',
            ]

        if self.game.status in [self.game.gs.players_decision, self.game.gs.judge_decision]:
            status_list = status_list[:2] + [
                f'Question: `{self.game.current_question_card}`',
                'Pickles Needed: {}'.format(
                    ','.join(['`{}`'.format(x) for x in self.game.players_left_to_decide()])),
            ] + status_list[2:]

        status_message = '\n'.join(status_list)
        self.message_grp(status_message)

    def refresh_sheets(self):
        """Refreshes the GSheet containing the Q&A cards"""
        self.decks = Decks(self.st.read_in_sheets(self.cah_gsheet))
