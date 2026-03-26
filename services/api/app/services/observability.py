"""
Observabilidade do pipeline MedReport via Langfuse.

Fornece:
  - Tracing por agente (researcher, writer, auditor, validator)
  - Custo por relatório (tokens + USD/BRL)
  - Latência P50/P95/P99 por agente
  - Error rate tracking
  - Prompt versioning

Fallback graceful: se Langfuse não estiver configurado, usa logging padrão.
Mantém compatibilidade com token_tracker.py existente.

Configuração via .env:
  LANGFUSE_PUBLIC_KEY=pk-...
  LANGFUSE_SECRET_KEY=sk-...
  LANGFUSE_HOST=https://cloud.langfuse.com (ou self-hosted)
"""
import logging
import time
import functools
from typing import Optional, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ── Langfuse Client (lazy init) ───────────────────────────────────────────

_langfuse = None
_langfuse_available: Optional[bool] = None


def _get_langfuse():
    global _langfuse, _langfuse_available
    if _langfuse_available is False:
        return None
    if _langfuse is not None:
        return _langfuse
    try:
        import os
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if not pk or not sk:
            _langfuse_available = False
            logger.debug("Langfuse not configured (missing LANGFUSE_PUBLIC_KEY/SECRET_KEY)")
            return None
        from langfuse import Langfuse
        _langfuse = Langfuse(public_key=pk, secret_key=sk, host=host)
        _langfuse_available = True
        logger.info("Langfuse connected: %s", host)
        return _langfuse
    except Exception as e:
        _langfuse_available = False
        logger.debug("Langfuse unavailable: %s", e)
        return None


# ── Trace Context Manager ─────────────────────────────────────────────────

class TraceContext:
    """
    Context for a pipeline trace (one report generation = one trace).
    Each agent call within the trace becomes a "generation" span.
    """

    def __init__(self, trace_id: str, user_id: str = "", metadata: dict = None):
        self.trace_id = trace_id
        self.user_id = user_id
        self.metadata = metadata or {}
        self._trace = None
        self._langfuse = _get_langfuse()

        if self._langfuse:
            self._trace = self._langfuse.trace(
                id=trace_id,
                name="report-pipeline",
                user_id=user_id,
                metadata=metadata,
            )

    def generation(
        self,
        name: str,
        model: str = "gpt-4o",
        input_data: Any = None,
        metadata: dict = None,
    ) -> "GenerationSpan":
        """Start a generation span (one LLM call)."""
        return GenerationSpan(
            trace=self._trace,
            langfuse=self._langfuse,
            name=name,
            model=model,
            input_data=input_data,
            metadata=metadata,
        )

    def span(self, name: str, metadata: dict = None) -> "SpanContext":
        """Start a generic span (non-LLM work like validation, search)."""
        return SpanContext(
            trace=self._trace,
            langfuse=self._langfuse,
            name=name,
            metadata=metadata,
        )

    def score(self, name: str, value: float, comment: str = ""):
        """Add a score to the trace (e.g., approval, consistency)."""
        if self._trace:
            try:
                self._trace.score(name=name, value=value, comment=comment)
            except Exception:
                pass

    def flush(self):
        """Flush pending events to Langfuse."""
        if self._langfuse:
            try:
                self._langfuse.flush()
            except Exception:
                pass


class GenerationSpan:
    """Context manager for an LLM generation call."""

    def __init__(self, trace, langfuse, name, model, input_data, metadata):
        self._trace = trace
        self._langfuse = langfuse
        self._name = name
        self._model = model
        self._input = input_data
        self._metadata = metadata
        self._generation = None
        self._start = None

    def __enter__(self):
        self._start = time.time()
        if self._trace:
            try:
                self._generation = self._trace.generation(
                    name=self._name,
                    model=self._model,
                    input=self._input,
                    metadata=self._metadata,
                )
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self._start
        level = "ERROR" if exc_type else "DEFAULT"

        if self._generation:
            try:
                self._generation.end(
                    level=level,
                    status_message=str(exc_val) if exc_val else None,
                )
            except Exception:
                pass

        # Always log locally
        logger.info(
            "agent=%s model=%s duration=%.2fs status=%s",
            self._name, self._model, duration, "error" if exc_type else "ok",
        )

    def update(self, output: Any = None, usage: dict = None, metadata: dict = None):
        """Update the generation with output, token usage, etc."""
        if self._generation:
            try:
                kwargs = {}
                if output is not None:
                    kwargs["output"] = output
                if usage:
                    kwargs["usage"] = usage
                if metadata:
                    kwargs["metadata"] = metadata
                self._generation.update(**kwargs)
            except Exception:
                pass

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


class SpanContext:
    """Context manager for a non-LLM span."""

    def __init__(self, trace, langfuse, name, metadata):
        self._trace = trace
        self._langfuse = langfuse
        self._name = name
        self._metadata = metadata
        self._span = None
        self._start = None

    def __enter__(self):
        self._start = time.time()
        if self._trace:
            try:
                self._span = self._trace.span(
                    name=self._name,
                    metadata=self._metadata,
                )
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self._start
        if self._span:
            try:
                self._span.end(
                    level="ERROR" if exc_type else "DEFAULT",
                    status_message=str(exc_val) if exc_val else None,
                )
            except Exception:
                pass

        logger.info(
            "span=%s duration=%.2fs status=%s",
            self._name, duration, "error" if exc_type else "ok",
        )

    def update(self, output: Any = None, metadata: dict = None):
        if self._span:
            try:
                kwargs = {}
                if output is not None:
                    kwargs["output"] = output
                if metadata:
                    kwargs["metadata"] = metadata
                self._span.update(**kwargs)
            except Exception:
                pass

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


# ── Convenience: create trace for a pipeline run ──────────────────────────

def create_pipeline_trace(
    session_id: str,
    user_id: str = "",
    product_name: str = "",
    cid: str = "",
) -> TraceContext:
    """Create a new trace for a pipeline run."""
    return TraceContext(
        trace_id=session_id,
        user_id=user_id,
        metadata={
            "product": product_name,
            "cid": cid,
        },
    )
