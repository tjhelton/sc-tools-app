# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SafetyCulture Tools.

Bundles the Streamlit app, pywebview, and all dependencies into a
standalone executable. Produces a .app bundle on macOS and a folder
with an .exe on Windows.

Build:  pyinstaller "SafetyCulture Tools.spec"
Output: dist/SafetyCulture Tools.app  (Mac)
        dist/SafetyCulture Tools/     (Windows)
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ── Analysis ──────────────────────────────────────────────────────────

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("app", "app"),  # Streamlit pages, core modules, and .streamlit config
    ],
    hiddenimports=[
        # Streamlit internals
        "streamlit.web.cli",
        "streamlit.web.bootstrap",
        "streamlit.runtime.scriptrunner",
        "streamlit.runtime.scriptrunner.magic_funcs",
        "streamlit.runtime.state",
        "streamlit.components.v1",
        # Tornado (Streamlit's web server)
        "tornado",
        "tornado.web",
        "tornado.httpserver",
        "tornado.ioloop",
        "tornado.websocket",
        # Click (Streamlit CLI)
        "click",
        # Typing extensions
        "typing_extensions",
        # importlib.metadata (used by many packages)
        "importlib.metadata",
        "importlib_metadata",
        # pandas optional backends
        "pandas._libs.tslibs.np_datetime",
        "pandas._libs.tslibs.nattype",
        "pandas._libs.tslibs.timezones",
        "pandas._libs.skiplist",
        # aiohttp
        "aiohttp",
        "aiohttp.cookiejar",
        # requests/urllib3
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Collect all files for packages that rely on bundled data / dynamic imports
for pkg in [
    "streamlit",
    "webview",
    "altair",
    "pandas",
    "pydeck",
    "pyarrow",
    "plotly",
    "aiohttp",
    "rich",
    "click",
    "tornado",
]:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        a.datas += pkg_datas
        a.binaries += pkg_binaries
        a.hiddenimports += pkg_hidden
    except Exception:
        pass  # optional package not installed

# ── Build ─────────────────────────────────────────────────────────────

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SafetyCulture Tools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no terminal window
    icon="build_assets/icon.icns" if sys.platform == "darwin" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SafetyCulture Tools",
)

# ── macOS .app bundle ─────────────────────────────────────────────────

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SafetyCulture Tools.app",
        icon="build_assets/icon.icns",
        bundle_identifier="com.safetyculture.tools",
        info_plist={
            "CFBundleName": "SafetyCulture Tools",
            "CFBundleDisplayName": "SafetyCulture Tools",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
