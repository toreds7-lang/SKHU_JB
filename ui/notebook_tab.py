"""
NotebookTab - 노트북 뷰어 + 요약 탭
좌측: 체크박스 노트북 목록 + 요약 생성 버튼
우측: 셀 보기 / 요약 보기 전환
"""

import json
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QScrollArea, QFrame, QTextEdit, QSizePolicy,
    QPushButton, QProgressBar, QSplitter, QStackedWidget, QCheckBox,
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage


class CellWidget(QFrame):
    """개별 셀 표시 위젯"""
    def __init__(self, cell: dict):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        # 헤더 레이블
        icon = "🟠" if cell["cell_type"] == "code" else "🟣"
        header = QLabel(f"{icon}  셀 #{cell['cell_idx']}  [{cell['cell_type']}]")
        header.setStyleSheet(
            "color: #475569; font-size: 10px; "
            "font-family: 'JetBrains Mono', Consolas, monospace;"
        )
        layout.addWidget(header)

        # 셀 내용
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(cell["source"])
        text_edit.setFont(QFont("JetBrains Mono, Consolas, Courier New", 11))
        text_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # 내용에 맞게 높이 조정 (최소 40, 최대 400)
        lines = cell["source"].count("\n") + 1
        height = min(max(lines * 20 + 16, 40), 400)
        text_edit.setFixedHeight(height)

        if cell["cell_type"] == "code":
            text_edit.setStyleSheet(
                "QTextEdit { background: #111827; color: #f8f8f2; "
                "border-left: 3px solid #fb923c; border-top: none; "
                "border-right: none; border-bottom: none; "
                "border-radius: 0 6px 6px 0; padding: 6px 8px; }"
            )
        else:
            text_edit.setStyleSheet(
                "QTextEdit { background: #111827; color: #c4b5fd; "
                "border-left: 3px solid #a78bfa; border-top: none; "
                "border-right: none; border-bottom: none; "
                "border-radius: 0 6px 6px 0; padding: 6px 8px; }"
            )
        layout.addWidget(text_edit)


_BTN_STYLE = (
    "QPushButton { background: #4f8ef7; color: #fff; border: none; "
    "border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; }"
    "QPushButton:hover { background: #3b7be0; }"
    "QPushButton:disabled { background: #334155; color: #64748b; }"
)
_STOP_BTN_STYLE = (
    "QPushButton { background: #dc2626; color: #fff; border: none; "
    "border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; }"
    "QPushButton:hover { background: #b91c1c; }"
)
_TOGGLE_ACTIVE = (
    "QPushButton { background: #1e2330; color: #e2e8f0; border: 1px solid #4f8ef7; "
    "border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: 600; }"
)
_TOGGLE_INACTIVE = (
    "QPushButton { background: transparent; color: #64748b; border: 1px solid #2a3045; "
    "border-radius: 4px; padding: 4px 12px; font-size: 11px; }"
    "QPushButton:hover { color: #94a3b8; border-color: #475569; }"
)


class _SummaryLinkPage(QWebEnginePage):
    """외부 링크 → 시스템 브라우저, __COPY__ → 클립보드"""

    def acceptNavigationRequest(self, url, nav_type, is_main):
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main)

    def javaScriptConsoleMessage(self, level, message, line, source):
        if message.startswith("__COPY__:"):
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(message[len("__COPY__:"):])


_SUMMARIZED_COLOR = QColor("#60a5fa")   # 파란색 — 요약 완료
_DEFAULT_COLOR    = QColor("#e2e8f0")   # 기본 텍스트 색


