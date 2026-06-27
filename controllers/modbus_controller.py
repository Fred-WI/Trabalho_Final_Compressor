import logging
logger = logging.getLogger("SCADA_ModbusController")

import os
import platform
import random
import threading
import time

from pyModbusTCP.client import ModbusClient
from pymodbus.exceptions import ConnectionException

from controllers.tag_manager import load_tags


class ModbusController:
    def __init__(self, app):
        self.app = app; self.mode = None; self.client = None; self.is_connected = False
        self.lock = threading.Lock(); self.polling_thread = None
        self._build_tag_map(); self._initialize_tags()

    def _build_tag_map(self):
        self.tags_addrs = load_tags('config/tags_compressor.json')
    

    def get_motor_status(self):
        """Retorna True se o motor estiver ligado.

        No modo real, o estado é lido do CLP.
        No modo simulação, o estado é lido diretamente da tag interna
        co.habilita, pois não existe self.client no simulador.
        """
        if not self.is_connected:
            return False

        if self.mode == 'simulation':
            return self.tags.get('co.habilita', 0) == 1
            
        try:
            with self.lock:
                if not self.client:
                    return False

                # Lê qual tipo de partida está selecionada no CLP
                indica_driver_regs = self.client.read_holding_registers(1216, 1)
                if not indica_driver_regs:
                    return False
                    
                indica_driver = indica_driver_regs[0]
                
                # Lê o estado atual baseado no tipo de partida
                if indica_driver == 1:      # Softstarter
                    estado_regs = self.client.read_holding_registers(886, 1)
                elif indica_driver == 2:    # Inversor
                    estado_regs = self.client.read_holding_registers(888, 1)
                elif indica_driver == 3:    # Partida direta
                    estado_regs = self.client.read_holding_registers(890, 1)
                else:                       # Padrão - partida direta
                    estado_regs = self.client.read_holding_registers(890, 1)
                    
                if estado_regs:
                    return estado_regs[0] == 1
                    
            return False
            
        except Exception as e:
            self.app.db.log_event('erro', f'Erro ao verificar estado do motor: {e}')
            print(f"Erro ao verificar estado do motor: {e}")
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

        if self.mode == 'simulation':
            with self.lock:
                self.tags['co.habilita'] = float(commandType)

                # Se nenhuma partida foi selecionada, usa Direta como padrão.
                if self.tags.get('co.sel_driver', 0) == 0:
                    self.tags['co.sel_driver'] = 3.0

                # Se for inversor e a referência ainda estiver zerada,
                # usa 20 Hz como valor inicial para o motor sair do zeco.
                if self.tags.get('co.sel_driver', 0) == 2 and self.tags.get('co.freq_ref', 0) == 0:
                    self.tags['co.freq_ref'] = 20.0

            tipo_nome = {0: 'Indefinida', 1: 'Soft-start', 2: 'Inversor', 3: 'Direta'}
            tipo = int(self.tags.get('co.sel_driver', 0))
            acao = 'LIGADO' if commandType == 1 else 'DESLIGADO'
            self.app.db.log_event('comando', f'[COMPRESSOR] Simulação: Motor {acao} - Partida: {tipo_nome.get(tipo, "Desconhecida")}')
            return True
            
        try:
            with self.lock:
                if not self.client:
                    self.app.db.log_event('erro', 'Cliente Modbus não inicializado')
                    return False

                # Lê qual tipo de partida está selecionada
                tipo_partida_regs = self.client.read_holding_registers(1216, 1)
                if not tipo_partida_regs:
                    self.app.db.log_event('erro', 'Falha ao ler tipo de partida')
                    return False
                    
                tipo_partida = tipo_partida_regs[0]
            
            # Endereços de comando para cada tipo de partida
            startTypeDictionary = {
                0: 1319,  # Sem partida definida - usa direta
                1: 1316,  # Softstarter
                2: 1312,  # Inversor
                3: 1319,  # Partida direta
            }
            
            endereco_comando = startTypeDictionary.get(tipo_partida, 1319)
            
            with self.lock:
                success = self.client.write_single_register(endereco_comando, commandType)
                
            if success:
                tipo_nome = {0: 'Indefinida', 1: 'Softstarter', 2: 'Inversor', 3: 'Direta'}
                acao = 'LIGADO' if commandType == 1 else 'DESLIGADO'
                self.app.db.log_event('comando', f'[COMPRESSOR] Motor {acao} - Partida: {tipo_nome.get(tipo_partida, "Desconhecida")}')
                self.tags['co.habilita'] = float(commandType)
                return True
            else:
                self.app.db.log_event('erro', f'Falha ao enviar comando motor (tipo partida: {tipo_partida})')
                return False
                
        except Exception as e:
            self.app.db.log_event('erro', f'Erro no comando motor: {e}')
            print(f"Erro no comando motor: {e}")
            return False

    def clique_motor(self):
        """
        Método para alternar estado do motor baseado no estado atual
        """
        if not self.is_connected:
            return False
            
        # Verifica o estado atual
        motor_ligado = self.get_motor_status()
        
        # Alterna o estado: se está ligado, desliga; se está desligado, liga
        novo_comando = 0 if motor_ligado else 1
        
        return self.comandoMotor(novo_comando)


    def muda_motor_ui_on(self):
        """Atualiza a UI quando o motor é ligado"""
        # Esta função pode ser chamada para atualizar elementos visuais específicos
        pass
        
    def muda_motor_ui_off(self):
        """Atualiza a UI quando o motor é desligado"""
        # Esta função pode ser chamada para atualizar elementos visuais específicos
        pass

    def _initialize_tags(self): self.tags = {tag: 0.0 for tag in self.tags_addrs.keys()}

    def connect(self, mode, ip='127.0.0.1', port=502):
        self.disconnect()
        self.mode = mode

        if mode == 'simulation':
            self.is_connected = True
            self.polling_thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self.polling_thread.start()
            return True, "Conectado ao Simulador Interno"

        # Validação do IP
        if ip != '10.15.30.182':
            return False, "Erro: IP Inválido. Conecte-se a 10.15.30.182"

        # Teste de ping
        param = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
        redir = '> NUL 2>&1' if platform.system().lower() == 'windows' else '> /dev/null 2>&1'
        if os.system(f"ping {param} {ip} {redir}") != 0:
            return False, f"Falha no Ping: Host {ip} inacessível."

        # Tentativa de conexão Modbus TCP
        try:
            self.client = ModbusClient(host=ip, port=port, timeout=3)
            self.is_connected = self.client.open()  # <-- Correção aqui

            if self.is_connected:
                self.polling_thread = threading.Thread(target=self._real_data_polling_loop, daemon=True)
                self.polling_thread.start()
                return True, f"Conectado ao CLP em {ip}"
            else:
                return False, f"Falha na conexão Modbus com {ip}"
        except Exception as e:
            return False, f"Erro de conexão: {e}"

    def disconnect(self):
        self.is_connected = False
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=1.5)
        if self.client:
            self.client.close()
        self.client = None
        self.mode = None
        self._initialize_tags()
        
    def read_tag(self, tag):
        with self.lock: return self.tags.get(tag, 0)
    def get_tag_info(self, tag): return self.tags_addrs.get(tag, {})
    

    def write_tag(self, tag_name, value):

        if tag_name not in self.tags_addrs:
            logger.warning(f"Tentativa de escrita em tag inexistente: {tag_name}")
            return False
        
        tag_info = self.tags_addrs[tag_name]

        if tag_info.get("rw") == "R":
            logger.warning(f"Tentativa de escrita na tag Somente Leitura: {tag_name}")
            return False
        
        address = tag_info["address"]
        tag_type = tag_info["type"]
        div = tag_info.get("div", 1)

        if not self.is_connected: return

        with self.lock: 
            self.tags[tag_name] = float(value)

        if self.mode == 'simulation':
            # Log da ação mesmo em simulação
            self.app.db.log_event('comando', f'[COMPRESSOR] Simulação: Tag {tag_name} escrita com valor {value}')
            return
        
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
                        print(f"Erro de escrita Modbus: Falha ao ler o registrador {address} para modificar o bit.")
                        self.app.db.log_event('erro', f"Falha de leitura ao preparar escrita no bit {bit} do registrador {address}")
                else:
                    self.client.write_single_register(address, int(value * div))
            
                self.app.db.log_event('comando', f'[COMPRESSOR] Tag {tag_name} escrita com valor {value}')
        except (ConnectionException, AttributeError) as e:
            print(f"Erro de escrita Modbus: {e}. Desconectando..."); self.is_connected = False
            self.app.db.log_event('erro', f"Falha de conexão na escrita em {tag_name}")
        except Exception as e:
            print(f"Erro de escrita Modbus: {e}"); self.app.db.log_event('erro', f"Falha de escrita em {tag}")

    def troca_partida(self, tipo_partida):
        if self.get_motor_status():
            return False
        
        with self.lock:
            self.client.write_single_register(1324,tipo_partida)
        return True
    
    def _converter_float32(self, regs):
        """Converte dois registradores Modbus de 16 bits em float32.

        A ordem abaixo mantém compatibilidade com a correção feita para substituir
        BinaryPayloadDecoder em versões novas do PyModbus. Caso a bancada use
        outra ordem de bytes/palavras, basta alterar esta função.
        """
        import struct
        if not regs or len(regs) < 2:
            return 0.0

        # Word order little: [low_word, high_word] -> high_word primeiro
        raw = int(regs[1]).to_bytes(2, byteorder='big') + int(regs[0]).to_bytes(2, byteorder='big')
        return struct.unpack('>f', raw)[0]

    def _real_data_polling_loop(self):
        while self.is_connected and self.mode == 'real':
            start_time = time.time()
            try:
                with self.lock:
                    # Correção: Lógica de leitura ajustada para pyModbusTCP e bug de bit corrigido
                    for tag, info in self.tags_addrs.items():
                        
                        addr, div, val = info["address"], info.get('div', 1), 0.0
                        try:
                            if info['type'] == '4X':
                                regs = self.client.read_holding_registers(addr, 1)
                                if regs:  # Leitura bem-sucedida, regs é uma lista (ex: [123])
                                    bit_val = info.get("bit")
                                    if bit_val != "" and bit_val is not None:
                                        bit = int(bit_val)
                                        # Se for um bit, extrai o valor do bit (0 ou 1)
                                        val = (regs[0] >> bit) & 1
                                    else:
                                        # Se for um registrador inteiro
                                        val = regs[0]
                            
                            elif info['type'] == 'FP':
                                regs = self.client.read_holding_registers(addr, 2)
                                if regs:  # Leitura bem-sucedida, regs é uma lista (ex: [16560, 29860])
                                    val = self._converter_float32(regs)
                            
                            # Atualiza o valor da tag
                            self.tags[tag] = val / div if div != 0 else val

                        except Exception as e:
                            # Em caso de erro na leitura de uma tag específica, imprime e continua para a próxima
                            print(f"Aviso: Falha ao ler a tag '{tag}'. Erro: {e}")
                            pass
                self.app.db.log_reading(self.tags)
                elapsed = time.time() - start_time
                if elapsed < 1.0: time.sleep(1.0 - elapsed)
            except (ConnectionException, AttributeError) as e: print(f"Polling Modbus falhou: {e}."); self.is_connected = False
            except Exception as e: print(f"Erro inesperado no polling: {e}")


    def _simulation_loop(self):
        dt = 1.0
        self.tags['co.temp_carc'] = 25.0
        self.tags['co.pressao'] = 1.0
        self.tags['co.freq_ref'] = 20.0

        while self.is_connected and self.mode == 'simulation':
            with self.lock:
                motor_on = self.tags.get('co.habilita', 0) == 1
                tipo_partida = int(self.tags.get('co.sel_driver', 0))

                # Define comportamento diferente para cada partida:
                # 1 = Soft-start, 2 = Inversor, 3 = Direta.
                if tipo_partida == 1:          # Soft-start
                    target_rpm = 60.0
                    aceleracao = 1.5
                elif tipo_partida == 2:        # Inversor
                    target_rpm = float(self.tags.get('co.freq_ref', 20.0))
                    target_rpm = max(0.0, min(60.0, target_rpm))
                    aceleracao = 3.0
                else:                          # Direta ou padrão
                    target_rpm = 60.0
                    aceleracao = 8.0
                
                if motor_on:
                    if self.tags['co.encoder'] < target_rpm - aceleracao:
                        self.tags['co.encoder'] += aceleracao
                    elif self.tags['co.encoder'] > target_rpm + aceleracao:
                        self.tags['co.encoder'] -= aceleracao
                    else:
                        self.tags['co.encoder'] = target_rpm + random.uniform(-0.5, 0.5)

                    self.tags['co.encoder'] = max(0, min(65.0, self.tags['co.encoder']))
                    base_power = 4000 * (self.tags['co.encoder'] / 60.0)**2
                    self.tags['co.ativa_total'] = base_power + random.uniform(-100, 100)
                    self.tags['co.reativa_total'] = base_power * 0.4 + random.uniform(-50, 50)
                    self.tags['co.aparente_total'] = (self.tags['co.ativa_total']**2 + self.tags['co.reativa_total']**2)**0.5
                    self.tags['co.fp_total'] = self.tags['co.ativa_total'] / self.tags['co.aparente_total'] if self.tags['co.aparente_total'] > 0 else 1
                    self.tags['co.torque'] = (self.tags['co.ativa_total'] / (2 * 3.14159 * self.tags['co.encoder'])) if self.tags['co.encoder'] > 1 else 0
                    self.tags['co.temp_carc'] = min(95, self.tags['co.temp_carc'] + 0.2 * (self.tags['co.encoder'] / 60.0) - 0.05)
                    self.tags['co.corrente_media'] = (self.tags['co.aparente_total'] / (220 * (3**0.5))) + random.uniform(-0.1, 0.1)
                else:
                    self.tags['co.encoder'] = max(0, self.tags['co.encoder'] - 4.0)
                    for tag in ['co.ativa_total', 'co.reativa_total', 'co.aparente_total', 'co.torque']:
                        self.tags[tag] *= 0.9
                    self.tags['co.corrente_media'] = random.uniform(0.0, 0.05)
                    self.tags['co.fp_total'] = 1.0
                    self.tags['co.temp_carc'] = max(25.0, self.tags['co.temp_carc'] - 0.1)

                self.tags['co.tensao_rs'] = 220.0 + random.uniform(-2, 2)
                self.tags['co.tensao_st'] = 220.0 + random.uniform(-2, 2)
                self.tags['co.tensao_tr'] = 220.0 + random.uniform(-2, 2)
                self.tags['co.corrente_r'] = self.tags['co.corrente_media'] + random.uniform(-0.05, 0.05)
                self.tags['co.corrente_s'] = self.tags['co.corrente_media'] + random.uniform(-0.05, 0.05)
                self.tags['co.corrente_t'] = self.tags['co.corrente_media'] + random.uniform(-0.05, 0.05)
                self.tags['co.corrente_n'] = random.uniform(0.0, 0.03)
                self.tags['co.frequencia'] = self.tags['co.encoder']

                # Lógica de pressão e vazão
                pressure_gen = (self.tags['co.encoder'] / 60.0) * 1.5
                pressao_efetiva = max(0, self.tags['co.pressao'] - 1.0)
                flow_loss = sum(0.8 for i in range(1, 7) if self.tags.get(f'co.xv{i}', 0)) * (pressao_efetiva / 9.0)
                self.tags['co.pressao'] += (pressure_gen - flow_loss) * dt * 0.2
                self.tags['co.pressao'] = max(1.0, min(10, self.tags['co.pressao']))
                
                self.tags['co.fit03'] = (15.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) if self.tags.get('co.xv1', 0) else 0.0
                self.tags['co.fit02'] = sum((12.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) for i in range(2, 7) if self.tags.get(f'co.xv{i}', 0))
                
                self.app.db.log_reading(self.tags)
            time.sleep(dt)

# --- Gerenciador do Banco de Dados ---
