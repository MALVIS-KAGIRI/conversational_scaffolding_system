from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from .router import router


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Rule-Guided Conversational System for Social Interaction Support",
    version="1.0.0",
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
