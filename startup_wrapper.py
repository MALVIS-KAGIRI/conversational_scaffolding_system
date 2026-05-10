#!/usr/bin/env python3
"""
startup_wrapper.py
------------------
Optional recovery launcher for cases where broken OTEL environment variables
prevent the backend from starting.

This wrapper is intentionally opt-in:
    set SANITIZE_OTEL_ON_STARTUP=true

Without that flag, the backend starts normally and valid tracing configuration
is preserved.
"""

from __future__ import annotations

import os

import uvicorn


def _should_sanitize_otel() -> bool:
    return os.getenv("SANITIZE_OTEL_ON_STARTUP", "").strip().lower() in {"1", "true", "yes"}


def _sanitize_otel_env() -> None:
    otel_keys = [k for k in os.environ if k.startswith(("OTEL_", "TRACEPARENT", "TRACESTATE"))]
    for key in otel_keys:
        del os.environ[key]
        print(f"[wrapper] Removed {key}")

    os.environ["DISABLE_OTEL_AT_STARTUP"] = "true"
    print("[wrapper] OTEL sanitization enabled for this startup.")


if __name__ == "__main__":
    if _should_sanitize_otel():
        _sanitize_otel_env()
    else:
        print("[wrapper] Starting normally. Set SANITIZE_OTEL_ON_STARTUP=true to scrub OTEL env.")

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
