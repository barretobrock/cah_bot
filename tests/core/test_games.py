import random
from unittest import TestCase, main
from unittest.mock import MagicMock
from typing import (
    List,
    Optional
)
from pukr import get_logger
from cah.model import (
    SettingType,
    TableGame,
    TableGameRound,
    TableQuestionCard
)
from cah.core.games import (
    Game,
    GameStatus
)
from tests.common import (
    make_patcher
)
from tests.mocks.users import random_user


class TestGames(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('test_cah', show_backtrace=False)

    def setUp(self) -> None:
        self.mock_gq = make_patcher(self, 'cah.core.games.GameQueries')

        self.mock_slack_base = MagicMock(name='SlackBotBase')
        self.mock_deck = MagicMock(name='Deck')
        self.mock_eng = MagicMock(name='PSQLClient')
        self.mock_session = self.mock_eng.session_mgr.return_value.__enter__.return_value
        self.player_hashes = [random_user() for x in range(6)]

        self.game = Game(
            player_hashes=self.player_hashes,
            deck=self.mock_deck,
            st=self.mock_slack_base,
            eng=self.mock_eng,
            parent_log=self.log
        )

    def test_init(self):
        self.mock_gq.assert_called()
        self.assertEqual(GameStatus.INITIATED, self.game.status)
        self.mock_eng.set_active_players.assert_called()
        self.assertEqual(len(self.player_hashes), len(self.game.players.player_dict.keys()))
        self.assertFalse(self.game.is_existing_game)
        self.assertIsNone(self.game.current_question_card)
        self.mock_deck.shuffle_deck.assert_called()

    def test_is_ping_winner(self):
        self.game.is_ping_winner = True
        self.mock_eng.set_setting.assert_called_with(SettingType.IS_PING_WINNER, True)

    def test_is_ping_judge(self):
        self.game.is_ping_judge = True
        self.mock_eng.set_setting.assert_called_with(SettingType.IS_PING_JUDGE, True)

    def test_decknuke_penalty(self):
        self.game.decknuke_penalty = -3
        self.mock_eng.set_setting.assert_called_with(SettingType.DECKNUKE_PENALTY, -3)

    def test_game_round_number(self):
        game_tbl = TableGame(deck_key=5, status=GameStatus.PLAYER_DECISION)
        n_rounds = random.randint(5, 25)
        rounds = [TableGameRound(game_key=7) for x in range(n_rounds)]
        game_tbl.rounds = rounds
        self.mock_eng.session_mgr.return_value.__enter__.return_value.query.return_value.\
            filter.return_value.one_or_none.return_value = game_tbl
        self.assertEqual(n_rounds, self.game.game_round_number)

    def test_init_with_existing_game(self):
        """Tests initialization when a previous, unfinished game is detected."""
        pass
        # Ensure judge is the same

    def test_process_picks(self):
        """Tests the process_picks method"""
        # Preload some mocks
        self.game.assign_player_pick = MagicMock(name='assign_player_pick', return_value='pick registered')
        mock_card_counter = MagicMock(name='get_all_cards', return_value=5)
        self.game.players_left_to_pick = MagicMock(name='players_left_to_pick',
                                                   return_value=['this_one', 'that_one'])
        self.game.round_wrap_up = MagicMock('round_wrap_up')
        self.game.game_round_tbl = TableGameRound(game_key=1, question_card_key=3)
        judge_hash = self.game.judge.player_hash
        p_hash, other_p_hash = random.sample([x for x in self.player_hashes if x != judge_hash], 2)
        cases = {
            'pick 5': {
                'result': [4]
            },
            # Commander is judge
            'pick 3': {
                'result': None,
                'cmd_sender': judge_hash
            },
            # Randpick
            'randpick': {
                'is_rand': True,
                'result': range(5)
            },
            f'randpick <@{other_p_hash.lower()}>': {
                'is_rand': True,
                'player_to_pick': f'{other_p_hash.upper()}',
                'cmd_sender': judge_hash,
                'result': range(5)
            },
            f'randpick <@{other_p_hash.lower()}> 523': {
                'is_rand': True,
                'player_to_pick': f'{other_p_hash.upper()}',
                'result': range(5)
            },
            'randpick 234': {
                'is_rand': True,
                'result': range(2, 5)
            },

            # Pick outside of bounds
            'pick 7': {'result': None, 'throws_exception': True},
            'pick 0': {'result': None, 'throws_exception': True},

            # Multiple picks
            'p 52': {
                'result': [4, 1],
                'resp_req': 2
            },
            'p 5,2': {
                'result': [4, 1],
                'resp_req': 2
            },
            'p 5 2': {
                'result': [4, 1],
                'resp_req': 2
            },
            'p 5, 2': {
                'result': [4, 1],
                'resp_req': 2
            },
        }
        for msg, res_dict in cases.items():
            is_rand = res_dict.get('is_rand', False)
            cmd_sender = res_dict.get('cmd_sender', p_hash)
            player_to_pick = res_dict.get('player_to_pick', p_hash)
            self.game.players.player_dict[player_to_pick].get_all_cards = mock_card_counter
            self.game.players.player_dict[player_to_pick].is_dm_cards = False
            exp_output = res_dict.get('result')  # type: Optional[List[int]]
            resp_req = res_dict.get('resp_req', 1)
            throws_exception = res_dict.get('throws_exception', False)
            self.game.current_question_card = TableQuestionCard(card_text='test', deck_key=3,
                                                                responses_required=resp_req)
            if throws_exception:
                with self.assertRaises(ValueError) as _:
                    res = self.game.process_picks(player_hash=cmd_sender, message=msg)
            else:
                res = self.game.process_picks(player_hash=cmd_sender, message=msg)
            if exp_output is None:
                self.assertIsNone(res)
            elif not is_rand:
                self.game.assign_player_pick.assert_called_once_with(player_to_pick, exp_output)
            else:
                # Assert the randomly picked list of picks are within the range
                self.game.assign_player_pick.assert_called()
            self.game.assign_player_pick.reset_mock()


if __name__ == '__main__':
    main()
