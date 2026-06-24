"""Speech-to-text for consultation audio — Deepgram prerecorded chunk mode only."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import struct
import subprocess
import tempfile
from typing import Any

import httpx

from app.database import get_settings

logger = logging.getLogger(__name__)

# Keep aligned with frontend MIN_TRANSCRIPT_CHUNK_BYTES / TRANSCRIPT_CHUNK_BYTES_DEFAULT in audioTracks.ts
MIN_AUDIO_BYTES = 1_400

_JUNK_PATTERNS = (
    r"thank you for watching",
    r"thanks for watching",
    r"please subscribe",
    r"\[music\]",
    r"\[silence\]",
)


def _clean_transcript(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 2:
        return ""
    lower = cleaned.lower()
    for pattern in _JUNK_PATTERNS:
        if re.search(pattern, lower):
            return ""
    return cleaned


def _normalize_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return "audio/webm"
    base = mime_type.split(";")[0].strip().lower()
    return base or "audio/webm"


def _wav_mean_volume_db(data: bytes) -> float | None:
    if len(data) < 44 or data[:4] != b"RIFF":
        return None
    try:
        bits = struct.unpack_from("<H", data, 34)[0]
        if bits != 16:
            return None
        pcm = data[44:]
        count = len(pcm) // 2
        if count == 0:
            return None
        sum_sq = 0.0
        for i in range(0, count * 2, 2):
            sample = struct.unpack_from("<h", pcm, i)[0] / 32768.0
            sum_sq += sample * sample
        rms = (sum_sq / count) ** 0.5
        if rms <= 1e-9:
            return -90.0
        return round(20.0 * math.log10(rms), 1)
    except Exception:
        return None


def _wav_header_info(data: bytes) -> dict[str, Any] | None:
    if len(data) < 44 or data[:4] != b"RIFF":
        return None
    try:
        sample_rate = struct.unpack_from("<I", data, 24)[0]
        channels = struct.unpack_from("<H", data, 22)[0]
        bits = struct.unpack_from("<H", data, 34)[0]
        data_bytes = struct.unpack_from("<I", data, 40)[0]
        samples = data_bytes // max(bits // 8, 1) // max(channels, 1)
        duration_sec = round(samples / sample_rate, 2) if sample_rate else None
        return {
            "sample_rate": sample_rate,
            "channels": channels,
            "bits": bits,
            "duration_sec": duration_sec,
        }
    except Exception:
        return None


def get_transcript_stt_config() -> dict[str, Any]:
    settings = get_settings()
    available = bool(settings.deepgram_api_key)
    config: dict[str, Any] = {
        "provider": "deepgram",
        "chunk_bytes": settings.transcript_chunk_bytes,
        "available": available,
        "model": settings.deepgram_model,
    }
    if not available:
        config["error"] = "Deepgram transcription is not configured (DEEPGRAM_API_KEY)."
    return config


async def build_transcript_stt_payload() -> dict[str, Any]:
    return get_transcript_stt_config()


def _convert_webm_to_wav_sync(data: bytes) -> bytes | None:
    ffmpeg = os.environ.get("FFMPEG_PATH", "ffmpeg")
    inp_path = ""
    out_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as inp:
            inp.write(data)
            inp_path = inp.name
        out_path = f"{inp_path}.wav"
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-fflags",
                "+genpts",
                "-i",
                inp_path,
                "-af",
                "aresample=async=1:first_pts=0",
                "-ar",
                "16000",
                "-ac",
                "1",
                out_path,
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "ffmpeg transcode failed: %s",
                result.stderr.decode("utf-8", errors="replace")[:200],
            )
            return None
        with open(out_path, "rb") as f:
            wav = f.read()
        return wav if len(wav) >= MIN_AUDIO_BYTES else None
    except FileNotFoundError:
        logger.warning("ffmpeg not installed — cannot transcode WebM")
        return None
    except Exception as exc:
        logger.warning("ffmpeg transcode error: %s", exc)
        return None
    finally:
        for path in (inp_path, out_path):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def _deepgram_listen_sync(
    data: bytes,
    content_type: str,
    model: str,
    *,
    auto_language: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    params: dict[str, str] = {
        "model": model,
        "smart_format": "true" if settings.deepgram_smart_format else "false",
        "punctuate": "true",
    }
    if not auto_language and settings.deepgram_language:
        params["language"] = settings.deepgram_language
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": content_type,
    }
    url = "https://api.deepgram.com/v1/listen"
    with httpx.Client(timeout=45.0) as client:
        response = client.post(url, params=params, content=data, headers=headers)
        body = response.json() if response.content else {}
        if not response.is_success:
            err = body.get("err_msg") or body.get("message") or response.text[:240]
            return {
                "text": "",
                "confidence": None,
                "error": f"Deepgram HTTP {response.status_code}: {err}",
                "raw_text_len": 0,
                "model": model,
            }

    metadata = body.get("metadata") or {}
    channels = body.get("channels") or []
    alternatives = (channels[0].get("alternatives") if channels else None) or []
    raw_text = alternatives[0].get("transcript") if alternatives else ""
    confidence = alternatives[0].get("confidence") if alternatives else None
    text = _clean_transcript(raw_text or "")
    return {
        "text": text,
        "confidence": confidence,
        "raw_text_len": len(raw_text or ""),
        "model": model,
        "dg_duration": metadata.get("duration"),
        "dg_channels": metadata.get("channels"),
    }


def _transcribe_groq_sync(data: bytes, mime_type: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.groq_api_key:
        return {"text": "", "confidence": None, "error": "missing_groq_key"}

    ext = "wav" if "wav" in mime_type else "webm"
    try:
        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        result = client.audio.transcriptions.create(
            file=(f"chunk.{ext}", data, mime_type),
            model="whisper-large-v3-turbo",
            language=settings.deepgram_language or "en",
            response_format="json",
            temperature=0.0,
        )
        raw_text = getattr(result, "text", "") or ""
        text = _clean_transcript(raw_text)
        return {
            "text": text,
            "confidence": None,
            "provider": "groq",
            "raw_text_len": len(raw_text),
        }
    except Exception as exc:
        logger.warning("Groq STT error: %s", exc)
        return {"text": "", "confidence": None, "error": str(exc)[:240]}


def _transcribe_deepgram_sync(
    data: bytes,
    mime_type: str | None,
    *,
    include_debug: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.deepgram_api_key:
        return {"text": "", "confidence": None, "error": "missing_deepgram_key"}

    input_mime = _normalize_mime_type(mime_type)
    content_type = input_mime
    audio = data
    debug: dict[str, Any] = {
        "input_bytes": len(data),
        "input_mime": input_mime,
        "ffmpeg_used": False,
    }

    if "webm" in content_type:
        wav = _convert_webm_to_wav_sync(data)
        if wav:
            audio = wav
            content_type = "audio/wav"
            debug["ffmpeg_used"] = True
        else:
            debug["ffmpeg_failed"] = True
            logger.warning("WebM transcode failed (%s bytes) — sending raw to Deepgram", len(data))

    debug["processed_bytes"] = len(audio)
    debug["processed_mime"] = content_type
    if content_type == "audio/wav":
        debug["mean_volume_db"] = _wav_mean_volume_db(audio)
        wav_info = _wav_header_info(audio)
        if wav_info:
            debug["wav_header"] = wav_info

    primary = settings.deepgram_model.strip() or "nova-3-medical"
    models = [primary]
    for fallback in ("nova-3", "nova-2"):
        if fallback not in models:
            models.append(fallback)

    last_error: str | None = None
    attempts: list[dict[str, Any]] = []
    for idx, model in enumerate(models):
        auto_language = idx == len(models) - 1
        result = _deepgram_listen_sync(audio, content_type, model, auto_language=auto_language)
        attempts.append(
            {
                "model": model,
                "raw_text_len": result.get("raw_text_len", 0),
                "text_len": len(result.get("text") or ""),
                "error": result.get("error"),
                "dg_duration": result.get("dg_duration"),
                "dg_channels": result.get("dg_channels"),
                "language": "auto" if auto_language else settings.deepgram_language,
            }
        )
        if result.get("text"):
            logger.info(
                "Deepgram STT model=%s mime=%s bytes=%s text_len=%s",
                model,
                content_type,
                len(audio),
                len(result["text"]),
            )
            out = {k: v for k, v in result.items() if k not in ("raw_text_len", "model", "dg_duration", "dg_channels")}
            if include_debug:
                debug["attempts"] = attempts
                out["debug"] = debug
            return out
        if result.get("error"):
            last_error = str(result["error"])
            break

    if include_debug:
        debug["attempts"] = attempts

    if last_error:
        logger.warning("Deepgram STT error: %s", last_error)
        out: dict[str, Any] = {"text": "", "confidence": None, "error": last_error}
        if include_debug:
            out["debug"] = debug
        return out

    vol = debug.get("mean_volume_db")
    if vol is not None and vol > -45:
        groq_result = _transcribe_groq_sync(audio, content_type)
        if include_debug:
            debug["groq_attempt"] = {
                "raw_text_len": groq_result.get("raw_text_len", 0),
                "text_len": len(groq_result.get("text") or ""),
                "error": groq_result.get("error"),
            }
        if groq_result.get("text"):
            logger.info(
                "Groq STT fallback mime=%s bytes=%s text_len=%s",
                content_type,
                len(audio),
                len(groq_result["text"]),
            )
            out = {
                "text": groq_result["text"],
                "confidence": groq_result.get("confidence"),
                "provider": "groq",
            }
            if include_debug:
                debug["groq_fallback"] = True
                out["debug"] = debug
            return out

    logger.info("Deepgram STT no speech mime=%s bytes=%s vol=%s", content_type, len(audio), debug.get("mean_volume_db"))
    out = {"text": "", "confidence": None}
    if include_debug:
        out["debug"] = debug
    return out


async def transcribe_audio_chunk(
    data: bytes,
    *,
    filename: str = "chunk.webm",
    mime_type: str | None = "audio/webm",
    include_debug: bool = False,
) -> dict[str, Any]:
    """Transcribe a short audio chunk. Returns { text, confidence, error?, debug? }."""
    del filename
    if not data or len(data) < MIN_AUDIO_BYTES:
        return {"text": "", "confidence": None}

    return await asyncio.to_thread(
        _transcribe_deepgram_sync,
        data,
        mime_type,
        include_debug=include_debug,
    )
