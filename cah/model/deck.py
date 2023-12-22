from sqlalchemy import (
    VARCHAR,
    Column,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship

# local imports
from cah.model.base import Base


class TableDeckGroup(Base):
    """deck_group table"""
    deck_group_id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(VARCHAR(50), unique=True, nullable=False)
    decks = relationship('TableDeck', back_populates='deck_group')
    n_answers = Column(Integer, default=0, nullable=False)
    n_questions = Column(Integer, default=0, nullable=False)
    times_used = Column(Integer, default=0, nullable=False)

    def __init__(self, group_name: str):
        self.group_name = group_name

    def __repr__(self) -> str:
        return f'<TableDeckGroup(id={self.deck_group_id}, name={self.group_name})>'


class TableDeck(Base):
    """decks table"""

    deck_id = Column(Integer, primary_key=True, autoincrement=True)
    deck_group_key = Column(ForeignKey(TableDeckGroup.deck_group_id), nullable=True)
    deck_group = relationship('TableDeckGroup', back_populates='decks')
    name = Column(VARCHAR(50), unique=True, nullable=False)
    n_answers = Column(Integer, default=0, nullable=False)
    n_questions = Column(Integer, default=0, nullable=False)
    times_used = Column(Integer, default=0, nullable=False)

    def __init__(self, name: str, n_answers: int = 0, n_questions: int = 0, deck_group: TableDeckGroup = None):
        self.name = name
        self.n_answers = n_answers
        self.n_questions = n_questions
        if deck_group is not None:
            self.deck_group = deck_group

    def __repr__(self) -> str:
        return f'<TableDeck(id={self.deck_id}, name={self.name})>'
