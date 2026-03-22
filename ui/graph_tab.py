"""
GraphTab - 그래프 탐색 탭
Streamlit Tab3 대체
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QTextBrowser, QTableWidget,
    QTableWidgetItem, QSplitter, QGroupBox, QHeaderView
)
from PyQt6.QtCore import Qt


class GraphTab(QWidget):
    def __init__(self):
        super().__init__()
        self._graph = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        title = QLabel("🕸️  셀 관계 그래프")
        title.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        # 수평 스플리터: 좌(통계+노드) | 우(엣지 테이블)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 좌측 패널 ─────────────────────────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(8)

        # 통계 카드
        self.stats_label = QLabel("RAG 시스템을 먼저 구축하세요.")
        self.stats_label.setStyleSheet(
            "QLabel { background: #161922; border: 1px solid #2a3045; "
            "border-radius: 8px; padding: 10px; color: #94a3b8; font-size: 12px; "
            "font-family: 'JetBrains Mono', Consolas; }"
        )
        self.stats_label.setWordWrap(True)
        left_layout.addWidget(self.stats_label)

        # 노드 검색
        search_group = QGroupBox("노드 검색")
        search_group.setStyleSheet(
            "QGroupBox { color: #94a3b8; font-size: 11px; border: 1px solid #2a3045; "
            "border-radius: 6px; margin-top: 8px; padding-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        sg_layout = QVBoxLayout(search_group)

        self.node_search_edit = QLineEdit()
        self.node_search_edit.setPlaceholderText("노트북명 또는 셀 번호…")
        self.node_search_edit.textChanged.connect(self._on_node_search)
        sg_layout.addWidget(self.node_search_edit)

        self.node_list = QListWidget()
        self.node_list.setMaximumHeight(150)
        self.node_list.setStyleSheet(
            "QListWidget { background: #1e2330; border: 1px solid #2a3045; "
            "border-radius: 4px; color: #e2e8f0; font-size: 11px; "
            "font-family: 'JetBrains Mono', Consolas; }"
            "QListWidget::item:selected { background: #1e3a5f; }"
        )
        self.node_list.itemClicked.connect(self._on_node_selected)
        sg_layout.addWidget(self.node_list)

        left_layout.addWidget(search_group)

        # 노드 상세 정보
        self.neighbor_display = QTextBrowser()
        self.neighbor_display.setStyleSheet(
            "QTextBrowser { background: #161922; border: 1px solid #2a3045; "
            "border-radius: 6px; color: #e2e8f0; font-size: 12px; padding: 6px; }"
        )
        self.neighbor_display.setPlaceholderText("노드를 선택하면 이웃 정보가 표시됩니다.")
        left_layout.addWidget(self.neighbor_display)

        splitter.addWidget(left_panel)

        # ── 우측: 엣지 테이블 ─────────────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)

        edge_title = QLabel("엣지 목록 (최대 50개)")
        edge_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        right_layout.addWidget(edge_title)

        self.edge_table = QTableWidget()
        self.edge_table.setColumnCount(4)
        self.edge_table.setHorizontalHeaderLabels(["출발", "도착", "관계", "공유 변수"])
        self.edge_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.edge_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.edge_table.setAlternatingRowColors(True)
        self.edge_table.setStyleSheet(
            "QTableWidget { background: #161922; border: 1px solid #2a3045; "
            "border-radius: 6px; color: #e2e8f0; font-size: 11px; "
            "font-family: 'JetBrains Mono', Consolas; gridline-color: #1e2330; }"
            "QTableWidget::item { padding: 4px; }"
            "QTableWidget::item:selected { background: #1e3a5f; }"
            "QHeaderView::section { background: #1e2330; color: #94a3b8; "
            "border: none; padding: 4px; }"
        )
        right_layout.addWidget(self.edge_table)
        splitter.addWidget(right_panel)

        splitter.setSizes([350, 600])
        layout.addWidget(splitter)

    # ── 공개 API ───────────────────────────────────────────────────────────────

    def load_graph(self, G):
        import networkx as nx
        self._graph = G

        seq_count = sum(1 for _, _, d in G.edges(data=True) if d.get("rel") == "sequential")
        var_count = sum(1 for _, _, d in G.edges(data=True) if d.get("rel") == "shared_var")

        self.stats_label.setText(
            f"노드: {G.number_of_nodes()}\n"
            f"엣지: {G.number_of_edges()}\n"
            f"  sequential: {seq_count}\n"
            f"  shared_var: {var_count}"
        )

        # 엣지 테이블 채우기
        edges = list(G.edges(data=True))[:50]
        self.edge_table.setRowCount(len(edges))
        for row, (u, v, d) in enumerate(edges):
            self.edge_table.setItem(row, 0, QTableWidgetItem(u))
            self.edge_table.setItem(row, 1, QTableWidgetItem(v))
            self.edge_table.setItem(row, 2, QTableWidgetItem(d.get("rel", "")))
            self.edge_table.setItem(row, 3, QTableWidgetItem(d.get("vars", "")))

        # 노드 목록 초기화
        self._populate_node_list("")

    # ── 내부 슬롯 ────────────────────────────────────────────────────────────

    def _populate_node_list(self, query: str):
        if not self._graph:
            return
        self.node_list.clear()
        matching = [
            n for n in self._graph.nodes()
            if not query or query.lower() in n.lower()
        ][:20]
        for node in matching:
            self.node_list.addItem(node)

    def _on_node_search(self, text: str):
        self._populate_node_list(text)

    def _on_node_selected(self, item: QListWidgetItem):
        if not self._graph:
            return
        node = item.text()
        G = self._graph
        preds = list(G.predecessors(node))
        succs = list(G.successors(node))

        html = (
            f"<b style='color:#e2e8f0;font-family:monospace'>{node}</b><br><br>"
            f"<span style='color:#64748b;font-size:11px'>← 이전 {len(preds)}개</span>"
            f"&nbsp;&nbsp;"
            f"<span style='color:#64748b;font-size:11px'>→ 다음 {len(succs)}개</span>"
            "<br>"
        )
        for p in preds[:5]:
            html += f"<span style='color:#a78bfa;background:#2d1a3a;border-radius:4px;padding:2px 6px;margin:2px;'>← {p}</span> "
        for s in succs[:5]:
            html += f"<span style='color:#34d399;background:#0d2a1e;border-radius:4px;padding:2px 6px;margin:2px;'>→ {s}</span> "

        self.neighbor_display.setHtml(html)
