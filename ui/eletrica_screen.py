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

class EletricaScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs); self.name = 'eletrica'; self.add_header("Painel Elétrico e Mecânico")
        grid = GridLayout(cols=3, spacing=15, padding=15)
        self.eletrica_indicators = {'co.corrente_media': self.create_eletrica_indicator('electrical_services', 'Corrente Média'), 'co.ativa_total': self.create_eletrica_indicator('bolt', 'Pot. Ativa'), 'co.reativa_total': self.create_eletrica_indicator('bolt', 'Pot. Reativa'), 'co.aparente_total': self.create_eletrica_indicator('bolt', 'Pot. Aparente'), 'co.tensao_rs': self.create_eletrica_indicator('electrical_services', 'Tensão RS'), 'co.fp_total': self.create_eletrica_indicator('power', 'FP Total'), 'co.frequencia': self.create_eletrica_indicator('timeline', 'Frequência'), 'co.torque': self.create_eletrica_indicator('settings', 'Torque'), 'co.encoder': self.create_eletrica_indicator('speed', 'Rotação'), 'co.temp_carc': self.create_eletrica_indicator('thermostat', 'Temp. Carcaça')}
        for ind in self.eletrica_indicators.values(): grid.add_widget(ind)
        self.root_layout.add_widget(grid); Clock.schedule_interval(self.update_data, 1.0)
    def create_eletrica_indicator(self, icon, name):
        box = BoxLayout(orientation='vertical', padding=10, spacing=5)
        with box.canvas.before: Color(*CORES['fundo_claro']); box.bg = RoundedRectangle(pos=box.pos, size=box.size, radius=[8])
        box.bind(pos=lambda i,v: setattr(box.bg, 'pos', v), size=lambda i,v: setattr(box.bg, 'size', v))
        if ICON_FONT: box.add_widget(Label(text=icon, font_name='MaterialIcons', font_size=sp(48), color=CORES['info']))
        box.add_widget(Label(text=name, font_size=sp(18), color=CORES['texto']))
        value_label = Label(text="---", font_size=sp(28), bold=True, color=CORES['texto']); box.add_widget(value_label)
        box.value_label = value_label; return box
    def update_data(self, dt):
        modbus = App.get_running_app().modbus
        if modbus and modbus.is_connected:
            for tag, widget in self.eletrica_indicators.items():
                value = modbus.read_tag(tag); info = modbus.get_tag_info(tag); unit = info.get('unit', '')
                widget.value_label.text = f"{value:.2f} {unit}"

