"""Util tests"""
import os
import unittest
from cah.utils import CAHBot


bot_name = 'cah'
key_path = os.path.join(os.path.expanduser('~'), 'keys')
key_dict = {}
for t in ['SIGNING_SECRET', 'XOXB_TOKEN', 'XOXP_TOKEN', 'VERIFY_TOKEN']:
    with open(os.path.join(key_path, f'{bot_name.upper()}_SLACK_{t}')) as f:
        key_dict[t.lower()] = f.read().strip()


class TestCAHBot(unittest.TestCase):
    cbot = CAHBot(bot_name, key_dict['xoxb_token'], key_dict['xoxp_token'], debug=True)
    p1 = 'UM35HE6R5'
    p2 = 'UM8N2JZE3'
    trigger = cbot.triggers[0]

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
        # Starts game with two players
        self.cbot.new_game(f'new game -s technerd -p <@{self.p1}> <@{self.p2}>')
        # Make sure players aren't dmed during testing
        for player in self.cbot.game.players.player_list:
            player.dm_cards = False
        # Turn off judge ping
        self.cbot.game.ping_judge = False
        # Turn off winner pingins
        self.cbot.game.ping_winner = False
        self.assertTrue(self.cbot.game.deck.name == 'technerd')
        self.assertTrue(self.cbot.game.rounds == 1)
        self.assertTrue(len(self.cbot.game.players.player_list) == 2)
        for game_round in range(1, 3):
            # Let's cycle through two rounds
            # Confirm we've transitioned to the player decision stage
            self.assertTrue(self.cbot.game.status == self.cbot.game.gs.players_decision)
            # All non-judge players make a pick
            for player in self.cbot.game.players.player_list:
                if player.player_id != self.cbot.game.judge.player_id:
                    # Determine required number of cards to choose
                    required_ans = self.cbot.game.current_question_card.required_answers
                    picks = ''.join([f'{x}' for x in range(1, required_ans + 1)])
                    self.cbot.process_picks(player.player_id, f'pick {picks}')
            # Confirm we've transitioned to the judge decision stage
            self.assertTrue(self.cbot.game.status == self.cbot.game.gs.judge_decision)
            # Judge chooses the winner
            self.cbot.choose_card(self.cbot.game.judge.player_id, 'choose 1')
            # Game _should_ transition to new round
            self.assertTrue(self.cbot.game.rounds == game_round + 1)
        self.assertTrue(self.cbot.game.status == self.cbot.game.gs.players_decision)
        # End the game
        self.cbot.end_game()
        # Confirm game is in the right status
        self.assertTrue(self.cbot.game.status == self.cbot.game.gs.ended)
