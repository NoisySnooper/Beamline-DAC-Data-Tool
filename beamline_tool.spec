# beamline_tool.spec  --  PyInstaller ONEDIR build for the DAC Quick-Look tool.
# Build:  pyinstaller beamline_tool.spec
# Output: dist\SPARTA\SPARTA.exe  (ship the whole folder)

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("matplotlib", "cmcrameri", "scipy", "numpy", "PIL", "sv_ttk"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ["win32clipboard", "win32con", "pywintypes"]
# ship the app icon so the runtime title-bar/taskbar icon loads (app.py
# reads icon.png from sys._MEIPASS when frozen)
datas += [("icon.png", ".")]
# brand typeface (SPARTA / DESIGN_RULES.md): Jost statics + license,
# loaded privately at startup from <app dir>/fonts. OpenDyslexic (also
# OFL) is an App-font choice in the top bar's Settings dropdown; without
# it that entry falls back to Comic Sans MS.
datas += [("fonts/Jost-Regular.ttf", "fonts"),
          ("fonts/Jost-Medium.ttf", "fonts"),
          ("fonts/Jost-SemiBold.ttf", "fonts"),
          ("fonts/Jost-Bold.ttf", "fonts"),
          ("fonts/OFL.txt", "fonts"),
          ("fonts/OpenDyslexic-Regular.otf", "fonts"),
          ("fonts/OpenDyslexic-Bold.otf", "fonts"),
          ("fonts/OpenDyslexic-Italic.otf", "fonts"),
          ("fonts/OpenDyslexic-Bold-Italic.otf", "fonts"),
          ("fonts/OFL-OpenDyslexic.txt", "fonts")]
# Guide panel content + the bundled demo series the welcome tour loads.
# guide_tour.py looks for both under sys._MEIPASS, beside the exe, and
# beside the source, so either destination layout works.
import glob as _glob
datas += [(p, "docs/guide_content")
          for p in _glob.glob("docs/guide_content/*.md")]
datas += [("docs/guide_content/manifest.json", "docs/guide_content"),
          ("docs/QUICKSTART.pdf", "docs")]
datas += [(p, "demo_data") for p in _glob.glob("demo_data/vis_*")]
datas += [("demo_data/README.txt", "demo_data")]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

# exclude_binaries=True + COLLECT => onedir (folder) build, not onefile.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SPARTA",
    debug=False,
    strip=False,
    upx=False,
    console=False,            # windowed app, no console box
    version="version_info.txt",
    icon="icon.ico",          # exe / taskbar icon
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SPARTA",
)
