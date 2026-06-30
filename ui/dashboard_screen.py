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

class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'dashboard'
        self.inverter_frequency = 0  # Variavel para armazenar a frequencia

        main_layout = BoxLayout(orientation='vertical')
        header = BoxLayout(size_hint_y=None, height=sp(60), padding=10, spacing=20)
        with header.canvas.before:
            Color(*CORES['primaria'])
            header.bg_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=lambda i, v: setattr(header.bg_rect, 'pos', v),
                    size=lambda i, v: setattr(header.bg_rect, 'size', v))
        header.add_widget(Label(text='COMPRESSOR', font_size=sp(22), bold=True, size_hint_x=0.4))
        self.connection_status = Label(text='', font_size=sp(16), markup=True, size_hint_x=0.4)
        self.clock_label = Label(text='', font_size=sp(14), size_hint_x=0.1)
        btn_disconnect = IconButton(icon_name='logout', size_hint_x=None, width=sp(120),
                                    on_press=lambda x: setattr(self.manager, 'current', 'conexao'))
        header.add_widget(self.connection_status)
        header.add_widget(self.clock_label)
        header.add_widget(btn_disconnect)
        main_layout.add_widget(header)

        content = BoxLayout(orientation='horizontal', padding=10, spacing=10)

        center_panel = BoxLayout(orientation='vertical', size_hint_x=0.62, spacing=10)
       

        # ==========================
        # DIAGRAMA DA BANCADA
        # ==========================

        diagram_placeholder = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint_y=1
        )

        with diagram_placeholder.canvas.before:
            Color(1, 1, 1, 0.95)
            self.diagram_bg = RoundedRectangle(
                pos=diagram_placeholder.pos,
                size=diagram_placeholder.size,
                radius=[10]
            )

        diagram_placeholder.bind(
            pos=lambda i, v: setattr(self.diagram_bg, 'pos', v),
            size=lambda i, v: setattr(self.diagram_bg, 'size', v)
        )

        self.diagram_layer = FloatLayout(
            size_hint=(0.95, 0.95)
        )

        img_path = os.path.join("assets", "bancada.png")

        if os.path.exists(img_path):

            self.bancada_img = Image(
                source=img_path,
                nocache=True,
                allow_stretch=True,
                keep_ratio=True,
                size_hint=(1, 1),
                pos_hint={"center_x":0.5, "center_y":0.5}
            )

            self.diagram_layer.add_widget(self.bancada_img)

            # ------------------------
            # PRESSÃO (PIT-01)
            # ------------------------
            self.pressao_label = Label(
                text="0.00 bar",
                markup=True,
                halign="center",
                valign="middle",
                font_size=sp(18),
                bold=True,
                color=(0, 0, 0, 1),
                size_hint=(0.12,0.08),
                #pos_hint={"x":0.065,"y":0.655}
                pos_hint={"x":0.063,"y":0.67}
            )

            # ------------------------
            # VAZÃO (FIT-03)
            # ------------------------
            self.vazao_label = Label(
                text="0.00 L/min",
                markup=True,
                halign="center",
                valign="middle",
                font_size=sp(18),
                bold=True,
                color=(0, 0, 0, 1),
                size_hint=(0.15,0.08),
                #pos_hint={"x":0.385,"y":0.71}
                pos_hint={"x":0.384,"y":0.73}
            )

            self.diagram_layer.add_widget(self.pressao_label)
            self.diagram_layer.add_widget(self.vazao_label)

            # ------------------------
            # BOTÕES INVISÍVEIS DAS VÁLVULAS
            # ------------------------
            self.valve_buttons = {}

            valve_positions = {
                2: {'x': 0.8475, 'y': 0.689},
                3: {'x': 0.8475, 'y': 0.568},
                4: {'x': 0.8475, 'y': 0.447},
                5: {'x': 0.8475, 'y': 0.326},
                6: {'x': 0.8475, 'y': 0.205},
            }

            for valve_id, pos in valve_positions.items():
                btn = Button(
                    text='OFF',
                    font_size=sp(11),
                    bold=True,
                    color=(1, 1, 1, 1),
                    background_normal='',
                    background_down='',
                    background_color=(0.35, 0.35, 0.35, 1),
                    size_hint=(0.055, 0.04),
                    pos_hint=pos
                )
                btn.valve_id = valve_id
                btn.bind(on_press=self.toggle_valve_from_diagram)
                self.valve_buttons[valve_id] = btn
                self.diagram_layer.add_widget(btn)

        else:

            self.diagram_layer.add_widget(
                Label(
                    text="Imagem da bancada não encontrada.",
                    color=(0,0,0,1)
                )
            )

        diagram_placeholder.add_widget(self.diagram_layer)

        center_panel.add_widget(diagram_placeholder)


        self.indicators = {}
        
        content.add_widget(center_panel)

        right_panel_scroll = ScrollView(size_hint_x=0.3)
        right_panel = GridLayout(cols=1, spacing=15, padding=10, size_hint_y=None)
        right_panel.bind(minimum_height=right_panel.setter('height'))
        with right_panel.canvas.before:
            Color(*CORES['fundo_claro'])
            self.right_bg = RoundedRectangle(pos=right_panel.pos, size=right_panel.size, radius=[10])
        right_panel.bind(pos=lambda i, v: setattr(self.right_bg, 'pos', v),
                         size=lambda i, v: setattr(self.right_bg, 'size', v))

        right_panel.add_widget(Label(
            text="Controle do Motor", font_size=sp(20), bold=True, color=CORES['primaria'], size_hint_y=None, height=sp(30)
        ))

        control_grid = GridLayout(cols=2, rows=1, spacing=10, size_hint_y=None, height=sp(50))

        self.motor_tipo = 'Verde'  # valor fixo interno para não quebrar o comando

        self.spinner_partida = Spinner(
            text='Escolha Partida',
            values=('Direta', 'Soft-start', 'Inversor'),
            background_color=CORES['primaria']
        )
        self.spinner_partida.bind(text=self.toggle_inverter_controls)

        control_grid.add_widget(Label(text='Partida:'))
        control_grid.add_widget(self.spinner_partida)

        right_panel.add_widget(control_grid)

        # --- INICIO DA SEÇÃO DO SLIDER ---
        self.inverter_controls = BoxLayout(orientation='vertical', size_hint_y=None, height=0, opacity=0, spacing=5)
        self.frequency_label = Label(text='Frequência: 0 Hz', size_hint_y=None, height=sp(25))
        self.frequency_slider = Slider(min=0, max=60, value=0, step=1)
        self.frequency_slider.bind(value=self.on_frequency_change)
        self.inverter_controls.add_widget(self.frequency_label)
        self.inverter_controls.add_widget(self.frequency_slider)
        right_panel.add_widget(self.inverter_controls)
        # --- FIM DA SEÇÃO DO SLIDER ---

        motor_buttons = BoxLayout(spacing=10, size_hint_y=None, height=sp(50))
        self.btn_ligar = HoverButton(text='LIGAR', on_press=self.handle_motor_toggle, background_color_normal=CORES['sucesso'])
        self.btn_desligar = HoverButton(text='DESLIGAR', on_press=self.handle_motor_toggle, background_color_normal=CORES['erro'])
        motor_buttons.add_widget(self.btn_ligar)
        motor_buttons.add_widget(self.btn_desligar)
        right_panel.add_widget(motor_buttons)
        self.motor_status_label = Label(
            text='MOTOR DESLIGADO', font_size=sp(18), bold=True, color=CORES['erro'], size_hint_y=None, height=sp(40)
        )
        right_panel.add_widget(self.motor_status_label)

        right_panel.add_widget(Label(
            text='',
            size_hint_y=None,
            height=sp(15)
        ))

        menu_buttons = {
            'Gráficos': ('show_chart', 'graficos'),
            'Elétrica': ('bolt', 'eletrica'),
            'Válvulas': ('toggle_on', 'valvulas'),
            'Histórico de eventos': ('history', 'historico'),
            'Banco de Dados': ('storage', 'bd'),
            'Sobre': ('info_outline', 'about')
        }

        for texto, (_, tela) in menu_buttons.items():
            btn = HoverButton(
                text=texto,
                size_hint_y=None,
                height=sp(50),
                on_press=self.navigate
            )
            btn.screen_name = tela
            right_panel.add_widget(btn)

        right_panel_scroll.add_widget(right_panel)
        content.add_widget(right_panel_scroll)
        main_layout.add_widget(content)
        self.add_widget(main_layout)
        Clock.schedule_interval(self.update_ui, 0.5)

    def toggle_inverter_controls(self, instance, text):
        """Seleciona a partida e configura os parâmetros antes de ligar o motor."""

        partida_map = {'Direta': 3, 'Soft-start': 1, 'Inversor': 2}

        # Mostra ou esconde o controle de frequência conforme o tipo de partida
        if text == 'Inversor':
            self.inverter_controls.height = sp(60)
            self.inverter_controls.opacity = 1
        else:
            self.inverter_controls.height = 0
            self.inverter_controls.opacity = 0

        app = App.get_running_app()

        if not app.modbus or not app.modbus.is_connected or text not in partida_map:
            return

        # Informa ao CLP/simulador qual partida foi escolhida
        app.modbus.troca_partida(partida_map[text])

        # Configura os parâmetros da partida no momento da escolha
        try:
            if text == 'Soft-start':
                app.modbus.write_tag('co.ats48_acc', 10)
                app.modbus.write_tag('co.ats48_dcc', 10)
                app.db.log_event('comando', '[COMPRESSOR] Soft-start selecionado: rampas configuradas em 10 s')

            elif text == 'Inversor':

                freq = self.inverter_frequency if self.inverter_frequency > 0 else 20

                # Configura as rampas do inversor
                app.modbus.write_tag('co.ats48_acc', 10)
                app.modbus.write_tag('co.ats48_dcc', 10)

                # Configura a frequência
                app.modbus.write_tag('co.freq_ref', freq)

                app.db.log_event(
                    'comando',
                    f'[COMPRESSOR] Inversor selecionado: ACC=10 s, DCC=10 s, Frequência={int(freq)} Hz'
                )

            elif text == 'Direta':
                app.db.log_event('comando', '[COMPRESSOR] Partida direta selecionada')

        except Exception as e:
            app.db.log_event('erro', f'Erro ao configurar partida {text}: {e}')


    # def seleciona_aceleracao()
    # def seleciona_desaceleracao()
    # def seleciona_frequencia_inversor()
        
        
            
    def on_frequency_change(self, instance, value):
        """Chamado quando o valor do slider muda.

        No modo inversor, a frequência escolhida também é enviada ao
        controlador Modbus. No modo simulação, ela muda a velocidade alvo
        do motor. No modo real, ela escreve no registrador 1313 por meio da
        tag co.freq_ref.
        """
        self.inverter_frequency = int(value)
        self.frequency_label.text = f'Frequência: {int(value)} Hz'

        app = App.get_running_app()
        if hasattr(app, 'modbus') and app.modbus and app.modbus.is_connected:
            if self.spinner_partida.text == 'Inversor':
                app.modbus.write_tag('co.freq_ref', self.inverter_frequency)


    def toggle_valve_from_diagram(self, instance):
        app = App.get_running_app()
        modbus = getattr(app, 'modbus', None)

        if not modbus or not modbus.is_connected:
            self.show_error_popup('Não há conexão com o CLP!')
            return

        valve_id = instance.valve_id
        tag = f'co.xv{valve_id}'

        estado_atual = modbus.read_tag(tag)
        novo_estado = 0 if estado_atual == 1 else 1

        modbus.write_tag(tag, novo_estado)

        estado_txt = 'ABERTA' if novo_estado == 1 else 'FECHADA'
        app.db.log_event('comando', f'Válvula XV-{valve_id} {estado_txt} pelo sinótico.')           

    def update_ui(self, dt):
        """Versão corrigida do update_ui com lógica de botões correta"""
        app = App.get_running_app()
        self.clock_label.text = datetime.now().strftime('%H:%M:%S')
        
        modbus = getattr(app, 'modbus', None)
        if not modbus or not modbus.is_connected:
            self.connection_status.text = f"[font=MaterialIcons]cloud_off[/font] OFFLINE"
            self.connection_status.color = CORES['erro']
            self.motor_status_label.text = 'MOTOR DESLIGADO'
            self.motor_status_label.color = CORES['erro']
            # Quando desconectado, desabilita ambos os botões
            self.btn_ligar.disabled = True
            self.btn_desligar.disabled = True
            return

        self.connection_status.text = f"[font=MaterialIcons]cloud_done[/font] CONECTADO ({modbus.mode})"
        self.connection_status.color = CORES['sucesso']

        pressao = modbus.read_tag("co.pressao")
        vazao = modbus.read_tag("co.fit02")

        self.pressao_label.text = f"{pressao:.2f} bar"
        self.vazao_label.text = f"{vazao:.2f} L/min"

        for valve_id, btn in self.valve_buttons.items():
            state = modbus.read_tag(f'co.xv{valve_id}') == 1

            if state:
                btn.text = "ON"
                btn.background_color = (0.10, 0.35, 0.60, 1)   # azul
            else:
                btn.text = "OFF"
                btn.background_color = (0.35, 0.35, 0.35, 1)   # cinza
        
        # Atualiza indicadores
        for tag, widget in self.indicators.items():
            if tag == 'vazao_total':
                widget.current_val = (modbus.read_tag('co.fit02'))
            else:
                widget.current_val = modbus.read_tag(tag)
        
        
        # CORREÇÃO PRINCIPAL: Verifica o estado real do motor
        motor_ligado = modbus.get_motor_status()  # Usa o novo método

        # Lógica correta dos botões:
        # - Se motor está DESLIGADO: habilita botão LIGAR, desabilita botão DESLIGAR
        # - Se motor está LIGADO: desabilita botão LIGAR, habilita botão DESLIGAR
        # - Se partida não foi escolhida: desabilita botão LIGAR

        partida_escolhida = self.spinner_partida.text != 'Escolha Partida'

        if motor_ligado:
            # Motor está LIGADO
            self.btn_ligar.disabled = True
            self.btn_desligar.disabled = False

            # NOVO
            self.spinner_partida.disabled = True
            # self.spinner_motor.disabled = True

            self.motor_status_label.text = f'MOTOR LIGADO ({self.spinner_partida.text})'
            self.motor_status_label.color = CORES['sucesso']

        else:
            # Motor está DESLIGADO
            self.btn_ligar.disabled = not partida_escolhida
            self.btn_desligar.disabled = True

            # NOVO
            self.spinner_partida.disabled = False
            # self.spinner_motor.disabled = False

            self.motor_status_label.text = 'MOTOR DESLIGADO'
            self.motor_status_label.color = CORES['erro']
            

    def handle_motor_toggle(self, instance):
        """Versão corrigida do handle_motor_toggle"""
        app = App.get_running_app()
        
        if not app.modbus or not app.modbus.is_connected:
            self.show_error_popup('Não há conexão com o CLP!')
            return
        
        if instance.text == 'LIGAR':
            # Verifica se uma partida foi selecionada
            if self.spinner_partida.text == 'Escolha Partida':
                self.show_error_popup('Por favor, selecione um tipo de partida primeiro!')
                return
            
            # Verifica se o motor já está ligado
            if app.modbus.get_motor_status():
                self.show_error_popup('O motor já está ligado!')
                return
            

            self.do_toggle_motor('LIGAR')
            
        elif instance.text == 'DESLIGAR':
            # Verifica se o motor já está desligado
            if not app.modbus.get_motor_status():
                self.show_error_popup('O motor já está desligado!')
                return
                
            # Para desligar, executa diretamente
            self.do_toggle_motor('DESLIGAR')

    def do_toggle_motor(self, action, popup=None):
        if popup:
            popup.dismiss()

        app = App.get_running_app()

        if action == 'LIGAR':
            app.modbus.comandoMotor(1)
        else:
            app.modbus.comandoMotor(0)

    def show_error_popup(self, message):
        """Mostra popup de erro"""
        content = BoxLayout(orientation='vertical', spacing=15, padding=15)
        content.add_widget(Label(text=message, font_size=sp(16), color=CORES['erro']))
        btn_ok = HoverButton(text='OK', size_hint_y=None, height=sp(40))
        content.add_widget(btn_ok)
        popup = Popup(title='Erro', content=content, size_hint=(None, None), 
                    size=(sp(400), sp(150)), title_align='center')
        btn_ok.bind(on_press=popup.dismiss)
        popup.open()


    def navigate(self, instance): self.manager.current = instance.screen_name

