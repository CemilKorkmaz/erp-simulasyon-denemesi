# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — ERP Simülasyonu tek dosyalık uygulama.

Üretmek için (kendi bilgisayarında):
    pip install -r requirements.txt pyinstaller
    pyinstaller --noconfirm --clean erp_launcher.spec

Çıktı: dist/ERP_Simulasyon   (Windows'ta dist/ERP_Simulasyon.exe)

Not: Arayüz dosyaları (frontend/) paketin İÇİNE gömülür ve çalışırken
geçici bir klasöre açılır. Veritabanı (erp_sim.db) ise her zaman
uygulamanın YANINA yazılır (launcher.py bunu ayarlar).
"""

import os
import sys

block_cipher = None

# Proje kökü (bu spec dosyasının bulunduğu klasör)
ROOT = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821  (PyInstaller sağlar)

datas = [
    # Arayüz: HTML/JS/CSS. Hedef klasör adı "frontend" olmalı.
    (os.path.join(ROOT, "frontend"), "frontend"),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "asyncua",
    "asyncua.server",
    "asyncua.client",
    "asyncua.crypto",
    "websockets",
    "websockets.legacy",
    "erp_backend.main",
    "erp_backend.database",
    "simulator.plant",
    "simulator.furnace",
    "simulator.opcua_server",
]

a = Analysis(
    [os.path.join(ROOT, "erp_backend", "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ERP_Simulasyon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # --windowed: Windows/macOS'ta konsol penceresi açmaz.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
