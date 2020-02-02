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
    me_user = 'UM35HE6R5'
    trigger = cbot.triggers[0]

    def setUp(self) -> None:
        self.msg1 = self.build_event_dict('cah help')
        self.msg2 = self.build_event_dict('cah status')

    def build_event_dict(self, msg, usr=None):
        return {
            'channel': self.cbot.channel_id,
            'message': msg.lower().strip(),
            'raw_message': msg,
            'user': usr if usr is not None else self.me_user
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


