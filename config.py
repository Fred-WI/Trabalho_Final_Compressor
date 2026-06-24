import os

CORES = {
    'primaria': (0.47, 0.32, 0.66, 1), 'fundo': (0.17, 0.17, 0.22, 1),
    'fundo_claro': (0.22, 0.22, 0.28, 1), 'fundo_painel': (0.20, 0.20, 0.26, 1),
    'texto': (0.95, 0.95, 0.95, 1), 'sucesso': (0.18, 0.80, 0.44, 1),
    'erro': (0.91, 0.30, 0.24, 1), 'alerta': (0.95, 0.77, 0.06, 1),
    'info': (0.20, 0.60, 0.86, 1), 'desabilitado': (0.5, 0.5, 0.5, 1),
    'hover': (0.57, 0.42, 0.76, 1)
}

ICON_FONT = os.path.join('assets', 'MaterialIcons-Regular.ttf')
if os.path.exists(ICON_FONT):
    from kivy.core.text import LabelBase
    LabelBase.register(name='MaterialIcons', fn_regular=ICON_FONT)
else:
    ICON_FONT = None
