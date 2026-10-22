# PyInstaller build for the desktop app: pyinstaller havoc_analyzer.spec
# Produces dist/HavocAnalyzer(.exe), a single file with the top-player benchmarks bundled.
a = Analysis(
    ["havoc_gui/__main__.py"],
    pathex=["."],
    datas=[("wcl/data/benchmarks.json", "wcl/data")],
    hiddenimports=["wcl.wcl_client"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="HavocAnalyzer",
    console=False,
    upx=False,
)
