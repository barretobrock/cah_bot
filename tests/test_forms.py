from unittest import TestCase, main
from unittest.mock import (
    patch,
    MagicMock
)
from tests.common import (
    get_test_logger,
    random_string
)


class TestForms(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_test_logger()



if __name__ == '__main__':
    main()
