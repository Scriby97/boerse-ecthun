# Einstellungen für dmgbuild: Installationsfenster mit App, Verknüpfung «Programme» und Hintergrundbild.
# Aufruf (im Bau auf GitHub): dmgbuild -s scripts/dmg_settings.py -D app=<App> -D background=<Bild> "<Name>" <Datei.dmg>
import os.path

app = defines["app"]  # noqa: F821 – dmgbuild stellt `defines` bereit
app_name = os.path.basename(app)

format = "UDZO"
files = [app]
symlinks = {"Programme": "/Applications"}
background = defines["background"]  # noqa: F821
# Fenster 600 × 400 wie das Hintergrundbild (scripts/dmg_background.py)
window_rect = ((200, 120), (600, 400))
default_view = "icon-view"
icon_size = 128
text_size = 13
icon_locations = {app_name: (150, 190), "Programme": (450, 190)}
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
