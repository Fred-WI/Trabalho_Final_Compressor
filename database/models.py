"""
Módulo de Mapeamento Objeto-Relacional (ORM) do Sistema SCADA.

Este módulo define os esquemas de dados persistentes utilizando a biblioteca SQLAlchemy.
A arquitetura adota um modelo relacional para o registro de eventos de sistema e 
um padrão de tabela estreita (Entity-Attribute-Value / Time-Series Historian) para 
o armazenamento das grandezas físicas, permitindo a escalabilidade dinâmica das tags 
monitoradas sem a necessidade de migrações estruturais no esquema do banco de dados.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Event(Base):
    """
    Entidade representativa do log de eventos, falhas e comandos do sistema.

    Mapeia a estrutura de dados responsável por registrar alterações de estado lógico,
    acionamentos do operador e exceções de comunicação, servindo como base para 
    auditoria e diagnóstico operacional.

    Attributes:
        id (Column[Integer]): Chave primária autoincremental.
        timestamp (Column[DateTime]): Marca temporal da ocorrência do evento.
        type (Column[String]): Categoria lógica do evento (ex: 'erro', 'comando', 'info').
        description (Column[String]): Detalhamento em texto do evento registrado.

    Complexity:
        Tempo (Inserção): O(1)
        Tempo (Busca por id): O(1)
        Tempo (Busca por type/timestamp): O(N) - Ausência de índices secundários.
        Espaço: O(E), onde E é o número de eventos registrados.

    Pré-condições:
        O motor do banco de dados (Engine) deve estar instanciado e vinculado à `Base`.
    Pós-condições:
        Os objetos instanciados representam tuplas na tabela relacional `events`.
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # TODO: Substituir `datetime.now` por `datetime.utcnow` ou utilizar datetimes com fuso horário (timezone-aware) para prevenir inconsistências de ordenação temporal relativas a fusos locais e horário de verão.
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
    type = Column(String, nullable=False)
    description = Column(String, nullable=False)


class TagReading(Base):
    """
    Entidade de armazenamento de séries temporais (Historian Industrial).

    Implementa uma estrutura vertical (Entity-Attribute-Value) para o registro 
    de grandezas numéricas contínuas. A modelagem desacopla a representação no banco 
    de dados da quantidade de sensores físicos da planta, permitindo a adição de novas 
    tags no sistema SCADA sem alteração do esquema de colunas da tabela.

    Attributes:
        id (Column[Integer]): Chave primária autoincremental.
        timestamp (Column[DateTime]): Marca temporal da coleta do dado pelo controlador.
        tag_name (Column[String]): Identificador único da variável no processo (ex: 'co.pressao').
        value (Column[Float]): Valor numérico da grandeza no instante da leitura.

    Complexity:
        Tempo (Inserção via Bulk): O(1) amortizado por registro.
        Tempo (Busca por tag_name): O(log N) - Índice B-Tree ativo.
        Espaço: O(N), onde N é o volume total de leituras armazenadas.

    Pré-condições:
        O dicionário de conversão de tipos deve garantir que `value` seja estritamente flutuante.
    Pós-condições:
        Tuplas inseridas na tabela `tag_readings`, indexadas pela coluna `tag_name` para 
        otimização de consultas de filtragem no momento da plotagem de gráficos.
    """
    __tablename__ = "tag_readings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    # TODO: Adicionar índice (index=True) na coluna `timestamp`. Em arquiteturas de banco de dados do tipo Historian, consultas de séries temporais (range queries via datas) são predominantes. A ausência deste índice causa degradação de performance (O(N) full table scan) ao delimitar janelas de tempo nos gráficos.
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
    tag_name = Column(String, index=True, nullable=False) 
    value = Column(Float, nullable=False)