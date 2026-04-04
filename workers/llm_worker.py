"""
QThread 기반 LLM / RAG 워커
- LLMWorker: 에이전트 검색 + LLM 스트리밍
- RagBuildWorker: RAG 시스템 구축
- ExampleQuestionsWorker: 예시 질문 생성
- SuggestedQueriesWorker: 후속 쿼리 생성
- SummaryWorker: 노트북 요약 생성
"""

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


class RagBuildWorker(QThread):
    """RAG 시스템 구축 (노트북 파싱 + FAISS + BM25 + Graph)"""
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object)   # rag_sys dict or None
    error_signal    = pyqtSignal(str)

    def __init__(self, nb_dir: str, emb_base_url: str, emb_api_key: str,
                 cache_dir: str, emb_model: str, clear_cache: bool = False):
        super().__init__()
        self.nb_dir       = nb_dir
        self.emb_base_url = emb_base_url
        self.emb_api_key  = emb_api_key
        self.cache_dir    = cache_dir
        self.emb_model    = emb_model
        self.clear_cache  = clear_cache

    def run(self):
        try:
            # 캐시 초기화
            if self.clear_cache:
                faiss_path = os.path.join(self.cache_dir, "faiss_index")
                bm25_path  = os.path.join(self.cache_dir, "bm25.pkl")
                if os.path.exists(faiss_path):
                    shutil.rmtree(faiss_path)
                if os.path.exists(bm25_path):
                    os.remove(bm25_path)

            # rag_core를 여기서 import (kiwipiepy 초기화 지연)
            from rag_core import build_rag_system
            rag_sys = build_rag_system(
                nb_dir          = self.nb_dir,
                embedding_base_url = self.emb_base_url,
                openai_api_key  = self.emb_api_key,
                cache_path      = self.cache_dir,
                embedding_model = self.emb_model,
                progress_callback = lambda msg: self.progress_signal.emit(msg),
            )
            self.finished_signal.emit(rag_sys)
        except Exception as e:
            self.error_signal.emit(str(e))


class LLMWorker(QThread):
    """에이전트 검색 + LLM 스트리밍"""
    status_signal   = pyqtSignal(str)        # "🔍 검색 중…"
    chunk_received  = pyqtSignal(str)        # 토큰 단위 스트리밍
    finished_signal = pyqtSignal(str, dict)  # (full_answer, result_state)
    error_signal    = pyqtSignal(str)

    def __init__(self, agent, llm, sys_prompt: str, llm_only_prompt: str,
                 query: str, retrieval_mode: str, is_suggested: bool,
                 conversation_history: list[dict] | None = None):
        super().__init__()
        self.agent            = agent
        self.llm              = llm
        self.sys_prompt       = sys_prompt
        self.llm_only_prompt  = llm_only_prompt
        self.query            = query
        self.retrieval_mode   = retrieval_mode
        self.is_suggested     = is_suggested
        self.conversation_history = conversation_history or []
        self._stopped         = False

    def _build_history_messages(self) -> list:
        """Convert conversation history dicts to LangChain message objects."""
        msgs = []
        for m in self.conversation_history:
            if m["role"] == "user":
                msgs.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                msgs.append(AIMessage(content=m["content"]))
        return msgs

    def stop(self):
        self._stopped = True

    def run(self):
        try:
            # 1. Retrieval (blocking)
            self.status_signal.emit("🔍 검색 중…")
            result = self.agent.invoke({
                "query":          self.query,
                "retrieval_mode": self.retrieval_mode,
                "vector_docs":    [],
                "bm25_docs":      [],
                "graph_docs":     [],
                "all_docs":       [],
                "context":        "",
                "answer":         "",
                "steps":          [],
            })

            if self._stopped:
                self.finished_signal.emit("", result)
                return

            context_found = len(result.get("all_docs", [])) > 0
            rag_not_found = lambda a: any(kw in a for kw in [
                "찾을 수 없습니다", "찾지 못했습니다", "찾을수 없습니다",
                "관련된 내용이 없", "관련 내용을 찾", "직접적인 답변을 찾",
                "해당하는 내용이 없", "관련 정보가 없",
            ])

            self.status_signal.emit("🤖 답변 생성 중…")

            def stream_messages(messages) -> str:
                buf = ""
                for chunk in self.llm.stream(messages):
                    if self._stopped:
                        break
                    buf += chunk.content
                    self.chunk_received.emit(chunk.content)
                return buf

            answer = ""

            if context_found:
                rag_prompt = (
                    f"컨텍스트:\n{result['context']}\n\n"
                    f"질문: {self.query}\n\n"
                    f"위 컨텍스트를 바탕으로 질문에 답변해 주세요."
                )
                answer = stream_messages(
                    [SystemMessage(content=self.sys_prompt)]
                    + self._build_history_messages()
                    + [HumanMessage(content=rag_prompt)]
                )

                if rag_not_found(answer):
                    if self.is_suggested:
                        # 스트리밍 버퍼 초기화 신호
                        self.chunk_received.emit("\x00RESET\x00")
                        answer = stream_messages(
                            [SystemMessage(content=self.llm_only_prompt)]
                            + self._build_history_messages()
                            + [HumanMessage(content=self.query)]
                        )
                else:
                    # 출처 추가
                    src_map: dict[str, list] = {}
                    for d in result["all_docs"]:
                        nb   = d.metadata.get("notebook", "unknown")
                        cidx = d.metadata.get("cell_idx", "?")
                        src_map.setdefault(nb, []).append(cidx)
                    src_parts = [
                        f"{nb} (셀 {', '.join(f'#{c}' for c in sorted(set(idxs)))})"
                        for nb, idxs in src_map.items()
                    ]
                    citation = "\n\n---\n📎 **출처**: " + " · ".join(src_parts)
                    answer += citation
                    self.chunk_received.emit("\x00CITATION\x00" + citation)

            elif self.is_suggested:
                answer = stream_messages(
                    [SystemMessage(content=self.llm_only_prompt)]
                    + self._build_history_messages()
                    + [HumanMessage(content=self.query)]
                )
            else:
                answer = "🔍 관련 문서를 찾지 못했습니다. 노트북 내용과 관련된 질문을 해주세요."
                self.chunk_received.emit(answer)

            self.finished_signal.emit(answer, result)

        except Exception as e:
            self.error_signal.emit(str(e))


