"""Módulo de interface para visualização do histórico de eventos do sistema.

Integra os componentes visuais do framework Kivy para apresentar registros
recuperados de um banco de dados local. Implementa filtragem categórica
para facilitar a análise de anomalias, comandos e alertas registrados
ao longo do tempo.
"""

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import sp
from datetime import datetime, timedelta
import os
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

try:
    from kivy_garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
    KIVY_GARDEN_AVAILABLE = True
except ImportError:
    KIVY_GARDEN_AVAILABLE = False

from config import CORES, ICON_FONT
from ui.custom_widgets import HoverButton, IconButton, ValueIndicator
from ui.base_screen import BaseScreen

class HistoricoScreen(BaseScreen):
    """Tela de apresentação do log histórico de operações e falhas.
    
    Gerencia o layout de rolagem e a conexão entre a seleção do usuário 
    (filtro categórico) e o modelo de dados subjacente persistido na base.
    """

    def __init__(self, **kwargs):
        """Inicializa a estrutura da tela e os controles de filtragem.
        
        Monta a hierarquia de widgets, estabelece o painel de controle com o 
        componente Spinner para seleção de tipos de eventos e cria o contêiner 
        de rolagem (ScrollView) para os registros.
        
        Args:
            **kwargs: Dicionário de argumentos nomeados repassados para a classe mãe (BaseScreen).
            
        Pre-condições:
            O dicionário global CORES deve estar previamente carregado.
            
        Pós-condições:
            A árvore de widgets fica preparada na memória, e o evento de alteração
            do Spinner fica vinculado ao método de recarregamento.
            
        Complexity:
            Tempo: O(1)
            Espaço: O(1)
        """
        # TODO: Refatorar múltiplas instruções na mesma linha separadas por ponto e vírgula para adequação ao padrão PEP 8.
        super().__init__(**kwargs); self.name = 'historico'; self.add_header("Histórico de Eventos")
        controls = BoxLayout(size_hint_y=None, height=sp(50), padding=10, spacing=10)
        # TODO: Refatorar múltiplas instruções na mesma linha separadas por ponto e vírgula.
        self.spinner_type = Spinner(text='Todos', values=('Todos', 'Sistema', 'Erro', 'Comando', 'Alerta'), background_color=CORES['primaria']); self.spinner_type.bind(text=self.load_events)
        controls.add_widget(Label(text="Filtrar por tipo:"))
        controls.add_widget(self.spinner_type)
        self.root_layout.add_widget(controls)
        self.scroll_view = ScrollView()
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=5, padding=5)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll_view.add_widget(self.grid)
        self.root_layout.add_widget(self.scroll_view)
        
    def on_enter(self, *args):
        """Hook de ciclo de vida disparado ao focar a tela.
        
        Garante que os dados apresentados correspondam ao estado atual do 
        banco de dados sempre que o usuário acessar a tela.
        
        Args:
            *args: Argumentos variáveis passados pelo gerenciador de telas do Kivy.
        """
        # TODO: Refatorar instrução na mesma linha da declaração da função para adequação à PEP 8.
        self.load_events()
    
    def load_events(self, *args):
        """Requisita, processa e renderiza os eventos na interface visual.
        
        Efetua a limpeza do contêiner atual, consulta o banco de dados filtrando 
        pelo valor ativo no componente Spinner e instancia componentes de texto 
        (Label) formatados com marcadores de cores baseados na gravidade do evento.
        
        Args:
            *args: Argumentos variáveis gerados por eventos de binding da interface.
            
        Pre-condições:
            A conexão com o banco de dados (App.get_running_app().db) deve estar ativa.
            
        Pós-condições:
            O contêiner 'self.grid' é preenchido com instâncias de Label representativas
            das tuplas retornadas pelo banco.
            
        Raises:
            ValueError: Se a string de data retornada pelo banco não for compatível 
                        com a formatação especificada em strptime.
                        
        Complexity:
            Tempo: O(n) onde n é o número de registros retornados (limitado pela constante 200).
            Espaço: O(n) referente à alocação das referências dos widgets na memória da árvore do Kivy.
        """
        self.grid.clear_widgets()

        # TODO: Delegar I/O de rede/disco para thread secundária. A chamada bloqueante 'query_events' na main thread degrada o tempo de resposta da interface gráfica (stuttering).
        events = App.get_running_app().db.query_events(event_type=self.spinner_type.text, limit=200)
        
        # TODO: Instanciar dinamicamente até 200 instâncias de Label e adicioná-las ao GridLayout acarreta processamento síncrono intensivo no renderizador Kivy. Recomenda-se a adoção de RecycleView para virtualização da lista.
        for ts, etype, desc in events:
            # TODO: Potencial desajuste de chaves no dicionário. O backend pode retornar 'etype' incompatível com as chaves predefinidas, forçando todas as anomalias para 'CORES['texto']'.
            color = {'erro': CORES['erro'], 'sistema': CORES['info'], 'comando': CORES['alerta'], 'alerta': CORES['alerta']}.get(etype, CORES['texto'])
            # TODO: Encapsular parsing temporal em bloco try-except. Inconsistências de gravação na base (formato diferente de YYYY-MM-DD HH:MM:SS) levantarão um ValueError fatal, abortando o processamento do restante da tela.
            ts_obj = datetime.strptime(ts.split('.')[0], '%Y-%m-%d %H:%M:%S')
            event_label = Label(text=f"[b]{ts_obj.strftime('%d/%m/%Y %H:%M:%S')} [/b] | [{etype.upper()}] - {desc}", markup=True, color=color, size_hint_y=None, height=sp(40), text_size=(self.width * 0.95, None), halign='left', valign='middle')
            self.grid.add_widget(event_label)