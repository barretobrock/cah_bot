from unittest import TestCase, main
from unittest.mock import (
    patch,
    MagicMock
)
from cah.core.cards import Card
from tests.common import get_test_logger


class TestCard(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_test_logger()

    def test_init(self):
        txt = 'test'
        cid = 2398
        card = Card(txt=txt, card_id=cid)

        self.assertEqual(txt, card.txt)
        self.assertEqual(cid, card.id)

    def test_str(self):
        card = Card(txt='txt', card_id=0)
        self.assertIsInstance(card.__str__(), str)


if __name__ == '__main__':
    main()
