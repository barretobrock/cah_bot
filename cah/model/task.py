from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    VARCHAR,
    Column,
    ForeignKey,
    Integer,
)
from sqlalchemy.sql import func

# local imports
from cah.model.base import Base


class TableTask(Base):
    """task table - for scheduling commands

    Attributes:
    """

    task_id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(VARCHAR(150), nullable=False, unique=True)
    from_timestamp = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    until_timestamp = Column(TIMESTAMP)
    last_triggered = Column(TIMESTAMP)
    trigger_every_n_minutes = Column(Integer, default=60, nullable=False)

    def __init__(self, endpoint: str, from_timestamp: datetime = None, until: datetime = None,
                 trigger_every_n_minutes: int = 60):
        if from_timestamp is None:
            from_timestamp = datetime.now().replace(minute=0, second=0, microsecond=0)

        self.endpoint = endpoint
        self.from_timestamp = from_timestamp
        self.until_timestamp = until
        self.trigger_every_n_minutes = trigger_every_n_minutes

    def __repr__(self) -> str:
        return f'<TableTask(endpoint={self.endpoint}, until={self.until_timestamp}, ' \
               f'every_n_mins={self.trigger_every_n_minutes})>'


class TableTaskParameter(Base):
    """task_parameter table - for adding params to scheduled commands

    Attributes:
    """

    task_attr_id = Column(Integer, primary_key=True, autoincrement=True)
    task_key = Column(ForeignKey('cah.task.task_id'))
    parameter_name = Column(VARCHAR(150), nullable=False, unique=True)
    value_str = Column(VARCHAR(150))
    value_int = Column(Integer)

    def __init__(self, parameter_name: str, task_key: int = None, value_str: str = None, value_int: int = None):
        self.task_key = task_key
        self.parameter_name = parameter_name
        self.value_str = value_str
        self.value_int = value_int

    def __repr__(self) -> str:
        return f'<TableTaskParameter(param={self.parameter_name}, value_str={self.value_str}, ' \
               f'value_int={self.value_int})>'