class NotebookTab(QWidget):
    summary_requested = pyqtSignal(dict)   # {name: [cells]}
    stop_requested    = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._cells: list[dict] = []
        self._summaries: dict[str, str] = {}   # in-memory cache
        self._cache_dir: str = ".rag_cache"
        self._current_nb: str = ""
        self._summary_font_size = 13
        self._summary_page_ready = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        title = QLabel("📓  노트북 뷰어")
        title.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        # ── 메인 스플리터 (좌: 목록 | 우: 콘텐츠) ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #2a3045; width: 1px; }"
        )

        # ── 좌측 패널: 체크박스 목록 + 요약 버튼 ────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        # 전체선택 체크박스
        self.select_all_cb = QCheckBox("전체선택")
        self.select_all_cb.setStyleSheet(
            "QCheckBox { color: #94a3b8; font-size: 11px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
        )
        self.select_all_cb.stateChanged.connect(self._on_select_all)
        left_layout.addWidget(self.select_all_cb)

        # 범례
        legend = QLabel("🔵 요약 완료")
        legend.setStyleSheet("color: #64748b; font-size: 10px;")
        left_layout.addWidget(legend)

        # 노트북 리스트 (체크박스)
        self.nb_list = QListWidget()
        self.nb_list.setStyleSheet(
            "QListWidget { background: #0d0f14; border: 1px solid #2a3045; "
            "border-radius: 6px; color: #e2e8f0; font-size: 11px; }"
            "QListWidget::item { padding: 4px 6px; }"
            "QListWidget::item:selected { background: #1e2330; color: #93c5fd; }"
            "QListWidget::item:hover { background: #161922; }"
        )
        self.nb_list.itemClicked.connect(self._on_item_clicked)
        self.nb_list.itemChanged.connect(self._on_item_check_changed)
        left_layout.addWidget(self.nb_list)

        # 요약 생성 버튼
        self.generate_btn = QPushButton("📝 요약 생성")
        self.generate_btn.setStyleSheet(_BTN_STYLE)
        self.generate_btn.clicked.connect(self._on_generate_click)
        left_layout.addWidget(self.generate_btn)

        # 프로그레스 바 (숨김)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #1e2330; border: 1px solid #2a3045; "
            "border-radius: 4px; text-align: center; color: #e2e8f0; "
            "font-size: 10px; height: 18px; }"
            "QProgressBar::chunk { background: #4f8ef7; border-radius: 3px; }"
        )
        self.progress_bar.hide()
        left_layout.addWidget(self.progress_bar)

        # 중지 버튼 (숨김)
        self.stop_btn = QPushButton("⏹️ 중지")
        self.stop_btn.setStyleSheet(_STOP_BTN_STYLE)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.hide()
        left_layout.addWidget(self.stop_btn)

        # 상태 레이블
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #64748b; font-size: 10px;")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)

        splitter.addWidget(left_panel)

        # ── 우측 패널: 셀 보기 / 요약 보기 ──────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        # 뷰 전환 버튼
        toggle_row = QHBoxLayout()
        self.cell_view_btn = QPushButton("셀 보기")
        self.cell_view_btn.setStyleSheet(_TOGGLE_ACTIVE)
        self.cell_view_btn.clicked.connect(lambda: self._switch_view(0))

        self.summary_view_btn = QPushButton("요약 보기")
        self.summary_view_btn.setStyleSheet(_TOGGLE_INACTIVE)
        self.summary_view_btn.clicked.connect(lambda: self._switch_view(1))

        toggle_row.addWidget(self.cell_view_btn)
        toggle_row.addWidget(self.summary_view_btn)
        toggle_row.addStretch()
        right_layout.addLayout(toggle_row)

        # 스택 위젯 (셀 뷰 / 요약 뷰)
        self.view_stack = QStackedWidget()

        # --- 셀 보기 (기존) ---
        self.cell_scroll = QScrollArea()
        self.cell_scroll.setWidgetResizable(True)
        self.cell_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #2a3045; border-radius: 6px; "
            "background: #0d0f14; }"
        )
        self._cell_container = QWidget()
        self._cell_layout = QVBoxLayout(self._cell_container)
        self._cell_layout.setContentsMargins(8, 8, 8, 8)
        self._cell_layout.setSpacing(6)
        self._cell_layout.addStretch()
        self.cell_scroll.setWidget(self._cell_container)
        self.view_stack.addWidget(self.cell_scroll)

        # --- 요약 보기 (QWebEngineView + marked.js) ---
        self.summary_web = QWebEngineView()
        self.summary_web.setPage(_SummaryLinkPage(self.summary_web))
        self.summary_web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        if getattr(sys, "frozen", False):
            _base = Path(sys._MEIPASS)
        else:
            _base = Path(__file__).parent.parent
        html_path = _base / "resources" / "summary.html"
        self.summary_web.setUrl(QUrl.fromLocalFile(str(html_path.resolve())))
        self.summary_web.loadFinished.connect(self._on_summary_page_loaded)
        self.view_stack.addWidget(self.summary_web)

        right_layout.addWidget(self.view_stack)
        splitter.addWidget(right_panel)

        splitter.setSizes([220, 780])
        layout.addWidget(splitter, 1)

        # 요약 보기 글자 크기 단축키
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self._zoom_reset)

    # ── 줌 (요약 보기 글자 크기) ─────────────────────────────────────────────

    def _zoom_in(self):
        if self._summary_font_size < 24:
            self._summary_font_size += 1
            self._run_summary_js(f"setFontSize({self._summary_font_size})")

    def _zoom_out(self):
        if self._summary_font_size > 8:
            self._summary_font_size -= 1
            self._run_summary_js(f"setFontSize({self._summary_font_size})")

    def _zoom_reset(self):
        self._summary_font_size = 13
        self._run_summary_js(f"setFontSize({self._summary_font_size})")

    def _on_summary_page_loaded(self, ok: bool):
        if ok:
            self._summary_page_ready = True
            self._run_summary_js(f"setFontSize({self._summary_font_size})")
            self._rebuild_summary_view()

    def _run_summary_js(self, script: str):
        if self._summary_page_ready:
            self.summary_web.page().runJavaScript(script)

    # ── 뷰 전환 ──────────────────────────────────────────────────────────────

    def _switch_view(self, idx: int):
        self.view_stack.setCurrentIndex(idx)
        self.cell_view_btn.setStyleSheet(
            _TOGGLE_ACTIVE if idx == 0 else _TOGGLE_INACTIVE
        )
        self.summary_view_btn.setStyleSheet(
            _TOGGLE_ACTIVE if idx == 1 else _TOGGLE_INACTIVE
        )

    # ── 체크박스 로직 ────────────────────────────────────────────────────────

    def _on_select_all(self, state):
        check = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        self.nb_list.blockSignals(True)
        for i in range(self.nb_list.count()):
            self.nb_list.item(i).setCheckState(check)
        self.nb_list.blockSignals(False)
        self._update_generate_btn_label()

    def _on_item_check_changed(self, _item):
        self._update_generate_btn_label()
        self._rebuild_summary_view()
        # 전체선택 체크박스 동기화
        total = self.nb_list.count()
        checked = sum(
            1 for i in range(total)
            if self.nb_list.item(i).checkState() == Qt.CheckState.Checked
        )
        self.select_all_cb.blockSignals(True)
        if checked == total:
            self.select_all_cb.setCheckState(Qt.CheckState.Checked)
        elif checked == 0:
            self.select_all_cb.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.select_all_cb.setCheckState(Qt.CheckState.PartiallyChecked)
        self.select_all_cb.blockSignals(False)

    def _get_checked_names(self) -> list[str]:
        names = []
        for i in range(self.nb_list.count()):
            item = self.nb_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.text())
        return names

    def _update_generate_btn_label(self):
        checked = self._get_checked_names()
        uncached = [n for n in checked if n not in self._summaries]
        if uncached:
            self.generate_btn.setText(f"📝 요약 생성 ({len(uncached)}개)")
        else:
            self.generate_btn.setText("📝 요약 생성")

    # ── 디스크 캐시 ─────────────────────────────────────────────────────────

    def set_cache_dir(self, path: str):
        self._cache_dir = path

    def _summary_cache_path(self) -> Path:
        return Path(self._cache_dir) / "summaries.json"

    def _get_nb_path(self, notebook_name: str) -> str | None:
        """cells에서 해당 노트북의 파일 경로를 반환"""
        for c in self._cells:
            if c["notebook"] == notebook_name:
                return c.get("notebook_path")
        return None

    def _load_summary_cache(self):
        """디스크 캐시에서 유효한 요약을 self._summaries에 로드"""
        cache_path = self._summary_cache_path()
        if not cache_path.exists():
            return
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        from rag_core import get_file_md5
        for name, entry in data.items():
            if name in self._summaries:
                continue  # 이미 인메모리 캐시에 있으면 스킵
            nb_path = self._get_nb_path(name)
            if nb_path and os.path.exists(nb_path):
                current_hash = get_file_md5(nb_path)
                if entry.get("hash") == current_hash:
                    self._summaries[name] = entry["summary"]

    def _save_summary_to_cache(self, notebook_name: str, summary: str):
        """하나의 요약을 디스크 캐시에 저장"""
        os.makedirs(self._cache_dir, exist_ok=True)
        cache_path = self._summary_cache_path()

        # 기존 캐시 로드
        data: dict = {}
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        # 파일 해시 계산
        nb_path = self._get_nb_path(notebook_name)
        file_hash = ""
        if nb_path and os.path.exists(nb_path):
            from rag_core import get_file_md5
            file_hash = get_file_md5(nb_path)

        data[notebook_name] = {"hash": file_hash, "summary": summary}

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 시각적 표시 (요약 완료 색상) ──────────────────────────────────────────

    def _update_all_indicators(self):
        for i in range(self.nb_list.count()):
            item = self.nb_list.item(i)
            if item.text() in self._summaries:
                item.setForeground(_SUMMARIZED_COLOR)
            else:
                item.setForeground(_DEFAULT_COLOR)

    def _update_item_indicator(self, notebook_name: str):
        for i in range(self.nb_list.count()):
            item = self.nb_list.item(i)
            if item.text() == notebook_name:
                item.setForeground(_SUMMARIZED_COLOR)
                break

    # ── 아이템 클릭 → 셀 보기 ────────────────────────────────────────────────

    def _on_item_clicked(self, item: QListWidgetItem):
        nb = item.text()
        if nb and nb != self._current_nb:
            self._current_nb = nb
            self._render_notebook(nb)

    # ── 요약 생성 ────────────────────────────────────────────────────────────

    def _on_generate_click(self):
        checked = self._get_checked_names()
        # 캐시에 없는 노트북만 요약 요청
        to_generate = {}
        for name in checked:
            if name not in self._summaries:
                nb_cells = sorted(
                    [c for c in self._cells if c["notebook"] == name],
                    key=lambda x: x["cell_idx"]
                )
                to_generate[name] = nb_cells

        if not to_generate:
            # 모두 캐시됨 → 바로 요약 보기 표시
            self._rebuild_summary_view()
            self._switch_view(1)
            return

        self.generate_btn.setEnabled(False)
        self.progress_bar.setMaximum(len(to_generate))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/%m")
        self.progress_bar.show()
        self.stop_btn.show()
        self.status_label.setText("⏳ 요약 생성 중...")

        self.summary_requested.emit(to_generate)

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def load_cells(self, cells: list[dict]):
        self._cells = cells

        # 기존 요약 중 아직 존재하는 노트북만 보존
        new_nbs = sorted(set(c["notebook"] for c in cells))
        self._summaries = {
            k: v for k, v in self._summaries.items() if k in new_nbs
        }

        # 디스크 캐시에서 유효한 요약 로드
        self._load_summary_cache()

        # 체크박스 리스트 재구성
        self.nb_list.blockSignals(True)
        self.nb_list.clear()
        for nb in new_nbs:
            item = QListWidgetItem(nb)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.nb_list.addItem(item)
        self.nb_list.blockSignals(False)

        self.select_all_cb.blockSignals(True)
        self.select_all_cb.setCheckState(Qt.CheckState.Unchecked)
        self.select_all_cb.blockSignals(False)

        self._update_all_indicators()
        self._update_generate_btn_label()

        # 첫 번째 노트북 셀 표시
        if new_nbs:
            self._current_nb = new_nbs[0]
            self.nb_list.setCurrentRow(0)
            self._render_notebook(new_nbs[0])

        # 요약 뷰 재구성
        self._rebuild_summary_view()

    def set_summary(self, notebook_name: str, summary: str):
        """워커에서 호출: 하나의 노트북 요약 결과를 캐시 + 표시"""
        self._summaries[notebook_name] = summary
        self._save_summary_to_cache(notebook_name, summary)
        self._update_item_indicator(notebook_name)
        self._rebuild_summary_view()
        self._update_generate_btn_label()

    def update_progress(self, processed: int, total: int):
        self.progress_bar.setValue(processed)
        self.progress_bar.setFormat(f"{processed}/{total}")
        self.status_label.setText(f"⏳ {processed}/{total} 노트북 처리 중...")

    def on_generation_finished(self):
        self.generate_btn.setEnabled(True)
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.status_label.setText("✅ 요약 생성 완료")
        self._switch_view(1)

    def on_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.status_label.setText(f"❌ {msg}")

    # ── 셀 렌더링 (기존) ─────────────────────────────────────────────────────

    def _render_notebook(self, nb_name: str):
        # 기존 셀 위젯 제거
        while self._cell_layout.count() > 1:
            item = self._cell_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        nb_cells = sorted(
            [c for c in self._cells if c["notebook"] == nb_name],
            key=lambda x: x["cell_idx"]
        )
        for cell in nb_cells:
            widget = CellWidget(cell)
            self._cell_layout.insertWidget(self._cell_layout.count() - 1, widget)

    # ── 요약 뷰 렌더링 ───────────────────────────────────────────────────────

    def _rebuild_summary_view(self):
        """체크된 노트북의 캐시된 요약을 요약 뷰에 표시"""
        if not self._summary_page_ready:
            return

        self._run_summary_js("clearCards()")

        checked = self._get_checked_names()
        has_summary = False

        for name in checked:
            if name in self._summaries:
                has_summary = True
                escaped = json.dumps(name)
                md_escaped = json.dumps(self._summaries[name])
                self._run_summary_js(
                    f"addSummaryCard({escaped},{md_escaped})"
                )

        if not has_summary:
            self._run_summary_js(
                'showPlaceholder("\\uD83D\\uDCDD 노트북을 선택하고 \'요약 생성\'을 클릭하세요.")'
            )
