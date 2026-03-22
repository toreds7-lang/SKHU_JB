# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['test_minimal.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['faiss', 'faiss.swigfaiss', 'langchain_community.retrievers.bm25', 'langchain_classic.retrievers', 'langchain_openai', 'langgraph.graph', 'langgraph.graph.state', 'kiwipiepy', 'networkx', 'numpy', 'nbformat', 'tiktoken', 'tiktoken_ext.openai_public', 'tiktoken_ext', 'PyQt6.QtCore', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.QtWebEngineWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['streamlit', 'tornado', 'matplotlib', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='test_minimal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='test_minimal',
)
