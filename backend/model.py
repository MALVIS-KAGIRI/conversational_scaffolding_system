from __future__ import annotations

import atexit
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, Optional
from urllib import error, request


logger = logging.getLogger(__name__)

DEFAULT_HF_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_GROQ_MODEL_NAME = "llama-3.1-8b-instant"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# HTTP status codes from Groq that should trigger fallback to local
_FALLBACK_ON_STATUS = {
    429,  # rate limit exceeded
    403,  # Cloudflare access block (error 1010) — treat as transient, fall back
    503,  # service unavailable
    529,  # overloaded (Groq-specific)
}

# Headers that satisfy Cloudflare's bot detection on the Groq endpoint
_GROQ_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "python-groq-client/1.0",
    "Accept": "application/json",
}


@dataclass
class ModelResult:
    text: str
    latency_ms: float
    token_usage: Dict[str, int]
    provider: str


class _GroqRateLimitError(Exception):
    """Raised when Groq returns 429 or another fallback-worthy status."""


class _GroqUnavailableError(Exception):
    """Raised when the network is unreachable or Groq is down."""


class ModelClient:
    """
    Provider priority:
      1. Groq (llama-3.1-8b-instant) — always tried first.
      2. llama.cpp local server       — fallback when:
           a) no internet / Groq unreachable, OR
           b) Groq rate limit (429) or overload (503/529) is hit.
      3. Hugging Face Inference API   — last resort if both above fail.

    Environment variables
    ---------------------
    Required for Groq (primary):
        GROQ_API_KEY         your Groq API key (gsk_...)
        GROQ_MODEL_ID        model slug (default: llama-3.1-8b-instant)

    Optional for local fallback:
        LLAMA_CPP_URL        base URL of a running llama.cpp server
        LLAMA_CPP_SERVER_PATH  path to llama-server binary (auto-start)
        LLAMA_CPP_MODEL_PATH   path to .gguf model file   (auto-start)
        LLAMA_CPP_CONTEXT_SIZE context window size (default 2048)
        LLAMA_CPP_GPU_LAYERS   layers offloaded to GPU (default 20)
        LLAMA_CPP_STARTUP_TIMEOUT seconds to wait for server (default 45)

    Optional for HuggingFace last-resort:
        HF_API_TOKEN
        HF_MODEL_ID
    """

    _server_process: subprocess.Popen[str] | None = None
    _server_lock = Lock()

    def __init__(
        self,
        local_url: Optional[str] = None,
        hf_model: Optional[str] = None,
        hf_token: Optional[str] = None,
    ) -> None:
        # ── Groq (primary) ──────────────────────────────────────────────────
        self.groq_api_key = os.getenv("GROQ_API_KEY") or ""
        self.groq_model = os.getenv("GROQ_MODEL_ID") or DEFAULT_GROQ_MODEL_NAME

        # ── llama.cpp local (fallback) ───────────────────────────────────────
        self.local_url = (local_url or os.getenv("LLAMA_CPP_URL") or "").rstrip("/")
        self.server_binary = os.getenv("LLAMA_CPP_SERVER_PATH", "").strip()
        self.model_path = os.getenv("LLAMA_CPP_MODEL_PATH", "").strip()
        self.context_size = int(os.getenv("LLAMA_CPP_CONTEXT_SIZE", "2048"))
        self.gpu_layers = int(os.getenv("LLAMA_CPP_GPU_LAYERS", "20"))
        self.startup_timeout = int(os.getenv("LLAMA_CPP_STARTUP_TIMEOUT", "45"))

        # ── Hugging Face (last resort) ────────────────────────────────────────
        self.hf_model = hf_model or os.getenv("HF_MODEL_ID") or DEFAULT_HF_MODEL_NAME
        self.hf_token = hf_token or os.getenv("HF_API_TOKEN") or ""

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        prompt: str,
        temperature: float = 0.6,
        top_p: float = 0.9,
        max_tokens: int = 120,
    ) -> ModelResult:
        """
        Try Groq first. On network failure or rate-limit, fall through to
        local llama.cpp (starting the server if needed), then HuggingFace.
        """
        if not self.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Groq is the required primary backend.\n"
                "Get a free key at https://console.groq.com and add it to your .env."
            )

        # ── 1. Groq ──────────────────────────────────────────────────────────
        try:
            result = self._call_groq_api(prompt, temperature, top_p, max_tokens)
            logger.debug("Groq responded in %.0f ms", result.latency_ms)
            return result

        except _GroqRateLimitError as exc:
            logger.warning("Groq rate limit hit — switching to local inference. (%s)", exc)

        except _GroqUnavailableError as exc:
            logger.warning("Groq unreachable (no internet?) — switching to local inference. (%s)", exc)

        except Exception as exc:
            # Unexpected Groq error: log and fall through so the app keeps running
            logger.error("Unexpected Groq error — falling back to local: %s", exc)

        # ── 2. llama.cpp local ───────────────────────────────────────────────
        local_ready = self._try_ensure_local_server()
        if local_ready:
            try:
                result = self._call_llama_cpp(prompt, temperature, top_p, max_tokens)
                logger.info("Using local llama.cpp inference.")
                return result
            except Exception as exc:
                logger.error("Local llama.cpp inference failed: %s", exc)

        # ── 3. HuggingFace last resort ───────────────────────────────────────
        if self.hf_token:
            logger.info("Falling back to Hugging Face inference API.")
            return self._call_hf_api(prompt, temperature, top_p, max_tokens)

        raise RuntimeError(
            "All inference backends failed.\n"
            "  • Groq: unreachable or rate-limited\n"
            "  • llama.cpp: not configured or failed to start\n"
            "  • HuggingFace: HF_API_TOKEN not set\n"
            "Please check your environment variables and connectivity."
        )

    # ------------------------------------------------------------------ #
    #  Groq                                                                #
    # ------------------------------------------------------------------ #

    def _call_groq_api(
        self,
        prompt: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> ModelResult:
        started = time.perf_counter()
        payload = {
            "model": self.groq_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a conversational social interaction coach. "
                        "Follow instructions strictly. Keep responses to 2–3 short sentences."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{GROQ_BASE_URL}/chat/completions",
            data=data,
            headers={**_GROQ_HEADERS, "Authorization": f"Bearer {self.groq_api_key}"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))

        except error.HTTPError as exc:
            if exc.code in _FALLBACK_ON_STATUS:
                details = exc.read().decode("utf-8", errors="ignore")
                if exc.code == 429:
                    raise _GroqRateLimitError(f"HTTP {exc.code}: {details}") from exc
                # 403 = Cloudflare block, 503/529 = Groq overload — all treated as transient
                raise _GroqUnavailableError(f"HTTP {exc.code}: {details}") from exc
            # Any other HTTP error (400 bad request, 401 bad key, etc.) — re-raise directly
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Groq API error {exc.code}: {details}") from exc

        except (OSError, TimeoutError) as exc:
            # Network-level failure: no internet, DNS failure, connection refused, timeout
            raise _GroqUnavailableError(str(exc)) from exc

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = (message.get("content") or "").strip()
        usage_body = body.get("usage") or {}
        usage = {
            "prompt_tokens": int(usage_body.get("prompt_tokens", _estimate_tokens(prompt))),
            "completion_tokens": int(usage_body.get("completion_tokens", _estimate_tokens(text))),
            "total_tokens": int(
                usage_body.get("total_tokens", _estimate_tokens(prompt) + _estimate_tokens(text))
            ),
        }
        return ModelResult(text=text, latency_ms=latency_ms, token_usage=usage, provider="groq")

    # ------------------------------------------------------------------ #
    #  llama.cpp local server                                              #
    # ------------------------------------------------------------------ #

    def _try_ensure_local_server(self) -> bool:
        """
        Returns True if a local llama.cpp server is ready to accept requests.
        Never raises — returns False instead so the caller can fall through.
        """
        # Already running and reachable
        if self.local_url and _server_is_ready(self.local_url):
            return True

        # Not configured at all
        if not self.server_binary and not self.local_url:
            logger.debug("No local llama.cpp backend configured.")
            return False

        # Configured but not yet started — try to auto-start
        try:
            self._ensure_local_server()
            return bool(self.local_url and _server_is_ready(self.local_url))
        except Exception as exc:
            logger.error("Could not start local llama.cpp server: %s", exc)
            return False

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
                    "-m", str(model),
                    "-c", str(self.context_size),
                    "-ngl", str(self.gpu_layers),
                    "--host", "127.0.0.1",
                    "--port", str(_port_from_url(self.local_url)),
                ]
                logger.info("Starting llama.cpp server: %s", " ".join(command))
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
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.local_url}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        choice = body.get("choices", [{}])[0]
        message = choice.get("message", {})
        text = (message.get("content") or "").strip()
        usage = {
            "prompt_tokens": int(body.get("tokens_evaluated", 0)),
            "completion_tokens": int(body.get("tokens_predicted", 0)),
            "total_tokens": int(body.get("tokens_evaluated", 0)) + int(body.get("tokens_predicted", 0)),
        }
        return ModelResult(text=text, latency_ms=latency_ms, token_usage=usage, provider="llama.cpp")

    # ------------------------------------------------------------------ #
    #  Hugging Face (last resort)                                          #
    # ------------------------------------------------------------------ #

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
        return ModelResult(text=text, latency_ms=latency_ms, token_usage=usage, provider="huggingface_api")


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _server_is_ready(local_url: str) -> bool:
    try:
        with request.urlopen(f"{local_url}/v1/models", timeout=2) as resp:
            return 200 <= resp.status < 300
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