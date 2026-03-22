"""
DirTab - 디렉토리 탭
Streamlit Tab5 대체
"""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f} KB"
    else:
        return f"{size/1024/1024:.1f} MB"


class DirTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        title = QLabel("📁  노트북 디렉토리")
        title.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        # 요약 메트릭 행
        self.stats_row = QHBoxLayout()
        self.root_label  = self._metric_label("루트 경로", "—")
        self.nb_label    = self._metric_label("노트북 수", "0")
        self.cell_label  = self._metric_label("총 셀 수", "0")
        self.stats_row.addWidget(self.root_label)
        self.stats_row.addWidget(self.nb_label)
        self.stats_row.addWidget(self.cell_label)
        layout.addLayout(self.stats_row)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2a3045;")
        layout.addWidget(line)

        # 트리 위젯
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["이름", "유형", "크기/셀 수"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 80)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet(
            "QTreeWidget { background: #0d0f14; border: 1px solid #2a3045; "
            "border-radius: 6px; color: #e2e8f0; font-size: 12px; "
            "font-family: 'JetBrains Mono', Consolas, monospace; }"
            "QTreeWidget::item { padding: 3px 0; }"
            "QTreeWidget::item:selected { background: #1e3a5f; }"
            "QHeaderView::section { background: #1e2330; color: #94a3b8; "
            "border: none; padding: 4px; font-size: 11px; }"
            "QTreeWidget::branch:has-children:!has-siblings:closed,"
            "QTreeWidget::branch:closed:has-children:has-siblings {"
            "  border-image: none; image: url(none); }"
        )
        layout.addWidget(self.tree)

    def _metric_label(self, label: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #161922; border: 1px solid #2a3045; "
            "border-radius: 6px; padding: 4px; }"
        )
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(8, 4, 8, 4)
        vbox.setSpacing(1)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            "color: #4f8ef7; font-size: 16px; font-weight: 700; "
            "font-family: 'JetBrains Mono', Consolas, monospace;"
        )
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setObjectName(f"val_{label}")

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(val_lbl)
        vbox.addWidget(lbl)
        frame._val_lbl = val_lbl
        return frame

    # ── 공개 API ───────────────────────────────────────────────────────────────

    def load_tree(self, nb_dir: str, cells: list[dict]):
        from rag_core import build_directory_tree

        # 통계 업데이트
        nb_count   = len(set(c["notebook"] for c in cells))
        cell_count = len(cells)
        root_name  = Path(nb_dir).name

        self.root_label._val_lbl.setText(root_name)
        self.nb_label._val_lbl.setText(str(nb_count))
        self.cell_label._val_lbl.setText(str(cell_count))

        # 노트북별 셀 수 맵
        cell_count_map: dict[str, int] = {}
        for c in cells:
            p = c.get("notebook_path", "")
            cell_count_map[p] = cell_count_map.get(p, 0) + 1

        nb_dir_abs = os.path.abspath(nb_dir)
        tree_data  = build_directory_tree(nb_dir_abs, cell_count_map)

        self.tree.clear()
        if tree_data:
            self._populate_tree(None, tree_data)
            self.tree.expandAll()

    def _populate_tree(self, parent: QTreeWidgetItem | None, node: dict):
        if node["type"] == "dir":
            name = f"📁  {node['name']}"
            nb_count = sum(1 for c in node.get("children", []) if c["type"] == "notebook")
            type_str = "디렉토리"
            size_str = f"{nb_count} notebooks" if nb_count else ""
            color = QColor("#60a5fa")
        elif node["type"] == "notebook":
            name = f"📓  {node['name']}"
            type_str = "Notebook"
            cc = node.get("cell_count")
            size_str = f"{cc} cells  ·  {_format_size(node.get('size', 0))}" if cc else _format_size(node.get("size", 0))
            color = QColor("#34d399")
        else:
            name = f"📄  {node['name']}"
            type_str = node.get("ext", "파일").lstrip(".")
            size_str = _format_size(node.get("size", 0))
            ext_colors = {".py": "#fb923c", ".md": "#a78bfa", ".csv": "#38bdf8",
                          ".json": "#fbbf24", ".txt": "#94a3b8"}
            color = QColor(ext_colors.get(node.get("ext", ""), "#64748b"))

        item = QTreeWidgetItem([name, type_str, size_str])
        item.setForeground(0, color)

        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)

        for child in node.get("children", []):
            self._populate_tree(item, child)
