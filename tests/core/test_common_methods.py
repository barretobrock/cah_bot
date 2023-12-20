from unittest import (
    TestCase,
    main,
)

from pukr import get_logger


class TestCommonMethods(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('cah_test')


if __name__ == '__main__':
    main()
