import threading
import time
from pyModbusTCP.server import ModbusServer

# Importando os modelos físicos
from controllers.simulador.Tanque import Tanque
from controllers.config_load import load_tags

import random

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
                self.server.data_bank.set_holding_registers(addr, [0, 0])
            else:
                self.server.data_bank.set_holding_registers(addr, [0])
        print(f"Memória do CLP simulado inicializada com {len(self.tags_addrs)} tags.")

    def _set_float(self, address, value):
        """Grava um Float32 (em 2 registradores) no DataBank."""
        import struct
        raw_bytes = struct.pack('>f', float(value))
        high_word = int.from_bytes(raw_bytes[0:2], byteorder='big')
        low_word = int.from_bytes(raw_bytes[2:4], byteorder='big')
        self.server.data_bank.set_holding_registers(address, [low_word, high_word])

    def _get_float(self, address):
        """Lê um Float32 (de 2 registradores) do DataBank."""
        import struct
        words = self.server.data_bank.get_holding_registers(address, 2)
        if not words or len(words) < 2: 
            return 0.0
        raw = int(words[1]).to_bytes(2, byteorder='big') + int(words[0]).to_bytes(2, byteorder='big')
        return struct.unpack('>f', raw)[0]

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
            words = self.server.data_bank.get_holding_registers(addr, 2)
            if not words or len(words) < 2: return 0.0
            import struct
            raw = int(words[1]).to_bytes(2, 'big') + int(words[0]).to_bytes(2, 'big')
            val = struct.unpack('>f', raw)[0]
            return val / div if div != 0 else val
        else:
            words = self.server.data_bank.get_holding_registers(addr, 1)
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
            self.server.data_bank.set_holding_registers(addr, [low_word, high_word])
        else:
            bit = info.get("bit")
            if bit != "" and bit is not None:
                words = self.server.data_bank.get_holding_registers(addr, 1)
                reg_val = words[0] if words else 0
                new_val = reg_val | (1 << int(bit)) if int(value) == 1 else reg_val & ~(1 << int(bit))
                self.server.data_bank.set_holding_registers(addr, [new_val])
            else:
                self.server.data_bank.set_holding_registers(addr, [int(val_to_write)])

    # =========================================================================
    # LOOP DA FÍSICA DO SISTEMA
    # =========================================================================

    def _physics_loop(self):
        estado_motor_interno = False

        while self.running:
            # -----------------------------------------------------------
            # 1. LEITURA (INPUTS DO SCADA)
            # -----------------------------------------------------------
            # Lê qual partida está selecionada (1: Soft, 2: Inversor, 3: Direta)
            sel_driver = int(self._read_tag("co.sel_driver") or 3)
            
            cmd_soft = int(self._read_tag("sys.cmd_softstarter"))
            cmd_inv  = int(self._read_tag("sys.cmd_inversor"))
            cmd_dir  = int(self._read_tag("sys.cmd_direta"))

            if cmd_soft == 1 or cmd_inv == 1 or cmd_dir == 1:
                estado_motor_interno = True

            elif cmd_soft == 0 or cmd_inv == 0 or cmd_dir == 0:
                if sel_driver == 1: estado_motor_interno = bool(cmd_soft)
                elif sel_driver == 2: estado_motor_interno = bool(cmd_inv)
                else: estado_motor_interno = bool(cmd_dir)

            # Busca o comando de ligar (motorState) e define o tempo de aceleração
            if sel_driver == 1: t_partida = 10.0
            elif sel_driver == 2: t_partida = 5.0
            else: t_partida = 0.2
                
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
            self.__tank.TankSimulation(freq_ref, t_partida, estado_motor_interno, xv_states)

            # -----------------------------------------------------------
            # 3. ESCRITA (FEEDBACK PARA O SCADA LER)
            # -----------------------------------------------------------
            # Atualiza indicadores de painel (Diz ao SCADA o que de fato está rodando)
            self._write_tag("sys.indica_driver", sel_driver)
            self._write_tag("sys.estado_softstarter", 1 if (estado_motor_interno and sel_driver == 1) else 0)
            self._write_tag("sys.estado_inversor", 1 if (estado_motor_interno and sel_driver == 2) else 0)
            self._write_tag("sys.estado_direta", 1 if (estado_motor_interno and sel_driver == 3) else 0)

            pressao_atual = self.__tank.getPressao()
            rpm_atual = self.__tank.motor.getRotacao()
            
            # Escreve as grandezas contínuas calculadas pelos modelos físicos
            self._write_tag("co.pressao", pressao_atual)
            self._write_tag("co.encoder", rpm_atual)

            if rpm_atual < 1.0:
                torque_realista = 0
            else:
                torque_base = self.__tank.motor.getTorque()
                esforco_compressor = pressao_atual * 0.45
                torque_realista = torque_base + esforco_compressor + random.uniform(-0.02, 0.02)


            self._write_tag("co.torque", torque_realista)
            self._write_tag("co.temp_carc", self.__tank.motor.getTemperature() + random.uniform(-1, 1))
            self._write_tag("co.corrente_media", self.__tank.motor.getCorrente())

            # ===========================================================
            # MULTIMEDIDOR VIRTUAL (Flutuação contínua independente do motor)
            # ===========================================================
            
            # A rede elétrica oscila em torno de 220V
            ruido_tensao = lambda: 220.0 + random.uniform(-1.5, 1.5)
            self._write_tag("co.tensao_rs", ruido_tensao())
            self._write_tag("co.tensao_st", ruido_tensao())
            self._write_tag("co.tensao_tr", ruido_tensao())
            
            # Frequência da rede elétrica oscila levemente em torno de 60Hz
            self._write_tag("co.frequencia", 60.0 + random.uniform(-0.1, 0.1))

            # Corrente real do motor somada ao ruído dos sensores (Transformadores de Corrente - TCs)
            corrente_real = self.__tank.motor.getCorrente()
            corrente_media_com_ruido = corrente_real + random.uniform(-0.02, 0.02)
            self._write_tag("co.corrente_r", corrente_real + random.uniform(-0.05, 0.05))
            self._write_tag("co.corrente_s", corrente_real + random.uniform(-0.05, 0.05))
            self._write_tag("co.corrente_t", corrente_real + random.uniform(-0.05, 0.05))
            self._write_tag("co.corrente_media", corrente_media_com_ruido)

            valvulas_abertas = sum(xv_states[1:6])
            pressao_atual = self.__tank.getPressao()
            rpm_atual = self.__tank.motor.getRotacao()

            vazao_calculada = pressao_atual * valvulas_abertas * 2.5

            vazao_fit02 = vazao_calculada + random.uniform(-0.2, 0.2) if valvulas_abertas > 0 else 0.0

            self._write_tag("co.fit02", max(0.0, vazao_fit02))

            pot_aparente = (1.732 * 220.0 * corrente_real) / 1000.0

            if estado_motor_interno:
                fp_total = 0.85 + random.uniform(-0.02, 0.02)
            else:
                fp_total = 0.0

            pot_ativa = pot_aparente * fp_total

            if pot_aparente > pot_ativa:
                pot_reativa = (pot_aparente**2-pot_ativa**2)**0.5
            else:
                pot_reativa = 0.0

            self._write_tag("co.aparente_total", pot_aparente)
            self._write_tag("co.ativa_total", pot_ativa)
            self._write_tag("co.reativa_total", pot_reativa)
            self._write_tag("co.fp_total", fp_total)
            
            # try:
            #     pressao_sim = self.__tank.getPressao()
            #     rpm_sim = self.__tank.motor.getRotacao()
            #     # Lê direto do DataBank para ver se gravou mesmo (ex: Tensão R-S no endereço 732, verifique o seu endereço no JSON)
            #     addr_tensao = self.tags_addrs.get("co.tensao_rs", {}).get("address", 0)
            #     words_tensao = self.server.data_bank.get_holding_registers(addr_tensao, 2)
                
                # print(f"[SIMULADOR] Física -> RPM: {rpm_sim:.1f} | Pressão: {pressao_sim:.2f}")
                # print(f"[SIMULADOR] Memória Modbus -> Endereço {addr_tensao} contém: {words_tensao}")
            # except Exception as debug_e:
            #     print(f"Erro no debug do simulador: {debug_e}")
            time.sleep(self.__tick)