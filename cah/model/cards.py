from sqlalchemy import Column, Integer, ForeignKey, Text
# local imports
from .base import Base


class TableAnswerCards(Base):
    """answer cards table"""
    __tablename__ = 'answer_cards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    deck_id = Column(Integer, ForeignKey('decks.id'), nullable=False)
    card_text = Column(Text, nullable=False)
    times_drawn = Column(Integer, default=0, nullable=False)
    times_picked = Column(Integer, default=0, nullable=False)
    times_burned = Column(Integer, default=0, nullable=False)
    times_chosen = Column(Integer, default=0, nullable=False)


class TableQuestionCards(Base):
    """question cards table"""
    __tablename__ = 'question_cards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    deck_id = Column(Integer, ForeignKey('decks.id'), nullable=False)
    responses_required = Column(Integer, default=1, nullable=False)
    card_text = Column(Text, nullable=False)
    times_drawn = Column(Integer, default=0, nullable=False)
    times_picked = Column(Integer, default=0, nullable=False)
    times_chosen = Column(Integer, default=0, nullable=False)
