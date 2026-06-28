import random
import struct
import time

from pyModbusTCP.server import ModbusServer, DataBank

HOST = "127.0.0.1"
PORT = 5020

# Endereços usados pelo supervisório
ADDR = {
    "valvulas": 712,
    "tipo_motor": 708,
    "pressao": 714,
    "fit02": 716,
    "fit03": 718,
    "temp_carc": 706,
    "encoder": 884,
    "torque": 1420,
    "corrente_r": 840,
    "corrente_s": 841,
    "corrente_t": 842,
    "corrente_n": 843,
    "corrente_media": 845,
    "tensao_rs": 847,
    "tensao_st": 848,
    "tensao_tr": 849,
    "ativa_total": 855,
    "reativa_total": 859,
    "aparente_total": 863,
    "fp_total": 871,
    "frequencia": 830,
    "freq_ref": 1313,
    "cmd_inversor": 1312,
    "cmd_soft": 1316,
    "cmd_direta": 1319,
    "sel_driver": 1324,
    "habilita": 1328,
    # Alguns códigos antigos leem indicação de partida em 1216.
    "indica_driver": 1216,
    # Alguns códigos antigos leem estado do motor por tipo de partida.
    "estado_soft": 886,
    "estado_inversor": 888,
    "estado_direta": 890,
}


def write_reg(addr, value):
    DataBank.set_words(addr, [int(value) & 0xFFFF])


def read_reg(addr, default=0):
    values = DataBank.get_words(addr, 1)
    if values:
        return int(values[0])
    return default


def write_bit(addr, bit, value):
    reg = read_reg(addr)
    if value:
        reg |= (1 << bit)
    else:
        reg &= ~(1 << bit)
    write_reg(addr, reg)


def read_bit(addr, bit):
    return (read_reg(addr) >> bit) & 1


def write_float32(addr, value):
    """Escreve float32 em dois registradores.

    O cliente do projeto converte usando regs[1] como high word e regs[0]
    como low word. Por isso escrevemos [low_word, high_word].
    """
    raw = struct.pack(">f", float(value))
    high_word = int.from_bytes(raw[0:2], byteorder="big")
    low_word = int.from_bytes(raw[2:4], byteorder="big")
    DataBank.set_words(addr, [low_word, high_word])


