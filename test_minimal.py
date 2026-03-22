"""최소 테스트 - PyInstaller 빌드 문제 진단용"""
import sys
print(f"Python started: {sys.version}")
print(f"Frozen: {getattr(sys, 'frozen', False)}")

# Step 1: 기본 import
try:
    from pathlib import Path
    print("Step 1 OK: pathlib")
except Exception as e:
    print(f"Step 1 FAIL: {e}")

# Step 2: PyQt6
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    print("Step 2 OK: PyQt6")
except Exception as e:
    print(f"Step 2 FAIL: {e}")

# Step 3: PyQt6 WebEngine
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    print("Step 3 OK: QtWebEngine")
except Exception as e:
    print(f"Step 3 FAIL: {e}")

# Step 4: numpy/faiss
try:
    import numpy
    print(f"Step 4a OK: numpy {numpy.__version__}")
except Exception as e:
    print(f"Step 4a FAIL: {e}")

try:
    import faiss
    print(f"Step 4b OK: faiss")
except Exception as e:
    print(f"Step 4b FAIL: {e}")

# Step 5: langchain
try:
    from langchain_openai import ChatOpenAI
    print("Step 5 OK: langchain")
except Exception as e:
    print(f"Step 5 FAIL: {e}")

# Step 6: rag_core
try:
    from rag_core import _load_env_txt
    print("Step 6 OK: rag_core")
except Exception as e:
    print(f"Step 6 FAIL: {e}")

# Step 7: UI
try:
    from ui.main_window import MainWindow
    print("Step 7 OK: MainWindow")
except Exception as e:
    print(f"Step 7 FAIL: {e}")

print("All steps completed")
input("Press Enter to exit...")
