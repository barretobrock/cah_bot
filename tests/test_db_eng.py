from unittest import TestCase, main
from unittest.mock import (
    patch,
    MagicMock
)
from cah.model import SettingType
from cah.db_eng import WizzyPSQLClient
from tests.common import (
    get_test_logger,
    make_patcher,
    random_string
)


class TestPSQLClient(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_test_logger()

    def setUp(self) -> None:
        self.mock_create_engine = make_patcher(self, 'cah.db_eng.create_engine')
        self.mock_url = make_patcher(self, 'cah.db_eng.URL')
        self.mock_sessionmacher = make_patcher(self, 'cah.db_eng.sessionmaker')
        props = {
            'usr': 'someone',
            'pwd': 'password',
            'host': 'hostyhost',
            'database': 'dateybase',
            'port': 5432,
        }
        self.eng = WizzyPSQLClient(props=props, parent_log=self.log)

    def test_init(self):
        self.mock_create_engine.assert_called()
        self.mock_url.create.assert_called()
        self.mock_sessionmacher.assert_called()

    def test_session_mgr(self):
        # Normal ops
        with self.eng.session_mgr() as session:
            self.mock_sessionmacher().assert_called()
        self.mock_sessionmacher()().commit.assert_called()
        self.mock_sessionmacher()().close.assert_called()
        self.mock_sessionmacher()().rollback.assert_not_called()
        # Exception
        with self.assertRaises(Exception) as err:
            with self.eng.session_mgr() as session:
                raise Exception('rollback')
        self.mock_sessionmacher()().rollback.assert_called()

    def test_get_setting(self):
        self.mock_sessionmacher()().query().filter().one_or_none.return_value = None
        resp = self.eng.get_setting(SettingType.IS_PING_WINNER)

        self.mock_sessionmacher()().query.assert_called()
        self.mock_sessionmacher()().commit.assert_called()
        self.mock_sessionmacher()().close.assert_called()
        self.assertIsNone(resp)


if __name__ == '__main__':
    main()
