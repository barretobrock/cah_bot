from random import shuffle
from typing import (
    List,
    Type,
    Union
)
from sqlalchemy.sql import (
    and_,
    not_
)
from cah.db_eng import WizzyPSQLClient
from cah.model import (
    TableAnswerCard,
    TableDeck,
    TableQuestionCard
)


class Deck:
    """Deck of question and answer cards for a game"""
    def __init__(self, name: str, eng: WizzyPSQLClient):
        self.name = name
        self.eng = eng
        # Read in questions and answers
        with self.eng.session_mgr() as session:
            tbl_deck = session.query(TableDeck).filter(and_(
                TableDeck.name == name,
                not_(TableDeck.is_deleted)
            )).one_or_none()
            self.deck_id = tbl_deck.deck_id
            qcards = session.query(TableQuestionCard).filter(and_(
                    TableQuestionCard.deck_key == self.deck_id,
                    not_(TableQuestionCard.is_deleted)
                )).all()
            acards = session.query(TableAnswerCard).filter(and_(
                    TableAnswerCard.deck_key == self.deck_id,
                    not_(TableAnswerCard.is_deleted)
                )).all()
            session.expunge_all()

            self.questions_card_list = qcards   # type: List[TableQuestionCard]
            self.answers_card_list = acards     # type: List[TableAnswerCard]

    @property
    def num_answer_cards(self) -> int:
        return len(self.answers_card_list)

    @property
    def num_question_cards(self) -> int:
        return len(self.questions_card_list)

    def shuffle_deck(self):
        """Shuffles the deck"""
        shuffle(self.questions_card_list)
        shuffle(self.answers_card_list)

    def deal_answer_card(self) -> TableAnswerCard:
        """Deals an answer card in the deck."""
        card: TableAnswerCard
        card = self._deal_card(tbl=TableAnswerCard)
        return card

    def deal_question_card(self) -> TableQuestionCard:
        """Deals a question card in the deck."""
        card: TableQuestionCard
        card = self._deal_card(tbl=TableQuestionCard)
        return card

    def _deal_card(self, tbl: Type[Union[TableAnswerCard, TableQuestionCard]]) -> \
            Union[TableAnswerCard, TableQuestionCard]:
        """Deals either a question or answer card and counts their times drawn"""
        if tbl.__tablename__ == 'answer_card':
            card = self.answers_card_list.pop(0)
            id_attr = TableAnswerCard.answer_card_id
            drawn_attr = TableAnswerCard.times_drawn
            card_id = card.answer_card_id
        elif tbl.__tablename__ == 'question_card':
            card = self.questions_card_list.pop(0)
            id_attr = TableQuestionCard.question_card_id
            drawn_attr = TableQuestionCard.times_drawn
            card_id = card.question_card_id
        else:
            raise ValueError(f'Unaccounted for table provided: {tbl}')
        with self.eng.session_mgr() as session:
            # Increment the times drawn attribute
            session.query(tbl).filter(
                id_attr == card_id
            ).update({
                drawn_attr: drawn_attr + 1
            })
        return card
