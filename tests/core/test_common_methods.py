from unittest import TestCase, main
from unittest.mock import (
    patch,
    MagicMock
)
from cah.core.common_methods import process_player_slack_details
from tests.common import (
    get_test_logger,
    random_string
)


class TestCommonMethods(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_test_logger()

    def test_process_player_slack_details(self):
        name = 'Gethrey Phranthis'
        real_name = 'wtfevenisyourname'
        uid = random_string(13)
        url = random_string(52)
        pdict = {
            'slack_user_hash': uid,
            'display_name': name,
            'avi32': url
        }
        resp = process_player_slack_details(uid, profile_dict=pdict)
        pdict['avi_url'] = pdict.pop('avi32')
        self.assertDictEqual(pdict, resp)

        # Now test if real name is none and display name is empty
        pdict['display_name'] = ''
        resp = process_player_slack_details(uid, profile_dict=pdict)
        self.assertEqual(real_name, resp['display_name'])


if __name__ == '__main__':
    main()