class CompressorSimulado:
    def __init__(self):
        self.pressao = 1.0
        self.temp_carc = 25.0
        self.encoder = 0.0
        self.torque = 0.0
        self.corrente_media = 0.0
        self.ativa_total = 0.0
        self.reativa_total = 0.0
        self.aparente_total = 0.0
        self.fp_total = 1.0
        self.fit02 = 0.0
        self.fit03 = 0.0
        self._inicializar_registradores()

    def _inicializar_registradores(self):
        write_reg(ADDR["valvulas"], 0)
        write_reg(ADDR["tipo_motor"], 1)
        write_reg(ADDR["sel_driver"], 3)
        write_reg(ADDR["indica_driver"], 3)
        write_reg(ADDR["freq_ref"], 20)
        write_reg(ADDR["habilita"], 0)
        write_reg(ADDR["cmd_inversor"], 0)
        write_reg(ADDR["cmd_soft"], 0)
        write_reg(ADDR["cmd_direta"], 0)
        write_reg(ADDR["estado_soft"], 0)
        write_reg(ADDR["estado_inversor"], 0)
        write_reg(ADDR["estado_direta"], 0)

    def atualizar_comandos(self):
        tipo_partida = read_reg(ADDR["sel_driver"], 3)
        if tipo_partida not in (1, 2, 3):
            tipo_partida = 3
            write_reg(ADDR["sel_driver"], tipo_partida)

        write_reg(ADDR["indica_driver"], tipo_partida)

        cmd_soft = read_reg(ADDR["cmd_soft"])
        cmd_inversor = read_reg(ADDR["cmd_inversor"])
        cmd_direta = read_reg(ADDR["cmd_direta"])

        if tipo_partida == 1:
            motor_on = 1 if cmd_soft == 1 else 0
        elif tipo_partida == 2:
            motor_on = 1 if cmd_inversor == 1 else 0
        else:
            motor_on = 1 if cmd_direta == 1 else 0

        write_bit(ADDR["habilita"], 1, motor_on)
        write_reg(ADDR["estado_soft"], 1 if motor_on and tipo_partida == 1 else 0)
        write_reg(ADDR["estado_inversor"], 1 if motor_on and tipo_partida == 2 else 0)
        write_reg(ADDR["estado_direta"], 1 if motor_on and tipo_partida == 3 else 0)

        return bool(motor_on), tipo_partida

    def passo(self, dt=1.0):
        motor_on, tipo_partida = self.atualizar_comandos()

        if tipo_partida == 1:
            target_rpm = 60.0
            aceleracao = 1.5
        elif tipo_partida == 2:
            target_rpm = max(0.0, min(60.0, float(read_reg(ADDR["freq_ref"], 20))))
            aceleracao = 3.0
        else:
            target_rpm = 60.0
            aceleracao = 8.0

        if motor_on:
            if self.encoder < target_rpm - aceleracao:
                self.encoder += aceleracao
            elif self.encoder > target_rpm + aceleracao:
                self.encoder -= aceleracao
            else:
                self.encoder = target_rpm + random.uniform(-0.5, 0.5)
        else:
            self.encoder = max(0.0, self.encoder - 4.0)

        self.encoder = max(0.0, min(65.0, self.encoder))

        if self.encoder > 1:
            base_power = 4000 * (self.encoder / 60.0) ** 2
            self.ativa_total = base_power + random.uniform(-100, 100)
            self.reativa_total = base_power * 0.4 + random.uniform(-50, 50)
            self.aparente_total = (self.ativa_total ** 2 + self.reativa_total ** 2) ** 0.5
            self.fp_total = self.ativa_total / self.aparente_total if self.aparente_total > 0 else 1.0
            self.torque = self.ativa_total / (2 * 3.14159 * self.encoder)
            self.temp_carc = min(95.0, self.temp_carc + 0.2 * (self.encoder / 60.0) - 0.05)
            self.corrente_media = self.aparente_total / (220 * (3 ** 0.5)) + random.uniform(-0.1, 0.1)
        else:
            self.ativa_total *= 0.9
            self.reativa_total *= 0.9
            self.aparente_total *= 0.9
            self.torque *= 0.9
            self.fp_total = 1.0
            self.temp_carc = max(25.0, self.temp_carc - 0.1)
            self.corrente_media = random.uniform(0.0, 0.05)

        pressure_gen = (self.encoder / 60.0) * 1.5
        pressao_efetiva = max(0.0, self.pressao - 1.0)
        qtd_valvulas_abertas = sum(read_bit(ADDR["valvulas"], bit) for bit in range(0, 6))
        flow_loss = qtd_valvulas_abertas * 0.8 * (pressao_efetiva / 9.0)
        self.pressao += (pressure_gen - flow_loss) * dt * 0.2
        self.pressao = max(1.0, min(10.0, self.pressao))

        # Válvula 1 fica disponível no registrador, mas você pode ignorar na IHM.
        self.fit03 = (15.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) if read_bit(ADDR["valvulas"], 0) else 0.0
        self.fit02 = sum(
            (12.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5))
            for bit in range(1, 6)
            if read_bit(ADDR["valvulas"], bit)
        )

        self.escrever_variaveis()

    def escrever_variaveis(self):
        write_float32(ADDR["pressao"], self.pressao)
        write_float32(ADDR["fit02"], max(0.0, self.fit02))
        write_float32(ADDR["fit03"], max(0.0, self.fit03))
        write_float32(ADDR["temp_carc"], self.temp_carc)
        write_float32(ADDR["encoder"], self.encoder)
        write_float32(ADDR["torque"], self.torque)

        write_reg(ADDR["corrente_media"], int(self.corrente_media * 10))
        write_reg(ADDR["corrente_r"], int((self.corrente_media + random.uniform(-0.05, 0.05)) * 10))
        write_reg(ADDR["corrente_s"], int((self.corrente_media + random.uniform(-0.05, 0.05)) * 10))
        write_reg(ADDR["corrente_t"], int((self.corrente_media + random.uniform(-0.05, 0.05)) * 10))
        write_reg(ADDR["corrente_n"], int(random.uniform(0.0, 0.03) * 10))
        write_reg(ADDR["tensao_rs"], int((220.0 + random.uniform(-2, 2)) * 10))
        write_reg(ADDR["tensao_st"], int((220.0 + random.uniform(-2, 2)) * 10))
        write_reg(ADDR["tensao_tr"], int((220.0 + random.uniform(-2, 2)) * 10))
        write_reg(ADDR["ativa_total"], int(self.ativa_total))
        write_reg(ADDR["reativa_total"], int(self.reativa_total))
        write_reg(ADDR["aparente_total"], int(self.aparente_total))
        write_reg(ADDR["fp_total"], int(self.fp_total * 1000))
        write_reg(ADDR["frequencia"], int(self.encoder * 100))


def main():
    print("====================================")
    print("CLP SIMULADO - COMPRESSOR")
    print(f"Servidor Modbus TCP: {HOST}:{PORT}")
    print("Conecte pelo supervisório em: Conectar à Simulação")
    print("Para encerrar: Ctrl+C")
    print("====================================")

    server = ModbusServer(host=HOST, port=PORT, no_block=True)
    planta = CompressorSimulado()

    try:
        server.start()
        while True:
            planta.passo(dt=1.0)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nEncerrando CLP simulado...")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
