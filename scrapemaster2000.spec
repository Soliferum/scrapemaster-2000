# PyInstaller build recipe for ScrapeMaster 2000.
# Used by build_windows.bat / build_mac_linux.sh - you normally don't need to touch this.
import sys

icon = "assets/icon.ico" if sys.platform == "win32" else "assets/icon.png"

a = Analysis(
    ["scrapemaster2000.py"],
    datas=[("scrapemaster2000.html", ".")],
    hiddenimports=["certifi"],
    excludes=["tkinter", "unittest", "pydoc", "PIL", "numpy"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="ScrapeMaster2000",
    icon=icon,
    console=True,   # the small window shows the app is running; closing it quits
    upx=False,      # UPX-compressed exes trigger more antivirus false alarms
)
