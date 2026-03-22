"""
DocsTab - 문서 탐색 탭
Streamlit Tab2 대체
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem,
    QDialog, QTextEdit, QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class CellDetailDialog(QDialog):
    """셀 전체 소스 표시 다이얼로그"""
    def __init__(self, cell: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"{'🟠' if cell['cell_type'] == 'code' else '🟣'} "
            f"{cell['notebook']} · 셀 #{cell['cell_idx']} [{cell['cell_type']}]"
        )
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(cell["source"])
        edit.setFont(QFont("JetBrains Mono, Consolas, Courier New", 11))
        if cell["cell_type"] == "code":
            edit.setStyleSheet(
                "QTextEdit { background: #111827; color: #f8f8f2; "
                "border: 1px solid #fb923c; border-radius: 6px; padding: 8px; }"
            )
        else:
            edit.setStyleSheet(
                "QTextEdit { background: #111827; color: #c4b5fd; "
                "border: 1px solid #a78bfa; border-radius: 6px; padding: 8px; }"
            )
        layout.addWidget(edit)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


class DocsTab(QWidget):
    def __init__(self):
        super().__init__()
        self._cells: list[dict] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        title = QLabel("📄  전체 셀 탐색")
        title.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        # ── 필터 행 ──────────────────────────────────────────────────────────
        filter_row = QHBoxLayout()

        self.nb_combo = QComboBox()
        self.nb_combo.addItem("전체 노트북")
        self.nb_combo.setMinimumWidth(160)
        self.nb_combo.currentIndexChanged.connect(self.apply_filters)

        self.type_combo = QComboBox()
        self.type_combo.addItem("전체 타입")
        self.type_combo.addItem("code")
        self.type_combo.addItem("markdown")
        self.type_combo.currentIndexChanged.connect(self.apply_filters)

        self.kw_edit = QLineEdit()
        self.kw_edit.setPlaceholderText("🔍 키워드 검색…")
        self.kw_edit.textChanged.connect(self.apply_filters)

        filter_row.addWidget(self.nb_combo, 2)
        filter_row.addWidget(self.type_combo, 1)
        filter_row.addWidget(self.kw_edit, 2)
        layout.addLayout(filter_row)

        # 카운트 레이블
        self.count_label = QLabel("총 0개 셀")
        self.count_label.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.count_label)

        # ── 셀 트리 ───────────────────────────────────────────────────────────
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["셀", "미리보기"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setStyleSheet(
            "QTreeWidget { background: #161922; border: 1px solid #2a3045; "
            "border-radius: 6px; color: #e2e8f0; font-size: 12px; }"
            "QTreeWidget::item { padding: 4px 2px; border-bottom: 1px solid #1e2330; }"
            "QTreeWidget::item:selected { background: #1e3a5f; }"
            "QHeaderView::section { background: #1e2330; color: #94a3b8; "
            "border: none; padding: 4px; font-size: 11px; }"
        )
        layout.addWidget(self.tree)

        hint = QLabel("더블클릭 시 전체 내용 표시")
        hint.setStyleSheet("color: #475569; font-size: 10px;")
        layout.addWidget(hint)

    # ── 공개 API ───────────────────────────────────────────────────────────────

    def load_cells(self, cells: list[dict]):
        self._cells = cells
        # 노트북 목록 갱신
        self.nb_combo.blockSignals(True)
        self.nb_combo.clear()
        self.nb_combo.addItem("전체 노트북")
        for nb in sorted(set(c["notebook"] for c in cells)):
            self.nb_combo.addItem(nb)
        self.nb_combo.blockSignals(False)
        self.apply_filters()

    def apply_filters(self):
        nb_filter   = self.nb_combo.currentText()
        type_filter = self.type_combo.currentText()
        keyword     = self.kw_edit.text().strip().lower()

        filtered = self._cells
        if nb_filter != "전체 노트북":
            filtered = [c for c in filtered if c["notebook"] == nb_filter]
        if type_filter != "전체 타입":
            filtered = [c for c in filtered if c["cell_type"] == type_filter]
        if keyword:
            filtered = [c for c in filtered if keyword in c["source"].lower()]

        self.count_label.setText(f"총 {len(filtered)}개 셀 (최대 50개 표시)")
        self._populate_tree(filtered[:50])

    def _populate_tree(self, cells: list[dict]):
        self.tree.clear()
        for c in cells:
            icon = "🟠" if c["cell_type"] == "code" else "🟣"
            header = f"{icon} {c['notebook']} · 셀 #{c['cell_idx']} [{c['cell_type']}]"
            preview = c["source"][:120].replace("\n", " ") + ("…" if len(c["source"]) > 120 else "")
            item = QTreeWidgetItem([header, preview])
            item.setData(0, Qt.ItemDataRole.UserRole, c)
            if c["cell_type"] == "code":
                item.setForeground(0, __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#fb923c"))
            else:
                item.setForeground(0, __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#a78bfa"))
            self.tree.addTopLevelItem(item)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int):
        cell = item.data(0, Qt.ItemDataRole.UserRole)
        if cell:
            dlg = CellDetailDialog(cell, self)
            dlg.exec()
