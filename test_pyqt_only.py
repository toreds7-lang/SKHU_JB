"""PyQt6만 테스트"""
import sys
print(f"Python: {sys.version}")
from PyQt6.QtWidgets import QApplication, QLabel
app = QApplication(sys.argv)
label = QLabel("Hello from PyInstaller!")
label.show()
print("App started OK")
sys.exit(app.exec())
