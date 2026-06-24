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


class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)

    pressao = Column(Float, default=0.0)
    torque = Column(Float, default=0.0)
    rotacao = Column(Float, default=0.0)
    vazao_fit02 = Column(Float, default=0.0)
    vazao_fit03 = Column(Float, default=0.0)
    temp_carc = Column(Float, default=0.0)
    pot_ativa = Column(Float, default=0.0)
    pot_reativa = Column(Float, default=0.0)
    pot_aparente = Column(Float, default=0.0)
