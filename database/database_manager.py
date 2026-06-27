from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from database.models import Base, Event, Reading


class DatabaseManager:
    def __init__(self, db_file="compressor_data_v1.db"):
        self.db_file = db_file

        self.engine = create_engine(
            f"sqlite:///{db_file}",
            echo=False,
            connect_args={"check_same_thread": False}
        )

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False
        )

        self.column_map = {
            "Pressão": "pressao",
            "Torque": "torque",
            "Rotação": "rotacao",
            "Vazão FIT-02": "vazao_fit02",
            "Vazão FIT-03": "vazao_fit03",
            "Temperatura": "temp_carc",
            "Potência Ativa": "pot_ativa",
            "Potência Reativa": "pot_reativa",
            "Potência Aparente": "pot_aparente",
        }

        self.create_tables()

    def create_tables(self):
        Base.metadata.create_all(self.engine)

    def log_event(self, event_type, description):
        session = self.SessionLocal()
        try:
            event = Event(
                timestamp=datetime.now(),
                type=str(event_type).lower(),
                description=str(description)
            )
            session.add(event)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Failed to log event: {e}")
        finally:
            session.close()

    def log_reading(self, tags):
        session = self.SessionLocal()
        try:
            reading = Reading(
                timestamp=datetime.now(),
                pressao=float(tags.get("co.pressao", 0)),
                torque=float(tags.get("co.torque", 0)),
                rotacao=float(tags.get("co.encoder", 0)),
                vazao_fit02=float(tags.get("co.fit02", 0)),
                vazao_fit03=float(tags.get("co.fit03", 0)),
                temp_carc=float(tags.get("co.temp_carc", 0)),
                pot_ativa=float(tags.get("co.ativa_total", 0)),
                pot_reativa=float(tags.get("co.reativa_total", 0)),
                pot_aparente=float(tags.get("co.aparente_total", 0)),
            )
            session.add(reading)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Failed to log reading: {e}")
        finally:
            session.close()

    def query_events(self, event_type="Todos", limit=100):
        session = self.SessionLocal()
        try:
            query = session.query(Event)
            if event_type and event_type != "Todos":
                query = query.filter(Event.type == str(event_type).lower())
            events = query.order_by(Event.timestamp.desc()).limit(limit).all()
            return [
                (
                    event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    event.type,
                    event.description
                )
                for event in events
            ]
        finally:
            session.close()

    def query_readings(self, variable, start_date=None, end_date=None):
        session = self.SessionLocal()
        try:
            db_column = self.column_map.get(variable, "pressao")
            column_attr = getattr(Reading, db_column)
            query = session.query(Reading.timestamp, column_attr)

            if start_date and end_date:
                query = query.filter(
                    Reading.timestamp >= start_date,
                    Reading.timestamp <= end_date
                )

            readings = query.order_by(Reading.timestamp.asc()).all()

            return [
                (
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    value
                )
                for timestamp, value in readings
            ]
        finally:
            session.close()

    def query_table(self, table_name, limit=100):
        session = self.SessionLocal()
        try:
            if table_name == "events":
                rows = session.query(Event).order_by(Event.timestamp.desc()).limit(limit).all()
                headers = ["id", "timestamp", "type", "description"]
                data = [
                    (
                        row.id,
                        row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        row.type,
                        row.description
                    )
                    for row in rows
                ]
                return data, headers

            if table_name == "readings":
                rows = session.query(Reading).order_by(Reading.timestamp.desc()).limit(limit).all()
                headers = [
                    "id",
                    "timestamp",
                    "pressao",
                    "torque",
                    "rotacao",
                    "vazao_fit02",
                    "vazao_fit03",
                    "temp_carc",
                    "pot_ativa",
                    "pot_reativa",
                    "pot_aparente",
                ]
                data = [
                    (
                        row.id,
                        row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        row.pressao,
                        row.torque,
                        row.rotacao,
                        row.vazao_fit02,
                        row.vazao_fit03,
                        row.temp_carc,
                        row.pot_ativa,
                        row.pot_reativa,
                        row.pot_aparente,
                    )
                    for row in rows
                ]
                return data, headers

            return [], []
        finally:
            session.close()
