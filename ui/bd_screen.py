"""Módulo de visualização e filtragem de dados históricos do sistema de compressão.

Este módulo provê componentes de interface gráfica baseados em Kivy e KivyMD
para apresentação, filtragem por critérios temporais ou categoriais (tags/eventos)
e exportação de dados armazenados em banco de dados para formatos tabulares (CSV).
"""

import csv
import os
from datetime import datetime

from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.factory import Factory
from kivy.properties import StringProperty
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import OneLineListItem
from kivymd.uix.snackbar import Snackbar

Builder.load_file('ui/bd_screen.kv')
from ui.base_screen import BaseScreen
from config import CORES


class MenuCustomItem(OneLineListItem):
    """Item de menu compatível com KivyMD 1.2.0."""

    text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_text_color = "Custom"
        self.text_color = CORES["texto"]


Factory.register("MenuCustomItem", cls=MenuCustomItem)


class BDScreen(BaseScreen):
    """Tela gerenciadora do visualizador de banco de dados e suas operações.
    
    Abstrai a lógica de orquestração de menus suspensos, controle de estados de 
    filtros, leitura sequencial do banco de dados relacional e gerenciamento do
    pipeline de exportação.
    """

    def __init__(self, **kwargs):
        """Inicializa a tela BDScreen configurando seu layout base e propriedades estruturais.
        
        Args:
            **kwargs: Parâmetros nomeados repassados para a classe BaseScreen.
        """
        super().__init__(**kwargs)
        self.name = 'bd'
        self.add_header("Visualizador do Banco de Dados")
        
        self.content = Factory.BDContent()
        self.content.parent_screen = self 
        self.root_layout.add_widget(self.content)
        
        self.menu_tabelas = None
        self.menu_tags = None
        
    def on_enter(self, *args):
        """Manipulador de evento acionado automaticamente ao focar a janela.
        
        Garante a reconstrução do estado dos menus de opções e reavaliação imediata
        dos filtros vigentes no momento do acesso.
        
        Args:
            *args: Argumentos posicionais variáveis disparados pelo gerenciador de telas.
        """
        self.inicializar_menus()
        self.aplicar_filtros()

    def inicializar_menus(self):
        """Instancia os componentes MDDropdownMenu de escopo de tabelas do sistema.
        
        Monta a matriz de dados que popula as opções de contexto operacional 
        entre as tabelas de leituras contínuas ('readings') e ocorrências ('events').
        
        Complexity:
            Tempo: O(1) devido à cardinalidade fixa de opções.
            Espaço: O(1).
        """
        itens_tabela = [
            {
                "viewclass": "MenuCustomItem",
                "text": "readings", 
                "on_release": lambda x="readings": self.set_tabela(x)
            },
            {
                "viewclass": "MenuCustomItem", 
                "text": "events", 
                "on_release": lambda x="events": self.set_tabela(x)
            }
        ]
        
        self.menu_tabelas = MDDropdownMenu(
            caller=self.content.ids.drop_table,
            items=itens_tabela,
            md_bg_color=CORES['fundo_claro']
        )
        self.atualizar_menu_tags()

    def set_tabela(self, nome_tabela):
        """Modifica o estado da tabela alvo de monitoramento.
        
        Atualiza o identificador textual visual do botão seletor, encerra o menu 
        suspenso associado, invalida as tags do escopo anterior e reprocessa a 
        filtragem linear de registros.
        
        Args:
            nome_tabela (str): Nome exato da entidade correspondente no banco (readings/events).
        """
        self.content.ids.text_table.text = nome_tabela 
        self.menu_tabelas.dismiss()
        self.atualizar_menu_tags()
        self.aplicar_filtros()

    def atualizar_menu_tags(self):
        """Reconstrói dinamicamente os submenus baseando-se no contexto de tabela ativa.
        
        Acessa a infraestrutura global da aplicação para extrair mapeamentos de colunas 
        ou tipos de eventos padrão, forçando uma reinicialização do label selecionado.
        
        Complexity:
            Tempo: O(k) onde k é o número de chaves/tags mapeadas no banco de dados.
            Espaço: O(k) para alocação da nova lista estrutural de itens do dropdown.
        """
        app = App.get_running_app()
        tabela_atual = self.content.ids.text_table.text
        
        opcoes = ["Todas as Tags" if tabela_atual == "readings" else "Todos os Eventos"]
        if tabela_atual == "readings":
            opcoes.extend(list(app.db.column_map.keys()))
        else:
            opcoes.extend(["comando", "erro", "info"])

        self.content.ids.text_tag.text = opcoes[0]

        itens_tag = [
            {
                "viewclass": "MenuCustomItem",
                "text": opt, 
                "on_release": lambda x=opt: self.set_tag(x)
            }
            for opt in opcoes
        ]
        
        self.menu_tags = MDDropdownMenu(
            caller=self.content.ids.drop_tag,
            items=itens_tag,
            md_bg_color=CORES['fundo_claro']
        )

    def set_tag(self, nome_tag):
        """Aplica a tag/evento selecionado ao estado lógico do filtro.
        
        Args:
            nome_tag (str): Identificador nominal do filtro categórico.
        """
        self.content.ids.text_tag.text = nome_tag 
        self.menu_tags.dismiss()

    def limpar_filtros(self):
        """Restaura o estado inicial vazio para todos os seletores e inputs da interface.
        
        Executa uma varredura iterativa nos dicionários de IDs visuais limpando strings de entrada
        e dispara de forma automatizada o recarregamento irrestrito de registros.
        """
        campos = ['start_y', 'start_m', 'start_d', 'start_h', 'start_min', 
                  'end_y', 'end_m', 'end_d', 'end_h', 'end_min']
        for c in campos:
            self.content.ids[c].text = ""
            
        tabela_atual = self.content.ids.text_table.text 
        self.content.ids.text_tag.text = "Todas as Tags" if tabela_atual == 'readings' else "Todos os Eventos"
        self.aplicar_filtros()

    # TODO: Refatorar paginação e filtragem. Trazer 2000 registros fixos do banco via `query_table` e aplicar múltiplos filtros lineares em Python gera sobrecarga desnecessária na CPU (O(N)). Recomenda-se delegar a filtragem de datas e tags diretamente ao motor SQL (cláusulas WHERE) no método `query_table`.
    def aplicar_filtros(self):
        """Aplica os critérios de filtragem sobre o conjunto de registros e atualiza a exibição.
        
        Realiza parse defensivo dos campos numéricos fragmentados de data/hora, 
        requisita um snapshot robusto do banco de dados, executa a filtragem linear 
        em memória RAM e formata os dados legíveis injetando-os no RecycleView.
        
        Pre-condições:
            Conexão com o banco ativa através do singleton global App.get_running_app().db.
            
        Pós-condições:
            A propriedade data do widget 'rv_dados' é completamente reestruturada com 
            os dados em conformidade com as restrições vigentes.
            
        Complexity:
            Tempo: O(N) onde N é o número de linhas retornadas pelo banco (limitado a 2000).
            Espaço: O(M) onde M representa a quantidade de dados remanescentes pós-filtragem.
        """
        app = App.get_running_app()
        tabela_atual = self.content.ids.text_table.text  
        filtro_tag = self.content.ids.text_tag.text      

        start_date = None
        end_date = None
        ids = self.content.ids
        
        try:
            if ids.start_y.text and ids.start_m.text and ids.start_d.text:
                h = int(ids.start_h.text) if ids.start_h.text else 0
                m = int(ids.start_min.text) if ids.start_min.text else 0
                start_date = datetime(int(ids.start_y.text), int(ids.start_m.text), int(ids.start_d.text), h, m)
        except ValueError: pass 

        try:
            if ids.end_y.text and ids.end_m.text and ids.end_d.text:
                h = int(ids.end_h.text) if ids.end_h.text else 23
                m = int(ids.end_min.text) if ids.end_min.text else 59
                end_date = datetime(int(ids.end_y.text), int(ids.end_m.text), int(ids.end_d.text), h, m)
        except ValueError: pass

        if tabela_atual == 'readings':
            ids.header_3.text = "Variável (Tag)"
            ids.header_4.text = "Valor Salvo"
        else:
            ids.header_3.text = "Tipo"
            ids.header_4.text = "Descrição do Evento"
            
        data, headers = app.db.query_table(tabela_atual, limit=2000)

        tag_real = app.db.column_map.get(filtro_tag, filtro_tag)
        dados_formatados = []

        for row in data:
            # TODO: Risco de quebra de execução. Se o formato string da data armazenado no row[1] não seguir estritamente o padrão especificado, strptime lançará um ValueError não tratado.
            row_time = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            
            # Filtro de Tempo
            if start_date and row_time < start_date: continue
            if end_date and row_time > end_date: continue
            
            # Filtro de Tag
            if filtro_tag not in ["Todas as Tags", "Todos os Eventos"]:
                if row[2] != tag_real and row[2] != filtro_tag:
                    continue

            # Formatação de Saída
            val = f"{row[3]:.2f}" if isinstance(row[3], float) else str(row[3])
            tag_nome = str(row[2])
            
            if tabela_atual == 'readings' and tag_nome.startswith("co."):
                tag_nome = app.db.tags_config.get(tag_nome, {}).get("descricao", tag_nome)

            dados_formatados.append({
                'col1': str(row[0]),
                'col2': str(row[1]),
                'col3': tag_nome,
                'col4': val
            })
            
        # Injeta na Tabela
        self.content.ids.rv_dados.data = dados_formatados

    # TODO: Possível contenção de escrita de arquivos ou quebra de concorrência. Se o arquivo gerado estiver em uso ou aberto pelo Excel em segundo plano, o interpretador lançará um PermissionError. Recomenda-se adicionar tratamento explícito com blocos try-except refinados.
    def exportar_csv(self):
        """Exporta o estado atual filtrado de dados visíveis em tela para arquivo .csv.
        
        Acessa o cache interno populado na RecycleView, otimizando o consumo de 
        recursos ao dispensar consultas secundárias ao banco de dados, e processa 
        a persistência estrutural de arquivos no formato compatível com planilhas locais.
        
        Pre-condições:
            Deve haver dados lógicos carregados no array 'self.content.ids.rv_dados.data'.
            
        Pós-condições:
            Um arquivo físico no formato UTF-8 com sinalização BOM (Bite Order Mark) é gravado 
            no disco rígido.
            
        Complexity:
            Tempo: O(D) onde D é a quantidade de elementos contidos no cache do RecycleView.
            Espaço: O(1) persistência direta em stream de disco via gerador interno.
        """
        dados_filtrados = self.content.ids.rv_dados.data
        
        if not dados_filtrados:
            self.mostrar_mensagem("Não há dados para exportar com os filtros atuais!")
            return

        tabela_atual = self.content.ids.text_table.text
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"relatorio_{tabela_atual}_{timestamp}.csv"

        cabecalhos = [
            self.content.ids.header_1.text,
            self.content.ids.header_2.text,
            self.content.ids.header_3.text,
            self.content.ids.header_4.text
        ]

        try:
            with open(nome_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                
                writer.writerow(cabecalhos)
                
                for linha in dados_filtrados:
                    writer.writerow([
                        linha['col1'], 
                        linha['col2'], 
                        linha['col3'], 
                        linha['col4']
                    ])
            
            caminho_completo = os.path.abspath(nome_arquivo)
            print(f"Exportado para: {caminho_completo}")
            self.mostrar_mensagem(f"Exportado com sucesso: {nome_arquivo}")

        except Exception as e:
            print(f"Erro ao exportar CSV: {e}")
            self.mostrar_mensagem("Erro ao exportar o arquivo. Verifique o terminal.")

    def mostrar_mensagem(self, texto):
        """Exibe mensagem curta compatível com KivyMD 1.2.0."""
        Snackbar(
            text=texto,
            duration=3
        ).open()
