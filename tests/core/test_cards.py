from unittest import TestCase, main
from unittest.mock import (
    patch,
    MagicMock
)
from pukr import get_logger
from cah.core.cards import Card


class TestCard(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('cah_test')

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
