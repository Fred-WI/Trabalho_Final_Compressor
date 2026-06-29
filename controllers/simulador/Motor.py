"""
Módulo de Modelagem Física de Motores de Indução.

Este módulo implementa o modelo matemático e termodinâmico de um motor de 
indução trifásico. O sistema resolve equações de regime permanente para o 
cálculo de conjugado (torque), escorregamento (slip), potências e correntes,
além de aplicar um modelo transitório de primeira ordem para o aquecimento
da carcaça e uma lógica discreta para simulação de rampa de aceleração (inversor).
"""

import math
import random

class Motor:
    """
    Representação termodinâmica e eletromecânica de um motor trifásico.

    A classe computa a conversão de energia elétrica em mecânica, considerando
    perdas no núcleo e no cobre (através da eficiência), fator de potência e 
    regime de carga. A temperatura é modelada como um sistema térmico RC.
    """
    
    def __init__(self, **params):
        """
        Inicializa os parâmetros nominais e o estado físico do motor.

        Args:
            **params: Dicionário contendo os parâmetros de placa do motor.
                tensao (float): Tensão de alimentação nominal em Volts.
                eff (float): Eficiência mecânica/elétrica (0 a 1).
                polo (int): Número de polos magnéticos.
                costheta (float): Fator de potência nominal.
                horsepower (float): Potência mecânica nominal em HP.
                slipNom (float): Escorregamento nominal em pu (0 a 1).
                frequencia (float): Frequência da rede em Hz.
                load (float): Fração de carga acoplada ao eixo (0 a 1).
                opFrequencia (float): Frequência operacional atual.
                TempAmbiente (float): Temperatura do meio (Celsius).
                tal (float): Constante de tempo térmica (tau) em segundos.
                tstart (float): Tempo configurado de rampa de partida em segundos.
                state (bool): Estado lógico inicial (Ligado/Desligado).

        Complexity:
            Tempo: O(1) | Espaço: O(1).

        Pré-condições:
            Os parâmetros mecânicos e elétricos devem ser não nulos e positivos 
            para evitar divisões por zero nas malhas subsequentes.
        Pós-condições:
            Objeto instanciado com grandezas nominais pré-calculadas e estado
            térmico equalizado com a temperatura ambiente.
        """     
        self.__tensao = params.get("tensao", 220.0)
        self.__eff = params.get("eff", 0.8)
        self.__polo = params.get("polo", 4)
        self.__costheta = params.get("costheta", 0.8)
        self.__horsepower = params.get("horsepower", 3.0)
        self.__slipNom = params.get("slipNom", 0.05)
        self.__frequencia = params.get("frequencia", 60.0)
        self.__load = params.get("load", 0.5)
        self.__opFrequencia = params.get("opFrequencia", 60.0)
        self.__tempAmb = params.get("TempAmbiente", 24.0)
        
        self.__temp_level = 0.0
        self.__oldTemp = self.__tempAmb
        self.__temp = self.__tempAmb
        self.__state = params.get("state", False)
        self.__elapsedTime = 0.0
        self.__tal = params.get("tal", 100.0)
        self.__tstart = params.get("tstart", 3.0)
        self.__f = 0.0
        
        self.__efInversor = 0.85
        self.__torqueNom = 0.0
        self.__torqueVazio = 0.0
        
        polo_calc = self.__polo if self.__polo > 0 else 4
        self.__wSincronaNom = (120.0 * self.__frequencia) / polo_calc
        self.__rotNom = (1.0 - self.__slipNom) * self.__wSincronaNom
        
        self.__wSincronaOperacao = 0.0
        self.__torque = 0.0
        self.__rotacao = 0.0
        self.__outpower = 0.0
        self.__inpower = 0.0
        self.__corrente = 0.0

    # ==========================================
    # GETTERS
    # ==========================================
    def getWsincrona(self):
        """Retorna a velocidade síncrona nominal (RPM)."""
        return float(self.__wSincronaNom)
        
    def getRotNom(self):
        """Retorna a velocidade nominal no eixo (RPM)."""
        return float(self.__rotNom)
        
    def getTensao(self):
        """Retorna a tensão de linha configurada (V)."""
        return float(self.__tensao)
        
    def getLoad(self):
        """Retorna a fração de carga aplicada ao eixo (pu)."""
        return float(self.__load)
        
    def getFrequencia(self):
        """Retorna a frequência elétrica nominal (Hz)."""
        return float(self.__frequencia)
        
    def getOpFrequencia(self):
        """Retorna a frequência imposta pelo driver no instante atual (Hz)."""
        return float(self.__opFrequencia)
        
    def getOpWsincrona(self):
        """Retorna a velocidade síncrona operacional baseada na frequência atual (RPM)."""
        return float(self.__wSincronaOperacao)
        
    def getTorque(self):
        """Retorna o torque mecânico desenvolvido no eixo (Nm*)."""
        return float(self.__torque)
        
    def getRotacao(self):
        """Retorna a velocidade mecânica instantânea do rotor (RPM)."""
        return float(self.__rotacao)    
        
    def getOutPower(self):
        """Retorna a potência mecânica útil no eixo (W)."""
        return float(self.__outpower)
        
    def getInPower(self):
        """Retorna a potência elétrica ativa absorvida da rede (W)."""
        return float(self.__inpower)
        
    def getCorrente(self):
        """Retorna a corrente elétrica de linha consumida (A)."""
        return float(self.__corrente)
        
    def getTemperature(self):
        """Retorna a temperatura atual da carcaça do motor (°C)."""
        return float(self.__temp)
        
    def getState(self):
        """Retorna o estado lógico do acionamento (True=Ligado)."""
        return self.__state
        
    def getTStart(self):
        """Retorna o tempo configurado para a rampa de aceleração (s)."""
        return float(self.__tstart)

    # ==========================================
    # SETTERS & CÁLCULOS FÍSICOS
    # ==========================================
    def setTStart(self, tstart):
        """
        Define o tempo de rampa de aceleração.

        Args:
            tstart (float): Tempo em segundos.
        """
        self.__tstart = tstart
        
    def setState(self, state):
        """
        Define o estado de operação lógica do motor.

        Args:
            state (bool): True para operação, False para parada.
        """
        self.__state = state

    # TODO: O cálculo subjacente `Potência(W) / Rotação(RPM)` não resulta em Torque na unidade padrão do SI (Newton-metro). Para obter o resultado em Nm, é imperativo converter RPM para radianos por segundo (rad/s) inserindo a constante `(2 * pi) / 60`.
    def TorqueNom(self):
        """
        Calcula o torque eletromagnético nominal.

        A computação converte a potência configurada de HP para Watts 
        e a divide pela rotação nominal para encontrar o conjugado intrínseco.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        if self.__rotNom != 0:
            self.__torqueNom = self.__horsepower * 746.0 / self.__rotNom
        else:
            self.__torqueNom = 0.0

    def setOpFrequencia(self, frequencia):
        """Define a frequência elétrica instantânea aplicada aos estatores."""
        self.__opFrequencia = frequencia

    def wSincronaOperacao(self):
        """
        Atualiza a velocidade síncrona com base na frequência operacional (inversor).

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        polo_calc = self.__polo if self.__polo > 0 else 4
        self.__wSincronaOperacao = (120.0 * self.__opFrequencia) / polo_calc

    # TODO: A constante `0.99` (simulando um escorregamento mínimo a vazio) é um número mágico hardcoded. Além disso, o mesmo problema dimensional de unidades (Potência/RPM) ocorrido no método `TorqueNom` se repete aqui.
    def TorqueVazio(self):
        """
        Calcula o torque necessário para vencer os atritos mecânicos a vazio.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        if self.__wSincronaOperacao != 0:
            self.__torqueVazio = self.__horsepower * 746.0 / (0.99 * self.__wSincronaOperacao)
        else:
            self.__torqueVazio = 0.0

    def Torque(self):
        """
        Define o torque de operação atual mediante a fração de carga mecânica acoplada.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        if self.__load == 0:
            self.__torque = self.__torqueVazio
        else:
            self.__torque = self.__load * self.__torqueNom

    def Rotacao(self):
        """
        Calcula a rotação mecânica instantânea operando na região linear da curva de conjugado.

        Determina o RPM equacionando a diferença entre velocidade síncrona e a 
        queda proporcional provocada pelo escorregamento da carga.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
            
        Pós-condições:
            A rotação calculada é truncada para o limite inferior de 0.0, prevenindo 
            velocidades reversas inconsistentes.
        """
        if self.__wSincronaOperacao != 0 and self.__torqueNom != 0:
            self.__rotacao = -(self.__wSincronaOperacao / self.__torqueNom) * \
                             (self.__slipNom * self.__torque - self.__torqueNom)
            self.__rotacao = max(0.0, self.__rotacao)
        else:
            self.__rotacao = 0.0

    def OutPower(self):
        """Calcula a potência mecânica (Watts) no eixo gerada sob a rotação e o torque vigentes."""
        self.__outpower = self.__torque * self.__rotacao

    def InPower(self):
        """Calcula a potência elétrica absorvida retrocedendo as perdas de eficiência."""
        denom = (self.__eff * self.__efInversor)
        self.__inpower = (self.__outpower / denom) if denom != 0 else 0.0

    def CalculaCorrente(self):
        """
        Determina a corrente de linha para o sistema trifásico balanceado.

        Utiliza o balanço de potência aparente baseado na potência ativa de entrada,
        tensão da rede e fator de potência.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        denom = (math.sqrt(3) * self.__tensao * self.__costheta)
        self.__corrente = (self.__inpower / denom) if denom != 0 else 0.0

    def Temperature(self, tick):
        """
        Integra a elevação de temperatura da máquina elétrica ao longo do tempo.

        Aplica um modelo térmico exponencial de 1ª ordem, equacionando a potência 
        dissipada (proporcional à diferença entre potência de saída e potência nominal). 
        Monitora mudanças no degrau de carga para reiniciar o transiente (elapsedTime).

        Args:
            tick (float): Delta temporal da iteração da simulação em segundos.

        Complexity:
            Tempo: O(1) | Espaço: O(1).
        """
        denom = self.__rotNom * self.__torque
        # TODO: A constante `40.0` atua como gradiente empírico para elevar a temperatura nominal da máquina (Elevação de Temperatura). Deve ser exposta no construtor para possibilitar a calibração da classe térmica do isolamento (B, F, H).
        nivel_calculado = (40.0 * self.__outpower / denom) if denom != 0 else 0.0
        
        # TODO: A comparação direta entre floats `nivel_calculado > or < self.__temp_level` (análoga a `!=`) é instável por conta das imprecisões do padrão IEEE 754. Recomenda-se o uso de `math.isclose()` com tolerância apropriada.
        if nivel_calculado > self.__temp_level or nivel_calculado < self.__temp_level: 
            self.__oldTemp = self.__temp
            self.__elapsedTime = 0.0
    
        self.__temp_level = nivel_calculado
        self.__elapsedTime += tick
        
        tal_calc = self.__tal if self.__tal > 0 else 1.0
        
        temp_alvo = self.__tempAmb + self.__temp_level
        self.__temp = temp_alvo + (self.__oldTemp - temp_alvo) * (math.exp(-self.__elapsedTime / tal_calc))

    def partida(self, estado, frequencia_desejada, tick):
        """
        Processa a rampa de aceleração da frequência elétrica imposta ao estator.

        Atua como o controle Volts/Hertz de um inversor de frequência, incrementando
        linearmente a frequência elétrica ao longo do tempo configurado (`__tstart`) 
        até atingir a referência.

        Args:
            estado (bool): O comando lógico alvo (True=Partir, False=Parar).
            frequencia_desejada (float): A referência de frequência em regime estável (Hz).
            tick (float): Discretização temporal do passo de integração (s).

        Returns:
            float: A frequência operacional momentânea após a iteração (Hz).

        Complexity:
            Tempo: O(1) | Espaço: O(1).
            
        Pré-condições:
            Parâmetros 'tstart' e 'tick' devem ser positivos para evitar divisão por zero 
            no cálculo dos passos da rampa.
        Pós-condições:
            Atributo de estado interno (`__state`) é alternado para True estritamente 
            quando a frequência atinge ou ultrapassa a referência de operação.
        """
        if estado is False:
            self.setState(False)
            self.__f = 0.0
            return self.__f

        if self.getState():
            self.__f = frequencia_desejada
        else:
            passos = (self.__tstart / tick) if tick > 0 else 1.0
            incremento = frequencia_desejada / passos if passos > 0 else frequencia_desejada
            
            if self.__f < frequencia_desejada:
                self.__f += incremento
                
            if self.__f >= frequencia_desejada:
                self.__f = frequencia_desejada
                self.setState(True)
                
        return self.__f