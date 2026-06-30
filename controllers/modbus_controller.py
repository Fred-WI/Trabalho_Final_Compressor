"""
Módulo de Controle Modbus TCP para Sistema SCADA.

Este módulo implementa a interface de comunicação entre o aplicativo Kivy e os
registradores do CLP (Controlador Lógico Programável). Ele opera em uma arquitetura
agnóstica, podendo atuar como cliente para um hardware físico ou instanciar e 
conectar-se a um servidor de simulação local.
"""

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
    """
    Controlador de comunicação e orquestração de threads para o protocolo Modbus TCP.

    Gerencia o ciclo de vida da conexão (abertura, polling de leitura e fechamento),
    mantém a sincronização de memória interna através de locks de thread e 
    encapsula a lógica de conversão de dados (Float32, bits, inteiros) baseada
    no dicionário de metadados das tags.
    """

    def __init__(self, app):
        """
        Inicializa as estruturas de dados e os controladores de concorrência.

        Args:
            app (App): Referência à instância principal do aplicativo (Kivy),
                       utilizada para acesso a módulos compartilhados (ex: banco de dados).
        """
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

    def _build_config_map(self):
        """Carrega os parâmetros de rede e metadados de configuração do arquivo JSON."""
        self.configs_map = load_configs('config/app_config.json')

    def _build_tag_map(self):
        """Carrega o mapeamento de endereços de registradores Modbus do arquivo JSON."""
        self.tags_addrs = load_tags('config/tags_compressor.json')

    def _initialize_tags(self):
        """
        Aloca o dicionário de estado interno das tags na memória RAM.

        Complexidade:
            Tempo: O(N) | Espaço: O(N), onde N é o número de tags carregadas.
        """
        self.tags = {tag: 0.0 for tag in self.tags_addrs.keys()}
    
    def connect(self, mode, ip='127.0.0.1', port=502):
        """
        Estabelece o canal de comunicação Modbus e inicia as threads subjacentes.

        Dependendo do parâmetro 'mode', a função pode instanciar o servidor de
        simulação em background antes de iniciar o cliente TCP. A inicialização
        inclui teste de ICMP (ping) para garantir roteamento antes do socket.

        Args:
            mode (str): Modo de operação ('simulation' ou 'real').
            ip (str, optional): Endereço IPv4 alvo. Padrão é '127.0.0.1'.
            port (int, optional): Porta TCP alvo. Padrão é 502.

        Returns:
            tuple: (bool, str) representando o estado de sucesso e a mensagem de log associada.

        Pré-condições:
            Estado interno indefinido. Conexões anteriores podem estar abertas.
        Pós-condições:
            Socket TCP aberto. Thread de polling instanciada e rodando em background.
            Se aplicável, Thread de simulação rodando.
        """
        self.disconnect()
        self.mode = mode

        net_cfg = self.configs_map["network"].get(mode, self.configs_map["network"]["simulation"])
        target_ip = ip if (ip and ip.strip() != "") else net_cfg["ip"]
        port = net_cfg["port"]
        timeout = net_cfg.get("timeout", 3)

        if mode == 'simulation':
            logger.info("Iniciando conexão com o Servidor Modbus Simulado local em outra Thread...")
            
            self.simulator_thread = threading.Thread(
                target=self._run_simulator_server,
                args=(target_ip, port),
                daemon=True
            )
            
            self.simulator_thread.start()
            time.sleep(0.5)

        # TODO: Substituir chamada síncrona `os.system` por `subprocess.run` para evitar 
        # bloqueio da thread chamadora e possíveis injeções de comandos do sistema operacional.
        if mode != 'simulation':
            param = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
            redir = '> NUL 2>&1' if platform.system().lower() == 'windows' else '> /dev/null 2>&1'
            if os.system(f"ping {param} {ip} {redir}") != 0:
                return False, f"Falha no Ping: Host {ip} inacessível."

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
        """
        Encerra o servidor de simulação local e aguarda a união (join) da thread.
        """
        if self.simulator_server:
            self.simulator_server.stop()
            self.simulator_server = None
            
        if self.simulator_thread and self.simulator_thread.is_alive():
            self.simulator_thread.join(timeout=1.0)
            self.simulator_thread = None

    def disconnect(self):
        """
        Interrompe a malha de leitura e finaliza os sockets e threads ativas.

        Garante o encerramento gracioso (graceful shutdown) para evitar o 
        aprisionamento da porta 502 no sistema operacional.
        """
        self.is_connected = False
        
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=1.5)
            self.polling_thread = None
            
        if self.client:
            self.client.close()
            self.client = None
            
        self.mode = None
        self._initialize_tags()
        self._stop_simulator()

    def get_motor_status(self):
        """
        Lê e interpreta o estado do motor baseado na topologia da partida.

        O método resolve o indirecionamento de registradores verificando primeiro
        qual drive está ativo (direta, inversor, soft-starter) e, em seguida,
        lê o estado específico correspondente.

        Returns:
            bool: True se o motor estiver ligado, False caso contrário ou em caso de erro.
        
        Complexidade:
            Tempo: O(1) | Espaço: O(1).
        """
        if not self.is_connected: return False
            
        try:
            with self.lock:
                if not self.client: return False

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
                
                estado_regs = self.client.read_holding_registers(addr_estado, 1)
                if estado_regs:
                    return estado_regs[0] == 1
            return False
            
        except Exception as e:
            self.app.db.log_event('erro', f'Erro ao verificar estado do motor: {e}')
            return False

    def comandoMotor(self, commandType):
        """
        Traduz a requisição lógica de acionamento em escrita de registradores.

        Identifica a rota ativa de controle no CLP (partida selecionada) e
        direciona o comando Modbus para o endereço apropriado.

        Args:
            commandType (int): 1 para pulso de ligar, 0 para pulso de desligar.

        Returns:
            bool: Sucesso ou falha na escrita Modbus.
        """
        if not self.is_connected:
            self.app.db.log_event('erro', 'Tentativa de comando motor sem conexão')
            return False

        commandType = int(commandType)
        tipos_nome = self.configs_map["tipos_partida"]
            
        try:
            # TODO: Unificar o bloco `with self.lock` desta função. Atualmente o lock é 
            # solto após a leitura de 'addr_indica' e retomado na escrita, criando brechas 
            # de concorrência onde o tipo de partida pode ser alterado por outra thread.
            with self.lock:
                if not self.client: return False

                addr_indica = self.tags_addrs["sys.indica_driver"]["address"]
                tipo_partida_regs = self.client.read_holding_registers(addr_indica, 1)
                
                if not tipo_partida_regs:
                    self.app.db.log_event('erro', 'Falha ao ler tipo de partida')
                    return False
                    
                tipo_partida = tipo_partida_regs[0]
            
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
        Inverte (toggle) o estado lógico atual do motor.

        Returns:
            bool: Resultado da execução de comandoMotor().
        """
        if not self.is_connected: return False
        motor_ligado = self.get_motor_status()
        novo_comando = 0 if motor_ligado else 1
        return self.comandoMotor(novo_comando)

    def troca_partida(self, tipo_partida):
        """
        Altera a malha lógica de acionamento de potência (driver).

        Impede a transição mecânica se o motor estiver operando, protegendo
        a simulação e a integridade de equipamentos físicos.

        Args:
            tipo_partida (int): ID identificador da topologia selecionada.

        Returns:
            bool: True se o intertravamento for aceito, False se rejeitado (motor ligado).
        """
        if self.get_motor_status(): return False
        
        addr_troca = self.tags_addrs["sys.cmd_troca_partida"]["address"]
        with self.lock:
            self.client.write_single_register(addr_troca, tipo_partida)
        return True

    def write_tag(self, tag_name, value):
        """
        Interface genérica para escrita formatada no servidor Modbus.

        Avalia os metadados da tag e aplica a conversão matemática (divisores)
        ou manipulação bit-a-bit (bit masking) necessárias antes do envio de rede.

        Args:
            tag_name (str): O identificador da tag no mapa.
            value (float/int): O valor numérico em base decimal a ser salvo.

        Returns:
            bool: Indicador do sucesso do pacote na camada TCP.
            
        Raises:
            ConnectionException: Em caso de queda abrupta do socket.
            AttributeError: Em caso do socket interno ser definido como None prematuramente.
        """
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
            logger.error(f"Erro de escrita Modbus: {e}. Desconectando...")
            self.is_connected = False
            self.app.db.log_event('erro', f"Falha de conexão na escrita em {tag_name}")
        except Exception as e:
            logger.error(f"Erro de escrita Modbus: {e}")
            self.app.db.log_event('erro', f"Falha de escrita em {tag_name}")
        return False

    def read_tag(self, tag):
        """Obtém o valor contido na representação local de memória da aplicação."""
        with self.lock: return self.tags.get(tag, 0)

    def get_tag_info(self, tag):
        """Retorna o dicionário de metadados referentes à tag consultada."""
        return self.tags_addrs.get(tag, {})

    def _float32_to_registers(self, value):
        """
        Serializa um Float nativo (IEEE 754) em formato Word Order do Modbus (Big-Endian).

        Args:
            value (float): Valor decimal.
            
        Returns:
            list[int]: Array contendo as duas words (16 bits cada) decodificadas.
        """
        import struct
        raw_bytes = struct.pack('>f', float(value))
        high_word = int.from_bytes(raw_bytes[0:2], byteorder='big')
        low_word = int.from_bytes(raw_bytes[2:4], byteorder='big')
        return [low_word, high_word]

    def _float32_from_registers(self, regs):
        """
        Desserializa um array de registradores Modbus em um Float (IEEE 754) para Python.

        Args:
            regs (list[int]): Lista de inteiros representando as word sizes lidas do servidor.

        Returns:
            float: O valor reconstituído, mantendo formato Big-Endian.
        """
        import struct
        if not regs or len(regs) < 2: return 0.0
        raw = int(regs[1]).to_bytes(2, byteorder='big') + int(regs[0]).to_bytes(2, byteorder='big')
        return struct.unpack('>f', raw)[0]

    def _real_data_polling_loop(self):
        """
        Laço de repetição bloqueante para sincronismo continuo (Master/Slave).

        Realiza iteração sobre o dicionário de metadados, constrói requisições
        individuais, atualiza a RAM com desmascaramento e invoca as estratégias de
        log no banco de dados. Compensação de tempo é aplicada para manter a taxa
        de atualização (tickrate) consistente.

        Complexidade:
            Tempo: O(N) | Espaço: O(1) de alocação de memória por ciclo.
        """
        tickrate = self.configs_map["network"].get(self.mode, self.configs_map["network"]["simulation"]).get("tickrate", 1.0)

        while self.is_connected:
            start_time = time.time()
            try:
                # with self.lock: 
                novas_leituras = {}
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
                        
                        # self.tags[tag] = val / div if div != 0 else val                        
                    # TODO: Substituir o bloco catch-all `except Exception: pass` pela 
                    # captura de exceções específicas ligadas ao Modbus/Network para evitar
                    # o mascaramento furtivo (silencing) de erros estruturais durante o loop.
                        novas_leituras[tag] = val / div if div != 0 else val
                    except Exception as e:
                        pass
                
                with self.lock:
                    self.tags.update(novas_leituras)

                self.app.db.log_reading(self.tags, self.tags_addrs)
                elapsed = time.time() - start_time
                if elapsed < tickrate: time.sleep(tickrate - elapsed)
            except (ConnectionException, AttributeError) as e: 
                logger.error(f"Polling Modbus falhou: {e}.")
                self.is_connected = False
            except Exception as e: 
                logger.error(f"Erro inesperado no polling: {e}")

    def _run_simulator_server(self, ip, port):
        """
        Inicia a classe orquestradora do simulador encapsulado, delegando o ciclo
        físico/termodinâmico para escopo independente.

        Args:
            ip (str): IP de vinculação do servidor local (Binding).
            port (int): Porta para Binding.
        """
        try:
            self.simulator_server = CompressorSimulator(host=ip, port=port)
            self.simulator_server.start()
            
            while getattr(self.simulator_server, 'running', False):
                time.sleep(1.0)
                
        except Exception as e:
            print(f"Erro Crítico no Servidor de Simulação: {e}")