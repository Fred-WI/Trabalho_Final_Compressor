from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.factory import Factory
from kivy.properties import StringProperty
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import MDListItem, MDListItemHeadlineText
from datetime import datetime

Builder.load_file('ui/bd_screen.kv')
from ui.base_screen import BaseScreen
from config import CORES


class MenuCustomItem(MDListItem):
    text = StringProperty()

    def __init__(self, **kwargs):
        # 1. Criamos o label de texto com a cor branca ANTES de iniciar a classe base
        # self.md_bg_color = CORES["fundo_claro"]
        self.lbl = MDListItemHeadlineText(
            theme_text_color="Custom",
            text_color=CORES["texto"] # A cor branca do seu config
        )
        # 2. Iniciamos a classe base (isso vai disparar o 'on_text' abaixo e criar os IDs internos)
        super().__init__(**kwargs)
        # 3. Com a classe base pronta e os IDs criados, adicionamos o texto com segurança
        self.add_widget(self.lbl)

    def on_text(self, instance, value):
        # Atualiza o texto do label sempre que o KivyMD mudar a propriedade 'text'
        if hasattr(self, 'lbl'):
            self.lbl.text = value

class BDScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'bd'
        self.add_header("Visualizador do Banco de Dados")
        
        # Cria a interface do KV usando Factory (Classe Dinâmica) e injeta no BaseScreen
        self.content = Factory.BDContent()  # <-- CORREÇÃO AQUI
        self.content.parent_screen = self 
        self.root_layout.add_widget(self.content)
        
        self.menu_tabelas = None
        self.menu_tags = None
        
    def on_enter(self, *args):
        self.inicializar_menus()
        self.aplicar_filtros()

    def inicializar_menus(self):
        # 1. Configuração dos itens usando nossa classe customizada
        itens_tabela = [
            {
                "viewclass": "MenuCustomItem", # <-- Usa o item que criamos acima
                "text": "readings", 
                "on_release": lambda x="readings": self.set_tabela(x)
            },
            {
                "viewclass": "MenuCustomItem", # <-- Usa o item que criamos acima
                "text": "events", 
                "on_release": lambda x="events": self.set_tabela(x)
            }
        ]
        
        # 2. Configuração do Menu (mantendo o seu fundo_claro customizado)
        self.menu_tabelas = MDDropdownMenu(
            caller=self.content.ids.drop_table,
            items=itens_tabela,
            md_bg_color=CORES['fundo_claro']
        )
        self.atualizar_menu_tags()

    def set_tabela(self, nome_tabela):
        self.content.ids.text_table.text = nome_tabela  # <- Mudou aqui
        self.menu_tabelas.dismiss()
        self.atualizar_menu_tags()
        self.aplicar_filtros()

    def atualizar_menu_tags(self):
        app = App.get_running_app()
        tabela_atual = self.content.ids.text_table.text
        
        opcoes = ["Todas as Tags" if tabela_atual == "readings" else "Todos os Eventos"]
        if tabela_atual == "readings":
            opcoes.extend(list(app.db.column_map.keys()))
        else:
            opcoes.extend(["comando", "erro", "info"])

        self.content.ids.text_tag.text = opcoes[0]

        # Aplicando a classe customizada nas tags também
        itens_tag = [
            {
                "viewclass": "MenuCustomItem", # <-- Usa o item que criamos acima
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
        self.content.ids.text_tag.text = nome_tag  # <- Mudou aqui
        self.menu_tags.dismiss()

    def limpar_filtros(self):
        campos = ['start_y', 'start_m', 'start_d', 'start_h', 'start_min', 
                  'end_y', 'end_m', 'end_d', 'end_h', 'end_min']
        for c in campos:
            self.content.ids[c].text = ""
            
        tabela_atual = self.content.ids.text_table.text  # <- Mudou aqui
        self.content.ids.text_tag.text = "Todas as Tags" if tabela_atual == 'readings' else "Todos os Eventos" # <- Mudou aqui
        self.aplicar_filtros()

    def aplicar_filtros(self):
        app = App.get_running_app()
        tabela_atual = self.content.ids.text_table.text  
        filtro_tag = self.content.ids.text_tag.text      

        # 1. Montagem Segura de Datas (Ignora se o usuário não preencheu tudo)
        start_date = None
        end_date = None
        ids = self.content.ids
        
        try:
            if ids.start_y.text and ids.start_m.text and ids.start_d.text:
                h = int(ids.start_h.text) if ids.start_h.text else 0
                m = int(ids.start_min.text) if ids.start_min.text else 0
                start_date = datetime(int(ids.start_y.text), int(ids.start_m.text), int(ids.start_d.text), h, m)
        except ValueError: pass # Data inválida (ex: 32 de Janeiro)

        try:
            if ids.end_y.text and ids.end_m.text and ids.end_d.text:
                h = int(ids.end_h.text) if ids.end_h.text else 23
                m = int(ids.end_min.text) if ids.end_min.text else 59
                end_date = datetime(int(ids.end_y.text), int(ids.end_m.text), int(ids.end_d.text), h, m)
        except ValueError: pass

        # 2. Busca e Atualização de Cabeçalhos
        if tabela_atual == 'readings':
            ids.header_3.text = "Variável (Tag)"
            ids.header_4.text = "Valor Salvo"
        else:
            ids.header_3.text = "Tipo"
            ids.header_4.text = "Descrição do Evento"
            
        # Traz um lote grande do banco para filtrar localmente
        data, headers = app.db.query_table(tabela_atual, limit=2000)

        # 3. Lógica de Filtragem
        tag_real = app.db.column_map.get(filtro_tag, filtro_tag)
        dados_formatados = []

        for row in data:
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

    def exportar_csv(self):
        print("Em breve: Exportar CSV!")