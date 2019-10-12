#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import traceback
from random import shuffle
from slacktools import SlackTools
from kavalkilu import Keys


help_txt = """
Hi! I'm Wizzy and I help you play shitty games!
*Commands*:
 - `cah new game [OPTIONS]`: start a new CAH game
    optional flags:
        - `-(set|s) <card-set-name>`: choose a specific card set (standard, indeed) default: *standard*
        - `-p @player1 @player2 ...`: tag a subset of the channel as current players (space-separated)
 - `cah pick <card-index>`: pick your card for the round
 - `cah (points|score|scores)`: show points/score of all players
 - `cah status`: get the current status of the game
 - `cah toggle jping`: Toggles whether or not the judge is pinged after all selections are made (default: off)
 - `cah toggle dm`: Toggles whether or not you receive cards as a DM from Wizzy (default is off)
 - `cah cahds now`: Send cards immediately without toggling DM
 - `cah choose <card-index>`: used by the judge to determine the best card from picks
 - `cah new round`: continue gameplay to a new round
 - `cah end game`: end the current game
 - `cah refresh sheets`: Refreshes the GSheets that contain the card sets. Can only be done outside a game.
"""


class CAHBot:
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, log):
        self.log = log
        self.bot_name = 'Wizzy'
        self.triggers = ['cah', 'c!']
        self.channel_id = 'CMPV3K8AE'  # #cah
        # Read in common tools for interacting with Slack's API
        k = Keys()
        self.st = SlackTools(self.log, triggers=self.triggers, team=k.get_key('okr-name'),
                             xoxp_token=k.get_key('wizzy-token'), xoxb_token=k.get_key('wizzy-bot-user-token'))
        # Two types of API interaction: bot-level, user-level
        self.bot = self.st.bot
        self.user = self.st.user
        self.bot_id = self.bot.api_call('auth.test')['user_id']
        self.RTM_READ_DELAY = 1

        # Starting number of cards for each player
        self.DECK_SIZE = 5
        # For storing game info
        self.game_dict = {
            'players': self.build_players(),
            'ping-judge': False,
            'status': 'stahted'
        }
        self.cah_gsheet = k.get_key('cah_sheet')
        self.set_dict = self.st.read_in_sheets(self.cah_gsheet)

    def run_rtm(self, startup_message='Booted up and ready to play! :tada:'):
        """Initiate real-time messaging"""
        if self.bot.rtm_connect(with_team_state=False):
            self.log.debug('{} is running.'.format(self.bot_name))
            self.st.send_message(self.channel_id, startup_message)
            while True:
                try:
                    msg_packet = self.st.parse_bot_commands(self.bot.rtm_read())
                    if msg_packet is not None:
                        try:
                            self.handle_command(**msg_packet)
                        except Exception as e:
                            exception_msg = '\n'.join(traceback.format_tb(e.__traceback__))
                            self.log.error(exception_msg)
                            self.st.send_message(msg_packet['channel'],
                                                 "Exception occurred: \n```{}```".format(exception_msg))
                    time.sleep(self.RTM_READ_DELAY)
                except Exception as e:
                    self.log.debug('Reconnecting...')
                    self.bot.rtm_connect(with_team_state=False)
        else:
            self.log.error('Connection failed.')

    def handle_command(self, channel, message, user):
        """Handles a bot command if it's known"""
        response = None
        if message == 'help':
            response = help_txt
        elif message.startswith('new game'):
            self.new_game(message)
        elif message == 'new round':
            self.new_round()
        elif message == 'end game':
            self.end_game()
        elif message.startswith('pick'):
            self.process_picks(user, message)
        elif message.startswith('choose'):
            self.choose_card(user, message)
        elif message in ['points', 'score', 'scores']:
            self.display_points()
        elif message == 'toggle jping':
            self.toggle_judge_ping()
        elif message == 'toggle dm':
            self.toggle_card_dm(user)
        elif message == 'cahds now':
            self.dm_cards_now(user)
        elif message == 'status':
            self.display_status()
        elif message == 'refresh sheets':
            if self.game_dict['status'] not in ['stahted', 'ended']:
                response = 'Please end the game before refreshing :))))))'
            else:
                self.st.read_in_sheets(self.cah_gsheet)
                response = 'Sheets have been refreshed! `{}`'.format(','.join(self.set_dict.keys()))
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

    def _determine_card_set(self, message_split):
        """Determines which card set to use"""
        if any([x in message_split for x in ['-set', '-s']]) and len(message_split) > 3:
            # We're going to skip some players
            set_idx = None
            for s in ['-set', '-s']:
                try:
                    set_idx = message_split.index(s)
                    break
                except ValueError:
                    continue
            card_set = message_split[set_idx + 1].strip()
            notify_msg = 'Using `{}` card set'.format(card_set)
        else:
            card_set = 'standard'
            notify_msg = 'Using `{}` card set'.format(card_set)

        return notify_msg, card_set

    def _determine_players(self, message_split):
        """Determines the players for the game"""

        # Our regular set of players, defined as any non-bot channel members
        players = self.game_dict['players']

        if '-p' in message_split and len(message_split) > 3:
            # We're going to play with only some players of the channel
            play_idx = message_split.index('-p')
            specific_player_ids = [x for x in message_split[play_idx + 1:] if '<@' in x]
        else:
            specific_player_ids = None

        if specific_player_ids is not None:
            # This game is set with specific players
            player_ids = []
            for p in specific_player_ids:
                # Extract user id
                uid = self.st.parse_tag_from_text(p)
                if uid is None:
                    # Failed at parsing
                    self.message_grp('Failed to parse a user id for `{}`. Game cannot proceed.'.format(p))
                    return None
                else:
                    player_ids.append(uid)

            for player in players:
                # Skip player if not in our list of ids
                player['skip'] = player['id'] not in player_ids

            # Build the notification message
            notify_msg = 'Skipping: `{}`'.format('`,`'.join([x['display_name'] for x in players if x['skip']]))
        else:
            notify_msg = 'Playing with everyone.'

        # Reload new player data
        self.game_dict['players'] = players
        return notify_msg

    def new_game(self, message):
        """Begins a new game"""
        msg_split = message.split()
        response_list = []

        # Determine card set to use
        card_set_msg, card_set = self._determine_card_set(msg_split)
        response_list.append(card_set_msg)
        cards = self._read_in_cards(set_type=card_set)
        if cards is not None:
            black_cards = cards['q']
            white_cards = cards['a']
            # Shuffle cards
            shuffle(black_cards)
            shuffle(white_cards)
        else:
            return None

        response_list.append('Cards have been shuffled. Generating players...')
        # Refresh the players' names
        self.refresh_players()
        player_notification = self._determine_players(msg_split)
        if player_notification is None:
            return None
        else:
            response_list.append(player_notification)
        players = self.game_dict['players']

        shuffle(players)
        response_list.append('Judge order: {}'.format(' :finger-wag-right: '.join(
            [x['display_name'] for x in players if not x['skip']])))

        # store game details in a dict
        self.game_dict.update({
            'status': 'initiated',
            'players': players,
            'player_names': ','.join([x['display_name'] for x in players]),
            'judge': players[0],
            'remaining_white': white_cards,
            'remaining_black': black_cards,
        })

        # Kick off the new round, message details to the group
        self.new_round(notifications=response_list, replace_all=True)

    def build_players(self):
        """
        Takes in a list of users in channel, sets basic, game-related details and
            returns a list of dicts for each human player
        """
        players = []
        for user in self.st.get_channel_members(self.channel_id, humans_only=True):
            user_cleaned = {
                'id': user['id'],
                'display_name': user['display_name'].lower(),
                'real_name': user['name'],
                'is_bot': user['is_bot'],
                'skip': False,
                'dm_cards': False,
                'score': 0
            }
            # Make sure display name is not empty
            if user_cleaned['display_name'] == '':
                user_cleaned['display_name'] = user_cleaned['real_name']
            players.append(user_cleaned)
        return players

    def get_player_ids(self, player_list):
        """Collect user ids from a list of players"""
        return [x['id'] for x in player_list]

    def get_player_index_by_id(self, player_id, player_list):
        """Returns the index of a player in a list of players that has a matching 'id' value"""
        return player_list.index([x for x in self.get_player_ids(player_list) if x == player_id][0])

    def get_player_by_id(self, player_id, player_list):
        """Returns a dictionary of player info that has a matching 'id' value in a list of player dicts"""
        player_idx = self.get_player_index_by_id(player_id, player_list)
        return player_list[player_idx]

    def refresh_players(self):
        """Refreshed existing player names and adds new players that may have joined the channel"""
        players = self.game_dict['players']
        refreshed_players = self.build_players()
        for refreshed_player in refreshed_players:
            refreshed_player_id = refreshed_player['id']
            if refreshed_player_id in self.get_player_ids(players):
                # Existing player, avoid updating score, prefs, but refresh names
                player_idx = self.get_player_index_by_id(refreshed_player_id, players)
                for key in ['display_name', 'real_name']:
                    if refreshed_player[key] != players[player_idx][key]:
                        players[player_idx][key] = refreshed_player[key]
                # Update player in list
                players[player_idx] = refreshed_player
            else:
                # New player
                players.append(refreshed_player)
        self.game_dict['players'] = players

    def _read_in_cards(self, set_type='standard'):
        """Reads in the cards"""

        if set_type in self.set_dict.keys():
            set_df = self.set_dict[set_type]
        else:
            self.message_grp('The card set `{}` was not found. '
                             'Possible sets: `{}`.'.format(set_type, ','.join(self.set_dict.keys())))
            return None

        cards = {}
        for part in ['questions', 'answers']:
            cards[part[0]] = set_df.loc[(~set_df[part].isnull()) & (set_df[part] != ''), part].unique().tolist()

        return cards

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        self.game_dict['ping-judge'] = not self.game_dict['ping-judge']

    def toggle_card_dm(self, user_id):
        """Toggles card dming"""
        players = self.game_dict['players']
        player_idx = self.get_player_index_by_id(user_id, players)
        self.game_dict['players'][player_idx]['dm_cards'] = not self.game_dict['players'][player_idx]['dm_cards']
        # Read in the new values
        player = self.game_dict['players'][player_idx]
        self.message_grp('Card DMing for player `{display_name}` set to `{dm_cards}`'.format(**player))
        # Send cards to user if the status shows we're currently in a game
        if self.game_dict['status'] == 'player_decision':
            self.dm_cards_now(user_id)

    def dm_cards_now(self, user_id):
        """DMs current card set to user"""
        players = self.game_dict['players']
        player = self.get_player_by_id(user_id, players)

        # Send cards to user if the status shows we're currently in a game
        if self.game_dict['status'] == 'players_decision':
            # self._distribute_cards(self.game_dict['players'][player_idx])
            question = 'Current Question:\n`{current_black}`'.format(**self.game_dict)
            cards_msg = ['\t`{}`: {}'.format(i + 1, x) for i, x in enumerate(player['cards'])]
            msg_txt = '{}\nYour cards:\n{}'.format(question, '\n'.join(cards_msg))
        else:
            msg_txt = "The game's current status doesn't allow for card DMing"
        self.st.private_message(player['id'], msg_txt)

    def new_round(self, notifications=None, replace_all=False):
        """Starts a new round
        :param notifications: list of str, notifications to be bundled together and posted to the group
        :param replace_all: bool, if True, replaces all cards for each player
        """
        if notifications is None:
            notifications = []

        if not self.game_dict['status'] in ['end_round', 'initiated']:
            # Avoid starting a new round when one has already been started
            self.message_grp('Cannot transition to new round '
                             'due to status (`{}`)'.format(self.game_dict['status']))
            return None

        if replace_all:
            # This is done for the first round of a new game
            num_cards = self.DECK_SIZE
            players = self.game_dict['players']
            judge = self._find_new_judge(new_game=True)
        else:
            # This is for sequential rounds
            num_cards = 1
            players = self.game_dict['players']
            judge = self._find_new_judge()

        notifications.append('`{display_name}` is the judge!'.format(**judge))
        self.st.private_channel_message(judge['id'], self.channel_id, "You're the judge this round!")
        white_cards = self.game_dict['remaining_white']
        black_cards = self.game_dict['remaining_black']

        if len(black_cards) == 0:
            self.message_grp('No more black cards! Game over!')
            self.display_points()
            self.end_game()
            return None
        else:
            current_black = black_cards.pop(0)

        notifications.append('Distributing cards...')

        # Distribute cards
        for i, player in enumerate(players):
            # Remove any possible pick from last round
            _ = player.pop('pick', None)
            if player['skip']:
                # Skip that player
                continue
            if len(white_cards) > 0:
                cards = white_cards[:num_cards]
                white_cards = white_cards[num_cards:]
                if replace_all:
                    player['cards'] = cards
                else:
                    if 'prev_judge' in self.game_dict:
                        # If the player was previously a judge, don't give them another card
                        #   because they didn't play last round
                        if self.game_dict['prev_judge'] != player:
                            player['cards'] += cards
                    else:
                        player['cards'] += cards
                if player != self.game_dict['judge']:
                    # Only send these to a player during this round
                    self._distribute_cards(player)
                players[i] = player
            else:
                notifications.append('No more cards left to deal!')
                break

        # Show group this round's question
        notifications.append("Q: `{}`".format(current_black))
        # Load everything back into the game dict
        self.game_dict.update({
            'status': 'players_decision',
            'players': players,
            'remaining_white': white_cards,
            'remaining_black': black_cards,
            'current_black': current_black,
            'chosen_cards': []
        })

        self.message_grp('\n'.join(notifications))

    def _find_new_judge(self, new_game=False):
        """Determines the next judge by order of players"""
        players = self.game_dict['players']
        judge = self.game_dict['judge']
        judge_pos = players.index(judge)
        if new_game:
            # In new_game(), the judge is the first player in the shuffled list of players
            return judge
        if judge_pos < len(players) - 1:
            # Increment up one player to get new judge
            new_judge_pos = judge_pos + 1
        else:
            # We're at the end of the list of players, go back to the start
            new_judge_pos = 0
        new_judge = players[new_judge_pos]
        self.game_dict['judge'] = new_judge
        self.game_dict['prev_judge'] = judge
        return new_judge

    def _distribute_cards(self, user_dict):
        """Distribute cards to user"""

        cards_msg = ['\t`{}`: {}'.format(i + 1, x) for i, x in enumerate(user_dict['cards'])]

        msg_txt = 'Here are your cards:\n{}'.format('\n'.join(cards_msg))
        self.st.private_channel_message(user_dict['id'], self.channel_id, msg_txt)
        if user_dict['dm_cards']:
            self.dm_cards_now(user_dict)

    def process_picks(self, user, message):
        """Processes the card selection made by the user"""
        if self.game_dict['status'] != 'players_decision':
            # Prevent this method from being called outside of the player's decision stage
            return None
        # Process the message
        pick = self._get_pick(user, message, pick_idx=1)
        if pick is None:
            return None
        elif pick > 4 or pick < 0:
            self.message_grp('<@{}> I think you picked outside the range of suggestions.'.format(user))
            return None
        for i, player in enumerate(self.game_dict['players']):
            if player['id'] == user and player != self.game_dict['judge']:
                if 'pick' not in player.keys():
                    player['pick'] = player['cards'].pop(pick)
                    self.message_grp("{display_name}'s pick has been registered.".format(**player))
                    # Store player's pick
                    self.game_dict['players'][i] = player
                else:
                    self.message_grp("{display_name}, you've already picked this round.".format(**player))
                break

        # See who else has yet to decide
        remaining = []
        for i, player in enumerate(self.game_dict['players']):
            if 'pick' not in player.keys() and player != self.game_dict['judge'] and not player['skip']:
                remaining.append(player['display_name'])
        if len(remaining) == 0:
            self.message_grp('All players have made their picks.')
            if self.game_dict['ping-judge']:
                judge_msg = '<@{}> to judge.'.format(self.game_dict['judge']['id'])
            else:
                judge_msg = '`{}` to judge.'.format(self.game_dict['judge']['display_name'])
            self.message_grp(judge_msg)
            self.game_dict['status'] = 'judge_decision'
            self._display_picks()
        else:
            self.message_grp('{} players remaining to decide: {}'.format(len(remaining), ', '.join(remaining)))

    def _get_pick(self, user, message, pick_idx):
        """Processes a number from a message"""
        # Process the message
        msg_split = message.split()
        if len(msg_split) > 1:
            if msg_split[pick_idx].isnumeric():
                pick = int(msg_split[pick_idx])
                return pick - 1
            else:
                self.message_grp("<@{}> - I didn't understand your pick: {}".format(user, message))
        else:
            self.message_grp("<@{}> - I didn't understand your pick: {}".format(user, message))
        return None

    def _display_picks(self):
        """Shows a random order of the picks"""
        picks = []
        for i, player in enumerate(self.game_dict['players']):
            if 'pick' in player.keys() and player != self.game_dict['judge']:
                player_details = {
                    'id': player['id'],
                    'pick': player['pick']
                }
                picks.append(player_details)
        shuffle(picks)
        pick_str = '\n'.join(['`{}`: {}'.format(x + 1, y['pick']) for x, y in enumerate(picks)])
        self.message_grp('Q: `{}`\n\n{}'.format(self.game_dict['current_black'], pick_str))
        self.game_dict['chosen_cards'] = picks

    def choose_card(self, user, message):
        """For the judge to choose the winning card"""
        if self.game_dict['status'] != 'judge_decision':
            # Prevent this method from being called outside of the judge's decision stage
            return None

        if user == self.game_dict['judge']['id']:
            pick = self._get_pick(user, message, pick_idx=1)
            if pick > len(self.game_dict['players']) - 2 or pick < 0:
                # Pick is rendered as an array index here.
                # Pick either be:
                #   -less than total players minus judge, minus 1 more to account for array
                #   -greater than -1
                self.message_grp('I think you picked outside the range of suggestions.')
                return None
            else:
                # Get the list of cards picked by each player
                chosen_cards = self.game_dict['chosen_cards']
                for i, player in enumerate(self.game_dict['players']):
                    if player['id'] == chosen_cards[pick]['id']:
                        player['score'] += 1
                        self.message_grp("Winning card: `{}`\n\t(`{display_name}`, new score: *{score}* )".format(
                            chosen_cards[pick]['pick'], **player))
                        self.game_dict['status'] = 'end_round'
                        self.message_grp('Round ended. `cah new round` to start another.')
                        break
        else:
            self.message_grp("Get yo _stanky_ ass outta here, you ain't the judge")

    def end_game(self):
        """Ends the current game"""
        self.game_dict['status'] = 'ended'
        self.message_grp('The game has ended.')

    def display_points(self):
        """Displays points for all players"""
        points = ['`{display_name:<20}`: {score}'.format(**player) for player in self.game_dict['players']]
        self.message_grp('*Current Scores*\n{}'.format('\n'.join(points)))

    def display_status(self):
        """Displays points for all players"""

        status_list = ['current game status: `{status}`']

        try:
            num_white = len(self.game_dict['remaining_white'])
            num_black = len(self.game_dict['remaining_black'])
        except KeyError:
            # No cards, no game
            num_white, num_black = None, None

        if 'player_names' in self.game_dict.keys():
            status_list.append('players: `{player_names}`')
        if 'judge' in self.game_dict.keys():
            status_list.append('judge: `{}`'.format(self.game_dict['judge']['display_name']))
        if self.game_dict['status'] in ['players_decision', 'judge_decision']:
            status_list.append('current q: `{current_black}`'.format(**self.game_dict))
        if all([x is not None for x in [num_white, num_black]]):
            status_list += [
                'remaining white cards: `{}`'.format(num_white),
                'remaining black cards: `{}`'.format(num_black),
            ]

        status_message = '\n'.join(status_list).format(**self.game_dict)
        self.message_grp(status_message)
