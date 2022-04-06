import re
from sqlalchemy import (
    Column,
    TIMESTAMP,
    Boolean,
    func
)
from sqlalchemy.ext.declarative import (
    declarative_base,
    declared_attr
)


class Base:

    @declared_attr
    def __table_args__(cls):
        """Sets the postgres schema for this model"""
        return {'schema': 'cah'}

    @declared_attr
    def __tablename__(cls):
        """Takes in a class name, sets the table name according to the class name, with some manipulation"""
        return '_'.join([x.lower() for x in re.findall(r'[A-Z][^A-Z]*', cls.__name__) if x != 'Table'])

    @declared_attr
    def created_date(self):
        return Column(TIMESTAMP, server_default=func.now())

    @declared_attr
    def update_date(self):
        return Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    @declared_attr
    def is_deleted(self):
        return Column(Boolean, default=False)


Base = declarative_base(cls=Base)
