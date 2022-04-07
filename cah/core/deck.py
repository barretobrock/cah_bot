from random import shuffle
from cah.db_eng import WizzyPSQLClient
from cah.model import (
    TableAnswerCard,
    TableDeck,
    TableQuestionCard
)
from cah.core.cards import (
    AnswerCard,
    QuestionCard
)


class Deck:
    """Deck of question and answer cards for a game"""
    def __init__(self, name: str, eng: WizzyPSQLClient):
        self.name = name
        self.eng = eng
        self.questions_card_list = list()
        # Read in cards to deck
        # Read in questions and answers
        with self.eng.session_mgr() as session:
            qcards, acards = session.query(TableQuestionCard, TableAnswerCard).\
                join(TableDeck, TableDeck.deck_id == TableQuestionCard.deck_key).\
                join(TableDeck, TableDeck.deck_id == TableAnswerCard.deck_key).filter(
                    TableDeck.name == name
                ).all()

            self.questions_card_list = [QuestionCard(q.card_text, q.question_card_id) for q in qcards]
            self.answers_card_list = [AnswerCard(a.card_text, a.answer_card_id,) for a in acards]

    @property
    def num_answer_cards(self):
        return len(self.answers_card_list)

    @property
    def num_question_cards(self):
        return len(self.questions_card_list)

    def shuffle_deck(self):
        """Shuffles the deck"""
        shuffle(self.questions_card_list)
        shuffle(self.answers_card_list)

    def deal_answer_card(self) -> AnswerCard:
        """Deals an answer card in the deck."""
        card = self.answers_card_list.pop(0)
        # Increment the card usage by one
        with self.eng.session_mgr() as session:
            session.query(TableAnswerCard).filter(
                TableAnswerCard.answer_card_id == card.id
            ).update({
                TableAnswerCard.times_drawn: TableAnswerCard.times_drawn + 1
            })
        return card

    def deal_question_card(self) -> QuestionCard:
        """Deals a question card in the deck."""
        card = self.questions_card_list.pop(0)
        # Increment the card usage by one
        with self.eng.session_mgr() as session:
            session.query(TableQuestionCard).filter(
                TableQuestionCard.question_card_id == card.id
            ).update({
                TableQuestionCard.times_drawn: TableQuestionCard.times_drawn + 1
            })
        return card
