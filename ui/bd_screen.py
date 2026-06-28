from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.metrics import sp
from config import CORES
from ui.base_screen import BaseScreen

class BDScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'bd'
        self.add_header("Visualizador do Banco de Dados")
        
        controls = BoxLayout(size_hint_y=None, height=sp(50), padding=10, spacing=10)
        self.spinner_table = Spinner(
            text='readings', 
            values=('readings', 'events'), 
            background_color=CORES['primaria']
        )
        self.spinner_table.bind(text=self.load_table)
        
        controls.add_widget(Label(text="Selecionar Tabela:", size_hint_x=0.3))
        controls.add_widget(self.spinner_table)
        self.root_layout.add_widget(controls)
        
        self.scroll_view = ScrollView()
        self.data_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.data_layout.bind(minimum_height=self.data_layout.setter('height'))
        
        self.scroll_view.add_widget(self.data_layout)
        self.root_layout.add_widget(self.scroll_view)

    def on_enter(self, *args): 
        self.load_table()

    def load_table(self, *args):
        self.data_layout.clear_widgets()
        table_name = self.spinner_table.text
        app = App.get_running_app()
        
        data, headers = app.db.query_table(table_name)
        if not headers: return
        
        # Mapa limpo e compatível com a nova estrutura do Historian
        if table_name == 'readings':
            header_map = {'id': 'ID', 'timestamp': 'Data e Hora', 'tag_name': 'Variável (Tag)', 'value': 'Valor Salvo'}
        else: 
            header_map = {'id': 'ID', 'timestamp': 'Data e Hora', 'type': 'Tipo', 'description': 'Descrição do Evento'}
            
        header_grid = GridLayout(cols=len(headers), size_hint_y=None, height=sp(40))
        for header in headers: 
            header_grid.add_widget(Label(text=header_map.get(header, header.title()), bold=True, color=CORES['primaria']))
        self.data_layout.add_widget(header_grid)
        
        for row in data:
            row_grid = GridLayout(cols=len(row), size_hint_y=None, height=sp(30))
            for item in row:
                if isinstance(item, float):
                    text = f"{item:.2f}"
                else:
                    text = str(item)
                
                # Tratamento para deixar tags mais legíveis na tela (opcional)
                if table_name == 'readings' and str(item).startswith("co."):
                    text = app.db.tags_config.get(str(item), {}).get("descricao", text)

                row_grid.add_widget(Label(text=text[:45] + "..." if len(text) > 48 else text, font_size=sp(12)))
            self.data_layout.add_widget(row_grid)