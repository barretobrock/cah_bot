"""Util tests"""
import os
import unittest
import numpy as np
from cah.common_methods import CAHBot


bot_name = 'cah'
key_path = os.path.join(os.path.expanduser('~'), 'keys')
key_dict = {}
for t in ['SIGNING_SECRET', 'XOXB_TOKEN', 'XOXP_TOKEN', 'VERIFY_TOKEN']:
    with open(os.path.join(key_path, f'{bot_name.upper()}_SLACK_{t}')) as f:
        key_dict[t.lower()] = f.read().strip()


class TestCAHBot(unittest.TestCase):
    cbot = CAHBot(bot_name, key_dict['xoxb_token'], key_dict['xoxp_token'], debug=True)
    p1 = 'UM35HE6R5'  # me
    p2 = 'UM8N2JZE3'  # weezy
    p3 = 'UM3AP9RQT'  # pip
    trigger = cbot.triggers[0]

    choices = ['choose 1', 'randchoose', 'randchoose 12']
    pick_method = ['randpick', 'randpick 12', 'randpick 15', 'randpick 2,3,4,5']

    # Set all players' dm_cards setting to False
    for player in cbot.players.player_list:
        player.dm_cards = False
        cbot.players.update_player(player)

    def setUp(self) -> None:
        self.msg1 = self.build_event_dict('cah help')
        self.msg2 = self.build_event_dict('cah status')

    def build_event_dict(self, msg, usr=None):
        return {
            'channel': self.cbot.channel_id,
            'message': msg.lower().strip(),
            'raw_message': msg,
            'user': usr if usr is not None else self.p1
        }

    def test_initial_data(self):
        """Check data on initiation"""
        # Players are loaded
        self.assertTrue(len(self.cbot.players.player_list) > 0)
        # Sheets are read in
        self.assertTrue(len(self.cbot.cah_sheets) > 0)
        # Game info sheet
        self.assertTrue('x_game_info' in self.cbot.cah_sheets.keys())
        # Scores sheet
        self.assertTrue('x_scores' in self.cbot.cah_sheets.keys())
        # Decks are read in
        self.assertTrue(len(self.cbot.decks.deck_list) > 0)
        self.assertTrue(len(self.cbot.decks.deck_list) < len(self.cbot.cah_sheets))

    def test_game_routine(self):
        """Tests the entire game process"""
        # Starts game with three players, avoid testhuman
        self.cbot.new_game(f'new game -s technerd -p <@{self.p1}> <@{self.p2}> <@{self.p3}>')
        # Make sure players aren't dmed during testing
        for player in self.cbot.game.players.player_list:
            player.dm_cards = False
            self.cbot.game.players.update_player(player)
        # Turn off judge ping
        self.cbot.game.ping_judge = False
        # Turn off winner pinging
        self.cbot.game.ping_winner = False
        self.assertTrue(self.cbot.game.deck.name == 'technerd')
        self.assertTrue(self.cbot.game.rounds == 1)
        self.assertTrue(len(self.cbot.game.players.player_list) == 3)
        for game_round in range(1, 10):
            # Let's cycle through three rounds
            # Confirm we've transitioned to the player decision stage
            self.assertTrue(self.cbot.game.status == self.cbot.game.gs.players_decision)
            # Determine required number of cards to choose
            required_ans = self.cbot.game.current_question_card.required_answers
            # All non-judge players make a pick
            for i, player in enumerate(self.cbot.game.players.player_list):
                if player.player_id != self.cbot.game.judge.player_id:
                    if i == 0:
                        # One player should test all random picking types
                        pick_type = np.random.choice(len(self.pick_method), 1).tolist()[0]
                        # Announce pick in channel
                        self.cbot.message_grp(f'caww {self.pick_method[pick_type]}')
                        self.cbot.process_picks(player.player_id, self.pick_method[pick_type])
                    else:
                        # One player should pick normally
                        picks = ''.join([f'{x}' for x in range(1, required_ans + 1)])
                        # Announce pick in channel
                        self.cbot.message_grp(f'caww pick {picks}')
                        self.cbot.process_picks(player.player_id, f'pick {picks}')
            # Confirm we've transitioned to the judge decision stage
            self.assertTrue(self.cbot.game.status == self.cbot.game.gs.judge_decision)
            # Judge chooses the winner, using all different methods
            choose_type = np.random.choice(len(self.choices), 1).tolist()[0]
            self.cbot.message_grp(f'caww {self.choices[choose_type]}')
            self.cbot.choose_card(self.cbot.game.judge.player_id, self.choices[choose_type])
        self.assertTrue(self.cbot.game.status == self.cbot.game.gs.players_decision)
        # End the game
        self.cbot.end_game()
        # Confirm game is in the right status
        self.assertTrue(self.cbot.game.status == self.cbot.game.gs.ended)
