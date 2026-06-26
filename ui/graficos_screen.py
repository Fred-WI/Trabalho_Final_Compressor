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

class GraficosScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs); self.name = 'graficos'; self.auto_update_event = None; self.add_header('Gráficos de Tendência')
        self.start_time = None; self.end_time = None
        controls = BoxLayout(size_hint_y=None, height=sp(50), spacing=10, padding=(10,0))
        self.spinner_var = Spinner(text='Pressão', values=list(App.get_running_app().db.column_map.keys()), background_color=CORES['primaria'])
        btn_interval = HoverButton(text='Selecionar Intervalo', on_press=self.show_interval_picker)
        btn_full_view = HoverButton(text='Visão Completa', on_press=self.set_full_view, background_color_normal=CORES['info'])
        auto_update_box = BoxLayout(orientation='horizontal', size_hint_x=None, width=sp(250)); auto_update_box.add_widget(Label(text='Atualizar (0.5s):'))
        self.auto_update_switch = Switch(active=False); self.auto_update_switch.bind(active=self.toggle_auto_update); auto_update_box.add_widget(self.auto_update_switch)
        controls.add_widget(Label(text='Variável:')); controls.add_widget(self.spinner_var); controls.add_widget(btn_interval); controls.add_widget(btn_full_view); controls.add_widget(auto_update_box)
        self.root_layout.add_widget(controls)
        self.graph_container = BoxLayout(padding=10); self.root_layout.add_widget(self.graph_container)
        if KIVY_GARDEN_AVAILABLE:
            plt.style.use('dark_background'); self.fig, self.ax = plt.subplots(); self.fig.set_facecolor(CORES['fundo']); self.ax.set_facecolor(CORES['fundo_claro'])
            self.graph_widget = FigureCanvasKivyAgg(self.fig); self.graph_container.add_widget(self.graph_widget)
        else: self.graph_container.add_widget(Label(text="[b]Erro:[/b] 'kivy-garden.matplotlib' não encontrada.", markup=True, color=CORES['erro']))
        Clock.schedule_once(self.update_graph, 1)

    def show_interval_picker(self, instance):
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
        try:
            s, e = self.start_inputs, self.end_inputs
            self.start_time = datetime(int(s['Y'].text),int(s['M'].text),int(s['D'].text),int(s['h'].text),int(s['m'].text),int(s['s'].text))
            self.end_time = datetime(int(e['Y'].text),int(e['M'].text),int(e['D'].text),int(e['h'].text),int(e['m'].text),int(e['s'].text))
            self.popup.dismiss(); self.update_graph()
        except (ValueError, TypeError) as ex: print(f"Erro ao definir data: {ex}")
    def set_full_view(self, instance): self.start_time = None; self.end_time = None; self.update_graph()
    def toggle_auto_update(self, i, val):
        if val: self.auto_update_event = Clock.schedule_interval(self.update_graph, 0.5)
        elif self.auto_update_event: self.auto_update_event.cancel(); self.auto_update_event = None
    def on_leave(self, *args):
        if self.auto_update_event: self.auto_update_event.cancel(); self.auto_update_switch.active = False
    def update_graph(self, *args):
        if not KIVY_GARDEN_AVAILABLE: return
        variable = self.spinner_var.text; db = App.get_running_app().db; unit = ""
        for tag_info in App.get_running_app().modbus.tags_addrs.values():
            if 'db_col' in tag_info and db.column_map.get(variable) == tag_info['db_col']: unit = tag_info.get('unit', ''); break
        data = db.query_readings(variable, self.start_time, self.end_time); self.ax.clear()
        if data:
            timestamps, values = zip(*data); timestamps = [datetime.strptime(ts.split('.')[0], '%Y-%m-%d %H:%M:%S') for ts in timestamps]
            self.ax.plot(timestamps, values, color=CORES['info'], marker='o', linestyle='-', markersize=2); self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M')); self.fig.autofmt_xdate()
        else: self.ax.text(0.5, 0.5, "Nenhum dado para o intervalo", ha='center', va='center', color=CORES['texto'], fontsize=14)
        self.ax.set_title(f'Tendência de {variable}', color=CORES['primaria'], fontsize=16); self.ax.set_xlabel('Horário', color=CORES['texto']); self.ax.set_ylabel(f'{variable} [{unit}]', color=CORES['texto'])
        self.ax.tick_params(colors=CORES['texto']); self.ax.grid(True, linestyle='--', color=CORES['desabilitado'], alpha=0.5)
        self.fig.tight_layout(pad=1.5); self.graph_widget.draw()

