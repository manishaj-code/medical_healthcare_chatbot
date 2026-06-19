"""Speech-to-text for consultation audio — Groq Whisper or Deepgram (chunk / live)."""
from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from typing import Any, Literal

import httpx

from app.database import get_settings
from app.services.deepgram_log import log_deepgram_request, log_deepgram_response

logger = logging.getLogger(__name__)

SttProvider = Literal["groq", "deepgram", "deepgram_live"]

MIN_AUDIO_BYTES = 1_500
WHISPER_PROMPT = (
    "Medical video consultation between a doctor and a patient. "
    "Symptoms, diagnosis, treatment, medications, and follow-up."
)

_JUNK_PATTERNS = (
    r"thank you for watching",
    r"thanks for watching",
    r"please subscribe",
    r"\[music\]",
    r"\[silence\]",
    r"^\s*\.\.\.\s*$",
    r"^you\s*$",
    r"^bye[\s!.]*$",
)


def _normalize_provider(value: str) -> SttProvider:
    normalized = (value or "groq").strip().lower()
    if normalized in ("deepgram", "deepgram_live"):
        return normalized  # type: ignore[return-value]
    return "groq"


def _clean_transcript(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 2:
        return ""
    lower = cleaned.lower()
    for pattern in _JUNK_PATTERNS:
        if re.search(pattern, lower):
            return ""
    return cleaned


def _provider_available(provider: SttProvider) -> bool:
    settings = get_settings()
    if provider == "groq":
        return bool(settings.groq_api_key)
    return bool(settings.deepgram_api_key)


def get_transcript_stt_config() -> dict[str, Any]:
    """STT settings exposed to the doctor client on transcript start."""
    settings = get_settings()
    provider = _normalize_provider(settings.transcript_stt_provider)
    chunk_ms = settings.transcript_chunk_ms
    if provider == "groq":
        chunk_ms = max(chunk_ms, 8_000)

    config: dict[str, Any] = {
        "provider": provider,
        "chunk_interval_ms": chunk_ms,
        "available": _provider_available(provider),
        "model": settings.deepgram_model if provider != "groq" else "whisper-large-v3",
        "deepgram_log_requests": settings.deepgram_log_requests,
    }

    if provider == "deepgram_live":
        config["deepgram"] = {
            "model": settings.deepgram_model,
            "language": settings.deepgram_language,
            "smart_format": settings.deepgram_smart_format,
            "interim_results": settings.deepgram_interim_results,
        }
    return config


async def create_deepgram_access_token(*, ttl_seconds: int | None = None) -> dict[str, str] | None:
    """Ephemeral browser credential for Deepgram live (grant token or temporary API key)."""
    settings = get_settings()
    if not settings.deepgram_api_key:
        return None

    ttl = ttl_seconds or settings.deepgram_token_ttl_seconds
    headers = {"Authorization": f"Token {settings.deepgram_api_key}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        grant_url = "https://api.deepgram.com/v1/auth/grant"
        grant_body = {"ttl_seconds": ttl}
        try:
            log_deepgram_request(
                "auth_grant",
                "POST",
                grant_url,
                headers=headers,
                json_body=grant_body,
            )
            started = time.perf_counter()
            response = await client.post(grant_url, headers=headers, json=grant_body)
            elapsed_ms = (time.perf_counter() - started) * 1000
            response_body = response.json() if response.content else {}
            if response.is_success:
                log_deepgram_response(
                    "auth_grant",
                    "POST",
                    grant_url,
                    status_code=response.status_code,
                    body={**response_body, "access_token": "[REDACTED]" if response_body.get("access_token") else None},
                    elapsed_ms=elapsed_ms,
                )
            else:
                log_deepgram_response(
                    "auth_grant",
                    "POST",
                    grant_url,
                    status_code=response.status_code,
                    body=response_body,
                    elapsed_ms=elapsed_ms,
                    error=response.text[:500] if response.text else "HTTP error",
                )
            response.raise_for_status()
            token = response_body.get("access_token")
            if token:
                return {"token": str(token), "token_type": "access_token"}
        except Exception as exc:
            log_deepgram_response(
                "auth_grant",
                "POST",
                grant_url,
                error=str(exc),
            )
            logger.warning("Deepgram auth/grant failed, trying temporary project key: %s", exc)

        try:
            project_id = settings.deepgram_project_id.strip() if settings.deepgram_project_id else ""
            if not project_id:
                projects_url = "https://api.deepgram.com/v1/projects"
                log_deepgram_request("list_projects", "GET", projects_url, headers=headers)
                started = time.perf_counter()
                projects_response = await client.get(projects_url, headers=headers)
                elapsed_ms = (time.perf_counter() - started) * 1000
                projects_body = projects_response.json() if projects_response.content else {}
                log_deepgram_response(
                    "list_projects",
                    "GET",
                    projects_url,
                    status_code=projects_response.status_code,
                    body=projects_body,
                    elapsed_ms=elapsed_ms,
                    error=None if projects_response.is_success else projects_response.text[:500],
                )
                projects_response.raise_for_status()
                projects = projects_body.get("projects") or []
                project_id = projects[0]["project_id"] if projects else ""

            if not project_id:
                return None

            keys_url = f"https://api.deepgram.com/v1/projects/{project_id}/keys"
            keys_body = {
                "comment": "consultation-live-transcript",
                "scopes": ["usage:write"],
                "time_to_live_in_seconds": ttl,
            }
            log_deepgram_request(
                "create_temp_key",
                "POST",
                keys_url,
                headers={**headers, "Content-Type": "application/json"},
                json_body=keys_body,
            )
            started = time.perf_counter()
            key_response = await client.post(
                keys_url,
                headers={**headers, "Content-Type": "application/json"},
                json=keys_body,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            body = key_response.json() if key_response.content else {}
            redacted_body = {**body}
            for secret_field in ("key", "api_key"):
                if redacted_body.get(secret_field):
                    redacted_body[secret_field] = "[REDACTED]"
            log_deepgram_response(
                "create_temp_key",
                "POST",
                keys_url,
                status_code=key_response.status_code,
                body=redacted_body,
                elapsed_ms=elapsed_ms,
                error=None if key_response.is_success else key_response.text[:500],
            )
            key_response.raise_for_status()
            token = body.get("key") or body.get("api_key")
            if token:
                return {"token": str(token), "token_type": "api_key"}
        except Exception as exc:
            log_deepgram_response(
                "create_temp_key",
                "POST",
                f"https://api.deepgram.com/v1/projects/{project_id or 'unknown'}/keys",
                error=str(exc),
            )
            logger.warning("Deepgram temporary key creation failed: %s", exc)
            return None

    return None


async def build_transcript_stt_payload() -> dict[str, Any]:
    """Full STT payload for transcript/start (includes ephemeral Deepgram token when needed)."""
    config = get_transcript_stt_config()
    provider = config["provider"]

    if provider == "deepgram_live":
        credential = await create_deepgram_access_token()
        if credential and credential["token_type"] == "api_key":
            config["available"] = True
            config.setdefault("deepgram", {})
            config["deepgram"]["token"] = credential["token"]
            config["deepgram"]["token_type"] = "api_key"
        else:
            # JWT grant tokens need Bearer auth; @deepgram/sdk v3 in the browser only supports API keys.
            # Server-side chunk transcription works with the same Deepgram project key.
            config["provider"] = "deepgram"
            config["available"] = _provider_available("deepgram")
            config["fallback_from"] = "deepgram_live"
            if config.get("deepgram"):
                config["deepgram"].pop("token", None)
                config["deepgram"].pop("token_type", None)
            config["warning"] = (
                "Deepgram live in the browser needs a temporary API key. "
                "Using Deepgram chunk mode — speak for ~6s to see transcript lines."
            )
            if not config["available"]:
                config["error"] = "Deepgram transcription is not configured (DEEPGRAM_API_KEY)."

    if not config.get("available") and provider == "groq":
        config["error"] = "Groq transcription is not configured (GROQ_API_KEY)."
    elif not config.get("available") and provider == "deepgram":
        config["error"] = "Deepgram transcription is not configured (DEEPGRAM_API_KEY)."

    return config


def _transcribe_groq_sync(data: bytes, filename: str) -> dict:
    settings = get_settings()
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    file_obj = io.BytesIO(data)
    result = client.audio.transcriptions.create(
        file=(filename or "chunk.webm", file_obj.read()),
        model="whisper-large-v3",
        language="en",
        temperature=0,
        prompt=WHISPER_PROMPT,
        response_format="verbose_json",
    )
    text = _clean_transcript(getattr(result, "text", None) or "")
    return {"text": text, "confidence": 0.9 if text else None}


def _transcribe_deepgram_sync(data: bytes, mime_type: str | None) -> dict:
    settings = get_settings()
    models = [settings.deepgram_model]
    if settings.deepgram_model != "nova-3":
        models.append("nova-3")

    last_error: Exception | None = None
    listen_url = "https://api.deepgram.com/v1/listen"
    for model in models:
        params = {
            "model": model,
            "language": settings.deepgram_language,
            "smart_format": "true" if settings.deepgram_smart_format else "false",
            "punctuate": "true",
        }
        headers = {
            "Authorization": f"Token {settings.deepgram_api_key}",
            "Content-Type": mime_type or "audio/webm",
        }
        log_deepgram_request(
            "listen_prerecorded",
            "POST",
            listen_url,
            params=params,
            headers=headers,
            content_bytes=len(data),
        )
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=45.0) as client:
                response = client.post(
                    listen_url,
                    params=params,
                    content=data,
                    headers=headers,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                body = response.json() if response.content else {}
                if not response.is_success:
                    log_deepgram_response(
                        "listen_prerecorded",
                        "POST",
                        listen_url,
                        status_code=response.status_code,
                        body=body,
                        elapsed_ms=elapsed_ms,
                        error=response.text[:500] if response.text else "HTTP error",
                    )
                response.raise_for_status()
                log_deepgram_response(
                    "listen_prerecorded",
                    "POST",
                    listen_url,
                    status_code=response.status_code,
                    body=body,
                    elapsed_ms=elapsed_ms,
                )
        except Exception as exc:
            last_error = exc
            log_deepgram_response(
                "listen_prerecorded",
                "POST",
                listen_url,
                error=str(exc),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            logger.warning("Deepgram STT failed (model=%s, %s bytes): %s", model, len(data), exc)
            continue

        channels = body.get("channels") or []
        alternatives = (channels[0].get("alternatives") if channels else None) or []
        raw_text = alternatives[0].get("transcript") if alternatives else ""
        confidence = alternatives[0].get("confidence") if alternatives else None
        text = _clean_transcript(raw_text or "")
        logger.debug(
            "Deepgram STT model=%s bytes=%s raw=%r cleaned=%r",
            model,
            len(data),
            (raw_text or "")[:120],
            (text or "")[:120],
        )
        if text:
            return {"text": text, "confidence": confidence}
        # Empty transcript — try next model in list
        continue

    if last_error:
        raise last_error
    return {"text": "", "confidence": None}


async def transcribe_audio_chunk(
    data: bytes,
    *,
    filename: str = "chunk.webm",
    mime_type: str | None = "audio/webm",
) -> dict:
    """
    Transcribe a short audio chunk using the configured STT provider.
    Returns { text, confidence } — text may be empty if STT unavailable or silent audio.
    """
    if not data or len(data) < MIN_AUDIO_BYTES:
        return {"text": "", "confidence": None}

    settings = get_settings()
    provider = _normalize_provider(settings.transcript_stt_provider)

    if provider in ("deepgram", "deepgram_live"):
        if not settings.deepgram_api_key:
            return {"text": "", "confidence": None}
        try:
            result = await asyncio.to_thread(_transcribe_deepgram_sync, data, mime_type)
            if result.get("text") or not settings.groq_api_key:
                return result
            logger.info("Deepgram returned no speech (%s bytes), trying Groq Whisper", len(data))
        except Exception as exc:
            logger.warning("Deepgram STT failed (%s bytes): %s", len(data), exc)
            if not settings.groq_api_key:
                return {"text": "", "confidence": None}

    if not settings.groq_api_key:
        return {"text": "", "confidence": None}
    try:
        return await asyncio.to_thread(_transcribe_groq_sync, data, filename)
    except Exception as exc:
        logger.warning("Groq STT failed (%s bytes): %s", len(data), exc)
        return {"text": "", "confidence": None}
