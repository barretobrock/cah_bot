"""Card tests"""
import unittest
from cah.cards import AnswerCard, QuestionCard


class TestQuestionCards(unittest.TestCase):
    def setUp(self) -> None:
        question_list = [
            'This ___ needs one answer',
            'No blanks should be a single answer.',
            'Cards having only one _',
            'Two _ answer _ blanks',
            '___ One at the front'
        ]
        question_list_with_reqs = [
            ('This ___ needs one answer', 1),
            ('Duplicate', 1),
            ('Duplicate', 3),
            ('Duplicate', 1),
            ('Duplicate', 2),
        ]

        self.qcards1 = [QuestionCard(x) for x in question_list]
        self.qcards2 = [QuestionCard(x, y) for x, y in question_list_with_reqs]

    def test_questions(self):
        self.assertEqual([x.required_answers for x in self.qcards1], [1, 1, 1, 2, 1])
        self.assertEqual([x.required_answers for x in self.qcards2], [1, 1, 3, 1, 2])
