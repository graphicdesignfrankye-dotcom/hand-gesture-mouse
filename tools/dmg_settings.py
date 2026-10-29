# Impostazioni per dmgbuild. Uso: dmgbuild -s tools/dmg_settings.py -D app=PATH -D bg=PATH "Hand Gesture Mouse" out.dmg
import os

app = defines["app"]
appname = os.path.basename(app)

format = "UDZO"
filesystem = "HFS+"
files = [app]
symlinks = {"Applications": "/Applications"}
icon = "icons/AppIcon.icns"            # icona del volume montato
background = defines["bg"]

window_rect = ((200, 120), (660, 400))
default_view = "icon-view"
icon_size = 128
text_size = 13
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_locations = {appname: (170, 200), "Applications": (490, 200)}
