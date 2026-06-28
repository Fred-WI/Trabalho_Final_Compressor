from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
    type = Column(String, nullable=False)
    description = Column(String, nullable=False)


class TagReading(Base):
    __tablename__ = "tag_readings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
    tag_name = Column(String, index=True, nullable=False) 
    value = Column(Float, nullable=False)