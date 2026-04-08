# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

> **중요**: 사용자는 PyQt6 데스크탑 앱(`python main.py`)을 사용합니다.
> `notebook_rag_agent.py`(Streamlit)는 레거시이며 사용하지 않습니다.
> **코드 수정 시 반드시 PyQt6 쪽 파일을 수정하세요.**

```bash
# Install dependencies (Python >= 3.10 required)
pip install -r requirements_1.txt

# Run the PyQt6 desktop app (기본 실행 방법)
python main.py

# (레거시, 미사용) Streamlit app
# streamlit run notebook_rag_agent.py
```

No build, lint, or test commands are defined for this project.

## Environment Configuration

Copy `.env` (or `env.txt`) to set these variables before running:
- `OPENAI_API_KEY` — Required for embeddings and LLM
- `LLM_MODEL` — Default: `gpt-4o-mini`
- `LLM_BASE_URL` — Leave empty for OpenAI; set for local servers (Ollama, etc.)
- `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` — Override embedding endpoint/model
- `FORCE_WORKERS` — Force Mode 병렬 워커 수 (기본값: 3, 범위: 1-10)

`env_loader.py`가 `env.txt`를 읽어 환경변수에 로드합니다 (`main.py`에서 호출).

## Architecture Overview

이 프로젝트에는 두 가지 UI 구현이 있습니다:

### 1. PyQt6 데스크탑 앱 (현재 사용 중) ← 모든 수정은 여기에

진입점: `main.py` → `ui/main_window.py` (MainWindow)

| 모듈 | 역할 |
|------|------|
| `main.py` | 앱 진입점 (QApplication, 다크 테마, 폰트 설정) |
| `ui/main_window.py` | MainWindow — 탭/패널 조립, 워커 관리, `/f` 감지 |
| `ui/config_panel.py` | 좌측 설정 패널 (LLM/임베딩 URL, 모델, RAG 빌드 버튼) |
| `ui/chat_tab.py` | 채팅 탭 (스트리밍, 답변 중지, Force Mode UI, 예시 질문 칩, 외부 링크) |
| `ui/docs_tab.py` | 문서 탐색 탭 |
| `ui/graph_tab.py` | 그래프 탐색 탭 |
| `ui/notebook_tab.py` | 노트북 뷰어 탭 |
| `ui/dir_tab.py` | 디렉토리 트리 탭 |
| `workers/llm_worker.py` | QThread 워커 (RagBuildWorker, LLMWorker, ForceWorker, ExampleQuestionsWorker, SuggestedQueriesWorker, SummaryWorker) |
| `rag_core.py` | RAG 비즈니스 로직 (UI 무관) — 파싱, 인덱싱, 검색, Force Mode, 요약 함수 |
| `env_loader.py` | env.txt 로더 |

### 2. Streamlit 앱 (레거시, 미사용)

`notebook_rag_agent.py` 단일 파일 (~1561줄). **수정하지 마세요.**

### Retrieval Pipeline (LangGraph StateGraph)

The core is a hybrid RAG pipeline with three parallel retrievers, orchestrated by LangGraph:

1. **Vector RAG** — FAISS index with OpenAI embeddings; cached to `.rag_cache/faiss_index/`
2. **BM25** — Keyword ranking via `rank-bm25`; cached to `.rag_cache/bm25.pkl`
3. **Graph RAG** — Custom NetworkX DiGraph over notebook cells with two edge types:
   - `sequential`: adjacent cells in the same notebook (decay 0.5)
   - `shared_var`: code cells sharing assigned variable names (decay 0.8)
   - Multi-hop propagation (2 hops) starting from vector-seeded nodes

After retrieval, `merge_docs` deduplicates results (max 10 docs) and formats the context for the LLM.

`AgentState` fields: `query`, `retrieval_mode`, `vector_docs`, `bm25_docs`, `graph_docs`, `all_docs`, `context`, `answer`, `steps`.

