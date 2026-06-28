import json
import os
import logging

# Configuração básica de log para monitoramento industrial
logger = logging.getLogger("SCADA_TagManager")

def load_tags(filepath: str = "config/tags_compressor.json") -> dict:
    """
    Lê as tags Modbus do arquivo JSON e retorna um dicionário em memória.
    """
    if not os.path.exists(filepath):
        logger.error(f"Erro Crítico: Arquivo de configuração não encontrado -> {filepath}")
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            tags_addrs = json.load(file)
            logger.info(f"Sucesso: {len(tags_addrs)} tags carregadas do arquivo {filepath}.")
            return tags_addrs
    except json.JSONDecodeError as e:
        logger.error(f"Erro de sintaxe no arquivo JSON ({filepath}): {e}")
        return {}
    except Exception as e:
        logger.error(f"Erro inesperado ao carregar tags: {e}")
        return {}

def load_configs(filepath: str = "config/app_configs.json") -> dict:
    """
    Lê as configurações do app Modbus do arquivo JSON e retorna um dicionário em memória.
    """
    if not os.path.exists(filepath):
        logger.error(f"Erro Crítico: Arquivo de configuração não encontrado -> {filepath}")
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            configs = json.load(file)
            logger.info(f"Sucesso: {len(configs)} configs carregadas do arquivo {filepath}.")
            return configs
    except json.JSONDecodeError as e:
        logger.error(f"Erro de sintaxe no arquivo JSON ({filepath}): {e}")
        return {}
    except Exception as e:
        logger.error(f"Erro inesperado ao carregar configs: {e}")
        return {}
