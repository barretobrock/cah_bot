from unittest import TestCase
from unittest.mock import (
    patch,
    MagicMock
)
from loguru import logger
from cah.core.cards import Card


class TestCard(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = logger

    def test_init(self):
        txt = 'test'
        cid = 2398
        card = Card(txt=txt, card_id=cid)

        self.assertEqual(txt, card.txt)
        self.assertEqual(cid, card.id)
