"""
ChatTab - 채팅 탭 (QWebEngineView + marked.js + highlight.js)
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextBrowser, QScrollArea, QGroupBox,
    QFrame, QSizePolicy, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView


# ── 출처 카드 (sources_display용, QTextBrowser에서 계속 사용) ─────────────────
def _doc_card(doc, tag_class: str, tag_name: str) -> str:
    nb    = doc.metadata.get("notebook", "?")
    cidx  = doc.metadata.get("cell_idx", "?")
    ctype = doc.metadata.get("cell_type", "?")
    preview = doc.page_content[:200].replace("<", "&lt;").replace(">", "&gt;")
    tag_colors = {
        "tag-vector": ("color:#60a5fa;background:#1e3a5f;border:1px solid #1d4ed8;"),
        "tag-bm25":   ("color:#34d399;background:#1a3a2a;border:1px solid #059669;"),
        "tag-graph":  ("color:#a78bfa;background:#2d1a3a;border:1px solid #7c3aed;"),
    }
    tag_style = tag_colors.get(tag_class, "color:#e2e8f0;background:#333;")
    ctype_style = ("color:#fb923c;background:#2a1a10;border:1px solid #c2410c;"
                   if ctype == "code" else
                   "color:#5eead4;background:#1a2a2a;border:1px solid #0d9488;")
    code_style = (
        "background:#111827;border-left:3px solid #fb923c;border-radius:0 4px 4px 0;padding:6px 8px;"
        if ctype == "code" else
        "border-left:3px solid #a78bfa;padding-left:8px;color:#c4b5fd;"
    )
    return (
        f'<div style="background:#161922;border:1px solid #2a3045;border-radius:8px;'
        f'padding:8px 10px;margin:4px 0;">'
        f'<span style="font-size:10px;font-family:JetBrains Mono,Consolas,monospace;'
        f'padding:2px 6px;border-radius:3px;margin-right:4px;{tag_style}">{tag_name}</span>'
        f'<span style="font-size:10px;font-family:JetBrains Mono,Consolas,monospace;'
        f'padding:2px 6px;border-radius:3px;margin-right:4px;{ctype_style}">{ctype.upper()}</span>'
        f'<span style="font-size:10px;color:#94a3b8;font-family:JetBrains Mono,Consolas,monospace;">'
        f'📓 {nb} · 셀 #{cidx}</span>'
        f'<div style="{code_style}margin-top:4px;font-size:11px;font-family:JetBrains Mono,Consolas,monospace;">'
        f'{preview}</div>'
        f'</div>'
    )


class ChatTab(QWidget):
    query_submitted = pyqtSignal(str, bool)   # (query, is_suggested)
    force_stop_requested = pyqtSignal()       # Force Mode 중지 요청
    llm_stop_requested = pyqtSignal()         # 일반 모드 스트리밍 중지 요청

    def __init__(self):
        super().__init__()
        self._messages: list[dict] = []       # {"role": "user"|"assistant", "content": str}
        self._streaming_buf = ""
        self._is_streaming  = False
        self._page_loaded   = False
        self._pending_js: list[str] = []
        self._build_ui()

    # ── JS 브릿지 헬퍼 ──────────────────────────────────────────────────────

    @staticmethod
    def _js_escape(text: str) -> str:
        """JS 템플릿 리터럴(backtick)에 안전하게 삽입할 수 있도록 이스케이프."""
        return (text
            .replace('\\', '\\\\')
            .replace('`', '\\`')
            .replace('$', '\\$')
            .replace('\r\n', '\\n')
            .replace('\n', '\\n')
            .replace('\r', '\\n'))

    def _run_js(self, script: str):
        """JavaScript 실행 — 페이지 로드 전이면 큐에 저장."""
        if self._page_loaded:
            self.chat_display.page().runJavaScript(script)
        else:
            self._pending_js.append(script)

    def _on_page_loaded(self, ok: bool):
        """QWebEngineView 페이지 로드 완료 콜백."""
        if not ok:
            return
        self._page_loaded = True
        # 기존 메시지 히스토리 복원
        for msg in self._messages:
            escaped = self._js_escape(msg["content"])
            if msg["role"] == "user":
                self.chat_display.page().runJavaScript(
                    f"appendUserMessage(`{escaped}`)"
                )
            else:
                self.chat_display.page().runJavaScript(
                    f"appendFinishedAiMessage(`{escaped}`)"
                )
        # 대기 중이던 JS 실행
        for js in self._pending_js:
            self.chat_display.page().runJavaScript(js)
        self._pending_js.clear()

    # ── UI 구성 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # ── 채팅 히스토리 (QWebEngineView) ────────────────────────────────────
        self.chat_display = QWebEngineView()
        self.chat_display.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        if getattr(sys, "frozen", False):
            _base = Path(sys._MEIPASS)
        else:
            _base = Path(__file__).parent.parent
        html_path = _base / "resources" / "chat.html"
        self.chat_display.setUrl(QUrl.fromLocalFile(str(html_path.resolve())))
        self.chat_display.loadFinished.connect(self._on_page_loaded)
        layout.addWidget(self.chat_display, stretch=1)

        # ── 상태 레이블 ────────────────────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #4f8ef7; font-size: 11px; "
            "font-family: 'JetBrains Mono', Consolas, monospace;"
        )
        layout.addWidget(self.status_label)

        # ── Force Mode 진행률 바 + 중지 버튼 ────────────────────────────────────
        self.force_bar = QWidget()
        force_layout = QHBoxLayout(self.force_bar)
        force_layout.setContentsMargins(0, 2, 0, 2)
        force_layout.setSpacing(8)
        self.force_progress = QProgressBar()
        self.force_progress.setMinimum(0)
        self.force_progress.setMaximum(100)
        self.force_progress.setTextVisible(True)
        self.force_progress.setFormat("Force Mode 검색 중… %v/%m")
        self.force_progress.setStyleSheet(
            "QProgressBar { background: #1e2330; border: 1px solid #2a3045; "
            "border-radius: 4px; height: 22px; color: #e2e8f0; font-size: 11px; }"
            "QProgressBar::chunk { background: #4f8ef7; border-radius: 3px; }"
        )
        self.force_stop_btn = QPushButton("⏹️ 중지")
        self.force_stop_btn.setFixedWidth(72)
        self.force_stop_btn.setMinimumHeight(26)
        self.force_stop_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: white; border: none; "
            "border-radius: 4px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #ef4444; }"
        )
        self.force_stop_btn.clicked.connect(self.force_stop_requested.emit)
        force_layout.addWidget(self.force_progress, stretch=1)
        force_layout.addWidget(self.force_stop_btn)
        self.force_bar.setVisible(False)
        layout.addWidget(self.force_bar)

        # ── 출처 그룹 (접기/펼치기) — 입력창 위에 배치 ────────────────────────
        self.sources_group = QGroupBox("🔍 검색 결과 상세")
        self.sources_group.setCheckable(True)
        self.sources_group.setChecked(False)
        self.sources_group.setStyleSheet(
            "QGroupBox { color: #94a3b8; font-size: 11px; border: 1px solid #2a3045; "
            "border-radius: 6px; margin-top: 6px; padding-top: 12px; max-height: 260px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            "QGroupBox::indicator { width: 14px; height: 14px; }"
        )
        src_layout = QVBoxLayout(self.sources_group)
        self.sources_display = QTextBrowser()
        self.sources_display.setStyleSheet(
            "QTextBrowser { background: #0d0f14; border: none; "
            "color: #e2e8f0; font-size: 11px; }"
        )
        self.sources_display.setMaximumHeight(200)
        src_layout.addWidget(self.sources_display)
        self.sources_group.setVisible(False)
        layout.addWidget(self.sources_group)

        # ── 추천 검색어 칩 ─────────────────────────────────────────────────────
        self.chips_scroll = QScrollArea()
        self.chips_scroll.setWidgetResizable(True)
        self.chips_scroll.setFixedHeight(44)
        self.chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chips_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.chips_scroll.setVisible(False)
        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 4, 0, 4)
        self._chips_layout.setSpacing(6)
        self._chips_layout.addStretch()
        self.chips_scroll.setWidget(self._chips_widget)
        layout.addWidget(self.chips_scroll)

        # ── 예시 질문 바 ───────────────────────────────────────────────────────
        self.example_bar = QWidget()
        example_layout = QVBoxLayout(self.example_bar)
        example_layout.setContentsMargins(0, 0, 0, 0)
        example_layout.setSpacing(2)
        ex_hint = QLabel("예시 질문:")
        ex_hint.setStyleSheet("color: #475569; font-size: 11px;")
        example_layout.addWidget(ex_hint)
        self._example_chips_widget = QWidget()
        self._example_chips_layout = QHBoxLayout(self._example_chips_widget)
        self._example_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._example_chips_layout.setSpacing(6)
        self._example_chips_layout.addStretch()
        example_layout.addWidget(self._example_chips_widget)
        self.example_bar.setVisible(False)
        layout.addWidget(self.example_bar)

        # ── 입력 행 (항상 하단 고정) ───────────────────────────────────────────
        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("질문을 입력하세요…")
        self.input_edit.setMinimumHeight(36)
        self.input_edit.returnPressed.connect(self._on_send)
        self.send_btn = QPushButton("전송")
        self.send_btn.setMinimumHeight(36)
        self.send_btn.setFixedWidth(64)
        self.send_btn.clicked.connect(self._on_send)
        self.clear_btn = QPushButton("🗑️")
        self.clear_btn.setMinimumHeight(36)
        self.clear_btn.setFixedWidth(40)
        self.clear_btn.setToolTip("대화 초기화")
        self.clear_btn.clicked.connect(self.clear_chat)
        input_row.addWidget(self.input_edit)
        input_row.addWidget(self.send_btn)
        input_row.addWidget(self.clear_btn)
        layout.addLayout(input_row)

    # ── 공개 API ───────────────────────────────────────────────────────────────

    def start_streaming(self, query: str):
        """검색+스트리밍 시작 시 호출"""
        self._append_user_message(query)
        self._streaming_buf = ""
        self._is_streaming  = True
        self._run_js("startAiMessage()")
        self.input_edit.setEnabled(False)
        self.send_btn.setText("⏹")
        self.send_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: white; border: none; "
            "border-radius: 4px; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: #ef4444; }"
        )
        self.send_btn.setEnabled(True)
        self.sources_group.setVisible(False)

    def on_chunk_received(self, chunk: str):
        """LLMWorker.chunk_received 신호 수신"""
        if chunk == "\x00RESET\x00":
            self._streaming_buf = ""
            self._run_js("resetStreamingBuffer()")
            return
        if chunk.startswith("\x00CITATION\x00"):
            citation = chunk[len("\x00CITATION\x00"):]
            self._streaming_buf += citation
            return
        self._streaming_buf += chunk
        escaped = self._js_escape(self._streaming_buf)
        self._run_js(f"streamingBuffer=`{escaped}`;renderStreamingBuffer()")

    def on_streaming_finished(self, answer: str, result: dict):
        """LLMWorker.finished_signal 수신"""
        self._is_streaming = False
        self._streaming_buf = ""
        self._messages.append({"role": "assistant", "content": answer})
        # 최종 버퍼를 answer로 설정 후 finishAiMessage 호출
        escaped = self._js_escape(answer)
        self._run_js(f"streamingBuffer=`{escaped}`;finishAiMessage()")
        self._render_sources(result)
        self.input_edit.setEnabled(True)
        self._restore_send_btn()
        self.status_label.setText("")
        self.example_bar.setVisible(False)

    def _restore_send_btn(self):
        """전송 버튼을 원래 상태로 복원"""
        self.send_btn.setText("전송")
        self.send_btn.setStyleSheet("")
        self.send_btn.setEnabled(True)

    # ── Force Mode API ────────────────────────────────────────────────────────

    def start_force_mode(self, query: str):
        """Force Mode 시작 시 호출"""
        self._append_user_message(f"🔍 [Force Mode] {query}")
        self._streaming_buf = ""
        self._is_streaming = True
        self._run_js("startAiMessage()")
        self.input_edit.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.sources_group.setVisible(False)
        self.force_bar.setVisible(True)
        self.force_progress.setValue(0)
        self.force_progress.setMaximum(1)

    def update_force_progress(self, processed: int, total: int):
        """Force Mode 진행률 업데이트"""
        self.force_progress.setMaximum(total)
        self.force_progress.setValue(processed)
        self.force_progress.setFormat(f"Force Mode 검색 중… {processed}/{total}")

    def update_force_preview(self, preview_md: str):
        """Force Mode 누적 결과 미리보기"""
        escaped = self._js_escape(preview_md)
        self._run_js(f"streamingBuffer=`{escaped}`;renderStreamingBuffer()")

    def finish_force_mode(self, answer: str):
        """Force Mode 완료"""
        self._is_streaming = False
        self._streaming_buf = ""
        self._messages.append({"role": "assistant", "content": answer})
        escaped = self._js_escape(answer)
        self._run_js(f"streamingBuffer=`{escaped}`;finishAiMessage()")
        self.force_bar.setVisible(False)
        self.input_edit.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.status_label.setText("")
        self.example_bar.setVisible(False)

    def on_error(self, msg: str):
        """LLMWorker.error_signal 수신"""
        self._is_streaming = False
        self._streaming_buf = ""
        self._run_js("finishAiMessage()")
        self.status_label.setText(f"❌ 오류: {msg}")
        self.input_edit.setEnabled(True)
        self.send_btn.setEnabled(True)

    def update_suggested_chips(self, queries: list[str]):
        """추천 검색어 칩 업데이트"""
        self._clear_layout(self._chips_layout)
        self._chips_layout.addStretch()

        if not queries:
            self.chips_scroll.setVisible(False)
            return

        hint = QLabel("💡 추천 검색어:")
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        self._chips_layout.insertWidget(0, hint)

        for i, q in enumerate(queries):
            btn = QPushButton(q)
            btn.setStyleSheet(
                "QPushButton { background: #1e2330; border: 1px solid #4f8ef7; "
                "color: #4f8ef7; border-radius: 12px; padding: 4px 10px; font-size: 11px; }"
                "QPushButton:hover { background: #1e3a5f; }"
            )
            btn.clicked.connect(lambda checked, sq=q: self._on_chip_clicked(sq))
            self._chips_layout.insertWidget(i + 1, btn)

        self.chips_scroll.setVisible(True)

    def update_example_chips(self, questions: list[str]):
        """예시 질문 칩 업데이트 (RAG 구축 완료 후)"""
        self._clear_layout(self._example_chips_layout)
        self._example_chips_layout.addStretch()

        if not questions:
            return

        for i, q in enumerate(questions):
            btn = QPushButton(q)
            btn.setStyleSheet(
                "QPushButton { background: #1e2330; border: 1px solid #2a3045; "
                "color: #94a3b8; border-radius: 12px; padding: 4px 10px; font-size: 11px; }"
                "QPushButton:hover { background: #1e3a5f; border-color: #4f8ef7; color: #4f8ef7; }"
            )
            btn.clicked.connect(lambda checked, ex=q: self._on_example_clicked(ex))
            self._example_chips_layout.insertWidget(i, btn)

        if not self._messages:
            self.example_bar.setVisible(True)

    def clear_chat(self):
        self._messages.clear()
        self._run_js("clearChat()")
        self.chips_scroll.setVisible(False)
        self.sources_group.setVisible(False)
        self.status_label.setText("")
        # 예시 질문 복원
        if self._example_chips_layout.count() > 1:
            self.example_bar.setVisible(True)

    # ── 내부 메서드 ────────────────────────────────────────────────────────────

    def _on_send(self):
        if self._is_streaming:
            self.llm_stop_requested.emit()
            return
        query = self.input_edit.text().strip()
        if not query:
            return
        self.input_edit.clear()
        self.chips_scroll.setVisible(False)
        self.query_submitted.emit(query, False)

    def _on_chip_clicked(self, query: str):
        self.chips_scroll.setVisible(False)
        self.query_submitted.emit(query, True)

    def _on_example_clicked(self, query: str):
        self.example_bar.setVisible(False)
        self.query_submitted.emit(query, False)

    def _append_user_message(self, text: str):
        self._messages.append({"role": "user", "content": text})
        escaped = self._js_escape(text)
        self._run_js(f"appendUserMessage(`{escaped}`)")

    def _render_sources(self, result: dict):
        if not result:
            return
        html = '<html><body style="background:#0d0f14;margin:0;padding:4px;">'

        v_docs = result.get("vector_docs", [])[:3]
        b_docs = result.get("bm25_docs",   [])[:3]
        g_docs = result.get("graph_docs",  [])[:3]

        if v_docs:
            html += '<div style="font-weight:600;color:#60a5fa;margin:6px 0 2px;font-size:11px;">📐 Vector RAG</div>'
            for d in v_docs:
                html += _doc_card(d, "tag-vector", "Vector RAG")
        if b_docs:
            html += '<div style="font-weight:600;color:#34d399;margin:6px 0 2px;font-size:11px;">🔤 BM25</div>'
            for d in b_docs:
                html += _doc_card(d, "tag-bm25", "BM25")
        if g_docs:
            html += '<div style="font-weight:600;color:#a78bfa;margin:6px 0 2px;font-size:11px;">🕸️ Graph RAG</div>'
            for d in g_docs:
                html += _doc_card(d, "tag-graph", "Graph RAG")

        html += "</body></html>"

        if v_docs or b_docs or g_docs:
            self.sources_display.setHtml(html)

    def _clear_layout(self, layout):
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
