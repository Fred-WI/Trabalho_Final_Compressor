from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import ListProperty, StringProperty, NumericProperty
from kivy.metrics import sp

from config import CORES, ICON_FONT

class HoverButton(Button):
    background_color_normal = ListProperty(CORES['primaria'])
    background_color_hover = ListProperty(CORES['hover'])
    disabled_color = ListProperty(CORES['desabilitado'])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''; self.background_down = ''
        Window.bind(mouse_pos=self.on_mouse_pos)
        self.update_color()

    def on_disabled(self, instance, value): self.update_color()
    def on_mouse_pos(self, *args):
        if not self.get_root_window(): return
        if self.collide_point(*self.to_widget(*args[1])) and not self.disabled:
            self.background_color = self.background_color_hover
        else: self.update_color()
    def update_color(self, *args):
        self.background_color = self.disabled_color if self.disabled else self.background_color_normal


class IconButton(HoverButton):
    def __init__(self, icon_name, **kwargs):
        kwargs.pop('text', None)
        super().__init__(**kwargs)
        self.font_name = 'MaterialIcons' if ICON_FONT else 'Roboto'
        self.text = icon_name if ICON_FONT else '?'


class ValueIndicator(BoxLayout):
    min_val = NumericProperty(0); max_val = NumericProperty(100); current_val = NumericProperty(0)
    alert_level = NumericProperty(80); critical_level = NumericProperty(90); unit = StringProperty(''); label_text = StringProperty('')
    status_color = ListProperty(CORES['sucesso'])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'; self.spacing = sp(5); self.padding = sp(8)
        with self.canvas.before:
            self.bg_color = Color(*CORES['fundo_claro'])
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
        self.bind(pos=self._update_canvas, size=self._update_canvas, current_val=self._update_status)
        
        self.value_label = Label(font_size=sp(20), bold=True, size_hint_y=None, height=sp(28))
        self.add_widget(Label(text=self.label_text, font_size=sp(15), size_hint_y=None, height=sp(20)))
        self.add_widget(self.value_label)
        self.bar = FloatLayout(size_hint_y=None, height=sp(10)); self.add_widget(self.bar)
        self.bind(current_val=self._update_display, pos=self._update_display, size=self._update_display)

    def _update_canvas(self, *args): self.bg_rect.pos = self.pos; self.bg_rect.size = self.size
    def _update_status(self, *args):
        if self.current_val >= self.critical_level: self.status_color = CORES['erro']
        elif self.current_val >= self.alert_level: self.status_color = CORES['alerta']
        else: self.status_color = CORES['sucesso']
        self.bg_color.rgba = (*self.status_color[:3], 0.25)
    def _update_display(self, *args):
        self.value_label.text = f"{self.current_val:.2f} {self.unit}"
        self.bar.canvas.clear()
        with self.bar.canvas:
            Color(*CORES['fundo_painel']); RoundedRectangle(pos=self.bar.pos, size=self.bar.size, radius=[5])
            progress = max(0, min(1, (self.current_val - self.min_val) / (self.max_val - self.min_val) if self.max_val > self.min_val else 0))
            Color(*self.status_color)
            RoundedRectangle(pos=self.bar.pos, size=(self.bar.width * progress, self.bar.height), radius=[5])

# --- Controlador Modbus ---
