import enum

from sqlalchemy import (
    VARCHAR,
    Column,
    Enum,
    Integer,
)

# local imports
from cah.model.base import Base


class RipType(enum.Enum):
    DECKNUKE = enum.auto()
    END_ROUND = enum.auto()
    START_ROUND = enum.auto()
    NEW_GAME = enum.auto()
    PLAYER_KICK = enum.auto()


class TableRip(Base):
    """rip table - for storing rips the bot might make at others

    Attributes:
    """

    rip_id = Column(Integer, primary_key=True, autoincrement=True)
    rip_type = Column(Enum(RipType), nullable=False)
    text = Column(VARCHAR(300), nullable=True)

    def __init__(self, rip_type: RipType, text: str):
        self.rip_type = rip_type
        self.text = text

    def __repr__(self) -> str:
        return f'<TableRip(type={self.rip_type.name}, text={self.text})>'
