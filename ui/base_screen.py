from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle
from kivy.metrics import sp

from config import CORES
from ui.custom_widgets import IconButton

class BaseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_layout = BoxLayout(orientation='vertical')
        with self.canvas.before: Color(*CORES['fundo']); self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda i,v: setattr(self.bg, 'pos', v), size=lambda i,v: setattr(self.bg, 'size', v))
        self.add_widget(self.root_layout)

    def add_header(self, title_text, show_back_button=True):
        header = BoxLayout(size_hint_y=None, height=sp(55), padding=(sp(15), sp(5)), spacing=sp(20))
        with header.canvas.before: Color(*CORES['fundo_claro']); header.bg_rect = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=lambda i, v: setattr(i.bg_rect, 'pos', v), size=lambda i, v: setattr(i.bg_rect, 'size', v))
        header.add_widget(Label(text=title_text, font_size=sp(20), bold=True, color=CORES['texto'], size_hint_x=0.8))
        if show_back_button:
            back_button = IconButton(icon_name='arrow_back', size_hint_x=None, width=sp(120))
            back_button.bind(on_press=lambda x: setattr(self.manager, 'current', 'dashboard'))
            header.add_widget(back_button)
        self.root_layout.add_widget(header)

