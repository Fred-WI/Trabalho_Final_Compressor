from controllers.simulador.Motor import Motor
import math
import random

class Tanque:
    """
    Classe Tanque adaptada para o Reservatório de Ar Comprimido (Compressor)
    """

    def __init__(self, tick, pressao_inicial=1.0, max_pressao=15.0, rst_time=5.0):
        """
        Construtor da classe.
        """
        self.__tick = tick
        self.__pressao = pressao_inicial
        self.__pressaoMax = max_pressao
        
        # O compressor possui 6 válvulas (XV-01 a XV-06)
        self.__solenoides = [False] * 6
        
        # Fatores randômicos para gerar um ruído realista na vazão de saída
        self._rand_factor = [random.uniform(0.9, 1.1) for _ in range(6)]
        self._rst_time = rst_time
        self.__elapsedTime = 0
        
        # Instancia o motor atrelado a este reservatório
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
        """Retorna a pressão atual do reservatório."""
        return self.__pressao
        
    def getPressaoEfetiva(self):
        """Retorna a pressão acima da atmosférica (usada para cálculo de vazão)."""
        return max(0, self.__pressao - 1.0)

    def getTick(self):
        return self.__tick

    # ==========================================
    # SETTERS PARA O SIMULADOR MODBUS ESCREVER
    # ==========================================

    def setSolenoides(self, estados_xv):
        """
        Recebe uma lista com o estado das 6 válvulas [xv1, xv2, xv3, xv4, xv5, xv6]
        """
        for i in range(6):
            if i < len(estados_xv):
                self.__solenoides[i] = bool(estados_xv[i])

    def muda_rnd_factor(self):
        """Gera novos ruídos brancos para simular turbulência do ar."""
        if self.__elapsedTime > self._rst_time:
            self._rand_factor = [random.uniform(0.9, 1.1) for _ in range(6)]
            self.__elapsedTime = 0

    # ==========================================
    # O CORAÇÃO DA FÍSICA (O PASSO DA SIMULAÇÃO)
    # ==========================================

    def TankSimulation(self, frequencia, t_partida, motorState, estados_xv):
        """
        Executa 1 ciclo (tick) da simulação física completa (Motor + Reservatório).
        Substitui a lógica de simulação que antes ficava presa na interface.
        """
        
        # 1. ATUALIZA A DINÂMICA ELÉTRICA E MECÂNICA DO MOTOR
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

        # 2. ATUALIZA O ESTADO DOS ATUADORES (Válvulas)
        self.setSolenoides(estados_xv)

        # 3. CALCULA A TERMODINÂMICA DO RESERVATÓRIO
        rpm = max(0, self.motor.getRotacao())
        
        # Vazão de entrada (gerada pelo compressor girando)
        pressure_gen = (rpm / 60.0) * 1.5
        
        # Vazão de saída (ar escapando pelas válvulas abertas)
        pressao_efetiva = self.getPressaoEfetiva()
        flow_loss = 0.0
        
        for i in range(6):
            if self.__solenoides[i]:
                # 0.8 é a constante de escoamento. Multiplicamos pelo fator random para realismo
                flow_loss += 0.8 * (pressao_efetiva / 9.0) * self._rand_factor[i]
                
        # Calcula o diferencial de pressão (Equação de conservação de massa)
        dP = (pressure_gen - flow_loss) * self.__tick * 0.2
        
        self.__pressao += dP
        
        # Saturação: O reservatório nunca fica com pressão menor que a atmosférica (1.0)
        # e é travado na pressão máxima estrutural ou de segurança (15.0 bar)
        self.__pressao = max(1.0, min(self.__pressaoMax, self.__pressao))

        # Atualiza contadores de tempo para o ruído estocástico
        self.__elapsedTime += self.__tick
        self.muda_rnd_factor()