### Indexing Unit

Notebooks in `work/` are parsed cell-by-cell using `nbformat`. Each **cell** is the atomic retrieval unit (a LangChain `Document`). Metadata per document: `cell_idx`, `cell_type`, `notebook`, `notebook_path`, `source` (node ID).

### RAG System Build & Caching

PyQt6 앱에서는 `RagBuildWorker` (QThread)가 `rag_core.build_rag_system()`을 백그라운드에서 호출합니다:
- Parses all `.ipynb` files from the configured notebook directory
- Builds or loads FAISS/BM25 indexes from disk cache
- Builds the NetworkX cell graph
- Returns a dict with all components + stats

File change detection uses MD5 hashing of `.ipynb` files + mtime (`get_dir_hash()`). `MainWindow._check_dir_hash()`가 30초 타이머로 감시하며 변경 감지 시 재구축을 안내합니다.

### Korean Language Support

`kiwipiepy` is used for morphological tokenization in BM25 and Graph RAG keyword boosting. If `kiwipiepy` is unavailable, the code falls back to regex-based tokenization.

### Custom System Prompt

Place a `system_prompt.txt` file in the project root to override the default LLM prompt. The default instructs the model to answer only from the retrieved notebook context and respond in Korean.

### Force Mode (전수 검색)

RAG 파이프라인과 완전히 분리된 **병렬** 검색 모드. 채팅 입력에 `/f 질문` 형태로 사용.

- **트리거**: `/f ` 접두어 (예: `/f 판다스 데이터프레임 병합`). 전각 슬래시(／), fraction slash(⁄) 등 자동 변환.
- **동작**: 모든 `.ipynb` 파일을 5셀 단위 청크로 분할 → N개 병렬 sub-worker가 동시에 LLM 관련성 판단 → 관련 있는 결과만 채팅에 누적 표시
- **병렬 처리**: `ForceWorker` QThread가 `ThreadPoolExecutor(max_workers=N)`으로 청크를 분배. N은 설정 패널의 "병렬 워커 수" SpinBox (1-10)에서 실시간 반영. `env.txt`의 `FORCE_WORKERS`로 초기값 설정 가능.
- **시스템 프롬프트**: `force_prompt.txt` (별도 파일, `system_prompt.txt`와 독립)
- **중지**: 진행 중 "⏹️ 중지" 버튼 클릭으로 모든 sub-worker 즉시 중단 가능
- **PyQt6 구현**:
  - `rag_core.py`: `load_force_prompt()`, `prepare_force_chunks()`, `process_force_chunk()`, `format_force_results()`
  - `workers/llm_worker.py`: `ForceWorker` QThread (내부 `ThreadPoolExecutor` 병렬 처리)
  - `ui/chat_tab.py`: Force Mode UI (QProgressBar + 중지 버튼)
  - `ui/config_panel.py`: `force_workers_spin` QSpinBox (병렬 워커 수, 실시간 반영)
  - `ui/main_window.py`: `_detect_force_mode()` → ForceWorker 생성/관리 (병렬 워커 수 전달)
- FAISS/BM25/Graph 인덱스 불필요 (LLM 설정만 필요)

### External Link Handling (외부 링크)

채팅 내 링크 클릭 시 QWebEngineView 내부에서 열리지 않고 시스템 기본 브라우저로 열리도록 처리.

- **구현**: `_ExternalLinkPage(QWebEnginePage)` — `acceptNavigationRequest()` 오버라이드
- **동작**: `NavigationTypeLinkClicked` 감지 → `QDesktopServices.openUrl()`로 외부 브라우저 실행, 내부 네비게이션 차단 (`return False`)
- **위치**: `ui/chat_tab.py` — `ChatTab.__init__()`에서 `self.chat_display.setPage(_ExternalLinkPage(...))`로 적용

### Chat Smart Scroll (스마트 스크롤)

