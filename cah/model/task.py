from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    TIMESTAMP,
    VARCHAR
)
from sqlalchemy.sql import func
# local imports
from cah.model.base import Base


class TableTask(Base):
    """task table - for scheduling commands

    Attributes:
    """

    task_id = Column(Integer, primary_key=True, autoincrement=True)
    command = Column(VARCHAR(150), nullable=False, unique=True)
    from_timestamp = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    until_timestamp = Column(TIMESTAMP)
    last_triggered = Column(TIMESTAMP)
    trigger_every_n_minutes = Column(Integer, default=60, nullable=False)

    def __init__(self, command: str, from_timestamp: datetime = None, until: datetime = None,
                 trigger_every_n_minutes: int = 60):
        if from_timestamp is None:
            from_timestamp = datetime.now().replace(minute=0, second=0, microsecond=0)

        self.command = command
        self.from_timestamp = from_timestamp
        self.until_timestamp = until
        self.trigger_every_n_minutes = trigger_every_n_minutes

    def __repr__(self) -> str:
        return f'<TableTasks(type={self.command}, until={self.until_timestamp}, ' \
               f'every_n_mins={self.trigger_every_n_minutes})>'
