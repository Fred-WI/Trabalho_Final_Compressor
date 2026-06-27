import math

class Motor:
    """
    Modelo Físico do Motor de Indução Trifásico
    """
    def __init__(self, **params):
        """
        Construtor da classe inicializado pelo dicionário do Tanque/Simulador
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
        
        # Proteção contra polo = 0
        polo_calc = self.__polo if self.__polo > 0 else 4
        self.__wSincronaNom = (120.0 * self.__frequencia) / polo_calc
        self.__rotNom = (1.0 - self.__slipNom) * self.__wSincronaNom
        
        # Variáveis calculadas dinamicamente
        self.__wSincronaOperacao = 0.0
        self.__torque = 0.0
        self.__rotacao = 0.0
        self.__outpower = 0.0
        self.__inpower = 0.0
        self.__corrente = 0.0

    # ==========================================
    # GETTERS (Retornando valores físicos reais)
    # ==========================================
    def getWsincrona(self): return float(self.__wSincronaNom)
    def getRotNom(self): return float(self.__rotNom)
    def getTensao(self): return float(self.__tensao)
    def getLoad(self): return float(self.__load)
    def getFrequencia(self): return float(self.__frequencia)
    def getOpFrequencia(self): return float(self.__opFrequencia)
    def getOpWsincrona(self): return float(self.__wSincronaOperacao)
    def getTorque(self): return float(self.__torque)
    def getRotacao(self): return float(self.__rotacao)    
    def getOutPower(self): return float(self.__outpower)
    def getInPower(self): return float(self.__inpower)
    def getCorrente(self): return float(self.__corrente)
    def getTemperature(self): return float(self.__temp)
    def getState(self): return self.__state
    def getTStart(self): return float(self.__tstart)

    # ==========================================
    # SETTERS & CÁLCULOS FÍSICOS
    # ==========================================
    def setTStart(self, tstart):
        self.__tstart = tstart
        
    def setState(self, state):
        self.__state = state

    def TorqueNom(self):
        if self.__rotNom != 0:
            self.__torqueNom = self.__horsepower * 746.0 / self.__rotNom
        else:
            self.__torqueNom = 0.0

    def setOpFrequencia(self, frequencia):
        self.__opFrequencia = frequencia

    def wSincronaOperacao(self):
        polo_calc = self.__polo if self.__polo > 0 else 4
        self.__wSincronaOperacao = (120.0 * self.__opFrequencia) / polo_calc

    def TorqueVazio(self):
        if self.__wSincronaOperacao != 0:
            self.__torqueVazio = self.__horsepower * 746.0 / (0.99 * self.__wSincronaOperacao)
        else:
            self.__torqueVazio = 0.0

    def Torque(self):
        if self.__load == 0:
            self.__torque = self.__torqueVazio
        else:
            self.__torque = self.__load * self.__torqueNom

    def Rotacao(self):
        if self.__wSincronaOperacao != 0 and self.__torqueNom != 0:
            self.__rotacao = -(self.__wSincronaOperacao / self.__torqueNom) * \
                             (self.__slipNom * self.__torque - self.__torqueNom)
            # Evita rotação negativa
            self.__rotacao = max(0.0, self.__rotacao)
        else:
            self.__rotacao = 0.0

    def OutPower(self):
        self.__outpower = self.__torque * self.__rotacao

    def InPower(self):
        denom = (self.__eff * self.__efInversor)
        self.__inpower = (self.__outpower / denom) if denom != 0 else 0.0

    def CalculaCorrente(self):
        denom = (math.sqrt(3) * self.__tensao * self.__costheta)
        self.__corrente = (self.__inpower / denom) if denom != 0 else 0.0

    def Temperature(self, tick):
        denom = self.__rotNom * self.__torque
        # Proteção contra divisão por zero (Motor desligado ou sem carga nominal)
        nivel_calculado = (40.0 * self.__outpower / denom) if denom != 0 else 0.0
        
        if nivel_calculado > self.__temp_level or nivel_calculado < self.__temp_level: 
            self.__oldTemp = self.__temp
            self.__elapsedTime = 0.0
    
        self.__temp_level = nivel_calculado
        self.__elapsedTime += tick
        
        # Tal deve ser maior que 0 para evitar erro na exponencial
        tal_calc = self.__tal if self.__tal > 0 else 1.0
        
        temp_alvo = self.__tempAmb + self.__temp_level
        self.__temp = temp_alvo + (self.__oldTemp - temp_alvo) * (math.exp(-self.__elapsedTime / tal_calc))

    def partida(self, estado, frequencia_desejada, tick):
        """
        Lógica de rampa de aceleração (Inversor / Soft-Starter).
        Retorna a frequência atual calculada.
        """
        if estado is False:
            self.setState(False)
            self.__f = 0.0
            return self.__f

        if self.getState():
            # Motor já em regime, apenas acompanha a referência
            self.__f = frequencia_desejada
        else:
            # Motor partindo, aplica rampa baseada no TStart
            passos = (self.__tstart / tick) if tick > 0 else 1.0
            incremento = frequencia_desejada / passos if passos > 0 else frequencia_desejada
            
            if self.__f < frequencia_desejada:
                self.__f += incremento
                
            if self.__f >= frequencia_desejada:
                self.__f = frequencia_desejada
                self.setState(True)
                
        return self.__f