`resources/chat.html`에 구현된 채팅 스크롤 제어 로직. AI 스트리밍 응답 중 사용자가 자유롭게 스크롤하여 이전 내용을 읽을 수 있도록 조건부 자동 스크롤 패턴 적용.

- **`isNearBottom(threshold)`**: 사용자가 하단에서 50px 이내에 있는지 판단
- **`scrollToBottom(force)`**: `force=true`이면 무조건 하단 스크롤, 없으면 하단 근처일 때만 스크롤
- **강제 스크롤 (`force=true`)**: `appendUserMessage()`, `startAiMessage()`, `appendFinishedAiMessage()` — 사용자 메시지 전송, AI 응답 시작, 히스토리 복원 시
- **조건부 스크롤 (force 없음)**: `renderStreamingBuffer()`, `finishAiMessage()` — 스트리밍 중/완료 시 사용자가 위로 스크롤했으면 위치 유지

### Streaming Stop (일반 모드 답변 중지)

일반 RAG 쿼리의 AI 스트리밍 응답 도중 사용자가 즉시 중단할 수 있는 기능. ChatGPT 스타일로 전송 버튼이 중지 버튼으로 전환된다.

- **UI**: 스트리밍 시작 시 "전송" 버튼 → 빨간 "⏹" 중지 버튼으로 자동 전환, 완료/중지 시 원래 버튼으로 복원
- **동작**: 중지 클릭 시 `LLMWorker._stopped` 플래그 설정 → 스트리밍 루프(`llm.stream()`) 내 매 토큰마다 체크하여 `break` → 현재까지의 부분 답변을 그대로 표시
- **중지 시점**: 검색(`agent.invoke`) 완료 직후 또는 스트리밍 도중 언제든 가능
- **PyQt6 구현**:
  - `workers/llm_worker.py`: `LLMWorker._stopped` 플래그 + `stop()` 메서드, `stream_messages()` 루프 내 체크
  - `ui/chat_tab.py`: `llm_stop_requested` 시그널, `_on_send()`에서 스트리밍 중이면 중지 emit, `start_streaming()`/`_restore_send_btn()`으로 버튼 전환
  - `ui/main_window.py`: `_on_llm_stop()` → `LLMWorker.stop()` 호출

### Notebook Summary (노트북 요약)

📓 노트북 뷰어 탭에 통합된 LLM 기반 요약 기능.

- **UI**: 좌측 체크박스 노트북 목록 + 우측 셀/요약 전환 뷰 (QSplitter)
- **동작**: 체크한 노트북들의 셀 내용을 LLM에 전송하여 한국어 요약 생성
- **마크다운 렌더링**: 요약 카드에서 `QTextBrowser.setMarkdown()` + `defaultStyleSheet`로 마크다운 렌더링 (헤더, 볼드, 리스트, 코드 블록 등). 채팅 탭의 `marked.js` 방식과 별도로 Qt 네이티브 마크다운 렌더링 사용.
- **시스템 프롬프트**: `summary_prompt.txt` (선택, 없으면 기본 프롬프트 사용)
- **캐시**: 인메모리 — 앱 실행 중 이미 요약된 노트북은 재요청하지 않음
- **중지**: 진행 중 "⏹️ 중지" 버튼으로 즉시 중단 가능
- **PyQt6 구현**:
  - `rag_core.py`: `load_summary_prompt()`, `prepare_notebook_summary_prompt()`
  - `workers/llm_worker.py`: `SummaryWorker` QThread
  - `ui/notebook_tab.py`: 체크박스 목록, 요약 생성 버튼, 프로그레스, 셀/요약 뷰 전환, `QTextBrowser` 마크다운 카드
  - `ui/main_window.py`: `_on_summary_requested()` → SummaryWorker 생성/관리

### RAG Parameter Configuration

