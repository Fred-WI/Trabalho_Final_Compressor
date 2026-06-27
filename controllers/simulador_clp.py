import threading
import time
from pyModbusTCP.server import ModbusServer

# Importando os modelos físicos
from controllers.simulador.Tanque import Tanque
from controllers.config_load import load_tags

class CompressorSimulator:
    __tick = 0.1

    def __init__(self, host='127.0.0.1', port=502):
        # Inicializa a termodinâmica do reservatório (ele já cria o Motor internamente)
        self.__tank = Tanque(self.__tick)
        
        # Configuração do Servidor Modbus
        self.server = ModbusServer(host=host, port=port, no_block=True)
        self.running = False
        self.sim_thread = None
        
        # Carrega as tags da mesma fonte da verdade que o SCADA utiliza
        self.tags_addrs = load_tags('config/tags_compressor.json')
        
        self._initialize_databank()

    def _initialize_databank(self):
        """Aloca a memória inicial do servidor baseado no JSON."""
        for info in self.tags_addrs.values():
            addr = info["address"]
            if info["type"] == "FP":
                self.server.data_bank.set_words(addr, [0, 0])
            else:
                self.server.data_bank.set_words(addr, [0])
        print(f"Memória do CLP simulado inicializada com {len(self.tags_addrs)} tags.")

    def start(self):
        self.server.start()
        self.running = True
        self.sim_thread = threading.Thread(target=self._physics_loop, daemon=True)
        self.sim_thread.start()
        print(f"Servidor CLP Simulado rodando em {self.server.host}:{self.server.port}")
        
    def stop(self):
        self.running = False
        if hasattr(self, 'server') and self.server:
            self.server.stop()

        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join()
        print("Servidor CLP Simulado encerrado.")

    # =========================================================================
    # HELPERS INTELIGENTES DE LEITURA/ESCRITA BASEADOS NO JSON
    # =========================================================================
    
    def _read_tag(self, tag_name):
        """Lê um valor do DataBank usando as configurações do JSON."""
        info = self.tags_addrs.get(tag_name)
        if not info: return 0.0
        
        addr = info["address"]
        div = info.get("div", 1)
        
        if info["type"] == "FP":
            words = self.server.data_bank.get_words(addr, 2)
            if not words or len(words) < 2: return 0.0
            import struct
            raw = int(words[1]).to_bytes(2, 'big') + int(words[0]).to_bytes(2, 'big')
            val = struct.unpack('>f', raw)[0]
            return val / div if div != 0 else val
        else:
            words = self.server.data_bank.get_words(addr, 1)
            val = words[0] if words else 0
            bit = info.get("bit")
            if bit != "" and bit is not None:
                return (val >> int(bit)) & 1
            return val / div if div != 0 else val

    def _write_tag(self, tag_name, value):
        """Escreve um valor no DataBank usando as configurações do JSON."""
        info = self.tags_addrs.get(tag_name)
        if not info: return
        
        addr = info["address"]
        div = info.get("div", 1)
        val_to_write = float(value * div)
        
        if info["type"] == "FP":
            import struct
            raw_bytes = struct.pack('>f', val_to_write)
            high_word = int.from_bytes(raw_bytes[0:2], 'big')
            low_word = int.from_bytes(raw_bytes[2:4], 'big')
            self.server.data_bank.set_words(addr, [low_word, high_word])
        else:
            bit = info.get("bit")
            if bit != "" and bit is not None:
                words = self.server.data_bank.get_words(addr, 1)
                reg_val = words[0] if words else 0
                new_val = reg_val | (1 << int(bit)) if int(value) == 1 else reg_val & ~(1 << int(bit))
                self.server.data_bank.set_words(addr, [new_val])
            else:
                self.server.data_bank.set_words(addr, [int(val_to_write)])

    # =========================================================================
    # LOOP DA FÍSICA DO SISTEMA
    # =========================================================================

    def _physics_loop(self):
        while self.running:
            # -----------------------------------------------------------
            # 1. LEITURA (INPUTS DO SCADA)
            # -----------------------------------------------------------
            # Lê qual partida está selecionada (1: Soft, 2: Inversor, 3: Direta)
            sel_driver = int(self._read_tag("co.sel_driver") or 3)
            
            # Busca o comando de ligar (motorState) e define o tempo de aceleração
            if sel_driver == 1:
                motor_on = bool(self._read_tag("sys.cmd_softstarter"))
                t_partida = 10.0 # Rampa suave do Soft-Starter
            elif sel_driver == 2:
                motor_on = bool(self._read_tag("sys.cmd_inversor"))
                t_partida = 5.0 # Rampa média do Inversor
            else:
                motor_on = bool(self._read_tag("sys.cmd_direta"))
                t_partida = 0.2 # Rampa violenta da Partida Direta
                
            freq_ref = self._read_tag("co.freq_ref")
            if freq_ref <= 0: freq_ref = 60.0
            
            # Extrai o estado das válvulas solenoides
            xv_states = [
                bool(self._read_tag("co.xv1")), bool(self._read_tag("co.xv2")),
                bool(self._read_tag("co.xv3")), bool(self._read_tag("co.xv4")),
                bool(self._read_tag("co.xv5")), bool(self._read_tag("co.xv6"))
            ]

            # -----------------------------------------------------------
            # 2. FÍSICA (EXECUTA 1 PASSO DA MATEMÁTICA)
            # -----------------------------------------------------------
            self.__tank.TankSimulation(freq_ref, t_partida, motor_on, xv_states)

            # -----------------------------------------------------------
            # 3. ESCRITA (FEEDBACK PARA O SCADA LER)
            # -----------------------------------------------------------
            # Atualiza indicadores de painel (Diz ao SCADA o que de fato está rodando)
            self._write_tag("sys.indica_driver", sel_driver)
            self._write_tag("sys.estado_softstarter", 1 if (motor_on and sel_driver == 1) else 0)
            self._write_tag("sys.estado_inversor", 1 if (motor_on and sel_driver == 2) else 0)
            self._write_tag("sys.estado_direta", 1 if (motor_on and sel_driver == 3) else 0)
            
            # Escreve as grandezas contínuas calculadas pelos modelos físicos
            self._write_tag("co.pressao_reservatorio", self.__tank.getPressao())
            self._write_tag("co.encoder", self.__tank.motor.getRotacao())
            self._write_tag("co.torque", self.__tank.motor.getTorque())
            self._write_tag("co.temp_carc", self.__tank.motor.getTemperature())
            self._write_tag("co.corrente_media", self.__tank.motor.getCorrente())
            
            time.sleep(self.__tick)