from datetime import datetime
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from database.models import Base, Event, TagReading
from controllers.config_load import load_tags

class DatabaseManager:
    def __init__(self, db_file="compressor_historian.db", tags_config_path='config/tags_compressor.json'):
        self.db_file = db_file

        self.tags_config = load_tags(tags_config_path)

        self.column_map = {
            info["descricao"] or tag_name: tag_name 
            for tag_name, info in self.tags_config.items() 
            if info.get("save_history") is True
        }

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

        self.create_tables()
        
        # Buffer de Alta Performance
        self._readings_buffer = []
        self._buffer_lock = threading.Lock()
        
        # Como gravamos ~82 tags por segundo, vamos descarregar no banco a cada 820 registros (10 segundos)
        self._buffer_limit = 820  

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

    def log_reading(self, tags_values, tags_definitions):
        """
        tags_values: o dicionário com os valores atuais (ex: {'co.pressao': 5.2, ...})
        tags_definitions: o dicionário que carregamos do tags_compressor.json
        """
        try:
            current_time = datetime.now()
            readings_to_add = []

            for tag_name, value in tags_values.items():
                # Busca a definição desta tag no JSON
                tag_def = tags_definitions.get(tag_name)
                
                # SÓ SALVA se a tag existir E o save_history for True
                if tag_def and tag_def.get("save_history") is True:
                    readings_to_add.append(TagReading(
                        timestamp=current_time,
                        tag_name=tag_name,
                        value=float(value)
                    ))

            with self._buffer_lock:
                self._readings_buffer.extend(readings_to_add)
                if len(self._readings_buffer) >= self._buffer_limit:
                    self.flush_readings()
                    
        except Exception as e:
            print(f"Erro ao filtrar e gravar leituras: {e}")

    def flush_readings(self):
        """Descarrega o buffer no SQLite via Bulk Insert (Ultra rápido)"""
        with self._buffer_lock:
            if not self._readings_buffer: return
            data_to_insert = self._readings_buffer.copy()
            self._readings_buffer.clear()

        session = self.SessionLocal()
        try:
            session.bulk_save_objects(data_to_insert)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            print(f"Falha ao descarregar buffer no banco: {e}")
        finally:
            session.close()

    # ==========================================
    # CONSULTAS PARA OS GRÁFICOS DO KIVY
    # ==========================================

    def query_readings(self, variable, start_date=None, end_date=None):
        self.flush_readings()
        
        session = self.SessionLocal()
        try:
            # Pega o nome real da tag através do nosso novo mapa
            tag_name = self.column_map.get(variable, variable)
            
            query = session.query(TagReading.timestamp, TagReading.value)\
                           .filter(TagReading.tag_name == tag_name)

            if start_date and end_date:
                query = query.filter(
                    TagReading.timestamp >= start_date,
                    TagReading.timestamp <= end_date
                )

            readings = query.order_by(TagReading.timestamp.asc()).all()

            return [(ts.strftime("%Y-%m-%d %H:%M:%S"), val) for ts, val in readings]
        finally:
            session.close()

    def query_table(self, table_name, limit=100):
        """
        Consulta as tabelas dinamicamente para exibição na UI.
        """
        self.flush_readings() # Garante que os dados em buffer foram pro disco
        
        session = self.SessionLocal()
        try:
            if table_name == "events":
                rows = session.query(Event).order_by(Event.timestamp.desc()).limit(limit).all()
                headers = ["id", "timestamp", "type", "description"]
                data = [(row.id, row.timestamp.strftime("%Y-%m-%d %H:%M:%S"), row.type, row.description) for row in rows]
                return data, headers

            if table_name == "readings":
                # Nova busca na tabela Historian (TagReading)
                rows = session.query(TagReading).order_by(TagReading.timestamp.desc()).limit(limit).all()
                headers = ["id", "timestamp", "tag_name", "value"]
                data = [
                    (
                        row.id,
                        row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        row.tag_name,
                        row.value
                    )
                    for row in rows
                ]
                return data, headers

            return [], []
        finally:
            session.close()
    
    def query_events(self, event_type="Todos", limit=100):
        """Busca os logs de eventos (erros, comandos) no banco."""
        session = self.SessionLocal()
        try:
            query = session.query(Event)
            if event_type and event_type != "Todos":
                query = query.filter(Event.type == str(event_type).lower())
            
            # Ordena pelos mais recentes
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