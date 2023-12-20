import random
from unittest import (
    TestCase,
    main,
)
from unittest.mock import (
    MagicMock,
    call,
)

from pukr import get_logger

from cah.core.players import Player
from cah.model import (
    TableAnswerCard,
    TablePlayer,
)
from tests.common import (
    make_patcher,
    random_string,
)


class TestPlayer(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('test_player')

    def setUp(self) -> None:
        self.mock_eng = MagicMock(name='PSQLClient')
        self.mock_player_tbl = TablePlayer(slack_user_hash=random_string(), display_name='test_user',
                                           avi_url='test.com')
        self.mock_player_tbl.player_id = 8
        self.mock_pq = make_patcher(self, 'cah.core.players.PlayerQueries').return_value
        self.mock_pq.get_player_table.return_value = self.mock_player_tbl
        self.player = Player(player_hash=self.mock_player_tbl.slack_user_hash, eng=self.mock_eng, log=self.log)
        equals = [
            (self.player.player_table_id, self.mock_player_tbl.player_id),
            (self.player.display_name, self.mock_player_tbl.display_name),
            (self.player.avi_url, self.mock_player_tbl.avi_url),
            (self.player._is_arp, self.mock_player_tbl.is_auto_randpick),
            (self.player._is_arc, self.mock_player_tbl.is_auto_randchoose),
            (self.player._is_dm_cards, self.mock_player_tbl.is_dm_cards),
            (self.player._choice_order, self.mock_player_tbl.choice_order),
        ]
        for x, y in equals:
            self.assertEqual(x, y)
        nones = [
            self.player.game_id,
            self.player.game_round_id,
            self.player._choice_order
        ]
        for nun in nones:
            self.assertIsNone(nun)

        self.assertDictEqual({}, self.player.pick_blocks)

    def test_start_round(self):
        game_id = 8
        game_round_id = 10
        self.player.start_round(game_id=game_id, game_round_id=game_round_id)
        equals = [
            (game_id, self.player.game_id),
            (game_round_id, self.player.game_round_id),
            (False, self.player._is_nuked_hand),
            (False, self.player._is_nuked_hand_caught),
            (False, self.player._is_picked),
        ]
        for x, y in equals:
            self.assertEqual(x, y)
        self.assertIsNone(self.player._choice_order)
        self.mock_pq.handle_player_new_round.assert_called()

    def test_pick_card(self):
        a_1 = TableAnswerCard(card_text='one', deck_key=random.randint(3, 500))
        a_2 = TableAnswerCard(card_text='two', deck_key=random.randint(3, 500))
        cases = {
            'successful_pick': {
                'hand': [None, None, a_1, None, a_2],
                'pos_list': [2, 4],
                'returns': True
            },
            'successful_pick_rev': {
                'hand': [None, None, a_2, None, a_1],
                'pos_list': [4, 2],
                'returns': True
            },
            'already_picked': {
                'is_picked': True,
                'hand': [None, None, a_2, None, a_1],
                'pos_list': [4, 2],
                'returns': False
            },
            'nuked': {
                'is_nuked_hand': True,
                'hand': [None, None, a_2, None, a_1],
                'pos_list': [4, 2],
                'returns': False
            },
            'is_puked': {
                'is_nuked_hand': True,
                'is_picked': True,
                'hand': [None, None, a_2, None, a_1],
                'pos_list': [4, 2],
                'returns': False
            },
            'out_of_bounds_high': {
                'hand': [None, None, a_2, None, a_1],
                'pos_list': [5],
                'returns': False
            },
            'out_of_bounds_low': {
                'hand': [None, None, a_2, None, a_1],
                'pos_list': [-1],
                'returns': False
            }
        }
        for case_name, cdict in cases.items():
            self.log.debug(f'Working on case {case_name}')
            is_picked = cdict.get('is_picked', False)
            is_nuked_hand = cdict.get('is_nuked_hand', False)
            self.player._is_picked = is_picked
            self.player._is_nuked_hand = is_nuked_hand
            exp_hand = cdict.get('hand')
            self.mock_pq.get_player_hand.return_value = exp_hand

            pos_list = cdict.get('pos_list')
            resp = self.player.pick_card(pos_list=pos_list)
            self.assertEqual(cdict.get('returns'), resp)
            if resp:
                for i, p in enumerate(pos_list):
                    card = exp_hand[p]
                    self.mock_pq.set_picked_card.assert_has_calls([
                        call(
                            player_id=self.player.player_table_id,
                            game_round_id=self.player.game_round_id,
                            slack_user_hash=self.player.player_hash,
                            position=i,
                            card=card
                        )
                    ])
            self.mock_pq.set_picked_card.reset_mocks()
            self.mock_pq.get_player_hand.reset_mocks()


class TestPlayers(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('cah_test')


if __name__ == '__main__':
    main()
