from unittest import (
    TestCase,
    main
)
from unittest.mock import MagicMock
from pukr import get_logger
from cah.model import SettingType
from cah.db_eng import WizzyPSQLClient
from tests.common import (
    make_patcher,
    random_string
)


class TestPSQLClient(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('cah_test')

    def setUp(self) -> None:
        self.mock_psql_client = make_patcher(self, 'cah.db_eng.PSQLClient')
        self.mock_session = MagicMock(name='session_mgr')
        props = {
            'usr': 'someone',
            'pwd': 'password',
            'host': 'hostyhost',
            'database': 'dateybase',
            'port': 5432,
        }
        self.eng = WizzyPSQLClient(props=props, parent_log=self.log)
        self.eng.session_mgr = self.mock_session

    def test_get_setting(self):
        self.mock_session().__enter__().query().filter().one_or_none.return_value = None
        resp = self.eng.get_setting(SettingType.IS_PING_WINNER)

        self.mock_session().__enter__().query.assert_called()
        self.assertIsNone(resp)


if __name__ == '__main__':
    main()
