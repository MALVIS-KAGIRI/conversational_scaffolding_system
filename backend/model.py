from __future__ import annotations

import atexit
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
from urllib import error, request


DEFAULT_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"


@dataclass
class ModelResult:
    text: str
    latency_ms: float
    token_usage: Dict[str, int]
    provider: str


class ModelClient:
    """Supports a managed local llama.cpp server, an existing local server, or HF fallback."""

    _server_process: subprocess.Popen[str] | None = None
    _server_lock = Lock()

    def __init__(
        self,
        local_url: Optional[str] = None,
        hf_model: Optional[str] = None,
        hf_token: Optional[str] = None,
    ) -> None:
        self.local_url = (local_url or os.getenv("LLAMA_CPP_URL") or "").rstrip("/")
        self.hf_model = hf_model or os.getenv("HF_MODEL_ID") or DEFAULT_MODEL_NAME
        self.hf_token = hf_token or os.getenv("HF_API_TOKEN") or ""
        self.server_binary = os.getenv("LLAMA_CPP_SERVER_PATH", "").strip()
        self.model_path = os.getenv("LLAMA_CPP_MODEL_PATH", "").strip()
        self.context_size = int(os.getenv("LLAMA_CPP_CONTEXT_SIZE", "2048"))
        self.gpu_layers = int(os.getenv("LLAMA_CPP_GPU_LAYERS", "20"))
        self.startup_timeout = int(os.getenv("LLAMA_CPP_STARTUP_TIMEOUT", "45"))

    def generate(
        self,
        prompt: str,
        temperature: float = 0.6,
        top_p: float = 0.9,
        max_tokens: int = 120,
    ) -> ModelResult:
        self._ensure_local_server()

        if self.local_url:
            try:
                return self._call_llama_cpp(prompt, temperature, top_p, max_tokens)
            except Exception:
                if not self.hf_token:
                    raise

        if self.hf_token:
            return self._call_hf_api(prompt, temperature, top_p, max_tokens)

        raise RuntimeError(
            "No model backend configured. Set LLAMA_CPP_URL, or set "
            "LLAMA_CPP_SERVER_PATH with LLAMA_CPP_MODEL_PATH, or provide HF_API_TOKEN."
        )

    def _ensure_local_server(self) -> None:
        if self.local_url and _server_is_ready(self.local_url):
            return

        if not self.server_binary or not self.model_path:
            return

        with self._server_lock:
            if self.local_url and _server_is_ready(self.local_url):
                return

            binary = Path(self.server_binary)
            model = Path(self.model_path)
            if not binary.exists():
                raise RuntimeError(f"llama.cpp server binary not found: {binary}")
            if not model.exists():
                raise RuntimeError(f"Local model file not found: {model}")

            if not self.local_url:
                self.local_url = "http://127.0.0.1:8080"

            if self._server_process is None or self._server_process.poll() is not None:
                command = [
                    str(binary),
                    "-m",
                    str(model),
                    "-c",
                    str(self.context_size),
                    "-ngl",
                    str(self.gpu_layers),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(_port_from_url(self.local_url)),
                ]

                self._server_process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                atexit.register(self._shutdown_server)

            self._wait_for_server()

    def _wait_for_server(self) -> None:
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self.local_url and _server_is_ready(self.local_url):
                return
            time.sleep(1)

        raise RuntimeError(
            f"Timed out waiting for local llama.cpp server at {self.local_url}."
        )

    @classmethod
    def _shutdown_server(cls) -> None:
        if cls._server_process and cls._server_process.poll() is None:
            cls._server_process.terminate()
            try:
                cls._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls._server_process.kill()

    def _call_llama_cpp(
        self,
        prompt: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> ModelResult:
        started = time.perf_counter()
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "n_predict": max_tokens,
            "stop": ["User:", "Guide:"],
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.local_url}/completion",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        text = (body.get("content") or "").strip()
        usage = {
            "prompt_tokens": int(body.get("tokens_evaluated", 0)),
            "completion_tokens": int(body.get("tokens_predicted", 0)),
            "total_tokens": int(body.get("tokens_evaluated", 0))
            + int(body.get("tokens_predicted", 0)),
        }
        return ModelResult(
            text=text,
            latency_ms=latency_ms,
            token_usage=usage,
            provider="llama.cpp",
        )

    def _call_hf_api(
        self,
        prompt: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> ModelResult:
        started = time.perf_counter()
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "top_p": top_p,
                "max_new_tokens": max_tokens,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"https://api-inference.huggingface.co/models/{self.hf_model}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.hf_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Hugging Face inference failed: {details}") from exc

        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        if isinstance(body, list) and body:
            text = (body[0].get("generated_text") or "").strip()
        elif isinstance(body, dict):
            text = (body.get("generated_text") or "").strip()
        else:
            text = ""

        usage = {
            "prompt_tokens": _estimate_tokens(prompt),
            "completion_tokens": _estimate_tokens(text),
            "total_tokens": _estimate_tokens(prompt) + _estimate_tokens(text),
        }
        return ModelResult(
            text=text,
            latency_ms=latency_ms,
            token_usage=usage,
            provider="huggingface_api",
        )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _server_is_ready(local_url: str) -> bool:
    try:
        with request.urlopen(f"{local_url}/health", timeout=2) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:
        return False


def _port_from_url(local_url: str) -> int:
    default_port = 8080
    if ":" not in local_url.rsplit("/", maxsplit=1)[-1]:
        return default_port
    try:
        return int(local_url.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        return default_port
