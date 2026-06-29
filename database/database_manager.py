"""
Módulo Gerenciador de Banco de Dados do Sistema SCADA.

Este módulo implementa a camada de persistência de dados (Historian), orquestrando 
a gravação de eventos e o armazenamento de séries temporais de telemetria. 
Utiliza o SQLAlchemy como ORM acoplado a um banco SQLite, adotando estratégias 
de concorrência (Locks) e processamento em lote (Bulk Insert) para sustentar 
altas taxas de amostragem sem bloqueio (deadlocks) ou degradação de I/O em disco.
"""

from datetime import datetime
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from database.models import Base, Event, TagReading
from controllers.config_load import load_tags

class DatabaseManager:
    """
    Controlador central de persistência e acesso a dados relacionais.

    Gerencia o ciclo de vida das sessões do banco de dados, mantém o buffer de 
    leituras de alta frequência na memória RAM e coordena o descarregamento 
    (flush) thread-safe para o armazenamento persistente.
    """

    def __init__(self, db_file="compressor_historian.db", tags_config_path='config/tags_compressor.json'):
        """
        Inicializa o motor relacional, os mapeamentos de tags e o buffer de memória.

        Lê o arquivo de configuração de tags para construir um mapa de colunas dinâmico 
        (`column_map`), filtrando estritamente as tags sinalizadas para retenção histórica.

        Args:
            db_file (str, opcional): Caminho ou nome do arquivo do banco SQLite. Padrão: "compressor_historian.db".
            tags_config_path (str, opcional): Caminho do arquivo JSON de configuração das tags. Padrão: 'config/tags_compressor.json'.

        Complexity:
            Tempo: O(T), onde T é o número de tags no arquivo JSON.
            Espaço: O(T) para o armazenamento do `column_map` e configurações carregadas.

        Pré-condições:
            O arquivo JSON referenciado deve existir e ser sintaticamente válido.
        Pós-condições:
            Motor SQLAlchemy instanciado. Tabelas geradas no banco de dados. Buffer e travas de concorrência (Locks) alocados na memória.
        """
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
            # Permite conexões multithread no SQLite (exige gestão rigorosa de sessões)
            connect_args={"check_same_thread": False}
        )

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False
        )

        self.create_tables()
        
        self._readings_buffer = []
        self._buffer_lock = threading.Lock()
        
        self._buffer_limit = 820  

    def create_tables(self):
        """
        Sincroniza os modelos mapeados em Python com o esquema do banco de dados.

        Invoca a metadata do SQLAlchemy para emitir os comandos DDL (Data Definition Language)
        necessários, criando tabelas inexistentes.

        Complexity:
            Tempo: O(1) relativo à chamada (delegado ao motor SQL). | Espaço: O(1).
        """
        Base.metadata.create_all(self.engine)

    def log_event(self, event_type, description):
        """
        Registra uma ocorrência discreta (evento) de forma síncrona no banco de dados.

        Abre uma transação dedicada, insere o objeto e consolida (commit). Em caso
        de falha, reverte a transação (rollback) para manter a integridade do banco.

        Args:
            event_type (str): Categoria ou classificação do evento (ex: 'alarme', 'sistema').
            description (str): Detalhamento em formato de texto sobre a ocorrência.

        Raises:
            SQLAlchemyError: Capturada internamente e logada no console, não repassada à thread principal.

        Complexity:
            Tempo: O(1) amortizado. | Espaço: O(1).

        Pré-condições:
            Motor de banco de dados ativo e schema `events` criado.
        Pós-condições:
            Novo registro permanente na tabela de eventos. A sessão SQL é encerrada.
        """
        session = self.SessionLocal()
        try:
            # TODO: A utilização de `datetime.now()` insere timestamps com fuso horário local não explícito. Recomenda-se a adoção de `datetime.utcnow()` para garantir a ordenação linear global (UTC) e consistência da série temporal.
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
        Processa as leituras das tags, filtra entidades armazenáveis e empacota no buffer RAM.

        Avalia o dicionário de valores de tempo real contra os metadados. Caso a tag possua 
        a flag `save_history` ativada, converte para a classe modelo `TagReading` e a adiciona
        ao buffer protegido por trava (lock). Dispara a escrita em massa no disco caso o 
        limite predefinido seja atingido.

        Args:
            tags_values (dict): Dicionário contendo os pares chave-valor `{'nome_tag': valor}` atuais.
            tags_definitions (dict): Dicionário contendo os metadados estruturais das tags.

        Complexity:
            Tempo: O(V), onde V é o número de chaves em `tags_values`.
            Espaço: O(V) temporário para a lista `readings_to_add`.

        Pré-condições:
            `tags_values` e `tags_definitions` devem ser dicionários válidos.
        Pós-condições:
            Buffer `_readings_buffer` incrementado. Possível operação de I/O efetuada 
            caso o limiar de limite seja excedido.
        """
        try:
            current_time = datetime.now()
            readings_to_add = []

            for tag_name, value in tags_values.items():
                tag_def = tags_definitions.get(tag_name)
                
                if tag_def and tag_def.get("save_history") is True:
                    readings_to_add.append(TagReading(
                        timestamp=current_time,
                        tag_name=tag_name,
                        value=float(value)
                    ))

            needs_flush = False  
            
            with self._buffer_lock:
                self._readings_buffer.extend(readings_to_add)
                if len(self._readings_buffer) >= self._buffer_limit:
                    needs_flush = True
            
            if needs_flush:
                self.flush_readings()
                    
        # TODO: O uso de captura genérica de exceções genérica (Exception) mascara anomalias lógicas (como TypeError ou falhas de memória), limitando a visibilidade no caso de corrupção dos dados de entrada.
        except Exception as e:
            print(f"Erro ao filtrar e gravar leituras: {e}")

    def flush_readings(self):
        """
        Descarrega os registros contidos no buffer da RAM para o banco de dados em disco.

        Utiliza a rotina de inserção em massa (`bulk_save_objects`) do SQLAlchemy,
        minimizando o overhead de processamento de consultas (query parsing) e 
        transações de rede. 

        Complexity:
            Tempo: O(B), onde B é a quantidade atual de registros no buffer.
            Espaço: O(B) para a alocação da cópia da lista e empacotamento SQL.

        Pré-condições:
            Instância e sessão do ORM ativas.
        Pós-condições:
            Buffer de leitura `_readings_buffer` esvaziado. Dados consolidados (committed) no SQLite.
        """
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
        """
        Consulta séries temporais armazenadas para uma variável de processo específica.

        Resolve identificadores descritivos de UI para a chave correspondente no banco. 
        Opera em dois regimes: 
        1. Consulta com intervalo fechado (ascendente).
        2. Consulta aberta limitando as 600 observações mais recentes (para gráficos de visão integral).

        Args:
            variable (str): Descrição ou nome da tag utilizada como chave de busca.
            start_date (datetime, opcional): Limite temporal inferior.
            end_date (datetime, opcional): Limite temporal superior.

        Returns:
            list[tuple]: Lista contendo tuplas no formato `(timestamp_formatado, valor_float)`.

        Complexity:
            Tempo: O(N log N) onde N é a quantidade de linhas recuperadas, dado o passo de ordenação. 
                   Cai para O(L) se utilizando limite (L=600).
            Espaço: O(N) para retenção dos resultados na memória.
        """
        
        session = self.SessionLocal()
        try:
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
            
            else:
                query = query.order_by(TagReading.timestamp.desc()).limit(600)
                readings = query.all()
                # TODO: O uso de `.reverse()` na aplicação onera memória e processamento em listas longas [Complexidade O(N)]. A ordenação cronológica primária poderia ser resolvida através de sub-consultas estruturadas diretamente no SQL.
                readings.reverse()
                return [(ts.strftime("%Y-%m-%d %H:%M:%S"), val) for ts, val in readings]
        finally:
            session.close()

    def query_table(self, table_name, limit=100):
        """
        Recupera os registros tabulares para renderização na interface (DataGrid).

        Força o esvaziamento do buffer de RAM (flush) antes da execução para assegurar 
        propriedades ACID e garantir a exibição dos dados atualizados até a última iteração.

        Args:
            table_name (str): O identificador da tabela alvo ("events" ou "readings").
            limit (int, opcional): Restrição no total de linhas recuperadas. Padrão: 100.

        Returns:
            tuple(list, list): Tupla contendo os dados empacotados (lista de tuplas) 
                               e a declaração de cabeçalhos (lista de strings).

        Complexity:
            Tempo: O(L) onde L é o limite da query (Limit parameter). 
                   Soma-se O(B) referente à operação prévia de descarregamento do buffer.
            Espaço: O(L) para armazenar os registros lidos no formato da UI.
        """
        self.flush_readings() 
        
        session = self.SessionLocal()
        try:
            if table_name == "events":
                rows = session.query(Event).order_by(Event.timestamp.desc()).limit(limit).all()
                headers = ["id", "timestamp", "type", "description"]
                data = [(row.id, row.timestamp.strftime("%Y-%m-%d %H:%M:%S"), row.type, row.description) for row in rows]
                return data, headers

            if table_name == "readings":
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
        """
        Realiza consulta paramétrica ao histórico de eventos do sistema.

        Fornece capacidade de filtragem pontual baseada na tipologia do log 
        (ex: "Comando", "Erro").

        Args:
            event_type (str, opcional): Filtro lógico para buscar a coluna `type`. 
                                        Se "Todos", ignora a condição WHERE.
            limit (int, opcional): Restrição máxima de amostras recuperadas. Padrão: 100.

        Returns:
            list[tuple]: Uma lista formatada ordenada de ocorrências.

        Complexity:
            Tempo: O(N) onde N é a proporção rastreada na tabela, truncada pelo limite estrito O(L).
            Espaço: O(L).
        """
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