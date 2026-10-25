# PyInstaller-Rezept: `pyinstaller --noconfirm boerse.spec`
# Auf dem Mac entsteht dist/Börse EC Thun.app, auf Windows dist/BoerseECThun mit .exe (zum Testen des Verpackens).
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

NAME = "Börse EC Thun"
# Programmdatei in der App ohne Umlaut: codesign stolpert über die zwei Schreibweisen von «ö» (Unicode NFC/NFD)
EXE_NAME = "BoerseECThun"
VERSION = re.search(r'__version__ = "(.+)"', Path("boerse/__init__.py").read_text(encoding="utf-8")).group(1)
ICON = "inventar/assets/app-icon.png"


def without_extras(name: str) -> bool:
    # GIS und Postgres braucht die App nicht; ihre Module lassen sich ohne Zusatzprogramme nicht laden
    return not any(part in name for part in (".gis", ".postgres", ".oracle", ".mysql"))


# Django sucht Vorlagen, statische Dateien und Migrationen als Dateien neben den Modulen
datas = [
    ("inventar/templates", "inventar/templates"),
    ("inventar/static", "inventar/static"),
    ("inventar/assets", "inventar/assets"),
    ("inventar/migrations", "inventar/migrations"),
]
datas += collect_data_files("django")
for app in ("django.contrib.contenttypes", "django.contrib.sessions"):
    datas += collect_data_files(app, include_py_files=True, subdir="migrations")
datas += collect_data_files("numbers_parser") + collect_data_files("fpdf")

hiddenimports = (
    collect_submodules("django", filter=without_extras)
    + collect_submodules("inventar", filter=lambda n: ".tests" not in n)
    + collect_submodules("boerse")
    + collect_submodules("whitenoise")
    + ["waitress"]
)

a = Analysis(
    ["app.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    console=sys.platform != "darwin",
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name=EXE_NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=ICON,
        bundle_identifier="ch.ecthun.boerse",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": NAME,
            "CFBundleName": NAME,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
