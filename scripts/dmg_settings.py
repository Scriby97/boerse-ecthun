# Einstellungen für dmgbuild: Installationsfenster mit App, Verknüpfung «Programme» und Hintergrundbild.
# Aufruf (im Bau auf GitHub): dmgbuild -s scripts/dmg_settings.py -D app=<App> -D background=<Bild> "<Name>" <Datei.dmg>
import os.path
import unicodedata

app = defines["app"]  # noqa: F821 – dmgbuild stellt `defines` bereit
app_name = os.path.basename(app)

format = "UDZO"
files = [app]
symlinks = {"Programme": "/Applications"}
background = defines["background"]  # noqa: F821
# Inhalt 600 × 400 wie das Hintergrundbild (scripts/dmg_background.py), plus 28 für die Titelleiste
window_rect = ((200, 120), (600, 428))
default_view = "icon-view"
icon_size = 128
text_size = 13
# «ö» in beiden Unicode-Schreibweisen: der Finder liefert den Namen zerlegt (NFD), hier steht er meist als NFC
icon_locations = {unicodedata.normalize(form, app_name): (150, 190) for form in ("NFC", "NFD")}
icon_locations["Programme"] = (450, 190)
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
