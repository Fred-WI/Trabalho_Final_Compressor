import random

class PlantSimulator:
    def __init__(self, initial_state):
        # Cria um estado independente para não partilhar referências diretas de memória
        self.state = initial_state.copy()
        
        # Condições iniciais seguras
        self.state['co.temp_carc'] = 25.0
        self.state['co.pressao'] = 1.0
        self.state['co.freq_ref'] = 20.0

    def update_physics(self, dt, motor_on, tipo_partida):
        """Processa 1 ciclo termodinâmico/elétrico da planta e devolve o novo estado."""
        
        # 1. Lógica de Alvo de Rotação (Setpoint)
        if tipo_partida == 1:          # Soft-start
            target_rpm = 60.0
            aceleracao = 1.5
        elif tipo_partida == 2:        # Inversor
            target_rpm = float(self.state.get('co.freq_ref', 20.0))
            target_rpm = max(0.0, min(60.0, target_rpm))
            aceleracao = 3.0
        else:                          # Direta ou padrão
            target_rpm = 60.0
            aceleracao = 8.0
        
        # 2. Lógica Eletromecânica do Motor
        if motor_on:
            if self.state.get('co.encoder', 0) < target_rpm - aceleracao:
                self.state['co.encoder'] += aceleracao
            elif self.state.get('co.encoder', 0) > target_rpm + aceleracao:
                self.state['co.encoder'] -= aceleracao
            else:
                self.state['co.encoder'] = target_rpm + random.uniform(-0.5, 0.5)

            self.state['co.encoder'] = max(0, min(65.0, self.state['co.encoder']))
            base_power = 4000 * (self.state['co.encoder'] / 60.0)**2
            self.state['co.ativa_total'] = base_power + random.uniform(-100, 100)
            self.state['co.reativa_total'] = base_power * 0.4 + random.uniform(-50, 50)
            self.state['co.aparente_total'] = (self.state['co.ativa_total']**2 + self.state['co.reativa_total']**2)**0.5
            self.state['co.fp_total'] = self.state['co.ativa_total'] / self.state['co.aparente_total'] if self.state['co.aparente_total'] > 0 else 1
            self.state['co.torque'] = (self.state['co.ativa_total'] / (2 * 3.14159 * self.state['co.encoder'])) if self.state['co.encoder'] > 1 else 0
            self.state['co.temp_carc'] = min(95, self.state.get('co.temp_carc', 25) + 0.2 * (self.state['co.encoder'] / 60.0) - 0.05)
            self.state['co.corrente_media'] = (self.state['co.aparente_total'] / (220 * (3**0.5))) + random.uniform(-0.1, 0.1)
        else:
            self.state['co.encoder'] = max(0, self.state.get('co.encoder', 0) - 4.0)
            for tag in ['co.ativa_total', 'co.reativa_total', 'co.aparente_total', 'co.torque']:
                self.state[tag] = self.state.get(tag, 0) * 0.9
            self.state['co.corrente_media'] = random.uniform(0.0, 0.05)
            self.state['co.fp_total'] = 1.0
            self.state['co.temp_carc'] = max(25.0, self.state.get('co.temp_carc', 25) - 0.1)

        # 3. Ruído Elétrico
        self.state['co.tensao_rs'] = 220.0 + random.uniform(-2, 2)
        self.state['co.tensao_st'] = 220.0 + random.uniform(-2, 2)
        self.state['co.tensao_tr'] = 220.0 + random.uniform(-2, 2)
        self.state['co.corrente_r'] = self.state['co.corrente_media'] + random.uniform(-0.05, 0.05)
        self.state['co.corrente_s'] = self.state['co.corrente_media'] + random.uniform(-0.05, 0.05)
        self.state['co.corrente_t'] = self.state['co.corrente_media'] + random.uniform(-0.05, 0.05)
        self.state['co.corrente_n'] = random.uniform(0.0, 0.03)
        self.state['co.frequencia'] = self.state['co.encoder']

        # 4. Lógica Termodinâmica de Pressão e Vazão
        pressure_gen = (self.state['co.encoder'] / 60.0) * 1.5
        pressao_efetiva = max(0, self.state.get('co.pressao', 1) - 1.0)
        flow_loss = sum(0.8 for i in range(1, 7) if self.state.get(f'co.xv{i}', 0)) * (pressao_efetiva / 9.0)
        
        self.state['co.pressao'] += (pressure_gen - flow_loss) * dt * 0.2
        self.state['co.pressao'] = max(1.0, min(10, self.state['co.pressao']))
        
        self.state['co.fit03'] = (15.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) if self.state.get('co.xv1', 0) else 0.0
        self.state['co.fit02'] = sum((12.0 * pressao_efetiva / 9.0 + random.uniform(-0.5, 0.5)) for i in range(2, 7) if self.state.get(f'co.xv{i}', 0))
        
        return self.state