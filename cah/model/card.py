from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Text
)
from sqlalchemy.orm import relationship
# local imports
from cah.model.base import Base


class TableAnswerCard(Base):
    """answer card table"""
    answer_card_id = Column(Integer, primary_key=True, autoincrement=True)
    deck_key = Column(Integer, ForeignKey('cah.deck.deck_id'), nullable=False)
    deck = relationship('TableDeck', backref='answer_cards')
    card_text = Column(Text, nullable=False)
    times_drawn = Column(Integer, default=0, nullable=False)
    times_picked = Column(Integer, default=0, nullable=False)
    times_burned = Column(Integer, default=0, nullable=False)
    times_chosen = Column(Integer, default=0, nullable=False)

    def __init__(self, card_text: str, deck_key: int):
        self.card_text = card_text
        self.deck_key = deck_key

    def __repr__(self) -> str:
        return f'<TableAnswerCard(id={self.answer_card_id}, deck_key={self.deck_key} text={self.card_text[:20]})>'


class TableQuestionCard(Base):
    """question card table"""

    question_card_id = Column(Integer, primary_key=True, autoincrement=True)
    deck_key = Column(Integer, ForeignKey('cah.deck.deck_id'), nullable=False)
    deck = relationship('TableDeck', backref='question_cards')
    card_text = Column(Text, nullable=False)
    responses_required = Column(Integer, default=1, nullable=False)
    times_drawn = Column(Integer, default=0, nullable=False)

    def __init__(self, card_text: str, deck_key: int, responses_required: int):
        self.card_text = card_text
        self.deck_key = deck_key
        self.responses_required = responses_required

    def __repr__(self) -> str:
        return f'<TableQuestionCard(id={self.question_card_id}, deck_key={self.deck_key} ' \
               f'text={self.card_text[:20]})>'
