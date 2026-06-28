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

class ValvulasScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs); self.name = 'valvulas'; self.add_header("Controle de Válvulas Solenoides")
        grid = GridLayout(cols=3, spacing=20, padding=20); self.valves = {}
        for i in range(2, 7):
            valve_box = BoxLayout(orientation='vertical', spacing=10, padding=10)
            with valve_box.canvas.before: Color(*CORES['fundo_claro']); valve_box.bg = RoundedRectangle(pos=valve_box.pos, size=valve_box.size, radius=[8])
            valve_box.bind(pos=lambda i,v: setattr(i.bg, 'pos', v), size=lambda i,v: setattr(i.bg, 'size', v))
            label = Label(text=f"Válvula XV-0{i}", font_size=sp(20), bold=True)
            switch = Switch(active=False, size_hint=(None,None), size=(sp(64), sp(48)), pos_hint={'center_x':0.5})
            switch.bind(active=lambda instance, value, index=i: App.get_running_app().modbus.write_tag(f'co.xv{index}', 1 if value else 0))
            status_label = Label(text="FECHADA", font_size=sp(18), bold=True, color=CORES['erro'])
            valve_box.add_widget(label); valve_box.add_widget(switch); valve_box.add_widget(status_label)
            grid.add_widget(valve_box); self.valves[i] = {'switch': switch, 'status': status_label}
        self.root_layout.add_widget(grid); Clock.schedule_interval(self.update_ui, 0.5)
    def update_valve_status(self, index, value):
        status, color = ("ABERTA", CORES['sucesso']) if value else ("FECHADA", CORES['erro'])
        self.valves[index]['status'].text = status; self.valves[index]['status'].color = color
    def update_ui(self, dt):
        app = App.get_running_app()
        if app.modbus and app.modbus.is_connected:
            for i in range(2, 7):
                state = app.modbus.read_tag(f'co.xv{i}') == 1
                if self.valves[i]['switch'].active != state: self.valves[i]['switch'].active = state
                self.update_valve_status(i, state)

