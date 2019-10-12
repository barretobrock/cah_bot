#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from random import shuffle
from slacktools import SlackTools
from kavalkilu import Keys, GSheetReader


help_txt = """
Hi! I'm Wizzy and I help you play shitty games!
*Commands*:
 - `cah new game [OPTIONS]`: start a new CAH game
    optional flags:
        - `-(set|s) <card-set-name>`: choose a specific card set (standard, indeed) default: *standard*
        - `-skip <disp-name1,disp-name2>`: skip some channel members
 - `cah pick <card-index>`: pick your card for the round
 - `cah (points|score|scores)`: show points/score of all players
 - `cah status`: get the current status of the game
 - `cah toggle dm`: Toggles whether or not you receive cards as a DM from Wizzy (default is off)
 - `cah cahds now`: Send cards immediately without toggling DM
 - `cah choose <card-index>`: used by the judge to determine the best card from picks
 - `cah new round`: continue gameplay to a new round
 - `cah end game`: end the current game
 - `cah refresh sheets`: Refreshes the GSheets that contain the card sets
"""


class CAHBot:
    """Bot for playing Cards Against Humanity on Slack"""

    def __init__(self, log):
        self.log = log
        k = Keys()
        self.st = SlackTools(self.log, bot_name='Wizzy', triggers=['cah', 'c!'], team=k.get_key('okr-name'),
                             xoxp_token=k.get_key('wizzy-token'), xoxb_token=k.get_key('wizzy-bot-user-token'))
        # Replace the empty handle_command with one that functions for this bot
        self.st.handle_command = self.handle_command
        self.bot = self.st.bot
        self.user = self.st.user

        self.channel_id = 'CMPV3K8AE'  # #cah
        # Starting number of cards for each player
        self.DECK_SIZE = 5
        # For storing game info
        self.game_dict = {
            'players': self.build_players(),
            'status': 'stahted'
        }
        cah_gsheet = k.get_key('cah_sheet')
        self.set_dict = self.st.read_in_sheets(cah_gsheet)

    def run_rtm(self):
        """Initiate real-time messaging"""
        self.st.run_rtm('Booted up and ready to play! :tada:', self.channel_id)

    def handle_command(self, channel, message, user):
        """Handles a bot command if it's known"""
        response = None
        if message == 'help':
            response = help_txt
        elif message.startswith('new game'):
            self.new_game(message)
        elif message == 'new round':
            response = self.new_round()
            if response is not None:
                '\n'.join(response)
        elif message == 'end game':
            self.end_game()
        elif message.startswith('pick'):
            self.process_picks(user, message)
        elif message.startswith('choose'):
            self.choose_card(user, message)
        elif message in ['points', 'score', 'scores']:
            self.display_points()
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
                self._read_in_sheets()
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

    def new_game(self, message):
        """Begins a new game"""
        msg_split = message.split()
        response_list = []
        if '-skip' in msg_split and len(msg_split) > 3:
            # We're going to skip some players
            skip_idx = msg_split.index('-skip')
            skip_players = msg_split[skip_idx + 1].split(',')
        else:
            skip_players = None

        if any([x in msg_split for x in ['-set', '-s']]) and len(msg_split) > 3:
            # We're going to skip some players
            set_idx = None
            for s in ['-set', '-s']:
                try:
                    set_idx = msg_split.index(s)
                except ValueError:
                    continue
            if set_idx is None:
                response_list.append('Could not find the \\-[s]?et flag. Defaulting to standard set.')
                card_set = 'standard'
            else:
                card_set = msg_split[set_idx + 1].strip()
        else:
            card_set = 'standard'

        cards = self._read_in_cards(set_type=card_set)
        if cards is not None:
            response_list.append('Reading in the `{}` card set'.format(card_set))
            black_cards = cards['q']
            white_cards = cards['a']
            # Shuffle cards
            shuffle(black_cards)
            shuffle(white_cards)
        else:
            return None

        response_list.append('Cards have been shuffled. Generating players...')
        # Refresh the players' names
        self.game_dict['players'] = self.refresh_players()
        players = self.game_dict['players']

        # Skipping players
        if skip_players is not None:
            for skip_player in skip_players:
                # pop out any player that we don't want to participate
                if skip_player in [x['display_name'].lower() for x in players]:
                    # Mark them as skipped
                    player_idx = players.index([x for x in players if x['display_name'].lower() == skip_player][0])
                    players[player_idx]['skip'] = True
                    response_list.append('Skipping: *{display_name}*'.format(**players[player_idx]))

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

        new_round_list = self.new_round(replace_all=True)
        if new_round_list is not None:
            response_list += new_round_list
        msg = '\n'.join(response_list)
        self.message_grp(msg)

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
        refreshed_players = self.refresh_players()
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

    def toggle_card_dm(self, user_id):
        """Toggles card dming"""
        players = self.game_dict['players']
        player_idx = players.index([x for x in players if x['id'] == user_id][0])
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
        player = [x for x in players if x['id'] == user_id][0]

        # Send cards to user if the status shows we're currently in a game
        if self.game_dict['status'] == 'players_decision':
            # self._distribute_cards(self.game_dict['players'][player_idx])
            question = 'Current Question:\n`{current_black}`'.format(**self.game_dict)
            cards_msg = ['\t`{}`: {}'.format(i + 1, x) for i, x in enumerate(player['cards'])]
            msg_txt = '{}\nYour cards:\n{}'.format(question, '\n'.join(cards_msg))
        else:
            msg_txt = "The game's current status doesn't allow for card DMing"
        self.st.private_message(player['id'], msg_txt)

    def new_round(self, replace_all=False):
        """Starts a new round"""
        resp_list = []
        if not self.game_dict['status'] in ['end_round', 'initiated']:
            # Avoid starting a new round when one has already been started
            self.message_grp('Cannot transition to new round '
                             'due to status (`{}`)'.format(self.game_dict['status']))
            return None

        if replace_all:
            # This is done for the first round of the game
            num_cards = self.DECK_SIZE
            players = self.game_dict['players']
            judge = self._find_new_judge(new_game=True)
        else:
            # This is for sequential rounds
            num_cards = 1
            players = self.game_dict['players']
            judge = self._find_new_judge()

        resp_list.append('*{display_name}* is the judge!'.format(**judge))
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

        resp_list.append('Distributing cards...')

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
                resp_list.append('No more cards left to deal!')
                break

        # Show group this round's question
        resp_list.append("Q: `{}`".format(current_black))
        # Load everything back into the game dict
        self.game_dict.update({
            'status': 'players_decision',
            'players': players,
            'remaining_white': white_cards,
            'remaining_black': black_cards,
            'current_black': current_black,
            'chosen_cards': []
        })

        return resp_list

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
            # DM cards if user has toggled that on
            msg_txt2 = "Psst - In case you didn't get the cards in the channel, here they are. " \
                       "*Reply in #cah though.*\n\n{}".format(msg_txt)
            self.st.private_message(user_dict['id'], msg_txt2)

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
            self.message_grp('`{}` to judge'.format(self.game_dict['judge']['display_name']))
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
            if pick > len(self.game_dict['players']) - 1 or pick < 1:
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
        points = ['*{display_name}*: {score}'.format(**player) for player in self.game_dict['players']]
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
