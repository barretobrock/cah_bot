import enum

from sqlalchemy import (
    VARCHAR,
    Column,
    Enum,
    Integer,
)

# local imports
from cah.model.base import Base


class SettingType(enum.Enum):
    IS_ANNOUNCE_STARTUP = enum.auto()
    IS_ANNOUNCE_SHUTDOWN = enum.auto()
    IS_POST_ERR_TRACEBACK = enum.auto()
    IS_PING_WINNER = enum.auto()
    IS_PING_JUDGE = enum.auto()
    DECKNUKE_PENALTY = enum.auto()
    IS_LOOK_FOR_ONGOING_GAMES = enum.auto()
    JUDGE_ORDER_DIVIDER = enum.auto()
    JUDGE_ORDER = enum.auto()


class TableSetting(Base):
    """setting table - for storing global bot settings

    Attributes:
    """

    setting_id = Column(Integer, primary_key=True, autoincrement=True)
    setting_type = Column(Enum(SettingType), nullable=False)
    setting_int = Column(Integer, nullable=True)
    setting_str = Column(VARCHAR(300), nullable=True)

    def __init__(self, setting_type: SettingType, setting_int: int = None, setting_str: str = None):
        self.setting_type = setting_type
        self.setting_int = setting_int
        self.setting_str = setting_str

    def __repr__(self) -> str:
        return f'<TableSetting(name={self.setting_type.name}, int={self.setting_int}, str={self.setting_str})>'
