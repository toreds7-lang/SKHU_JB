# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 빌드 스펙 파일
사용법:
  pyinstaller build.spec
결과물:
  dist/SKHU_Agent/SKHU_Agent.exe
"""

import os
import sys
from pathlib import Path

block_cipher = None

# kiwipiepy + kiwipiepy_model 데이터 파일 경로 자동 탐색
def _collect_kiwipiepy():
    result = []
    for pkg_name in ["kiwipiepy", "kiwipiepy_model"]:
        try:
            pkg = __import__(pkg_name)
            pkg_dir = Path(pkg.__file__).parent
            for pattern in ["**/*.dict", "**/*.bin", "**/*.json", "**/*.txt",
                            "**/*.mdl", "**/*.morph"]:
                for f in pkg_dir.glob(pattern):
                    dest = str(f.parent.relative_to(pkg_dir.parent))
                    result.append((str(f), dest))
        except ImportError:
            pass
    return result


a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # 리소스 파일
        ("SK_Hynix.png",          "."),
        ("system_prompt.txt",     "."),
        ("resources/dark_theme.qss", "resources"),
        ("resources/chat.html",      "resources"),
        ("resources/js",             "resources/js"),
        # kiwipiepy 모델 데이터
        *_collect_kiwipiepy(),
    ],
    hiddenimports=[
        # FAISS
        "faiss",
        "faiss.swigfaiss",
        # LangChain 생태계
        "langchain_community.retrievers.bm25",
        "langchain_classic.retrievers",
        "langchain_openai",
        "langchain_core.messages",
        "langchain_core.documents",
        "langchain_text_splitters",
        "langgraph.graph",
        "langgraph.graph.state",
        # kiwipiepy
        "kiwipiepy",
        "kiwipiepy_model",
        # networkx
        "networkx",
        "networkx.algorithms",
        # numpy / scipy
        "numpy",
        "scipy.sparse",
        # nbformat
        "nbformat",
        "nbformat.v4",
        # tiktoken
        "tiktoken",
        "tiktoken_ext.openai_public",
        "tiktoken_ext",
        # Pillow
        "PIL.Image",
        # PyQt6
        "PyQt6.QtCore",
        "PyQt6.QtWidgets",
        "PyQt6.QtGui",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "streamlit",
        "tornado",
        "altair",
        "bokeh",
        "matplotlib",
        "tkinter",
        "jupyter",
        "notebook",
        "IPython",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SKHU_Agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # 배포용 - 콘솔 창 없음
    icon="SK_Hynix.ico" if os.path.exists("SK_Hynix.ico") else None,
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SKHU_Agent",
)

# ──────────────────────────────────────────────────────────────────────────────
# 빌드 전 준비 사항:
#
# 1. ICO 파일 생성 (PNG → ICO):
#    python -c "from PIL import Image; Image.open('SK_Hynix.png').save('SK_Hynix.ico')"
#
# 2. PyInstaller 설치:
#    pip install pyinstaller>=6.8.0
#
# 3. 빌드 실행:
#    pyinstaller build.spec
#
# 4. 배포:
#    dist/SKHU_Agent/ 폴더 전체를 배포
#    사용자는 SKHU_Agent.exe 옆에 env.txt와 work/ 폴더를 배치
# ──────────────────────────────────────────────────────────────────────────────
