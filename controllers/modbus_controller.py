import os
import platform
import random
import threading
import time

from pyModbusTCP.client import ModbusClient
from pymodbus.exceptions import ConnectionException

class ModbusController:
    def __init__(self, app):
        self.app = app; self.mode = None; self.client = None; self.is_connected = False
        self.lock = threading.Lock(); self.polling_thread = None
        self._build_tag_map(); self._initialize_tags()

    def _build_tag_map(self):
        self.tags_addrs = {
            "ro.encoder": {"type":"FP","address":884,"div":1,"unit":"Hz","db_col":"rotacao"}, 
            "ro.torque": {"type":"FP","address":1420,"div":1,"unit":"N·m","db_col":"torque"},
            "ro.pressostato": {"type":"4X","address":710,"div":1,"unit":""}, 
            "ro.temp_carc": {"type":"FP","address":706,"div":10,"unit":"°C","db_col":"temp_carc"},
            "ro.temp_r": {"type":"FP","address":700,"div":10,"unit":"°C"}, 
            "ro.temp_s": {"type":"FP","address":702,"div":10,"unit":"°C"},
            "ro.temp_t": {"type":"FP","address":704,"div":10,"unit":"°C"}, 
            "ro.corrente_r": {"type":"4X","address":840,"div":10,"unit":"A"},
            "ro.corrente_s": {"type":"4X","address":841,"div":10,"unit":"A"}, 
            "ro.corrente_t": {"type":"4X","address":842,"div":10,"unit":"A"},
            "ro.corrente_n": {"type":"4X","address":843,"div":10,"unit":"A"}, 
            "ro.fit02": {"type":"FP","address":716,"div":1,"unit":"L/min","db_col":"vazao_fit02"},
            "ro.fit03": {"type":"FP","address":718,"div":1,"unit":"L/min","db_col":"vazao_fit03"}, 
            "ro.tensao_rs": {"type":"4X","address":847,"div":10,"unit":"V"},
            "ro.tensao_st": {"type":"4X","address":848,"div":10,"unit":"V"}, 
            "ro.tensao_tr": {"type":"4X","address":849,"div":10,"unit":"V"},
            "ro.corrente_media": {"type":"4X","address":845,"div":10,"unit":"A"}, 
            "ro.pressao": {"type":"FP","address":714,"div":1,"unit":"bar","db_col":"pressao"},
            'ro.ativa_total': {'type':'4X','address':855,'div':1,'unit':'W',"db_col":"pot_ativa"}, 
            'ro.reativa_total': {'type':'4X','address':859,'div':1,'unit':'VAR',"db_col":"pot_reativa"},
            'ro.aparente_total': {'type':'4X','address':863,'div':1,'unit':'VA',"db_col":"pot_aparente"}, 
            'ro.fp_total': {'type':'4X','address':871,'div':1000,'unit':''},
            'ro.frequencia': {'type':'4X','address':830,'div':100,'unit':'Hz'}, 
            "co.xv1": {"type":"4X","address":712,"bit":0}, "co.xv2": {"type":"4X","address":712,"bit":1},
            "co.xv3": {"type":"4X","address":712,"bit":2}, "co.xv4": {"type":"4X","address":712,"bit":3},
            "co.xv5": {"type":"4X","address":712,"bit":4}, "co.xv6": {"type":"4X","address":712,"bit":5},
            "co.tipo_motor": {"type":"4X","address":708}, "co.sel_driver": {"type":"4X","address":1324},
            "co.freq_ref": {"type":"4X","address":1313,"div":1,"unit":"Hz"},
            "co.habilita": {"type":"4X","address":1328,"bit":1},
        }
    

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
        """Liga ou desliga o motor via Modbus TCP.

        commandType = 1 -> ligar
        commandType = 0 -> desligar

        O método funciona tanto para o CLP real quanto para o CLP simulado
        externo. A diferença agora é somente o IP/porta da conexão.
        """
        if not self.is_connected:
            self.app.db.log_event('erro', 'Tentativa de comando motor sem conexão')
            return False

        commandType = int(commandType)

        try:
            with self.lock:
                if not self.client:
                    self.app.db.log_event('erro', 'Cliente Modbus não inicializado')
                    return False

                # Tipo de partida selecionado: 1=Soft, 2=Inversor, 3=Direta
                tipo_regs = self.client.read_holding_registers(1324, 1)
                tipo_partida = tipo_regs[0] if tipo_regs else int(self.tags.get('co.sel_driver', 3) or 3)

                startTypeDictionary = {
                    1: 1316,  # Softstarter
                    2: 1312,  # Inversor
                    3: 1319,  # Partida direta
                }

                endereco_comando = startTypeDictionary.get(tipo_partida, 1319)
                success = self.client.write_single_register(endereco_comando, commandType)

            if success:
                tipo_nome = {1: 'Softstarter', 2: 'Inversor', 3: 'Direta'}
                acao = 'LIGADO' if commandType == 1 else 'DESLIGADO'
                self.tags['co.habilita'] = float(commandType)
                self.app.db.log_event('comando', f'[COMPRESSOR] Motor {acao} - Partida: {tipo_nome.get(tipo_partida, "Desconhecida")}')
                return True

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
        """Conecta o supervisório a um servidor Modbus TCP.

        Modo simulation:
            conecta no CLP simulado externo, rodando em outro terminal.
            Padrão: 127.0.0.1:5020

        Modo real:
            conecta no CLP real da bancada.
            Padrão aceito: 10.15.30.182:502
        """
        self.disconnect()
        self.mode = mode

        if mode == 'simulation':
            ip = '127.0.0.1'
            port = 5020
        else:
            # Validação do IP real da bancada
            if ip != '10.15.30.182':
                return False, "Erro: IP Inválido. Conecte-se a 10.15.30.182"

            # Teste de ping apenas no CLP real
            param = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
            redir = '> NUL 2>&1' if platform.system().lower() == 'windows' else '> /dev/null 2>&1'
            if os.system(f"ping {param} {ip} {redir}") != 0:
                return False, f"Falha no Ping: Host {ip} inacessível."

        try:
            self.client = ModbusClient(host=ip, port=port, timeout=3)
            self.is_connected = self.client.open()

            if self.is_connected:
                self.polling_thread = threading.Thread(target=self._real_data_polling_loop, daemon=True)
                self.polling_thread.start()
                if mode == 'simulation':
                    return True, f"Conectado ao CLP Simulado em {ip}:{port}"
                return True, f"Conectado ao CLP em {ip}:{port}"

            if mode == 'simulation':
                return False, "Falha ao conectar ao CLP Simulado."
            return False, f"Falha na conexão Modbus com {ip}:{port}"

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
    

    def write_tag(self, tag, value):
        if not self.is_connected or tag not in self.tags_addrs:
            return False

        info = self.tags_addrs[tag]
        addr = info['address']

        try:
            with self.lock:
                if not self.client:
                    self.app.db.log_event('erro', f'Cliente Modbus não inicializado ao escrever {tag}')
                    return False

                if info.get('bit') is not None:
                    regs = self.client.read_holding_registers(addr, 1)
                    if regs:
                        reg_val = regs[0]
                        bit = info['bit']
                        new_val = reg_val | (1 << bit) if int(value) == 1 else reg_val & ~(1 << bit)
                        success = self.client.write_single_register(addr, new_val)
                    else:
                        self.app.db.log_event('erro', f"Falha de leitura ao preparar escrita no bit {info['bit']} do registrador {addr}")
                        return False
                else:
                    div = info.get('div', 1)
                    success = self.client.write_single_register(addr, int(float(value) * div))

                if success:
                    self.tags[tag] = float(value)
                    self.app.db.log_event('comando', f'[COMPRESSOR] Tag {tag} escrita com valor {value}')
                    return True

                self.app.db.log_event('erro', f'Falha de escrita Modbus em {tag}')
                return False

        except (ConnectionException, AttributeError) as e:
            print(f"Erro de escrita Modbus: {e}. Desconectando...")
            self.is_connected = False
            self.app.db.log_event('erro', f"Falha de conexão na escrita em {tag}")
            return False
        except Exception as e:
            print(f"Erro de escrita Modbus: {e}")
            self.app.db.log_event('erro', f"Falha de escrita em {tag}: {e}")
            return False

    def troca_partida(self, tipo_partida):
        """Seleciona o tipo de partida no CLP.

        1 = Soft-start
        2 = Inversor
        3 = Direta
        """
        if not self.is_connected:
            return False

        if self.get_motor_status():
            return False

        return self.write_tag('co.sel_driver', int(tipo_partida))

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
        while self.is_connected and self.mode in ('real', 'simulation'):
            start_time = time.time()
            try:
                with self.lock:
                    # Correção: Lógica de leitura ajustada para pyModbusTCP e bug de bit corrigido
                    for tag, info in self.tags_addrs.items():
                        if tag.startswith('co_'):
                            continue
                        
                        addr, div, val = info["address"], info.get('div', 1), 0.0
                        try:
                            if info['type'] == '4X':
                                regs = self.client.read_holding_registers(addr, 1)
                                if regs:  # Leitura bem-sucedida, regs é uma lista (ex: [123])
                                    bit = info.get("bit")
                                    if bit is not None:
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
        self.tags['ro.temp_carc'] = 25.0
        self.tags['ro.pressao'] = 1.0
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
                    if self.tags['ro.encoder'] < target_rpm - aceleracao:
                        self.tags['ro.encoder'] += aceleracao
                    elif self.tags['ro.encoder'] > target_rpm + aceleracao:
                        self.tags['ro.encoder'] -= aceleracao
                    else:
                        self.tags['ro.encoder'] = target_rpm + random.uniform(-0.5, 0.5)

                    self.tags['ro.encoder'] = max(0, min(65.0, self.tags['ro.encoder']))
                    base_power = 4000 * (self.tags['ro.encoder'] / 60.0)**2
                    self.tags['ro.ativa_total'] = base_power + random.uniform(-100, 100)
                    self.tags['ro.reativa_total'] = base_power * 0.4 + random.uniform(-50, 50)
                    self.tags['ro.aparente_total'] = (self.tags['ro.ativa_total']**2 + self.tags['ro.reativa_total']**2)**0.5
                    self.tags['ro.fp_total'] = self.tags['ro.ativa_total'] / self.tags['ro.aparente_total'] if self.tags['ro.aparente_total'] > 0 else 1
                    self.tags['ro.torque'] = (self.tags['ro.ativa_total'] / (2 * 3.14159 * self.tags['ro.encoder'])) if self.tags['ro.encoder'] > 1 else 0
                    self.tags['ro.temp_carc'] = min(95, self.tags['ro.temp_carc'] + 0.2 * (self.tags['ro.encoder'] / 60.0) - 0.05)
                    self.tags['ro.corrente_media'] = (self.tags['ro.aparente_total'] / (220 * (3**0.5))) + random.uniform(-0.1, 0.1)
                else:
                    self.tags['ro.encoder'] = max(0, self.tags['ro.encoder'] - 4.0)
                    for tag in ['ro.ativa_total', 'ro.reativa_total', 'ro.aparente_total', 'ro.torque']:
                        self.tags[tag] *= 0.9
                    self.tags['ro.corrente_media'] = random.uniform(0.0, 0.05)
                    self.tags['ro.fp_total'] = 1.0
                    self.tags['ro.temp_carc'] = max(25.0, self.tags['ro.temp_carc'] - 0.1)

                self.tags['ro.tensao_rs'] = 220.0 + random.uniform(-2, 2)
                self.tags['ro.tensao_st'] = 220.0 + random.uniform(-2, 2)
                self.tags['ro.tensao_tr'] = 220.0 + random.uniform(-2, 2)
                self.tags['ro.corrente_r'] = self.tags['ro.corrente_media'] + random.uniform(-0.05, 0.05)
                self.tags['ro.corrente_s'] = self.tags['ro.corrente_media'] + random.uniform(-0.05, 0.05)
                self.tags['ro.corrente_t'] = self.tags['ro.corrente_media'] + random.uniform(-0.05, 0.05)
                self.tags['ro.corrente_n'] = random.uniform(0.0, 0.03)
                self.tags['ro.frequencia'] = self.tags['ro.encoder']

                # Lógica de pressão e vazão
                pressure_gen = (self.tags['ro.encoder'] / 60.0) * 1.5
                pressao_efetiva = max(0, self.tags['ro.pressao'] - 1.0)
                flow_loss = sum(0.8 for i in range(1, 7) if self.tags.get(f'co.xv{i}', 0)) * (pressao_efetiva / 9.0)
                self.tags['ro.pressao'] += (pressure_gen - flow_loss) * dt * 0.2
                self.tags['ro.pressao'] = max(1.0, min(10, self.tags['ro.pressao']))
                
                self.tags['ro.fit03'] = (15.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) if self.tags.get('co.xv1', 0) else 0.0
                self.tags['ro.fit02'] = sum((12.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) for i in range(2, 7) if self.tags.get(f'co.xv{i}', 0))
                
                self.app.db.log_reading(self.tags)
            time.sleep(dt)

# --- Gerenciador do Banco de Dados ---
