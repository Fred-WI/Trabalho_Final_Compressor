"""
Módulo de Simulação de Reservatório Termodinâmico.

Este módulo implementa o modelo matemático de um tanque de ar comprimido (compressor),
acoplando a dinâmica eletromecânica de um motor de indução com as equações de 
conservação de massa e escoamento de fluidos.
"""

from controllers.simulador.Motor import Motor
import math
import random


class Tanque:
    """
    Representação termodinâmica de um reservatório de ar comprimido.

    A classe modela o acúmulo de pressão resultante da diferença entre a vazão 
    mássica de entrada (gerada pelo eixo do motor) e a vazão de saída (escape 
    pelas válvulas solenoides). Inclui componentes estocásticos para emular a 
    turbulência do ar em regime de escoamento.
    """

    # TODO: Substituir constantes mágicas intrínsecas (ex: 6 válvulas, parâmetros elétricos do motor) por argumentos de inicialização ou arquivo de configuração externo.
    def __init__(self, tick, pressao_inicial=1.0, max_pressao=15.0, rst_time=5.0):
        """
        Inicializa o estado termodinâmico e aloca o modelo do motor associado.

        Args:
            tick (float): Passo de integração temporal (dt) da simulação em segundos.
            pressao_inicial (float, optional): Pressão absoluta inicial em bar. Padrão é 1.0 (atmosférica).
            max_pressao (float, optional): Limite estrutural de pressão do vaso em bar. Padrão é 15.0.
            rst_time (float, optional): Intervalo temporal em segundos para atualização da matriz estocástica de ruído. Padrão é 5.0.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        
        Pré-condições:
            'tick' deve ser um valor numérico positivo estritamente maior que zero.
        Pós-condições:
            Variáveis de estado interno inicializadas e instância da classe Motor alocada na memória.
        """
        self.__tick = tick
        self.__pressao = pressao_inicial
        self.__pressaoMax = max_pressao
        
        self.__solenoides = [False] * 6
        
        self._rand_factor = [random.uniform(0.9, 1.1) for _ in range(6)]
        self._rst_time = rst_time
        self.__elapsedTime = 0
        
        self.__motorDic = {
            "state": False, "tensao": 220, "eff": 0.8, "polo": 4, 
            "costheta": 0.8, "horsepower": 3, "slipNom": 0.05,
            "load": 0.5, "frequencia": 60, "opFrequencia": 60, 
            "TempAmbiente": 24, "tal": 100, "tstart": 3
        }
        self.motor = Motor(**self.__motorDic)

    # ==========================================
    # GETTERS PARA O SIMULADOR MODBUS LER
    # ==========================================
    
    def getPressao(self):
        """
        Retorna a variável de estado da pressão absoluta.

        Returns:
            float: Pressão atual do reservatório.
        """
        return self.__pressao
        
    def getPressaoEfetiva(self):
        """
        Calcula a pressão manométrica (diferencial em relação ao ambiente).

        A pressão efetiva atua como força motriz geométrica para as equações 
        de escoamento de saída nas válvulas.

        Returns:
            float: Pressão manométrica. O piso numérico é 0.0.
            
        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        return max(0, self.__pressao - 1.0)

    def getTick(self):
        """
        Retorna o passo de integração temporal (dt) da simulação.

        Returns:
            float: Valor de dt em segundos.
        """
        return self.__tick

    # ==========================================
    # SETTERS PARA O SIMULADOR MODBUS ESCREVER
    # ==========================================

    # TODO: Refatorar a rotina de atualização iterativa. A verificação if i < len(estados_xv) dentro do laço de tamanho fixo apresenta risco lógico silencioso caso a entrada possua mais elementos que a alocação interna. Recomenda-se o uso de slicing (self.__solenoides[:len(estados_xv)] = map(bool, estados_xv)).
    def setSolenoides(self, estados_xv):
        """
        Atualiza o vetor de estado lógico dos atuadores de escape (válvulas).

        Args:
            estados_xv (list): Vetor sequencial de estados booleanos ou numéricos avaliáveis como booleanos.

        Complexity:
            Tempo: O(V) | Espaço: O(1), onde V é o número de válvulas analisadas (fixado em 6).
        """
        for i in range(6):
            if i < len(estados_xv):
                self.__solenoides[i] = bool(estados_xv[i])

    def muda_rnd_factor(self):
        """
        Atualiza o vetor de perturbação estocástica das válvulas.

        Substitui o coeficiente de escoamento para simular variações fluidodinâmicas 
        (turbulência) no escape do ar. A operação é dependente da contagem do tempo de simulação.

        Complexity:
            Tempo: O(V) | Espaço: O(V), onde V é o número de válvulas.
        """
        if self.__elapsedTime > self._rst_time:
            self._rand_factor = [random.uniform(0.9, 1.1) for _ in range(6)]
            self.__elapsedTime = 0

    # ==========================================
    # O CORAÇÃO DA FÍSICA (O PASSO DA SIMULAÇÃO)
    # ==========================================

    # TODO: Isolar os coeficientes físicos de integração (1.5, 0.8, 9.0, 0.2) em atributos explícitos da classe para viabilizar calibração do modelo sistêmico sem alteração algorítmica.
    def TankSimulation(self, frequencia, t_partida, motorState, estados_xv):
        """
        Executa a iteração (step) do solver numérico para o sistema físico acoplado.

        Resolve sequencialmente:
        1. A cinemática e eletromecânica do motor de indução.
        2. A transição de estado discreto das válvulas solenoides.
        3. A equação diferencial de balanço de massa no reservatório pelo método de Euler (dP/dt).

        Args:
            frequencia (float): Frequência elétrica da rede ou do inversor em Hz.
            t_partida (float): Tempo configurado de rampa de aceleração em segundos.
            motorState (bool): Estado lógico de comando do motor (True=Ligado).
            estados_xv (list): Matriz de comandos lógicos das válvulas.

        Complexity:
            Tempo: O(V) | Espaço: O(1), onde V é a quantidade de válvulas interpeladas.

        Pré-condições:
            Parâmetros numéricos válidos e objeto `Motor` corretamente instanciado.
        Pós-condições:
            Vetor de estado do motor atualizado. Pressão do reservatório recalculada,
            garantidamente saturada entre 1.0 e `max_pressao`.
        """
        
        self.motor.setTStart(t_partida)
        freq = self.motor.partida(motorState, frequencia, self.__tick)
        self.motor.TorqueNom()
        self.motor.setOpFrequencia(freq)
        self.motor.wSincronaOperacao()
        self.motor.TorqueVazio()
        self.motor.Torque()
        self.motor.Rotacao()
        self.motor.OutPower()
        self.motor.InPower()
        self.motor.CalculaCorrente()
        self.motor.Temperature(self.__tick)

        self.setSolenoides(estados_xv)

        rpm = max(0, self.motor.getRotacao())
        
        pressure_gen = (rpm / 60.0) * 1.5
        
        pressao_efetiva = self.getPressaoEfetiva()
        flow_loss = 0.0
        
        for i in range(6):
            if self.__solenoides[i]:
                flow_loss += 0.8 * (pressao_efetiva / 9.0) * self._rand_factor[i]
                
        dP = (pressure_gen - flow_loss) * self.__tick * 0.2
        
        self.__pressao += dP
        
        self.__pressao = max(1.0, min(self.__pressaoMax, self.__pressao))

        self.__elapsedTime += self.__tick
        self.muda_rnd_factor()