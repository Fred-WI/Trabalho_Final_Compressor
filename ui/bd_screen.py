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

class BDScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs); self.name = 'bd'; self.add_header("Visualizador do Banco de Dados")
        controls = BoxLayout(size_hint_y=None, height=sp(50), padding=10, spacing=10)
        self.spinner_table = Spinner(text='readings', values=('readings', 'events'), background_color=CORES['primaria']); self.spinner_table.bind(text=self.load_table)
        controls.add_widget(Label(text="Selecionar Tabela:")); controls.add_widget(self.spinner_table); self.root_layout.add_widget(controls)
        self.scroll_view = ScrollView(); self.data_layout = BoxLayout(orientation='vertical', size_hint_y=None); self.data_layout.bind(minimum_height=self.data_layout.setter('height'))
        self.scroll_view.add_widget(self.data_layout); self.root_layout.add_widget(self.scroll_view)
    def on_enter(self): self.load_table()
    def load_table(self, *args):
        self.data_layout.clear_widgets(); table_name = self.spinner_table.text; app = App.get_running_app()
        data, headers = app.db.query_table(table_name)
        if not headers: return
        header_map = {}
        if table_name == 'readings':
            for tag_info in app.modbus.tags_addrs.values():
                if 'db_col' in tag_info: header_map[tag_info['db_col']] = f"{tag_info['db_col'].replace('_', ' ').title()} [{tag_info.get('unit', '')}]"
            header_map['timestamp'] = 'Data e Hora'
        else: header_map = {'id': 'ID', 'timestamp': 'Data e Hora', 'type': 'Tipo', 'description': 'Descrição'}
        header_grid = GridLayout(cols=len(headers), size_hint_y=None, height=sp(40))
        for header in headers: header_grid.add_widget(Label(text=header_map.get(header, header.title()), bold=True, color=CORES['primaria']))
        self.data_layout.add_widget(header_grid)
        for row in data:
            row_grid = GridLayout(cols=len(row), size_hint_y=None, height=sp(30))
            for item in row:
                text = f"{item:.2f}" if isinstance(item, float) else str(item)
                row_grid.add_widget(Label(text=text[:37] + "..." if len(text) > 40 else text, font_size=sp(12)))
            self.data_layout.add_widget(row_grid)

