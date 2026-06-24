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

        left_panel = BoxLayout(orientation='vertical', size_hint_x=0.2, spacing=10)
        nav_buttons = {
            'Gráficos': ('show_chart', 'graficos'),
            'Elétrica': ('bolt', 'eletrica'),
            'Válvulas': ('toggle_on', 'valvulas'),
            'Histórico': ('history', 'historico'),
            'Banco de Dados': ('storage', 'bd'),
            'Sobre': ('info_outline', 'about')
        }
        for text, (icon, screen) in nav_buttons.items():
            btn_container = BoxLayout(orientation='horizontal', size_hint_y=None, height=sp(50))
            icon_btn = IconButton(icon_name=icon, size_hint_x=None, width=sp(50), on_press=self.navigate)
            icon_btn.screen_name = screen
            label_btn = Button(
                text=text,
                font_size=sp(18),
                background_color=(0, 0, 0, 0),
                text_size=(Window.width * 0.15, None),
                halign='left',
                valign='middle',
                on_press=self.navigate
            )
            label_btn.screen_name = screen
            btn_container.add_widget(icon_btn)
            btn_container.add_widget(label_btn)
            left_panel.add_widget(btn_container)
        content.add_widget(left_panel)

        center_panel = BoxLayout(orientation='vertical', size_hint_x=0.5, spacing=10)
        diagram_placeholder = AnchorLayout(anchor_x='center', anchor_y='center')
        with diagram_placeholder.canvas.before:
            Color(1, 1, 1, 0.9)
            self.diagram_bg = RoundedRectangle(pos=diagram_placeholder.pos, size=diagram_placeholder.size, radius=[10])
        diagram_placeholder.bind(pos=lambda i, v: setattr(self.diagram_bg, 'pos', v),
                                size=lambda i, v: setattr(self.diagram_bg, 'size', v))
        img_path = 'assets/bancada.png'
        if os.path.exists(img_path):
            diagram_placeholder.add_widget(Image(source=img_path, nocache=True))
        else:
            diagram_placeholder.add_widget(Label(
                text=f"Diagrama da Bancada\n({img_path} não encontrada)",
                color=(0, 0, 0, 1),
                halign='center'
            ))
        center_panel.add_widget(diagram_placeholder)

        indicators_grid = GridLayout(cols=4, spacing=10, size_hint_y=0.25)
        self.indicators = {
            'ro.pressao': ValueIndicator(label_text='Pressão', unit='bar', min_val=0, max_val=10, alert_level=7, critical_level=9),
            'ro.encoder': ValueIndicator(label_text='Rotação', unit='Hz', min_val=0, max_val=70, alert_level=62, critical_level=65),
            'vazao_total': ValueIndicator(label_text='Vazão Total', unit='L/min', min_val=0, max_val=100, alert_level=80, critical_level=90),
            'ro.torque': ValueIndicator(label_text='Torque', unit='N·m', min_val=0, max_val=20, alert_level=15, critical_level=18)
        }
        for ind in self.indicators.values():
            indicators_grid.add_widget(ind)
        center_panel.add_widget(indicators_grid)
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
        control_grid = GridLayout(cols=2, rows=2, spacing=10, size_hint_y=None, height=sp(100))
        self.spinner_motor = Spinner(text='Verde', values=('Verde', 'Azul'), background_color=CORES['primaria'])
        self.spinner_partida = Spinner(text='Escolha Partida', values=('Direta', 'Soft-start', 'Inversor'), background_color=CORES['primaria'])
        self.spinner_partida.bind(text=self.toggle_inverter_controls)
        control_grid.add_widget(Label(text='Motor:'))
        control_grid.add_widget(self.spinner_motor)
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

        self.indicator_temp = ValueIndicator(
            label_text="Temp. Carcaça", unit="°C", min_val=20, max_val=100, alert_level=80, critical_level=85, size_hint_y=None, height=sp(90)
        )
        self.indicator_corrente = ValueIndicator(
            label_text="Corrente Média", unit="A", min_val=0, max_val=10, alert_level=7, critical_level=8.5, size_hint_y=None, height=sp(90)
        )
        right_panel.add_widget(self.indicator_temp)
        right_panel.add_widget(self.indicator_corrente)

        right_panel.add_widget(Label(
            text="Controle de Válvulas", font_size=sp(20), bold=True, color=CORES['primaria'], size_hint_y=None, height=sp(30)
        ))
        self.valves = {}
        valves_grid = GridLayout(cols=3, spacing=sp(15), size_hint_y=None, height=sp(180))
        for i in range(1, 7):
            valve_box = BoxLayout(orientation='vertical', spacing=5)
            switch = Switch(active=False, size_hint_y=None, height=sp(48))
            switch.bind(active=lambda instance, value, index=i: App.get_running_app().modbus.write_tag(f'co.xv{index}', 1 if value else 0))
            valve_box.add_widget(Label(text=f"XV-0{i}", font_size=sp(14), size_hint_y=None, height=sp(20)))
            valve_box.add_widget(switch)
            valves_grid.add_widget(valve_box)
            self.valves[i] = switch
        right_panel.add_widget(valves_grid)

        right_panel_scroll.add_widget(right_panel)
        content.add_widget(right_panel_scroll)
        main_layout.add_widget(content)
        self.add_widget(main_layout)
        Clock.schedule_interval(self.update_ui, 0.5)

    def toggle_inverter_controls(self, instance, text):
        """Mostra ou esconde o slider de frequência baseado na seleção da partida."""
        if text == 'Inversor':
            self.inverter_controls.height = sp(60)
            self.inverter_controls.opacity = 1
        else:
            self.inverter_controls.height = 0
            self.inverter_controls.opacity = 0
            
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
        
        # Atualiza indicadores
        for tag, widget in self.indicators.items():
            if tag == 'vazao_total':
                widget.current_val = (modbus.read_tag('ro.fit02') + modbus.read_tag('ro.fit03'))
            else:
                widget.current_val = modbus.read_tag(tag)
        
        self.indicator_temp.current_val = modbus.read_tag('ro.temp_carc')
        self.indicator_corrente.current_val = modbus.read_tag('ro.corrente_media')
        
        # CORREÇÃO PRINCIPAL: Verifica o estado real do motor
        motor_ligado = modbus.get_motor_status()  # Usa o novo método
        
        # Lógica correta dos botões:
        # - Se motor está DESLIGADO: habilita botão LIGAR, desabilita botão DESLIGAR
        # - Se motor está LIGADO: desabilita botão LIGAR, habilita botão DESLIGAR
        # - Se partida não foi escolhida: desabilita botão LIGAR
        
        partida_escolhida = self.spinner_partida.text != 'Escolha Partida'
        
        if motor_ligado:
            # Motor está LIGADO
            self.btn_ligar.disabled = True  # Não pode ligar novamente
            self.btn_desligar.disabled = False  # Pode desligar
            self.motor_status_label.text = f'MOTOR LIGADO ({self.spinner_partida.text})'
            self.motor_status_label.color = CORES['sucesso']
        else:
            # Motor está DESLIGADO
            self.btn_ligar.disabled = not partida_escolhida  # Só pode ligar se partida foi escolhida
            self.btn_desligar.disabled = True  # Não pode desligar se já está desligado
            self.motor_status_label.text = 'MOTOR DESLIGADO'
            self.motor_status_label.color = CORES['erro']
        
        # Atualiza estado das válvulas
        for i, switch in self.valves.items():
            state = modbus.read_tag(f'co.xv{i}') == 1
            if switch.active != state:
                switch.active = state

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
                
            # Confirmação para ligar
            content = BoxLayout(orientation='vertical', spacing=15, padding=15)
            content.add_widget(Label(text=f'Tem certeza que deseja LIGAR o motor?\n'
                                        f'Tipo de Partida: {self.spinner_partida.text}\n'
                                        f'Motor: {self.spinner_motor.text}', 
                                font_size=sp(16)))
            btn_box = BoxLayout(spacing=10, size_hint_y=None, height=sp(40))
            popup = Popup(title='Confirmação de Ação', content=content, size_hint=(None, None), 
                        size=(sp(400), sp(200)), title_align='center')
            btn_confirm = HoverButton(text='Confirmar', 
                                    on_press=lambda x: self.do_toggle_motor('LIGAR', popup))
            btn_cancel = HoverButton(text='Cancelar', on_press=popup.dismiss, 
                                background_color_normal=(0.7,0.7,0.7,1))
            btn_box.add_widget(btn_confirm)
            btn_box.add_widget(btn_cancel)
            content.add_widget(btn_box)
            popup.open()
            
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
            partida_map = {'Direta': 3, 'Soft-start': 1, 'Inversor': 2}
            motor_map = {'Verde': 1, 'Azul': 2}

            app.modbus.write_tag('co.sel_driver', partida_map.get(self.spinner_partida.text, 0))
            app.modbus.write_tag('co.tipo_motor', motor_map.get(self.spinner_motor.text, 0))

            # Se for partida por inversor, envia também a referência de frequência.
            if self.spinner_partida.text == 'Inversor':
                freq = self.inverter_frequency if self.inverter_frequency > 0 else 20
                app.modbus.write_tag('co.freq_ref', freq)
            
            # Escritas diretas nos registradores específicos por tipo de partida.
            # No modo simulação não existe app.modbus.client; por isso, apenas registra.
            if self.spinner_partida.text == 'Soft-start':
                if app.modbus.is_connected and app.modbus.mode == 'real' and app.modbus.client:
                    try:
                        with app.modbus.lock:
                            app.modbus.client.write_single_register(1317, 10)  # rampa aceleração
                            app.modbus.client.write_single_register(1318, 10)  # rampa desaceleração
                            app.modbus.client.write_single_register(1316, 1)   # liga soft-start
                        app.db.log_event('comando', '[COMPRESSOR] Registradores soft-start configurados (1316=1, 1317=10, 1318=10)')
                    except Exception as e:
                        print(f"Erro ao configurar soft-start: {e}")
                elif app.modbus.is_connected and app.modbus.mode == 'simulation':
                    app.db.log_event('comando', '[COMPRESSOR] Simulação: partida Soft-start selecionada')
                    
            elif self.spinner_partida.text == 'Inversor':
                freq = self.inverter_frequency if self.inverter_frequency > 0 else 20
                if app.modbus.is_connected and app.modbus.mode == 'real' and app.modbus.client:
                    try:
                        with app.modbus.lock:
                            app.modbus.client.write_single_register(1313, int(freq))  # velocidade inversor
                            app.modbus.client.write_single_register(1312, 1)          # liga inversor
                        app.db.log_event('comando', f'[COMPRESSOR] Registradores inversor configurados (1312=1, 1313={int(freq)})')
                    except Exception as e:
                        print(f"Erro ao configurar inversor: {e}")
                elif app.modbus.is_connected and app.modbus.mode == 'simulation':
                    app.db.log_event('comando', f'[COMPRESSOR] Simulação: partida Inversor selecionada com {int(freq)} Hz')

            elif self.spinner_partida.text == 'Direta':
                if app.modbus.is_connected and app.modbus.mode == 'simulation':
                    app.db.log_event('comando', '[COMPRESSOR] Simulação: partida Direta selecionada')
                
            app.modbus.comandoMotor(1)
                
        else:  # DESLIGAR
            app.modbus.comandoMotor(0)

            # Só escreve nos registradores reais se houver cliente Modbus real.
            if app.modbus.is_connected and app.modbus.mode == 'real' and app.modbus.client:
                try:
                    with app.modbus.lock:
                        app.modbus.client.write_single_register(1316, 0)  # desligar soft-start
                        app.modbus.client.write_single_register(1312, 0)  # desligar inversor
                    app.db.log_event('comando', '[COMPRESSOR] Comandos de desligamento enviados aos registradores 1316 e 1312')
                except Exception as e:
                    print(f"Erro ao desligar registradores de partida: {e}")
            elif app.modbus.is_connected and app.modbus.mode == 'simulation':
                app.db.log_event('comando', '[COMPRESSOR] Simulação: motor desligado')

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

