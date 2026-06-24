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

class AboutScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.name = 'about'
        self.add_header("Sobre o Sistema")

        content = AnchorLayout(anchor_x='center', anchor_y='center')

        box = BoxLayout(
            orientation='vertical',
            spacing=25,
            padding=30,
            size_hint=(None, None),
            size=(sp(700), sp(500))
        )

        titulo = Label(
            text="COMPRESSOR INDUSTRIAL",
            font_size=sp(32),
            bold=True,
            color=CORES['primaria'],
            size_hint_y=None,
            height=sp(50)
        )

        subtitulo = Label(
            text="Sistema Supervisório para Bancada de Compressor",
            font_size=sp(18),
            color=CORES['texto'],
            size_hint_y=None,
            height=sp(40)
        )

        descricao = Label(
            text=(
                "Este sistema permite o monitoramento e o controle \n"
                "de uma bancada de compressor industrial através \n"
                "de comunicação Modbus TCP. \n \n"
                "Funcionalidades: \n"
                "• Monitoramento em tempo real \n"
                "• Controle do motor elétrico \n"
                "• Controle de válvulas \n"
                "• Tendências e gráficos \n"
                "• Histórico de eventos \n"
                "• Banco de dados utilizando ORM"
            ),
            font_size=sp(16),
            halign='center',
            valign='middle',
            color=CORES['texto']
        )

        descricao.bind(
            size=lambda instance, value: setattr(instance, 'text_size', value)
        )

        autores = Label(
            text="Desenvolvido por Fred e Daniel",
            font_size=sp(16),
            color=CORES['desabilitado'],
            size_hint_y=None,
            height=sp(40)
        )

        instituicao = Label(
            text="UFJF - Informática Industrial",
            font_size=sp(14),
            color=CORES['desabilitado'],
            size_hint_y=None,
            height=sp(30)
        )

        box.add_widget(titulo)
        box.add_widget(subtitulo)
        box.add_widget(descricao)
        box.add_widget(autores)
        box.add_widget(instituicao)

        content.add_widget(box)
        self.root_layout.add_widget(content)
