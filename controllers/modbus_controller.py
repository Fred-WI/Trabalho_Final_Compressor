import logging
logger = logging.getLogger("SCADA_ModbusController")

logging.getLogger("pyModbusTCP.client").setLevel(logging.WARNING)
logging.getLogger("pyModbusTCP.server").setLevel(logging.WARNING)

import os
import platform
import random
import threading
import time

from pyModbusTCP.client import ModbusClient
from pymodbus.exceptions import ConnectionException

from controllers.config_load import load_tags, load_configs

from controllers.simulador_clp import CompressorSimulator


class ModbusController:
    def __init__(self, app):
        self.app = app
        self.mode = None
        self.client = None
        self.is_connected = False
        self.lock = threading.Lock()

        self.polling_thread = None
        self.simulator_server = None
        self.simulator_thread = None

        self._build_tag_map()
        self._build_config_map()
        self._initialize_tags()


    # Inicialização de configs_map, tags_addrs e tags
    def _build_config_map(self): self.configs_map = load_configs('config/app_config.json')
    def _build_tag_map(self): self.tags_addrs = load_tags('config/tags_compressor.json')
    def _initialize_tags(self): self.tags = {tag: 0.0 for tag in self.tags_addrs.keys()}
    
    # Conexão
    def connect(self, mode, ip='127.0.0.1', port=502):
        self.disconnect()
        self.mode = mode

        net_cfg = self.configs_map["network"].get(mode, self.configs_map["network"]["simulation"])
        target_ip = ip if (ip and ip.strip() != "") else net_cfg["ip"]
        port = net_cfg["port"]
        timeout = net_cfg.get("timeout", 3)

        if mode == 'simulation':
            logger.info("Iniciando conexão com o Servidor Modbus Simulado local em outra Thread...")
            
            self.simulator_thread = threading.Thread(
                target= self._run_simulator_server,
                args=(target_ip, port),
                daemon=True
            )
            
            self.simulator_thread.start()
            time.sleep(0.5)

        # Teste de ping
        if mode != 'simulation':
            param = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
            redir = '> NUL 2>&1' if platform.system().lower() == 'windows' else '> /dev/null 2>&1'
            if os.system(f"ping {param} {ip} {redir}") != 0:
                return False, f"Falha no Ping: Host {ip} inacessível."

        # Tentativa de conexão Modbus TCP
        try:
            self.client = ModbusClient(host=target_ip, port=port, timeout=timeout)
            self.is_connected = self.client.open() 

            if self.is_connected:
                self.polling_thread = threading.Thread(target=self._real_data_polling_loop, daemon=True)
                self.polling_thread.start()
                return True, f"Conectado ao CLP em {ip}"
            else:
                self._stop_simulator()
                return False, f"Falha na conexão Modbus com {ip}"
        except Exception as e:
            self._stop_simulator()
            return False, f"Erro de conexão: {e}"

    def _stop_simulator(self):
        """Para o servidor do professor e aguarda a thread morrer."""
        if self.simulator_server:
            self.simulator_server.stop()
            self.simulator_server = None
            
        if self.simulator_thread and self.simulator_thread.is_alive():
            self.simulator_thread.join(timeout=1.0)
            self.simulator_thread = None

    def disconnect(self):
        self.is_connected = False
        
        # 1. Para a leitura de dados do SCADA
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=1.5)
            self.polling_thread = None
            
        # 2. Fecha a conexão do Cliente
        if self.client:
            self.client.close()
            self.client = None
            
        self.mode = None
        self._initialize_tags()
        
        # 3. Derruba a Thread da simulação (se houver)
        self._stop_simulator()

    def get_motor_status(self):
        """Retorna True se o motor estiver ligado.

        No modo real, o estado é lido do CLP.
        No modo simulação, o estado é lido diretamente da tag interna
        co.habilita, pois não existe self.client no simulador.
        """
        if not self.is_connected: return False
            
        try:
            with self.lock:
                if not self.client: return False

                # Lê qual tipo de partida está selecionada no CLP
                addr_indica = self.tags_addrs["sys.indica_driver"]["address"]
                indica_driver_regs = self.client.read_holding_registers(addr_indica, 1)
                
                if not indica_driver_regs: return False    
                indica_driver = indica_driver_regs[0]

                mapa_tags_estado = {
                    1: "sys.estado_softstarter",
                    2: "sys.estado_inversor",
                    3: "sys.estado_direta"
                }

                tag_alvo = mapa_tags_estado.get(indica_driver, "sys.estado_direta")
                addr_estado = self.tags_addrs[tag_alvo]["address"]
                
                # Lê o estado atual baseado no tipo de partida
                estado_regs = self.client.read_holding_registers(addr_estado, 1)
                if estado_regs:
                    return estado_regs[0] == 1
            return False
            
        except Exception as e:
            self.app.db.log_event('erro', f'Erro ao verificar estado do motor: {e}')
            return False

    def comandoMotor(self, commandType):
        """Liga ou desliga o motor.

        commandType = 1 -> ligar
        commandType = 0 -> desligar

        No modo simulação, não existe comunicação Modbus real. Por isso,
        o comando apenas altera as tags internas usadas pelo simulador.
        No modo real, o comando é enviado ao CLP pelo registrador correto.
        """
        if not self.is_connected:
            self.app.db.log_event('erro', 'Tentativa de comando motor sem conexão')
            return False

        commandType = int(commandType)
        tipos_nome = self.configs_map["tipos_partida"]
            
        try:
            with self.lock:
                if not self.client: return False

                addr_indica = self.tags_addrs["sys.indica_driver"]["address"]

                tipo_partida_regs = self.client.read_holding_registers(addr_indica, 1)
                if not tipo_partida_regs:
                    self.app.db.log_event('erro', 'Falha ao ler tipo de partida')
                    return False
                    
                tipo_partida = tipo_partida_regs[0]
            
            # Endereços de comando para cada tipo de partida
            mapa_tags_cmd = {
                0: "sys.cmd_direta",
                1: "sys.cmd_softstarter",
                2: "sys.cmd_inversor",
                3: "sys.cmd_direta"
            }
            
            tag_cmd_alvo = mapa_tags_cmd.get(tipo_partida, "sys.cmd_direta")
            endereco_comando = self.tags_addrs[tag_cmd_alvo]["address"]
            
            with self.lock:
                success = self.client.write_single_register(endereco_comando, commandType)
                
            if success:
                acao = 'LIGADO' if commandType == 1 else 'DESLIGADO'
                nome_partida = tipos_nome.get(str(tipo_partida), "Desconhecida")
                self.app.db.log_event('comando', f'[COMPRESSOR] Motor {acao} - Partida: {nome_partida}')
                self.tags['co.habilita'] = float(commandType)
                return True
            return False
                
        except Exception as e:
            self.app.db.log_event('erro', f'Erro no comando motor: {e}')
            return False

    def clique_motor(self):
        """
        Método para alternar estado do motor baseado no estado atual
        """
        if not self.is_connected: return False
        motor_ligado = self.get_motor_status()
        novo_comando = 0 if motor_ligado else 1
        return self.comandoMotor(novo_comando)

    def troca_partida(self, tipo_partida):
        if self.get_motor_status(): return False
        
        addr_troca = self.tags_addrs["sys.cmd_troca_partida"]["address"]
        with self.lock:
            self.client.write_single_register(addr_troca, tipo_partida)
        return True

    def write_tag(self, tag_name, value):
        if tag_name not in self.tags_addrs:
            logger.warning(f"Tentativa de escrita em tag inexistente: {tag_name}")
            return False
        
        tag_info = self.tags_addrs[tag_name]
        if tag_info.get("rw") == "R":
            logger.warning(f"Tentativa de escrita na tag Somente Leitura: {tag_name}")
            return False
        
        address = tag_info["address"]
        div = tag_info.get("div", 1)

        if not self.is_connected: return

        with self.lock: 
            self.tags[tag_name] = float(value)
        
        try:
            with self.lock:
                bit_val = tag_info.get('bit')
                if bit_val != "" and bit_val is not None:
                    bit = int(bit_val)
                    regs = self.client.read_holding_registers(address, 1)
                    if regs:
                        reg_val = regs[0]
                        new_val = reg_val | (1 << bit) if value == 1 else reg_val & ~(1 << bit)
                        self.client.write_single_register(address, new_val)
                    else:
                        logger.error(f"Falha de leitura ao preparar escria no bit {bit}  do registrador {address}")
                elif tag_info['type'] == 'FP':
                    regs_to_write = self._float32_to_registers(value / div)
                    self.client.write_multiple_registers(address, regs_to_write)
                else:
                    self.client.write_single_register(address, int(value * div))
            
                self.app.db.log_event('comando', f'[COMPRESSOR] Tag {tag_name} escrita com valor {value}')
                return True
        except (ConnectionException, AttributeError) as e:
            logger.error(f"Erro de escrita Modbus: {e}. Desconectando..."); self.is_connected = False
            self.app.db.log_event('erro', f"Falha de conexão na escrita em {tag_name}")
        except Exception as e:
            logger.error(f"Erro de escrita Modbus: {e}")
            self.app.db.log_event('erro', f"Falha de escrita em {tag_name}")
        return False

    def read_tag(self, tag): 
        with self.lock: return self.tags.get(tag, 0)

    def get_tag_info(self, tag): 
        return self.tags_addrs.get(tag, {})

    def _float32_to_registers(self, value):
        """Converte um float32 do Python em dois registradores de 16 bits.
        Faz o inverso exato da função _converter_float32_from_registers.
        """
        # Word order little: [low_word, high_word] -> high_word primeiro
        import struct
        raw_bytes = struct.pack('>f', float(value))
        high_word = int.from_bytes(raw_bytes[0:2], byteorder='big')
        low_word = int.from_bytes(raw_bytes[2:4], byteorder='big')
        return [low_word, high_word]

    def _float32_from_registers(self, regs):
        """Converte dois registradores Modbus de 16 bits em float32.

        A ordem abaixo mantém compatibilidade com a correção feita para substituir
        BinaryPayloadDecoder em versões novas do PyModbus. Caso a bancada use
        outra ordem de bytes/palavras, basta alterar esta função.
        """
        # Word order little: [low_word, high_word] -> high_word primeiro
        import struct
        if not regs or len(regs) < 2: return 0.0
        raw = int(regs[1]).to_bytes(2, byteorder='big') + int(regs[0]).to_bytes(2, byteorder='big')
        return struct.unpack('>f', raw)[0]

    def _real_data_polling_loop(self):
        tickrate = self.configs_map["network"].get(self.mode, self.configs_map["network"]["simulation"]).get("tickrate", 1.0)

        while self.is_connected:
            start_time = time.time()
            try:
                with self.lock:
                    for tag, info in self.tags_addrs.items():
                        addr, div, val = info["address"], info.get('div', 1), 0.0
                        try:
                            if info['type'] == '4X':
                                regs = self.client.read_holding_registers(addr, 1)
                                if regs:
                                    bit_val = info.get("bit")
                                    if bit_val != "" and bit_val is not None:
                                        val = (regs[0] >> int(bit_val)) & 1
                                    else:
                                        val = regs[0]
                            
                            elif info['type'] == 'FP':
                                regs = self.client.read_holding_registers(addr, 2)
                                if regs:
                                    val = self._float32_from_registers(regs)
                            
                            self.tags[tag] = val / div if div != 0 else val
                        except Exception as e:
                            pass

                # # --- ADICIONE ESTE PRINT PARA DEBUG ---
                # pressao_kivy = self.tags.get('co.pressao_reservatorio', 0.0)
                # tensao_kivy = self.tags.get('co.tensao_rs', 0.0)
                # habilita_kivy = self.tags.get('co.habilita', 0.0)
                
                # print(f"[KIVY SCADA] Lendo -> Habilita: {habilita_kivy} | Tensão RS: {tensao_kivy:.1f} | Pressão: {pressao_kivy:.2f}")
                
                
                self.app.db.log_reading(self.tags)
                elapsed = time.time() - start_time
                if elapsed < tickrate: time.sleep(tickrate - elapsed)
            except (ConnectionException, AttributeError) as e: 
                logger.error(f"Polling Modbus falhou: {e}.")
                self.is_connected = False
            except Exception as e: 
                logger.error(f"Erro inesperado no polling: {e}")

    def _run_simulator_server(self, ip, port):
        """
        Este método rodará isolado na simulator_thread.
        """
        try:
            self.simulator_server = CompressorSimulator(host=ip, port=port)
            self.simulator_server.start()
            
            # Mantém a thread viva enquanto o servidor estiver rodando
            while getattr(self.simulator_server, 'running', False):
                time.sleep(1.0)
                
        except Exception as e:
            print(f"Erro Crítico no Servidor de Simulação: {e}")