"""Structured Deepgram HTTP request/response logging (toggle via DEEPGRAM_LOG_REQUESTS)."""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from app.database import get_settings

logger = logging.getLogger("deepgram")


def deepgram_logging_enabled() -> bool:
    return get_settings().deepgram_log_requests


def _redact_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    if not headers:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def _serialize_body(body: Any) -> Any:
    if body is None:
        return None
    if isinstance(body, (dict, list, str, int, float, bool)):
        return body
    return str(body)


def log_deepgram_request(
    operation: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    content_bytes: int | None = None,
) -> None:
    if not deepgram_logging_enabled():
        return
    payload: dict[str, Any] = {
        "direction": "request",
        "operation": operation,
        "method": method,
        "url": url,
    }
    if params:
        payload["params"] = params
    if headers:
        payload["headers"] = _redact_headers(headers)
    if json_body is not None:
        payload["json"] = json_body
    if content_bytes is not None:
        payload["content_bytes"] = content_bytes
    logger.info("Deepgram %s", json.dumps(payload, default=str))


def log_deepgram_response(
    operation: str,
    method: str,
    url: str,
    *,
    status_code: int | None = None,
    body: Any = None,
    elapsed_ms: float | None = None,
    error: str | None = None,
) -> None:
    if not deepgram_logging_enabled():
        return
    payload: dict[str, Any] = {
        "direction": "response",
        "operation": operation,
        "method": method,
        "url": url,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if elapsed_ms is not None:
        payload["elapsed_ms"] = round(elapsed_ms, 2)
    if error:
        payload["error"] = error
    if body is not None:
        payload["body"] = _serialize_body(body)
    logger.info("Deepgram %s", json.dumps(payload, default=str))


@contextmanager
def deepgram_http_trace(
    operation: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    content_bytes: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Log request on enter; call ctx['respond'](status, body) or ctx['fail'](error) on exit."""
    log_deepgram_request(
        operation,
        method,
        url,
        params=params,
        headers=headers,
        json_body=json_body,
        content_bytes=content_bytes,
    )
    started = time.perf_counter()
    ctx: dict[str, Any] = {}

    def respond(status_code: int, body: Any = None) -> None:
        log_deepgram_response(
            operation,
            method,
            url,
            status_code=status_code,
            body=body,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def fail(error: str, *, status_code: int | None = None, body: Any = None) -> None:
        log_deepgram_response(
            operation,
            method,
            url,
            status_code=status_code,
            body=body,
            error=error,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    ctx["respond"] = respond
    ctx["fail"] = fail
    try:
        yield ctx
    except Exception as exc:
        fail(str(exc))
        raise
