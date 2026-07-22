"""
tts.py — Text-to-Speech endpoint for KYRO.
Supports ElevenLabs and OpenAI. Falls back to 503 if keys not configured.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])

# ── Config ─────────────────────────────────────────────────────────────────────
TTS_PROVIDER          = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY", "")
TTS_MODEL             = os.getenv("TTS_MODEL", "tts-1-hd")
TTS_VOICE             = "onyx"
TTS_SPEED             = float(os.getenv("TTS_SPEED", "1.0"))

ELEVENLABS_API_KEY    = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID   = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
ELEVENLABS_MODEL_ID   = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

MAX_TEXT_LENGTH       = 4096
_CACHE_MAX            = int(os.getenv("TTS_CACHE_SIZE", "512"))

# ── In-memory cache ────────────────────────────────────────────────────────────
_tts_cache: dict[str, bytes] = {}
_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=8.0, max_retries=1)
    return _openai_client


def _cache_key(text: str, voice: str, speed: float) -> str:
    return hashlib.sha256(f"{text}|{voice}|{speed}".encode()).hexdigest()


def _store_cache(key: str, data: bytes) -> None:
    if len(_tts_cache) >= _CACHE_MAX:
        del _tts_cache[next(iter(_tts_cache))]
    _tts_cache[key] = data


# ── Schema ─────────────────────────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    voice: str | None = None
    speed: float | None = None


# ── Main endpoint ──────────────────────────────────────────────────────────────
@router.post("/speak")
async def text_to_speech(req: TTSRequest):
    """Convert text to speech. Returns audio/mpeg."""
    if TTS_PROVIDER == "elevenlabs":
        return await _elevenlabs_tts(req)
    return await _openai_tts(req)


# ── ElevenLabs ─────────────────────────────────────────────────────────────────
async def _elevenlabs_tts(req: TTSRequest) -> Response:
    api_key  = ELEVENLABS_API_KEY.strip()
    voice_id = ELEVENLABS_VOICE_ID.strip()

    if not api_key:
        raise HTTPException(503, "ElevenLabs API key not configured")
    if not voice_id:
        raise HTTPException(503, "ElevenLabs voice ID not configured")

    text = req.text.strip()
    key  = _cache_key(text, voice_id, 1.0)

    if key in _tts_cache:
        return _audio_response(_tts_cache[key], "elevenlabs", voice_id, cached=True)

    def _sync() -> bytes:
        from elevenlabs import VoiceSettings
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        gen = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=ELEVENLABS_MODEL_ID,
            voice_settings=VoiceSettings(
                stability=0.71,
                similarity_boost=0.85,
                style=0.15,
                use_speaker_boost=True,
            ),
        )
        return b"".join(gen)

    try:
        audio = await asyncio.to_thread(_sync)
    except ImportError:
        raise HTTPException(503, "elevenlabs package not installed")
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        body   = getattr(exc, "body", None)
        if status and body:
            detail = body.get("detail", body) if isinstance(body, dict) else body
            msg    = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            raise HTTPException(503, f"ElevenLabs: {msg}") from exc
        logger.error("ElevenLabs TTS failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"ElevenLabs error: {exc}") from exc

    _store_cache(key, audio)
    return _audio_response(audio, "elevenlabs", voice_id, cached=False)


# ── OpenAI ─────────────────────────────────────────────────────────────────────
async def _openai_tts(req: TTSRequest) -> Response:
    if not OPENAI_API_KEY:
        raise HTTPException(503, "OpenAI API key not configured")

    voice = "onyx"
    speed = req.speed or TTS_SPEED
    text  = req.text.strip()
    key   = _cache_key(text, voice, speed)

    if key in _tts_cache:
        return _audio_response(_tts_cache[key], "openai", voice, cached=True)

    def _sync() -> bytes:
        return _get_openai_client().audio.speech.create(
            model=TTS_MODEL, voice=voice, input=text,
            speed=speed, response_format="mp3",
        ).content

    try:
        audio = await asyncio.to_thread(_sync)
    except ImportError:
        raise HTTPException(503, "openai package not installed")
    except Exception as exc:
        logger.error("OpenAI TTS failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"TTS error: {exc}") from exc

    _store_cache(key, audio)
    return _audio_response(audio, "openai", voice, cached=False)


# ── Helper ─────────────────────────────────────────────────────────────────────
def _audio_response(data: bytes, provider: str, voice: str, *, cached: bool) -> Response:
    return Response(
        content=data,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "public, max-age=3600",
            "X-TTS-Provider": provider,
            "X-TTS-Voice": voice,
            "X-TTS-Cached": str(cached).lower(),
        },
    )
