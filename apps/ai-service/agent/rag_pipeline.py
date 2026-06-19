import json
import time
from enum import Enum
from typing import Callable

from langchain_core.messages import SystemMessage, HumanMessage
from utils.tracing import _iso_ms, _store_event


class RAGSource(str, Enum):
    """Enumeration of possible RAG retrieval source types."""
    RAG_INDEX = "rag_index"
    HARDCODED_KB = "hardcoded_kb"
    WARDROBE = "wardrobe"
    API = "api"
    FALLBACK = "fallback"
    MEMORY = "memory"
    UNKNOWN = "unknown"


# Source label mapping: retriever name prefix -> RAGSource
_RETRIEVER_SOURCE_MAP: dict[str, RAGSource] = {
    # English prefixes (backward compat)
    "fashion_knowledge": RAGSource.HARDCODED_KB,
    "external_fashion_knowledge": RAGSource.HARDCODED_KB,
    "faiss": RAGSource.WARDROBE,
    "vector": RAGSource.WARDROBE,
    "web_search": RAGSource.API,
    "weather": RAGSource.API,
    # Chinese retriever names used in agents
    "衣橱检索": RAGSource.WARDROBE,
    "时尚知识": RAGSource.HARDCODED_KB,
    "天气信息": RAGSource.API,
    "身材分析": RAGSource.RAG_INDEX,
    "用户偏好": RAGSource.MEMORY,
}


def _infer_source(name: str) -> RAGSource:
    """Map a retriever name to a RAGSource."""
    for prefix, source in _RETRIEVER_SOURCE_MAP.items():
        if name.lower().startswith(prefix):
            return source
    return RAGSource.UNKNOWN


def trace_rag_event(session_id: str, phase: str, data: dict):
    event = {"ts": _iso_ms(), "type": "rag", "phase": phase, "data": data}
    print(f"[RAG] {event['ts']} | session:{session_id} | phase:{phase} | {json.dumps(data, ensure_ascii=False)[:300]}")
    _store_event(session_id, event)


class RAGSourceInfo:
    """Metadata about a single retrieved piece of context."""
    def __init__(self, name: str, source: RAGSource, content_preview: str, latency_ms: int = 0):
        self.name = name
        self.source = source
        self.content_preview = content_preview[:200]
        self.latency_ms = latency_ms

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source.value,
            "content_preview": self.content_preview,
            "latency_ms": self.latency_ms,
        }


class RAGPipeline:
    """检索→增强→生成→反馈 闭环"""
    def __init__(self, llm, retrievers: list[tuple[str, Callable]], system_prompt: str, session_id: str = ""):
        self.llm = llm
        self.retrievers = retrievers  # [(name, callable) -> str]
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.retrieved_contexts: dict = {}
        self.source_infos: list[RAGSourceInfo] = []
        self.augmented_prompt: str = ""
        self.generation: str = ""
        self.feedback: dict = {}

    def retrieve(self, **kwargs) -> dict:
        """阶段1: 检索 — 系统性地调用所有检索器收集上下文"""
        trace_rag_event(self.session_id, "retrieve_start", {"retrievers": [r[0] for r in self.retrievers], "kwargs_keys": list(kwargs.keys())})
        self.source_infos = []
        for name, retriever_fn in self.retrievers:
            t0 = time.time()
            try:
                result = retriever_fn(**kwargs) if kwargs else retriever_fn()
                self.retrieved_contexts[name] = result
                elapsed = int((time.time() - t0) * 1000)
                preview = str(result)[:300]
                source = _infer_source(name)
                self.source_infos.append(RAGSourceInfo(name, source, str(result), elapsed))
                trace_rag_event(self.session_id, "retrieve_done", {
                    "retriever": name, "latency_ms": elapsed, "source": source.value,
                    "result_len": len(str(result)), "preview": preview,
                })
            except Exception as e:
                self.retrieved_contexts[name] = f"检索失败: {e}"
                self.source_infos.append(RAGSourceInfo(name, RAGSource.UNKNOWN, f"error: {e}", 0))
                trace_rag_event(self.session_id, "retrieve_error", {"retriever": name, "error": str(e)})
        return self.retrieved_contexts

    def augment(self) -> str:
        """阶段2: 增强 — 将检索到的上下文注入 prompt，附带来源信息"""
        parts = []
        for name, ctx in self.retrieved_contexts.items():
            source = _infer_source(name)
            citation = f"【{name}】(来源: {source.value})"
            parts.append(f"{citation}\n{ctx}")
        augmentation = "\n\n".join(parts)
        sources_summary = self._compile_sources()
        self.augmented_prompt = (
            f"{self.system_prompt}\n\n"
            f"以下是从知识库和工具中检索到的相关信息，请基于这些信息生成回答。\n"
            f"信息来源: {json.dumps(sources_summary, ensure_ascii=False)}\n\n"
            f"{augmentation}"
        )
        trace_rag_event(self.session_id, "augment", {
            "prompt_len": len(self.augmented_prompt),
            "context_count": len(self.retrieved_contexts),
            "context_keys": list(self.retrieved_contexts.keys()),
            "sources": sources_summary,
        })
        return self.augmented_prompt

    def _compile_sources(self) -> list[dict]:
        """列出本次 RAG 使用的所有信息来源及元数据。"""
        return [si.to_dict() for si in self.source_infos]

    def generate(self, user_message: str) -> str:
        """阶段3: 生成 — 用增强后的 prompt 调用 LLM"""
        t0 = time.time()
        messages = [
            SystemMessage(content=self.augmented_prompt),
            HumanMessage(content=user_message),
        ]
        resp = self.llm.invoke(messages)
        self.generation = resp.content
        elapsed = int((time.time() - t0) * 1000)
        trace_rag_event(self.session_id, "generate", {
            "input_len": len(user_message),
            "output_len": len(self.generation),
            "latency_ms": elapsed,
        })
        return self.generation

    def collect_feedback(self, rating: int = None, comment: str = None):
        """阶段4: 反馈 — 收集用户对生成结果的评价"""
        self.feedback = {
            "rating": rating,
            "comment": comment,
            "retrieved_contexts": list(self.retrieved_contexts.keys()),
            "generation_preview": self.generation[:200],
            "timestamp": _iso_ms(),
        }
        trace_rag_event(self.session_id, "feedback", self.feedback)
        return self.feedback

    def run(self, user_message: str, **retrieval_kwargs) -> dict:
        """一键执行完整 RAG 闭环"""
        self.retrieve(**retrieval_kwargs)
        self.augment()
        reply = self.generate(user_message)
        return {
            "reply": reply,
            "retrieved_contexts": dict(self.retrieved_contexts),
            "augmented_prompt_len": len(self.augmented_prompt),
            "sources": self._compile_sources(),
        }
