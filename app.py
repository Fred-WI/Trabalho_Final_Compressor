import kivy
kivy.require('2.3.0')

import os
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, FadeTransition

from config import CORES
from controllers.modbus_controller import ModbusController
from database.database_manager import DatabaseManager
from ui.conexao_screen import ConexaoScreen
from ui.dashboard_screen import DashboardScreen
from ui.valvulas_screen import ValvulasScreen
from ui.eletrica_screen import EletricaScreen
from ui.graficos_screen import GraficosScreen
from ui.historico_screen import HistoricoScreen
from ui.bd_screen import BDScreen
from ui.about_screen import AboutScreen


class CompressorApp(App):
    def build(self):
        Window.clearcolor = CORES['fundo']
        Window.size = (1600, 900)
        self.title = "COMPRESSOR INDUSTRIAL"

        self.db = DatabaseManager()
        self.modbus = ModbusController(self)

        sm = ScreenManager(transition=FadeTransition(duration=0.2))
        screens = [
            ConexaoScreen(),
            DashboardScreen(),
            ValvulasScreen(),
            EletricaScreen(),
            GraficosScreen(),
            HistoricoScreen(),
            BDScreen(),
            AboutScreen(),
        ]
        for screen in screens:
            sm.add_widget(screen)
        return sm

    def on_start(self):
        self.db.log_event('sistema', 'Aplicação COMPRESSOR iniciada.')
        print("=== COMPRESSOR INDUSTRIAL INICIADO ===")

    def on_stop(self):
        self.db.log_event('sistema', 'Aplicação COMPRESSOR encerrada.')
        self.modbus.disconnect()
        print("=== COMPRESSOR ENCERRADO ===")
