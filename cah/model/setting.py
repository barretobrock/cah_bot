import enum
from sqlalchemy import (
    Column,
    Integer,
    Enum
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


class TableSetting(Base):
    """setting table - for storing global bot settings

    Attributes:
    """

    setting_id = Column(Integer, primary_key=True, autoincrement=True)
    setting_type = Column(Enum(SettingType), nullable=False)
    setting_int = Column(Integer, nullable=False)

    def __init__(self, setting_type: SettingType, setting_int: int = 1):
        self.setting_type = setting_type
        self.setting_int = setting_int

    def __repr__(self) -> str:
        return f'<TableSetting(name={self.setting_type.name}, val={self.setting_int})>'
