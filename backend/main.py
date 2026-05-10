from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# Only disable OTEL when explicitly requested for recovery/debugging.
if os.getenv("DISABLE_OTEL_AT_STARTUP", "").strip().lower() in {"1", "true", "yes"}:
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["OTEL_TRACES_EXPORTER"] = "none"
    os.environ["OTEL_METRICS_EXPORTER"] = "none"
    os.environ["OTEL_LOGS_EXPORTER"] = "none"

from .router import router


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Rule-Guided Conversational System for Social Interaction Support",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llama_cpp_url_configured": str(bool(os.getenv("LLAMA_CPP_URL"))).lower(),
        "llama_cpp_managed_configured": str(
            bool(os.getenv("LLAMA_CPP_SERVER_PATH")) and bool(os.getenv("LLAMA_CPP_MODEL_PATH"))
        ).lower(),
        "groq_configured": str(bool(os.getenv("GROQ_API_KEY"))).lower(),
        "huggingface_configured": str(bool(os.getenv("HF_API_TOKEN"))).lower(),
        "langfuse_configured": str(
            bool(os.getenv("LANGFUSE_PUBLIC_KEY")) and bool(os.getenv("LANGFUSE_SECRET_KEY"))
        ).lower(),
        "otel_disabled_at_startup": str(
            os.getenv("DISABLE_OTEL_AT_STARTUP", "").strip().lower() in {"1", "true", "yes"}
        ).lower(),
    }
