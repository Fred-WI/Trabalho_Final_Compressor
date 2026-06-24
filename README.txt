SUPER-AURORA MODULAR

Execução:
python main.py

Estrutura:
- main.py: ponto de entrada do programa.
- app.py: cria a aplicação Kivy e registra as telas.
- config.py: cores e configurações globais.
- controllers/: comunicação Modbus, controle e simulação.
- database/: banco de dados e futura implementação ORM.
- ui/: telas e widgets da interface gráfica.
- assets/: imagens, ícones e fontes.

Divisão sugerida:
- Aba 1 e 4: controllers/modbus_controller.py, database/, ui/graficos_screen.py, ui/historico_screen.py.
- Aba 2 e 3: ui/dashboard_screen.py, ui/valvulas_screen.py, ui/base_screen.py, ui/custom_widgets.py e partes de controle.
