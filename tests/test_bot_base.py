from datetime import datetime
from unittest import (
    TestCase,
    main,
)
from unittest.mock import MagicMock

from pukr import get_logger

from cah.bot_base import CAHBot
from cah.model import GameStatus
from tests.common import (
    make_patcher,
    random_string,
)
from tests.mocks.db_objects import (
    mock_game_tbl,
    mock_get_rounds_df,
    mock_get_score,
)


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
        self.mock_session.query.return_value.join.return_value.filter.return_value.all.side_effect =\
            self._side_effect_query_stmt_decider
        self.mock_config = MagicMock(name='config')
        self.mock_config.UPDATE_DATE = datetime.now().strftime('%Y-%m-%d_%H:%M:%S')

        self.mock_creds = {
            'team': 't;a',
            'xoxp-token': random_string(),
            'xoxb-token': 'al;dskj'
        }
        self.mock_slack_base = make_patcher(self, 'cah.bot_base.SlackBotBase')
        self.mock_forms_init = make_patcher(self, 'cah.bot_base.Forms.__init__')
        self.mock_forms = make_patcher(self, 'cah.bot_base.Forms')
        self.mock_game = MagicMock(name='Game')
        if self.cahbot is None:
            # We're simulating normal operation, so load query response to look like the previous game ended
            self.mock_session.query.return_value.order_by.return_value.limit.return_value.one_or_none.\
                return_value = mock_game_tbl(status=GameStatus.ENDED)
            self.cahbot = CAHBot(eng=self.mock_eng, props=self.mock_creds, parent_log=self.log, config=self.mock_config)

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
            # Getting the overall score
            return self.mock_overall_score.copy()
        elif select_cols == ['player_id', 'display_name', 'current']:
            # Getting the current score
            return self.mock_current_score.copy()
        elif select_cols == ['player_id', 'display_name', 'prev']:
            # Getting the previous round's score
            return self.mock_previous_score.copy()
        elif select_cols == ['player_id', 'game_round_key', 'is_judge', 'is_nuked_hand_caught', 'score']:
            # Getting the table of rounds for the game
            return mock_get_rounds_df(n_rounds=10, n_players=8)
        else:
            raise ValueError(f'Unaccounted query condition for these selections: {select_cols}')

    # def test_display_points(self):
    #     """Tests the display_poinst method"""
    #     # In-game score retrieval
    #     self.log.debug('Testing in-game score displaying under expected conditions')
    #     self.mock_overall_score, self.mock_current_score, self.mock_previous_score = mock_get_score(n_players=8)
    #     self.cahbot.current_game = self.mock_game
    #     resp = self.cahbot.display_points()
    #     self.assertIsInstance(resp, list)
    #     self.assertEqual(3, len(resp))
    #     self.mock_eng.session_mgr.assert_called()
    #
    #     # Score retrieval without a current game
    #     self.log.debug('Testing display outside of current game')
    #     self.cahbot.current_game = None
    #     resp = self.cahbot.display_points()
    #     self.assertIsInstance(resp, list)
    #     self.assertEqual(3, len(resp))
    #
    #     # Check that ranks are handled properly
    #     self.log.debug('Testing ranking for similar scores')
    #     self.mock_overall_score, self.mock_current_score, self.mock_previous_score = mock_get_score(
    #         n_players=10, lims_overall=(0, 20), lims_current=(0, 1))
    #     self.cahbot.current_game = self.mock_game
    #     resp = self.cahbot.display_points()
    #     self.assertIsInstance(resp, list)
    #     self.assertEqual(3, len(resp))
    #     self.mock_eng.session_mgr.assert_called()

    def test_ping(self):
        # In-game ping
        self.mock_game.judge.player_hash = 'XXXX'
        # ... During JUDGE_DECISION
        self.mock_game.status = GameStatus.JUDGE_DECISION
        self.cahbot.current_game = self.mock_game
        resp = self.cahbot.ping_players_left_to_pick()
        self.assertEqual('Hey <@XXXX> time to wake up and do your CAHvic doodie', resp)

        # ... During PLAYER_DECISION
        self.mock_game.status = GameStatus.PLAYER_DECISION
        self.mock_game.players_left_to_pick.return_value = ['YYYY', 'ZZZZ']
        self.cahbot.current_game = self.mock_game
        resp = self.cahbot.ping_players_left_to_pick()
        self.assertEqual('Hey <@YYYY> and <@ZZZZ> - get out there and make pickles! '
                         ':pickle-sword::pickle-sword::pickle-sword:', resp)

        # Pinging when no game exists
        self.cahbot.current_game = None
        resp = self.cahbot.ping_players_left_to_pick()
        self.assertEqual('I can\'t really do this outside of a game WHAT DO YOU WANT FROM ME?!?!?!?!??!', resp)


if __name__ == '__main__':
    main()
