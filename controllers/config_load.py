"""
Módulo de gerenciamento de configurações estruturadas para o sistema SCADA.

Este módulo é responsável por carregar, validar e desserializar metadados 
de comunicação Modbus e parâmetros operacionais da aplicação a partir de 
arquivos de configuração no formato JSON, transferindo essas estruturas 
para o endereçamento em memória RAM.
"""

import json
import os
import logging

# Configuração básica de log para monitoramento industrial
logger = logging.getLogger("SCADA_TagManager")

# TODO: Centralizar a lógica de leitura e parsing de JSON em uma função genérica (ex: _load_json) para respeitar o princípio DRY (Don't Repeat Yourself), visto que 'load_tags' e 'load_configs' possuem estrutura idêntica.
def load_tags(filepath: str = "config/tags_compressor.json") -> dict:
    """
    Carrega e desserializa o mapeamento de tags Modbus a partir de um arquivo JSON.

    Este dicionário resultante orienta o roteamento de leitura e escrita do controlador 
    Modbus, definindo os endereços de registradores, tipos de dados e permissões 
    necessárias para a comunicação com o CLP.

    Args:
        filepath (str, opcional): Caminho relativo ou absoluto para o arquivo JSON de definição de tags. Padrão é "config/tags_compressor.json".

    Returns:
        dict: Estrutura de dados contendo o mapeamento das tags. Retorna um dicionário vazio em caso de falha de localização ou parsing.

    Raises:
        Nenhuma exceção é propagada ao chamador; erros de sistema de arquivos ou decodificação JSON são isolados e registrados no log interno.

    Complexity:
        Tempo: O(N) | Espaço: O(N), onde N é o tamanho (número de caracteres/chaves) do arquivo JSON.

    Pré-condições:
        O arquivo no caminho especificado deve existir e possuir uma estrutura JSON válida.
    Pós-condições:
        O estado global da aplicação permanece inalterado. Os dados são transferidos do armazenamento secundário para a memória primária estruturada.
    """
    # TODO: A utilização de caminhos relativos como padrão lógico pode causar falhas de resolução (FileNotFound) caso o diretório de trabalho atual (CWD) do processo principal difira da raiz projetada.
    if not os.path.exists(filepath):
        logger.error(f"Erro Crítico: Arquivo de configuração não encontrado -> {filepath}")
        # TODO: O retorno de um dicionário vazio mascara a falha crítica de dependência para a função chamadora. Considerar a propagação da exceção (raise) ou retorno de flag de status lógico.
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
    Carrega e desserializa os parâmetros globais e de rede da aplicação SCADA.

    A estrutura gerada fornece os parâmetros estáticos de configuração (ex: IPs, 
    portas TCP, timeouts e mapeamentos de interface) exigidos para a inicialização 
    e orquestração das instâncias do controlador.

    Args:
        filepath (str, opcional): Caminho relativo ou absoluto para o arquivo JSON de configurações. Padrão é "config/app_configs.json".

    Returns:
        dict: Estrutura contendo os parâmetros de configuração. Retorna um dicionário vazio em caso de falha no processo de leitura.

    Raises:
        Nenhuma exceção é propagada ao chamador. Falhas são processadas via rotinas de logging.

    Complexity:
        Tempo: O(M) | Espaço: O(M), onde M é o tamanho do arquivo JSON de configurações.

    Pré-condições:
        O arquivo especificado deve estar acessível para leitura e formatado com sintaxe JSON.
    Pós-condições:
        Nenhum efeito colateral no estado do sistema fora o consumo de I/O temporário para a leitura do disco.
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