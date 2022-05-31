import random
from unittest import TestCase, main
from unittest.mock import MagicMock
from typing import (
    List,
    Optional
)
from pukr import get_logger
from cah.core.selections import (
    Choice,
    Pick,
    Selection
)
from tests.mocks.users import random_user


class TestSelections(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('test_selections', show_backtrace=False)

    def setUp(self) -> None:
        pass

    def test_parse(self):
        """Tests the parse method"""
        cases = {
            'pick 3': {
                'positions': [3]
            }
        }

        for msg, result_dict in cases.items():
            is_rand = result_dict.get('is_rand', False)
            tgt_player = result_dict.get('target_player')
            selection = Selection()
            selection.parse(message=msg)
            if tgt_player is None:
                self.assertIsNone(selection.player_hash)
            if is_rand:
                self.assertTrue(selection.is_random)

    def test_pick(self):
        command_sender_hash = random_user()
        cases = {
            'pick 5': {
                'exp_pick': [4]
            },
            # Randpick
            'randpick': {
                'is_rand': True,
                'result': range(5)
            },
            f'randpick <@aslkdjfhu2>': {
                'is_rand': True,
                'player_to_pick': 'aslkdjfhu2',
                'result': range(5)
            },
            f'randpick <@aslkdjfhu2> 523': {
                'is_rand': True,
                'player_to_pick': 'aslkdjfhu2',
                'subset': [4, 1, 2]
            },
            'randpick 234': {
                'is_rand': True,
                'subset': [1, 2, 3]
            },

            # Pick outside of bounds
            'pick 7': {'exp_pick': None, 'throws_exception': True},
            'pick 0': {'exp_pick': None, 'throws_exception': True},

            # Multiple picks
            'p 52': {
                'exp_pick': [4, 1],
                'resp_req': 2
            },
            'p 5,2': {
                'exp_pick': [4, 1],
                'resp_req': 2
            },
            'p 5 2': {
                'exp_pick': [4, 1],
                'resp_req': 2
            },
            'p 5, 2': {
                'exp_pick': [4, 1],
                'resp_req': 2
            },
        }
        for msg, res_dict in cases.items():
            is_rand = res_dict.get('is_rand', False)
            player_to_pick = res_dict.get('player_to_pick')
            exp_pick = res_dict.get('exp_pick')  # type: Optional[List[int]]
            resp_req = res_dict.get('resp_req', 1)
            total_cards = res_dict.get('total_cards', 5)
            subset = res_dict.get('subset')
            throws_exception = res_dict.get('throws_exception', False)
            pick = Pick(player_hash=command_sender_hash, message=msg, n_required=resp_req, total_cards=5)
            if throws_exception:
                with self.assertRaises(ValueError) as e:
                    pick.handle_pick(total_cards=total_cards)
            else:
                pick.handle_pick(total_cards=total_cards)
            if player_to_pick is not None:
                self.assertEqual(player_to_pick.upper(), pick.player_hash)
            else:
                self.assertEqual(command_sender_hash.upper(), pick.player_hash)
            self.assertEqual(is_rand, pick.is_random)
            if not pick.is_random:
                self.assertEqual(exp_pick, pick.picks)
            if subset is not None:
                self.assertListEqual(subset, pick.random_subset)

    def test_choose(self):
        command_sender_hash = random_user()
        cases = {
            'choose 5': {
                'exp_choice': 4
            },
            'c 5': {
                'exp_choice': 4
            },
            # Randchoose
            'randchoose': {
                'is_rand': True,
                'result': range(5)
            },
            f'randchoose <@aslkdjfhu2>': {
                'is_rand': True,
                'player_to_pick': 'aslkdjfhu2',
                'result': range(5)
            },
            f'randchoose <@aslkdjfhu2> 523': {
                'is_rand': True,
                'player_to_pick': 'aslkdjfhu2',
                'subset': [4, 1, 2]
            },
            'randchoose 234': {
                'is_rand': True,
                'subset': [1, 2, 3]
            },

            # Choice outside of bounds
            'choose 7': {'exp_choice': 6, 'max_position': 6},
            'choose 0': {'exp_choice': -1},
        }
        for msg, res_dict in cases.items():
            is_rand = res_dict.get('is_rand', False)
            exp_choice = res_dict.get('exp_choice')  # type: Optional[List[int]]
            max_position = res_dict.get('max_position', 4)
            subset = res_dict.get('subset')
            chos = Choice(player_hash=command_sender_hash, message=msg, max_position=max_position)

            self.assertEqual(is_rand, chos.is_random)
            if not chos.is_random:
                self.assertEqual(exp_choice, chos.choice)
            if subset is not None:
                self.assertListEqual(subset, chos.random_subset)


if __name__ == '__main__':
    main()
