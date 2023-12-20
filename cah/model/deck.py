from sqlalchemy import (
    VARCHAR,
    Column,
    Integer,
)

# local imports
from cah.model.base import Base


class TableDeck(Base):
    """decks table"""

    deck_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(VARCHAR(50), unique=True, nullable=False)
    times_used = Column(Integer, default=0, nullable=False)

    def __init__(self, name: str, deck_id: int = None):
        self.name = name
        self.deck_id = deck_id

    def __repr__(self) -> str:
        return f'<TableDeck(id={self.deck_id}, name={self.name})>'
