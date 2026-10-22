# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

在仓库根目录执行::

    pyinstaller --clean --noconfirm packaging/AutoLogin.spec

产物位于 ``dist/AutoLogin/``（onedir 模式，便于替换配置与排查问题）。
"""
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
SRC = os.path.join(ROOT, "src")
ASSETS = os.path.join(SRC, "autologin", "assets")

datas = [
    (os.path.join(ASSETS, "autologin.ico"), os.path.join("autologin", "assets")),
    (os.path.join(ASSETS, "ATTRIBUTION.txt"), os.path.join("autologin", "assets")),
    (os.path.join(ASSETS, "TWEMOJI-LICENSE.txt"), os.path.join("autologin", "assets")),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all("playwright")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoLogin",
    icon=os.path.join(ASSETS, "autologin.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AutoLogin",
)
