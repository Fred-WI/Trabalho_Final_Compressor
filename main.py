import os
import logging

# 1. Cria uma pasta dedicada para os logs não sujarem a raiz do projeto
diretorio_logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(diretorio_logs):
    os.makedirs(diretorio_logs)

# 2. Caminho do arquivo de log principal
arquivo_log = os.path.join(diretorio_logs, 'scada_system.log')

# 3. Configuração Mestra do Logger
logging.basicConfig(
    level=logging.INFO,  # Captura INFO, WARNING, ERROR e CRITICAL
    format='%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        # Grava os dados no arquivo de texto
        logging.FileHandler(arquivo_log, encoding='utf-8'),
        # (Opcional) Mantém as mensagens aparecendo no terminal enquanto você programa
        logging.StreamHandler() 
    ]
)

from app import CompressorApp

if __name__ == "__main__":
    CompressorApp().run()