class ForceWorker(QThread):
    """Force Mode: 전수 검색 (N개 병렬 sub-worker로 LLM 관련성 판단)"""
    progress_signal  = pyqtSignal(int, int)      # (processed, total)
    result_signal    = pyqtSignal(dict)           # 관련 청크 발견 시
    preview_signal   = pyqtSignal(str)            # 누적 결과 미리보기 마크다운
    finished_signal  = pyqtSignal(str)            # 최종 포맷된 답변
    error_signal     = pyqtSignal(str)

    def __init__(self, llm, query: str, nb_dir: str, max_workers: int = 3):
        super().__init__()
        self.llm         = llm
        self.query       = query
        self.nb_dir      = nb_dir
        self.max_workers = max(1, min(max_workers, 10))
        self._stopped    = False

    def stop(self):
        self._stopped = True

    def run(self):
        try:
            from rag_core import (
                load_force_prompt, prepare_force_chunks,
                process_force_chunk, format_force_results,
            )

            force_prompt = load_force_prompt()
            chunks = prepare_force_chunks(self.nb_dir)

            if not chunks:
                self.finished_signal.emit(
                    "📂 노트북 파일을 찾을 수 없습니다. 디렉토리를 확인하세요."
                )
                return

            total = len(chunks)
            results = []
            processed_count = 0
            lock = threading.Lock()

            def _process(chunk):
                """Sub-worker: plain thread 내에서 단일 청크 처리."""
                if self._stopped:
                    return None
                try:
                    return process_force_chunk(
                        self.llm, force_prompt, self.query, chunk
                    )
                except Exception:
                    return None  # 실패한 청크는 건너뜀

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(_process, chunk): chunk
                    for chunk in chunks
                }

                for future in as_completed(futures):
                    if self._stopped:
                        for f in futures:
                            f.cancel()
                        answer = format_force_results(
                            results, (processed_count, total), stopped=True
                        )
                        self.finished_signal.emit(answer)
                        return

                    result = future.result()

                    with lock:
                        processed_count += 1
                        if result is not None:
                            results.append(result)
                            self.result_signal.emit(result)

                    self.progress_signal.emit(processed_count, total)

                    # 관련 결과 발견 시 또는 일정 간격마다 미리보기 갱신
                    if (result is not None
                            or processed_count % self.max_workers == 0
                            or processed_count == total):
                        preview = format_force_results(
                            list(results), (processed_count, total),
                            stopped=False,
                        )
                        self.preview_signal.emit(preview)

            answer = format_force_results(
                results, (total, total), stopped=False
            )
            self.finished_signal.emit(answer)

        except Exception as e:
            self.error_signal.emit(str(e))


class ExampleQuestionsWorker(QThread):
    """예시 질문 생성 (백그라운드)"""
    finished_signal = pyqtSignal(list)

    def __init__(self, llm, docs: list):
        super().__init__()
        self.llm  = llm
        self.docs = docs

    def run(self):
        try:
            from rag_core import generate_example_questions
            questions = generate_example_questions(self.llm, self.docs)
            self.finished_signal.emit(questions)
        except Exception:
            self.finished_signal.emit([])


class SuggestedQueriesWorker(QThread):
    """후속 검색 쿼리 생성 (백그라운드)"""
    finished_signal = pyqtSignal(list)

    def __init__(self, llm, query: str, answer: str):
        super().__init__()
        self.llm    = llm
        self.query  = query
        self.answer = answer

    def run(self):
        try:
            from rag_core import generate_suggested_queries
            queries = generate_suggested_queries(self.llm, self.query, self.answer)
            self.finished_signal.emit(queries)
        except Exception:
            self.finished_signal.emit([])


class SummaryWorker(QThread):
    """노트북별 LLM 요약 생성 (백그라운드)"""
    progress_signal  = pyqtSignal(int, int)    # (processed, total)
    summary_signal   = pyqtSignal(str, str)    # (notebook_name, summary_text)
    finished_signal  = pyqtSignal()
    error_signal     = pyqtSignal(str)

    def __init__(self, llm, notebooks: dict):
        """notebooks = {name: [cells]} — 요약할 노트북만 전달"""
        super().__init__()
        self.llm       = llm
        self.notebooks = notebooks
        self._stopped  = False

    def stop(self):
        self._stopped = True

    def run(self):
        try:
            from rag_core import load_summary_prompt, prepare_notebook_summary_prompt

            sys_prompt = load_summary_prompt()
            names = list(self.notebooks.keys())
            total = len(names)

            for i, name in enumerate(names):
                if self._stopped:
                    self.finished_signal.emit()
                    return

                try:
                    prompt = prepare_notebook_summary_prompt(
                        name, self.notebooks[name]
                    )
                    response = self.llm.invoke([
                        SystemMessage(content=sys_prompt),
                        HumanMessage(content=prompt),
                    ])
                    self.summary_signal.emit(name, response.content.strip())
                except Exception as e:
                    self.summary_signal.emit(name, f"❌ 요약 생성 실패: {e}")

                self.progress_signal.emit(i + 1, total)

            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))
