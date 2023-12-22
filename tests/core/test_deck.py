from typing import Union
from unittest import (
    TestCase,
    main,
)
from unittest.mock import MagicMock

from pukr import get_logger

from cah.core.deck import Deck
from cah.model import (
    TableAnswerCard,
    TableDeck,
    TableQuestionCard,
)


class TestDeck(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = get_logger('deck_test')
        cls.n_answer_cards = 16
        cls.n_question_cards = 8

    def setUp(self) -> None:
        self.mock_eng = MagicMock(name='PSQLClient')
        self.mock_session = self.mock_eng.session_mgr.return_value.__enter__.return_value

        self.mock_session.query.return_value.filter.return_value.one_or_none = self._query_handler
        self.mock_session.query.return_value.filter.return_value.all.side_effect = self._query_handler
        self.mock_deck_combo = ['this', 'is', 'a', 'combooooooooooooooooooooooooooooooooooooooo']

        self.deck = Deck(deck_combo=self.mock_deck_combo, eng=self.mock_eng)
        self.mock_session.expunge_all.assert_called()

    def _query_handler(self, *args, **kwargs):
        select_tbl = self.mock_session.query.call_args.args
        if TableDeck in select_tbl:
            return [TableDeck(name=x) for x in self.mock_deck_combo]
        elif TableAnswerCard in select_tbl:
            return [TableAnswerCard(card_text=f'Test answer {i}.', deck_key=2) for i in range(self.n_answer_cards)]
        elif TableQuestionCard in select_tbl:
            return [TableQuestionCard(card_text=f'Test question {i}.', deck_key=2, responses_required=1)
                    for i in range(self.n_question_cards)]

    def test_num_answer_cards(self):
        self.assertEqual(self.n_answer_cards, len(self.deck.answers_card_list))
        self.assertEqual(self.n_answer_cards, self.deck.num_answer_cards)

    def test_num_question_cards(self):
        self.assertEqual(self.n_question_cards, len(self.deck.questions_card_list))
        self.assertEqual(self.n_question_cards, self.deck.num_question_cards)

    def test_shuffle(self):
        alist = self.deck.answers_card_list.copy()
        qlist = self.deck.questions_card_list.copy()
        self.deck.shuffle_deck()
        self.assertNotEqual(alist, self.deck.answers_card_list)
        self.assertNotEqual(qlist, self.deck.questions_card_list)

    def test_deal(self):
        instances = {
            'answer': TableAnswerCard,
            'question': TableQuestionCard,
        }
        for instance, tbl in instances.items():
            before = getattr(self.deck, f'{instance}s_card_list').copy()
            method = getattr(self.deck, f'deal_{instance}_card')
            card = method()  # type: Union[TableAnswerCard, TableQuestionCard]
            self.assertLess(len(getattr(self.deck, f'{instance}s_card_list')), len(before))
            self.assertNotIn(card, getattr(self.deck, f'{instance}s_card_list'))


if __name__ == '__main__':
    main()
