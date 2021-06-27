from sqlalchemy import Column, VARCHAR, Integer
# local imports
from .base import Base


class TableDecks(Base):
    """decks table"""
    __tablename__ = 'decks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(VARCHAR(50), unique=True, nullable=False)
    times_used = Column(Integer, default=0, nullable=False)
