# tracing.py
"""
tracing.py
----------
Langfuse SDK v3/v4 (OTEL-based) initialisation.

Reads credentials from environment variables:
    LANGFUSE_PUBLIC_KEY   pk-lf-...
    LANGFUSE_SECRET_KEY   sk-lf-...
    LANGFUSE_HOST         https://cloud.langfuse.com  (default)

Import `langfuse` anywhere in the backend to access the singleton client.
Import `observe` for the decorator, `propagate_attributes` for tag/session propagation.
Import `start_as_current_span` for v3/v4-compatible span creation.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialise the Langfuse client once at import time.
# ---------------------------------------------------------------------------

_LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)

if _LANGFUSE_ENABLED:
    try:
        from langfuse import get_client, observe, propagate_attributes  # noqa: F401

        langfuse = get_client()
        logger.info(
            "Langfuse tracing enabled → %s",
            os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Langfuse initialisation failed — tracing disabled: %s", exc)
        _LANGFUSE_ENABLED = False

if not _LANGFUSE_ENABLED:
    # ---------------------------------------------------------------------------
    # Graceful no-op shims so the rest of the codebase imports without changes
    # ---------------------------------------------------------------------------
    import contextlib
    from typing import Any, Generator

    class _NoOpClient:
        """Drop-in replacement when Langfuse is not configured."""

        def start_as_current_span(self, name: str, **kwargs: Any):
            return contextlib.nullcontext()

        def start_as_current_observation(self, as_type: str, name: str, **kwargs: Any):
            return contextlib.nullcontext()

        def update_current_span(self, **kwargs: Any) -> None:
            pass

        def set_current_trace_io(self, **kwargs: Any) -> None:
            pass

        def score(self, **kwargs: Any) -> None:
            pass

        def get_current_trace_id(self) -> None:
            return None

        def flush(self) -> None:
            pass

    langfuse = _NoOpClient()  # type: ignore[assignment]

    def observe(*args: Any, **kwargs: Any):  # type: ignore[misc]
        """No-op decorator shim."""
        def decorator(func: Any) -> Any:
            return func
        if args and callable(args[0]):
            return args[0]
        return decorator

    @contextlib.contextmanager
    def propagate_attributes(*args: Any, **kwargs: Any) -> Generator[None, None, None]:  # type: ignore[misc]
        yield


# ---------------------------------------------------------------------------
# Version-agnostic helpers
# ---------------------------------------------------------------------------

def start_as_current_span(name: str, **kwargs: Any):
    """Start a span. Works with Langfuse v3 (start_as_current_span) and v4 (start_as_current_observation)."""
    if hasattr(langfuse, "start_as_current_observation"):
        return langfuse.start_as_current_observation(as_type="span", name=name, **kwargs)
    return langfuse.start_as_current_span(name=name, **kwargs)


def get_current_trace_id() -> str | None:
    """Get the current OTEL trace ID if available."""
    try:
        # Try Langfuse native method first
        if hasattr(langfuse, "get_current_trace_id"):
            tid = langfuse.get_current_trace_id()
            if tid:
                return tid
    except Exception:
        pass

    try:
        # Fallback to OTEL context (Langfuse v4 is OTEL-based)
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass

    return None