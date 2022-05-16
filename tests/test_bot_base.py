from unittest import TestCase, main
from unittest.mock import MagicMock
from pukr import get_logger
from cah.bot_base import CAHBot
from tests.common import (
    make_patcher,
    random_string
)
from tests.mocks.db_objects import mock_get_score


class TestCAHBot(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('test_cah')
        cls.cahbot = None

    def setUp(self) -> None:
        self.mock_eng = MagicMock(name='PSQLClient')
        self.mock_session = self.mock_eng.session_mgr.return_value.__enter__.return_value
        # Load how to return things from the various ORM paths
        self.mock_session.query.return_value.join.return_value.filter.return_value.group_by.return_value\
            .all.side_effect = self._side_effect_query_stmt_decider
        self.mock_creds = make_patcher(self, 'cah.bot_base.SimpleNamespace')
        self.mock_slack_base = make_patcher(self, 'cah.bot_base.SlackBotBase')
        self.mock_forms_init = make_patcher(self, 'cah.bot_base.Forms.__init__')
        self.mock_forms = make_patcher(self, 'cah.bot_base.Forms')
        self.mock_game = MagicMock(name='Game')
        if self.cahbot is None:
            self.cahbot = CAHBot(eng=self.mock_eng, bot_cred_entry=self.mock_creds, parent_log=self.log)
        self.mock_overall_score, self.mock_current_score, self.mock_previous_score = mock_get_score(n_players=8)

    def test_init(self):
        # Assert greater than 10 entries
        self.assertGreater(len(self.cahbot.commands), 10)
        self.mock_eng.get_setting.assert_called()
        self.mock_slack_base.assert_called()
        self.mock_forms_init.assert_called()

    def _side_effect_query_stmt_decider(self, *args, **kwargs):
        """Decides which mocked pandas query to IMLdb to return based on the select arguments provided"""
        # Check the most recent call; if the arguments in query match what's below, return the designated result
        select_cols = [x.__dict__.get('key') for x in self.mock_session.query.call_args.args]
        if select_cols == ['player_id', 'display_name', 'overall']:
            # Getting the overall
            return self.mock_overall_score.copy()
        elif select_cols == ['player_id', 'display_name', 'current']:
            # This is from _get_data_check_info
            return self.mock_current_score.copy()
        elif select_cols == ['player_id', 'display_name', 'prev_round']:
            # This id from the update_data_check_metrics method. It's to simulate pulling in a wide date range
            # of daily snapshots and aggregate them according to different time windows (mtd, ytd, etc.)
            return self.mock_previous_score.copy()
        else:
            raise ValueError(f'Unaccounted query condition for these selections: {select_cols}')

    def test_display_points(self):
        """Tests the display_poinst method"""
        # In-game score retrieval
        self.cahbot.current_game = self.mock_game
        resp = self.cahbot.display_points()
        self.assertIsInstance(resp, list)
        self.assertEqual(3, len(resp))
        self.mock_eng.session_mgr.assert_called()

        # Score retrieval without a current game
        self.cahbot.current_game = None
        resp = self.cahbot.display_points()
        self.assertIsInstance(resp, list)
        self.assertEqual(3, len(resp))


if __name__ == '__main__':
    main()
