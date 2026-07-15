#!/usr/bin/env python3
"""
Shared local-Ollama client for NERO's LLM-backed components.

Nick's ANTHROPIC_API_KEY has been disabled — reflect.py (reflection loop),
skill_curator.py (umbrella consolidation), and auto_summarize.py (LTMemory
session summaries) now run entirely against a local Ollama instance instead
of the Anthropic API. Everything else (semantic recall embeddings) was
already local.

Two models, picked after benchmarking every locally-installed general-
purpose model against this project's real gate/writer/summarizer prompts
(2026-07-15):

  GATE_MODEL   "mistral:latest"       — Stage 1 fast YES/NO classifier.
                                          Fastest (4-8s), no thinking-mode
                                          empty-output failure mode, already
                                          Lucent's default sub-agent model.
  WRITER_MODEL "mistral-small:latest" — Structured JSON + long-form writing
                                          (Stage 2 writer, curator umbrella
                                          plan, LTMemory summaries). Reliable
                                          clean JSON, 32K context (comfortably
                                          covers the 60K-char archive cap).

Qwen3 models were also tested but excluded: they default to a "thinking"
mode that consumes the num_predict budget on reasoning tokens before ever
emitting `content`, producing silent empty-output failures unless `think:
false` is explicitly passed — and even with thinking disabled, qwen3.6:27b
produced trailing non-JSON data after the object on one of two test runs.
mistral/mistral-small have no such failure mode.

override the endpoint with OLLAMA_URL (matches ui/discord_monitor.py's
env var convention) if Ollama isn't on localhost:11434.
"""

import json
import os
import socket
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

GATE_MODEL = "mistral:latest"
WRITER_MODEL = "mistral-small:latest"

CONNECT_CHECK_TIMEOUT = 3


def check_ollama_health(timeout: float = CONNECT_CHECK_TIMEOUT) -> bool:
    """Fast reachability check, so callers can log a clear reason before
    attempting a real call rather than waiting out a full request timeout."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def call_ollama(
    model: str,
    system: str,
    user: str,
    num_predict: int = 1024,
    num_ctx: int = 8192,
    timeout: float = 120,
    think: bool = False,
    log_fn=None,
) -> tuple[str | None, str | None]:
    """Call the local Ollama chat endpoint.

    Returns (content, error). On any failure, content is None and error is a
    short human-readable reason (timeout, connection refused, empty
    response, malformed response) — this function never raises.
    """

    def _log(msg: str) -> None:
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": think,
        "options": {"num_predict": num_predict, "num_ctx": num_ctx},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except socket.timeout:
        err = f"timeout after {timeout}s calling {model}"
        _log(f"OLLAMA TIMEOUT: {err}")
        return None, err
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout) or "timed out" in str(e.reason).lower():
            err = f"timeout after {timeout}s calling {model}"
            _log(f"OLLAMA TIMEOUT: {err}")
            return None, err
        err = f"connection failed calling {model}: {e.reason} (is Ollama running? `systemctl status ollama` / `ollama serve`)"
        _log(f"OLLAMA CONNECTION FAILED: {err}")
        return None, err
    except Exception as e:
        err = f"request failed calling {model}: {e}"
        _log(f"OLLAMA REQUEST FAILED: {err}")
        return None, err

    try:
        data = json.loads(raw)
        content = data["message"]["content"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        err = f"malformed response from {model}: {e}"
        _log(f"OLLAMA MALFORMED RESPONSE: {err} raw={raw[:300]!r}")
        return None, err

    if not content or not content.strip():
        err = f"empty response from {model} (thinking-token exhaustion? eval_count={data.get('eval_count')})"
        _log(f"OLLAMA EMPTY RESPONSE: {err}")
        return None, err

    return content.strip(), None