`config.txt` (project root, `KEY=VALUE` format) controls RAG pipeline parameters. The file is loaded once at startup via `_load_config()` into the `RAG_CONFIG` dict. If the file is missing, all parameters use built-in defaults.

| Key | Default | Description |
|-----|---------|-------------|
| `VECTOR_K` | 5 | Vector retriever top-k |
| `BM25_K` | 5 | BM25 retriever top-k |
| `GRAPH_K` | 5 | Graph RAG top-k |
| `GRAPH_HOPS` | 2 | Multi-hop propagation depth |
| `SEQ_DECAY` | 0.5 | Sequential edge decay |
| `VAR_DECAY` | 0.8 | Shared variable edge decay |
| `KEYWORD_BOOST` | 0.4 | Keyword score boost multiplier |
| `SEED_COUNT` | 3 | Vector seed documents for Graph RAG |
| `VECTOR_WEIGHT` | 0.6 | Ensemble vector weight |
| `BM25_WEIGHT` | 0.4 | Ensemble BM25 weight |
| `MAX_DOCS` | 10 | Max merged context documents |
| `LLM_TEMPERATURE` | 0.2 | LLM response temperature |
| `TRACE_DEBUG` | false | 쿼리별 retriever 결과를 trace_logs/에 저장 |

### Trace Debug Logging (트레이스 디버그)

RAG 검색 파이프라인의 디버깅을 위한 retriever별 결과 로깅 기능. `config.txt`에서 `TRACE_DEBUG=true`로 활성화.

- **활성화**: `config.txt`에서 `TRACE_DEBUG=true` 설정
- **출력 경로**: `trace_logs/` 폴더에 타임스탬프+쿼리명 형태의 `.txt` 파일 생성 (예: `20260324_211218_판다스_데이터프레임.txt`)
- **로그 내용**: 각 쿼리마다 Vector RAG, BM25, Graph RAG, Merged 4단계의 검색 결과를 기록 (노트북명, 셀 번호, 셀 타입, 셀 내용)
- **호출 시점**: `merge_docs` 노드에서 문서 병합 완료 후 자동 호출
- **구현**:
  - `rag_core.py`: `_is_trace_debug()` (설정 확인), `_format_docs_section()` (결과 포맷), `_write_trace_log()` (파일 저장)
  - `merge_docs` 노드 내부에서 `_write_trace_log()` 호출

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | PyQt6 앱 진입점 |
| `ui/main_window.py` | MainWindow (탭/패널 조립, 워커 관리) |
| `ui/config_panel.py` | 좌측 설정 패널 |
| `ui/chat_tab.py` | 채팅 탭 (스트리밍, 답변 중지, Force Mode UI, 외부 링크) |
| `ui/docs_tab.py` | 문서 탐색 탭 |
| `ui/graph_tab.py` | 그래프 탐색 탭 |
| `ui/notebook_tab.py` | 노트북 뷰어 탭 |
| `ui/dir_tab.py` | 디렉토리 트리 탭 |
| `workers/llm_worker.py` | QThread 워커 (RAG빌드, LLM, Force, 예시질문, 후속쿼리) |
| `rag_core.py` | RAG 비즈니스 로직 (UI 무관) |
| `env_loader.py` | env.txt 환경변수 로더 |
| `notebook_rag_agent.py` | **레거시** Streamlit 앱 (미사용, 수정 금지) |
| `work/` | Lecture notebook directory (`.ipynb` files) |
| `prompts/system_prompt.txt` | Optional custom LLM system prompt |
| `prompts/force_prompt.txt` | Force Mode system prompt (관련성 판단용) |
| `prompts/summary_prompt.txt` | Notebook summary system prompt |
| `config.txt` | RAG pipeline parameter configuration |
| `trace_logs/` | Trace debug 로그 출력 폴더 (`TRACE_DEBUG=true` 시 생성) |
| `requirements_1.txt` | Python dependencies |
| `.env` / `env.txt` | Environment variables (API keys, model config) |
