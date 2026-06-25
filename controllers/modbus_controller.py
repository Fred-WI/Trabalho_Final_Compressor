"""
Módulo de Controle Modbus TCP para o Sistema SCADA do Compressor.

Este módulo gerencia a comunicação com o Controlador Lógico Programável (CLP)
utilizando o protocolo Modbus TCP, mantendo as camadas de interface isoladas
das regras de negócio de automação. Inclui um Gêmeo Digital para simulações offline.
"""

import json
import logging
import os
import platform
import struct
import threading
import time

from pyModbusTCP.client import ModbusClient
from pymodbus.exceptions import ConnectionException

from controllers.plant_simulator import PlantSimulator

logger = logging.getLogger(__name__)

class ModbusController:
    """
    Gerenciador central de comunicação e aquisição de dados.

    Atua de forma assíncrona para garantir alta performance, utilizando
    Locks de granularidade fina para proteger a memória compartilhada
    entre as rotinas de polling e a interface gráfica (Kivy).
    """

    def __init__(self, app):
        """
        Inicializa o controlador Modbus.

        :param app: Instância principal do aplicativo Kivy.
        """
        self.app = app
        self.mode = None
        self.client = None
        self.is_connected = False
        self.lock = threading.Lock()
        self.polling_thread = None
        self.tags_addrs = {}
        self.tags = {}

        self.config = self._load_system_config()
        self._load_tag_map()
        self._initialize_tags()

    def _load_system_config(self):
        """
        Carrega os parâmetros de operação e rede a partir de um JSON.
        Se o arquivo não for encontrado, utiliza padrões de fábrica seguros.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, 'system_config.json')

        default_config = {
            "COMANDO_DESLIGAR": 0,
            "COMANDO_LIGAR": 1,
            "PARTIDA_INDEFINIDA": 0,
            "PARTIDA_SOFTSTARTER": 1,
            "PARTIDA_INVERSOR": 2,
            "PARTIDA_DIRETA": 3,
            "FREQ_PADRAO_INVERSOR": 20.0,
            "TICK_RATE_POLLING": 1.0,
            "TIMEOUT_MODBUS": 3.0
        }

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info("Configurações do sistema (system_config.json) carregadas.")
            return config
        except Exception as e:
            logger.warning(f"Aviso: Falha ao ler system_config.json ({e}). Usando padrões de fábrica.")
            return default_config

    def _load_tag_map(self):
        """
        Carrega o mapa de memória do CLP a partir do arquivo JSON externo.
        Garante que a lógica de controle fique separada da configuração de hardware.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'tags_map.json')

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.tags_addrs = json.load(f)
            logger.info(f"Mapa de tags carregado com sucesso ({len(self.tags_addrs)} tags).")
        except FileNotFoundError:
            msg_erro = f"ERRO CRÍTICO: Arquivo de configuração '{json_path}' não encontrado."
            logger.critical(msg_erro)
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', msg_erro)
            self.tags_addrs = {}
        except json.JSONDecodeError as e:
            msg_erro = f"ERRO CRÍTICO: Arquivo JSON mal formatado: {e}"
            logger.critical(msg_erro)
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', msg_erro)
            self.tags_addrs = {}

    def _initialize_tags(self):
        """
        Preenche o dicionário interno de tags com valores iniciais zerados.
        """
        self.tags = {tag: 0.0 for tag in self.tags_addrs.keys()}

    def _get_address(self, tag_name: str, fallback: int) -> int:
        """
        Busca o endereço Modbus de uma tag com segurança.

        :param tag_name: Nome da tag conforme o JSON.
        :param fallback: Valor padrão caso a tag não exista.
        :return: Endereço inteiro.
        """
        return self.tags_addrs.get(tag_name, {}).get('address', fallback)

    def get_motor_status(self) -> bool:
        """
        Verifica se o motor está ligado.

        No modo de simulação, o estado é lido da memória interna. No modo real,
        os registradores de status do CLP são consultados ativamente via rede TCP.

        :return: True se o motor estiver operando, False caso contrário.
        """
        if not self.is_connected:
            return False

        if self.mode == 'simulation':
            return self.tags.get('co.habilita', 0) == self.config['COMANDO_LIGAR']

        try:
            with self.lock:
                if not self.client:
                    return False

                # Busca dinâmica dos endereços do JSON
                addr_indica = self._get_address('co.indica_driver', 1216)
                indica_driver_regs = self.client.read_holding_registers(addr_indica, 1)
                
                if not indica_driver_regs:
                    return False

                indica_driver = indica_driver_regs[0]

                # Mapeamento do status com base no driver selecionado referenciando a configuração
                mapa_status = {
                    self.config['PARTIDA_SOFTSTARTER']: self._get_address('co.status_ats48', 886),
                    self.config['PARTIDA_INVERSOR']: self._get_address('co.status_atv31', 888),
                    self.config['PARTIDA_DIRETA']: self._get_address('co.status_tesys', 890)
                }

                # Fallback para partida direta se o valor for indefinido
                addr_status = mapa_status.get(indica_driver, mapa_status[self.config['PARTIDA_DIRETA']])
                estado_regs = self.client.read_holding_registers(addr_status, 1)

                if estado_regs:
                    return estado_regs[0] == self.config['COMANDO_LIGAR']

            return False

        except Exception as e:
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', f'Erro ao verificar estado do motor: {e}')
            logger.error(f"Erro ao verificar estado do motor: {e}")
            return False

    def comando_motor(self, command_type: int) -> bool:
        """
        Envia o sinal de acionamento ou parada do motor.

        :param command_type: 1 para ligar, 0 para desligar.
        :return: Booleano indicando o sucesso da operação.
        """
        if not self.is_connected:
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', 'Tentativa de comando motor sem conexão')
            return False

        command_type = int(command_type)

        if self.mode == 'simulation':
            with self.lock:
                self.tags['co.habilita'] = float(command_type)

                if self.tags.get('co.sel_driver', self.config['PARTIDA_INDEFINIDA']) == self.config['PARTIDA_INDEFINIDA']:
                    self.tags['co.sel_driver'] = float(self.config['PARTIDA_DIRETA'])

                if (self.tags.get('co.sel_driver', self.config['PARTIDA_INDEFINIDA']) == self.config['PARTIDA_INVERSOR'] 
                        and self.tags.get('co.freq_ref', 0) == 0):
                    self.tags['co.freq_ref'] = self.config['FREQ_PADRAO_INVERSOR']

            tipo_nome = {
                self.config['PARTIDA_INDEFINIDA']: 'Indefinida',
                self.config['PARTIDA_SOFTSTARTER']: 'Soft-start',
                self.config['PARTIDA_INVERSOR']: 'Inversor',
                self.config['PARTIDA_DIRETA']: 'Direta'
            }
            tipo = int(self.tags.get('co.sel_driver', self.config['PARTIDA_INDEFINIDA']))
            acao = 'LIGADO' if command_type == self.config['COMANDO_LIGAR'] else 'DESLIGADO'
            
            if hasattr(self.app, 'db'):
                self.app.db.log_event(
                    'comando',
                    f'[COMPRESSOR] Simulação: Motor {acao} - Partida: {tipo_nome.get(tipo, "Desconhecida")}'
                )
            return True

        try:
            with self.lock:
                if not self.client:
                    if hasattr(self.app, 'db'):
                        self.app.db.log_event('erro', 'Cliente Modbus não inicializado')
                    return False

                addr_indica = self._get_address('co.indica_driver', 1216)
                tipo_partida_regs = self.client.read_holding_registers(addr_indica, 1)
                
                if not tipo_partida_regs:
                    if hasattr(self.app, 'db'):
                        self.app.db.log_event('erro', 'Falha ao ler tipo de partida')
                    return False

                tipo_partida = tipo_partida_regs[0]

            # Busca dinâmica dos endereços de comando
            addr_tesys = self._get_address('co.tesys', 1319)
            addr_ats48 = self._get_address('co.ats48', 1316)
            addr_atv31 = self._get_address('co.atv31', 1312)

            mapa_comandos = {
                self.config['PARTIDA_INDEFINIDA']: addr_tesys,
                self.config['PARTIDA_SOFTSTARTER']: addr_ats48,
                self.config['PARTIDA_INVERSOR']: addr_atv31,
                self.config['PARTIDA_DIRETA']: addr_tesys,
            }

            endereco_comando = mapa_comandos.get(tipo_partida, addr_tesys)

            with self.lock:
                success = self.client.write_single_register(endereco_comando, command_type)

            if success:
                tipo_nome = {
                    self.config['PARTIDA_INDEFINIDA']: 'Indefinida',
                    self.config['PARTIDA_SOFTSTARTER']: 'Soft-start',
                    self.config['PARTIDA_INVERSOR']: 'Inversor',
                    self.config['PARTIDA_DIRETA']: 'Direta'
                }
                acao = 'LIGADO' if command_type == self.config['COMANDO_LIGAR'] else 'DESLIGADO'
                
                if hasattr(self.app, 'db'):
                    self.app.db.log_event(
                        'comando',
                        f'[COMPRESSOR] Motor {acao} - Partida: {tipo_nome.get(tipo_partida, "Desconhecida")}'
                    )
                self.tags['co.habilita'] = float(command_type)
                return True
            
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', f'Falha comando motor (tipo partida: {tipo_partida})')
            return False

        except Exception as e:
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', f'Erro no comando motor: {e}')
            logger.error(f"Erro no comando motor: {e}")
            return False

    # Alias mantido para compatibilidade reversa com elementos visuais da UI existentes
    comandoMotor = comando_motor

    def clique_motor(self) -> bool:
        """
        Alterna o estado do motor baseado na sua operação atual (Toggle).

        :return: Booleano indicando o sucesso da operação Modbus.
        """
        if not self.is_connected:
            return False

        motor_ligado = self.get_motor_status()
        novo_comando = self.config['COMANDO_DESLIGAR'] if motor_ligado else self.config['COMANDO_LIGAR']

        return self.comando_motor(novo_comando)

    def muda_motor_ui_on(self):
        """Atualiza a UI quando o motor é ligado."""
        pass

    def muda_motor_ui_off(self):
        """Atualiza a UI quando o motor é desligado."""
        pass

    def connect(self, mode: str, ip: str = '127.0.0.1', port: int = 502) -> tuple[bool, str]:
        """
        Inicia a rotina de conexão com o equipamento ou simulação.

        :param mode: 'real' para TCP ou 'simulation' para Gêmeo Digital.
        :param ip: Endereço de IP do CLP.
        :param port: Porta de comunicação.
        :return: Tupla com status booleano e mensagem descritiva.
        """
        self.disconnect()
        self.mode = mode

        if mode == 'simulation':
            self.is_connected = True
            self.polling_thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self.polling_thread.start()
            return True, "Conectado ao Simulador Interno"

        # Teste preventivo de latência (Ping)
        param = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
        redir = '> NUL 2>&1' if platform.system().lower() == 'windows' else '> /dev/null 2>&1'
        if os.system(f"ping {param} {ip} {redir}") != 0:
            return False, f"Falha no Ping: Host {ip} inacessível."

        try:
            self.client = ModbusClient(host=ip, port=port, timeout=self.config['TIMEOUT_MODBUS'])
            self.is_connected = self.client.open()

            if self.is_connected:
                self.polling_thread = threading.Thread(
                    target=self._real_data_polling_loop, daemon=True
                )
                self.polling_thread.start()
                return True, f"Conectado ao CLP em {ip}"
            
            return False, f"Falha na conexão Modbus com {ip}"
            
        except Exception as e:
            return False, f"Erro de conexão: {e}"

    def disconnect(self):
        """
        Interrompe ciclos e fecha sessões Modbus ativas de forma segura.
        """
        self.is_connected = False
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=1.5)
        if self.client:
            self.client.close()
            
        self.client = None
        self.mode = None
        self._initialize_tags()

    def read_tag(self, tag: str) -> float:
        """
        Lê uma tag da memória com proteção de thread (Thread-safe).
        
        :param tag: Nome da grandeza.
        :return: Valor numérico armazenado.
        """
        with self.lock:
            return self.tags.get(tag, 0.0)

    def get_tag_info(self, tag: str) -> dict:
        """Retorna o esquema JSON completo de uma tag."""
        return self.tags_addrs.get(tag, {})

    def write_tag(self, tag: str, value: float):
        """
        Executa operação de gravação de holding register no CLP e atualiza memória.

        Lida com lógica bitwise caso a tag no JSON indique edição via bits numicos.

        :param tag: Identificador da variável Modbus.
        :param value: Valor escalar a ser escrito.
        """
        if not self.is_connected or tag not in self.tags_addrs:
            return

        with self.lock:
            self.tags[tag] = float(value)

        if self.mode == 'simulation':
            if hasattr(self.app, 'db'):
                self.app.db.log_event(
                    'comando', f'[COMPRESSOR] Simulação: Tag {tag} escrita com valor {value}'
                )
            return

        info = self.tags_addrs[tag]
        addr = info['address']
        
        try:
            with self.lock:
                bit_val = info.get('bit')
                # Máscara de bit para escrita controlada num registrador
                if bit_val is not None and bit_val != "":
                    bit_index = int(bit_val)
                    regs = self.client.read_holding_registers(addr, 1)
                    if regs:
                        reg_val = regs[0]
                        new_val = reg_val | (1 << bit_index) if value == 1 else reg_val & ~(1 << bit_index)
                        self.client.write_single_register(addr, new_val)
                    else:
                        logger.error(f"Erro Modbus: Falha de leitura ao editar bit no registrador {addr}.")
                        if hasattr(self.app, 'db'):
                            self.app.db.log_event(
                                'erro',
                                f"Falha ao preparar escrita de bit {bit_index} no addr {addr}"
                            )
                else:
                    # Escrita escalar comum baseada no divisor
                    fator_divisao = info.get('div', 1)
                    self.client.write_single_register(addr, int(value * fator_divisao))

                if hasattr(self.app, 'db'):
                    self.app.db.log_event('comando', f'[COMPRESSOR] Tag {tag} escrita com valor {value}')
                
        except (ConnectionException, AttributeError) as e:
            logger.error(f"Erro de escrita Modbus: {e}. Desconectando...")
            self.is_connected = False
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', f"Falha de conexão na escrita em {tag}")
        except Exception as e:
            logger.error(f"Erro de escrita Modbus: {e}")
            if hasattr(self.app, 'db'):
                self.app.db.log_event('erro', f"Falha de escrita em {tag}")

    def _converter_float32(self, regs: list) -> float:
        """
        Realiza unpacking de dois registradores uint16 em um Float 32 IEEE-754.
        
        :param regs: Lista com dois blocos de 16 bits vindos do CLP.
        :return: Valor de ponto flutuante convertido.
        """
        if not regs or len(regs) < 2:
            return 0.0

        raw = int(regs[1]).to_bytes(2, byteorder='big') + int(regs[0]).to_bytes(2, byteorder='big')
        return struct.unpack('>f', raw)[0]

    def _real_data_polling_loop(self):
        """
        Trabalhador assíncrono para coleta contínua da planta real.
        Varre o dicionário JSON fazendo polling com política fail-safe e Micro-Locks.
        """
        logger.info("[Modbus] Thread de polling real iniciada.")
        
        while self.is_connected and self.mode == 'real':
            start_time = time.time()
            try:
                current_readings = {}

                # TODO: Estudar viabilidade de ler bloco em bloco inves de endereço em endereço
                for tag, info in self.tags_addrs.items():
                    addr = info["address"]
                    div = info.get('div', 1)
                    tag_type = info['type']

                    try:
                        # Chamadas TCP Assíncronas Livres (Sem travar Interface UI)
                        if tag_type == '4X':
                            regs = self.client.read_holding_registers(addr, 1)
                            if regs:
                                bit = info.get("bit")
                                if bit is not None and bit != "":
                                    val = (regs[0] >> int(bit)) & 1
                                else:
                                    val = regs[0]

                                current_readings[tag] = val / div if div != 0 else val

                        elif tag_type == 'FP':
                            regs = self.client.read_holding_registers(addr, 2)
                            if regs:
                                val = self._converter_float32(regs)
                                current_readings[tag] = val / div if div != 0 else val

                    except Exception as e:
                        logger.error(f"[Modbus] Aviso: Falha ao ler '{tag}' (Endereço {addr}): {e}")
                        continue

                # Micro-Lock de exclusão mútua (Atualização RAM)
                with self.lock:
                    self.tags.update(current_readings)
                    tags_to_log = self.tags.copy()

                # Delegar para ORM/SQLite Assincronamente 
                if hasattr(self.app, 'db'):
                    self.app.db.log_reading(tags_to_log)

                # Gestor de Sincronia 
                elapsed = time.time() - start_time
                if elapsed < self.config['TICK_RATE_POLLING']:
                    time.sleep(self.config['TICK_RATE_POLLING'] - elapsed)

            except (ConnectionException, AttributeError) as e:
                logger.error(f"[Modbus] Erro fatal de conexão no polling: {e}")
                self.is_connected = False
            except Exception as e:
                logger.exception("[Modbus] Erro inesperado no polling.")

        logger.info("[Modbus] Thread de polling real encerrada.")

    def _simulation_loop(self):
        """
        Gêmeo Digital Assíncrono que processa lógicas termoelétricas.
        """
        dt = 1.0
        logger.info("[Simulador] Thread de simulação iniciada.")

        simulator = PlantSimulator(self.tags)

        while self.is_connected and self.mode == 'simulation':
            start_time = time.time()
            try:
                # 1. Leitura com Lock 
                with self.lock:
                    motor_on = self.tags.get('co.habilita', 0) == self.config['COMANDO_LIGAR']
                    tipo_partida = int(self.tags.get('co.sel_driver', self.config['PARTIDA_INDEFINIDA']))

                    for i in range(1, 7):
                        tag_valvula = f'co.xv{i}'
                        simulator.state[tag_valvula] = self.tags.get(tag_valvula, 0)
                        
                    simulator.state['co.freq_ref'] = self.tags.get('co.freq_ref', self.config['FREQ_PADRAO_INVERSOR'])

                # 2. Resolução da Física
                new_state = simulator.update_physics(dt, motor_on, tipo_partida)

                # 3. Escrita com Lock
                with self.lock:
                    self.tags.update(new_state)
                    tags_to_log = self.tags.copy()

                # 4. Gravação Banco de Dados
                if hasattr(self.app, 'db'):
                    self.app.db.log_reading(tags_to_log)

            except Exception as e:
                logger.exception(f"[Simulador] ERRO CRÍTICO na física ou banco de dados: {e}")

            elapsed = time.time() - start_time
            if elapsed < dt:
                time.sleep(dt - elapsed)

        logger.info("[Simulador] Thread de simulação encerrada.")