"""Módulo de renderização de gráficos temporais de variáveis industriais.

Integra as bibliotecas Kivy e Matplotlib para gerar representações visuais 
bidimensionais a partir de dados serializados provenientes de um banco de dados. 
Disponibiliza controles de filtragem de tempo e funcionalidades de atualização 
periódica de interface.
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
import numpy as np

# TODO: Modularizar as dependências condicionais do kivy-garden para evitar falhas silenciadas na renderização do layout base caso a biblioteca não esteja instalada.
try:
    from kivy_garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
    KIVY_GARDEN_AVAILABLE = True
except ImportError:
    KIVY_GARDEN_AVAILABLE = False

from config import CORES, ICON_FONT
from ui.custom_widgets import HoverButton, IconButton, ValueIndicator
from ui.base_screen import BaseScreen

class GraficosScreen(BaseScreen):
    """Tela gerenciadora do ciclo de vida de renderização gráfica.
    
    Orquestra a integração entre o motor Kivy (interface) e o backend Matplotlib (desenho), 
    gerenciando os estados de filtros temporais (start_time, end_time) e a reatividade 
    automática através do event loop do Kivy.
    """

    def __init__(self, **kwargs):
        """Inicializa os contêineres e injeta os eixos (Axes) do Matplotlib.
        
        Args:
            **kwargs: Argumentos passados para a classe herdada BaseScreen.
            
        Pre-condições:
            Conexão com o banco de dados principal instanciada na aplicação Kivy.
        Pós-condições:
            Cria a infraestrutura de eixos (ax) na memória para posteriores injeções de dados.
        """
        # TODO: Refatorar o agrupamento de múltiplas instruções na mesma linha (uso de ';') para alinhar-se à diretriz PEP 8 de formatação de código.
        super().__init__(**kwargs); self.name = 'graficos'; self.auto_update_event = None; self.add_header('Gráficos de Tendência')
        self.start_time = None; self.end_time = None
        controls = BoxLayout(size_hint_y=None, height=sp(50), spacing=10, padding=(10,0))
        self.spinner_var = Spinner(text='Escolha', values=list(App.get_running_app().db.column_map.keys()), background_color=CORES['primaria'])
        self.spinner_var.bind(text=lambda *args: self.update_graph())
        btn_interval = HoverButton(text='Selecionar Intervalo', on_press=self.show_interval_picker)
        btn_full_view = HoverButton(text='Visão Completa', on_press=self.set_full_view, background_color_normal=CORES['info'])
        controls.add_widget(Label(text='Variável:')); controls.add_widget(self.spinner_var); controls.add_widget(btn_interval); controls.add_widget(btn_full_view)
        self.root_layout.add_widget(controls)
        self.graph_container = BoxLayout(padding=10); self.root_layout.add_widget(self.graph_container)
        if KIVY_GARDEN_AVAILABLE:
            plt.style.use('dark_background'); self.fig, self.ax = plt.subplots(); self.fig.set_facecolor(CORES['fundo']); self.ax.set_facecolor(CORES['fundo_claro'])
            self.graph_widget = FigureCanvasKivyAgg(self.fig); self.graph_container.add_widget(self.graph_widget)
        else: self.graph_container.add_widget(Label(text="[b]Erro:[/b] 'kivy-garden.matplotlib' não encontrada.", markup=True, color=CORES['erro']))
        Clock.schedule_once(lambda dt: self.update_graph(), 0)
        self.auto_update_event = Clock.schedule_interval(self.update_graph, 1)

    def show_interval_picker(self, instance):
        """Constrói e exibe a interface modal para seleção de restrições temporais.
        
        Args:
            instance (Widget): O componente gráfico que emitiu o evento de chamada.
            
        Complexity:
            Tempo: O(1).
            Espaço: O(1) referências de alocação de UI temporária.
        """
        content = GridLayout(cols=1, spacing=10, padding=10); start_default = self.start_time or datetime.now() - timedelta(hours=1); end_default = self.end_time or datetime.now()
        def create_time_input_group(title, dt_obj):
            box = BoxLayout(orientation='vertical', spacing=5, size_hint_y=None, height=sp(120)); box.add_widget(Label(text=title, font_size=sp(16), bold=True, color=CORES['primaria']))
            grid = GridLayout(cols=6, spacing=5); inputs = {'Y': TextInput(text=f"{dt_obj.year:04d}"), 'M': TextInput(text=f"{dt_obj.month:02d}"), 'D': TextInput(text=f"{dt_obj.day:02d}"),'h': TextInput(text=f"{dt_obj.hour:02d}"), 'm': TextInput(text=f"{dt_obj.minute:02d}"), 's': TextInput(text=f"{dt_obj.second:02d}")}
            for widget in inputs.values(): grid.add_widget(widget)
            box.add_widget(grid); return box, inputs
        start_group, self.start_inputs = create_time_input_group("Data/Hora de Início", start_default); end_group, self.end_inputs = create_time_input_group("Data/Hora de Fim", end_default)
        btn_confirm = HoverButton(text="Confirmar", on_press=self.set_interval, size_hint_y=None, height=sp(40)); content.add_widget(start_group); content.add_widget(end_group); content.add_widget(btn_confirm)
        self.popup = Popup(title='Selecionar Intervalo', content=content, size_hint=(0.5, 0.6), title_align='center'); self.popup.open()

    def set_interval(self, instance):
        """Avalia a consistência dos dados do modal e aplica os filtros no modelo interno.
        
        Args:
            instance (Widget): O botão de confirmação que emitiu o evento.
            
        Raises:
            ValueError, TypeError: Capturados silenciosamente caso o usuário informe dados que 
            inviabilizem a construção estrutural do objeto datetime.
        """
        # TODO: Substituir o log via console por notificação contextual na interface (ex: MDSnackbar/Popup) informando o usuário sobre tipagem de dados incorreta.
        try:
            s, e = self.start_inputs, self.end_inputs
            self.start_time = datetime(int(s['Y'].text),int(s['M'].text),int(s['D'].text),int(s['h'].text),int(s['m'].text),int(s['s'].text))
            self.end_time = datetime(int(e['Y'].text),int(e['M'].text),int(e['D'].text),int(e['h'].text),int(e['m'].text),int(e['s'].text))
            self.popup.dismiss(); self.update_graph()
        except (ValueError, TypeError) as ex: print(f"Erro ao definir data: {ex}")
        
    def set_full_view(self, instance): 
        """Invalida os filtros de delimitação temporal.
        
        Args:
            instance (Widget): A fonte emissora do evento da interface.
        """
        self.start_time = None; self.end_time = None; self.update_graph()
        
    def toggle_auto_update(self, i, val):
        """Manipula a inscrição no escalonador de eventos para renderização contínua.
        
        Args:
            i (Widget): A instância do Switch acionado.
            val (bool): O valor booleano determinando ativação (True) ou desativação (False).
        """
        # TODO: A hardcode intervalada de 0.5 segundos unida com I/O de banco de dados na thread principal criará engasgos severos em volumetrias grandes de dados. Considerar debouncing ou aumento paramétrico de ciclo.
        if val: self.auto_update_event = Clock.schedule_interval(self.update_graph, 0.5)
        elif self.auto_update_event: self.auto_update_event.cancel(); self.auto_update_event = None
        
    def on_leave(self, *args):
     if self.auto_update_event:
        self.auto_update_event.cancel()
        self.auto_update_event = None

    def update_graph(self, *args):
        """Requisita leitura ao modelo de dados persistente e recompõe o quadro visual Matplotlib.
        
        Consulta o banco de dados filtrando os intervalos de interesse. Opera a decomposição e 
        conversão de strings de timestamps em objetos datetimes para eixo X, formatando a visualização.
        
        Args:
            *args: Aceita eventos variáveis enviados pelo Kivy Clock.
            
        Pre-condições:
            A integração KIVY_GARDEN_AVAILABLE deve ser verdadeira para prosseguir a injeção.
            
        Complexity:
            Tempo: O(n), no qual n representa a quantidade agregada de pares (timestamp, leitura).
            Espaço: O(n) resultante da expansão da tupla do cursor via zip e alocação na RAM para plotting.
        """
        if not KIVY_GARDEN_AVAILABLE: return
        variable = self.spinner_var.text; db = App.get_running_app().db; unit = ""
        for tag_info in App.get_running_app().modbus.tags_addrs.values():
            if 'db_col' in tag_info and db.column_map.get(variable) == tag_info['db_col']: unit = tag_info.get('unit', ''); break
        # TODO: Isolar a execução assíncrona da chamada bloqueante 'db.query_readings' (I/O). Operações deste tipo congelam o Event Loop principal inviabilizando animações/fluidity do Kivy.
        data = db.query_readings(variable, self.start_time, self.end_time); self.ax.clear()
        if data:
            timestamps, values = zip(*data)
            timestamps = [datetime.strptime(ts.split('.')[0], '%Y-%m-%d %H:%M:%S') for ts in timestamps]
            
            # Plotagem dos dados brutos originais
            self.ax.plot(timestamps, values, color=CORES['info'], marker='o', linestyle='-', markersize=2, label='Leituras')
            
            # Converte as datas (datetime) para valores numéricos contínuos
            x_num = mdates.date2num(timestamps)
            
            if len(x_num) > 1:
                # Calcula os coeficientes da reta (grau 1) usando o método dos mínimos quadrados
                coeficientes = np.polyfit(x_num, values, 1)
                polinomio = np.poly1d(coeficientes)
                
                # Plota a linha de tendência baseada na equação calculada
                self.ax.plot(timestamps, polinomio(x_num), color='red', linestyle='--', linewidth=2, label='Tendência (Linear)')
                
                # Adiciona a legenda para diferenciar as linhas
                self.ax.legend(loc='best', facecolor=CORES['fundo_claro'], labelcolor=CORES['texto'])

            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M'))
            self.fig.autofmt_xdate()
        else: 
            self.ax.text(0.5, 0.5, "Nenhum dado para o intervalo", ha='center', va='center', color=CORES['texto'], fontsize=14)
        self.ax.set_title(f'Tendência de {variable}', color=CORES['primaria'], fontsize=16); self.ax.set_xlabel('Horário', color=CORES['texto']); self.ax.set_ylabel(f'{variable}', color=CORES['texto'])
        self.ax.tick_params(colors=CORES['texto']); self.ax.grid(True, linestyle='--', color=CORES['desabilitado'], alpha=0.5)
        self.fig.tight_layout(pad=1.5); self.graph_widget.draw_idle()