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
    def __init__(self, **kwargs):
        super().__init__(**kwargs); self.name = 'historico'; self.add_header("Histórico de Eventos")
        controls = BoxLayout(size_hint_y=None, height=sp(50), padding=10, spacing=10)
        self.spinner_type = Spinner(text='Todos', values=('Todos', 'Sistema', 'Erro', 'Comando', 'Alerta'), background_color=CORES['primaria']); self.spinner_type.bind(text=self.load_events)
        controls.add_widget(Label(text="Filtrar por tipo:"))
        controls.add_widget(self.spinner_type)
        self.root_layout.add_widget(controls)
        self.scroll_view = ScrollView()
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=5, padding=5)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll_view.add_widget(self.grid)
        self.root_layout.add_widget(self.scroll_view)
    def on_enter(self, *args): self.load_events()
    
    def load_events(self, *args):
        self.grid.clear_widgets()

        events = App.get_running_app().db.query_events(event_type=self.spinner_type.text, limit=200)
        
        for ts, etype, desc in events:
            color = {'erro': CORES['erro'], 'sistema': CORES['info'], 'comando': CORES['alerta'], 'alerta': CORES['alerta']}.get(etype, CORES['texto'])
            ts_obj = datetime.strptime(ts.split('.')[0], '%Y-%m-%d %H:%M:%S')
            event_label = Label(text=f"[b]{ts_obj.strftime('%d/%m/%Y %H:%M:%S')} [/b] | [{etype.upper()}] - {desc}", markup=True, color=color, size_hint_y=None, height=sp(40), text_size=(self.width * 0.95, None), halign='left', valign='middle')
            self.grid.add_widget(event_label)

