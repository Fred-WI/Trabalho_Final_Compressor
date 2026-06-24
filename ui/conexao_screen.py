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

class ConexaoScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs); self.name = 'conexao'
        with self.canvas.before: Color(*CORES['fundo']); self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda i,v: setattr(self.bg, 'pos', v), size=lambda i,v: setattr(self.bg, 'size', v))
        center_box = BoxLayout(orientation='vertical', size_hint=(None, None), size=(sp(550), sp(500)),pos_hint={'center_x': 0.5, 'center_y': 0.5}, padding=sp(40), spacing=sp(25))
        with center_box.canvas.before: Color(*CORES['fundo_claro']); center_box.bg = RoundedRectangle(pos=center_box.pos, size=center_box.size, radius=[15])
        center_box.bind(pos=lambda i,v: setattr(i.bg, 'pos', v), size=lambda i,v: setattr(i.bg, 'size', v))
        center_box.add_widget(Label(text='COMPRESSOR', font_size=sp(48), bold=True, color=CORES['primaria']))
        center_box.add_widget(Label(text='Sistema Supervisório para Bancada de Compressor', font_size=sp(18), color=CORES['texto']))
        btn_sim = HoverButton(text='CONECTAR À SIMULAÇÃO', font_size=sp(18), size_hint_y=None, height=sp(55), background_color_normal=CORES['sucesso'], on_press=lambda x: self._connect('simulation', ''))
        center_box.add_widget(btn_sim)
        center_box.add_widget(Label(text='OU', size_hint_y=None, height=sp(10)))
        ip_layout = BoxLayout(spacing=10, size_hint_y=None, height=sp(55))
        self.input_ip = TextInput(text='10.15.30.182', font_size=sp(18), multiline=False, size_hint_x=0.7, halign='center', padding=[10, 15, 10, 15])
        btn_ip = HoverButton(text='CONECTAR', font_size=sp(16), size_hint_x=0.3, background_color_normal=CORES['info'], on_press=self.connect_ip)
        ip_layout.add_widget(self.input_ip); ip_layout.add_widget(btn_ip)
        center_box.add_widget(ip_layout)
        self.status_label = Label(text='Aguardando Conexão...', font_size=sp(16), size_hint_y=None, height=sp(30))
        center_box.add_widget(self.status_label)
        self.add_widget(center_box)

    def on_enter(self, *args):
        app = App.get_running_app()
        if hasattr(app, 'modbus') and app.modbus.is_connected:
            app.modbus.disconnect(); app.db.log_event('sistema', "Sessão encerrada.")
            self.status_label.text = "Sessão anterior encerrada."; self.status_label.color = CORES['info']
        else: self.status_label.text = "Aguardando Conexão..."; self.status_label.color = CORES['texto']

    def _connect(self, mode, ip):
        self.status_label.text = f"Conectando a {ip if ip else 'Simulação'}..."; self.status_label.color = CORES['info']
        Clock.schedule_once(lambda dt: self._do_connect(mode, ip), 0.1)

    def connect_ip(self, instance): self._connect('real', self.input_ip.text.strip())

    def _do_connect(self, mode, ip):
        app = App.get_running_app()
        success, message = app.modbus.connect(mode, ip=ip)
        self.status_label.text = message
        if success:
            self.status_label.color = CORES['sucesso']; app.db.log_event('sistema', message)
            Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'dashboard'), 1.5)
        else:
            self.status_label.color = CORES['erro']; app.db.log_event('erro', message)
            
