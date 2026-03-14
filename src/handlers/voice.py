"""
Voice handler supporting:
  - STT: OpenAI Whisper + Sarvam AI Saaras (speech-to-text)
  - TTS: Sarvam AI Bulbul (text-to-speech)
"""

import json
import uuid
import base64
import tempfile
import os
from typing import Dict, Any

import requests as http_requests
from utils.http import respond, get_user_id
from utils.timestamps import utc_now
from lib.auth_provider import require_auth
from lib.logger import logger
from lib.model_manager import get_model_manager
from openai import OpenAI


def _get_sarvam_config():
    """Get Sarvam AI config from model_manager (DB-driven, env: SARVAM_API_KEY)"""
    manager = get_model_manager()
    api_key = manager.get_api_key("sarvam")
    if not api_key:
        raise Exception("SARVAM_API_KEY not configured. Set it as an environment variable.")
    stt_config = manager.get_model_config("voice_stt")
    tts_config = manager.get_model_config("voice_tts")
    return {
        "api_key": api_key,
        "stt_model": stt_config.model_name,  # e.g. "saaras:v3"
        "tts_model": tts_config.model_name,  # e.g. "bulbul:v3"
        "stt_url": f"{stt_config.base_url}/speech-to-text",
        "tts_url": f"{tts_config.base_url}/text-to-speech",
    }


def _get_openai_client():
    """Get OpenAI client for Whisper"""
    manager = get_model_manager()
    api_key = manager.get_api_key("openai")
    return OpenAI(api_key=api_key, timeout=60.0, max_retries=2)


def _transcribe_whisper(tmp_path: str) -> Dict[str, Any]:
    """Transcribe using OpenAI Whisper"""
    client = _get_openai_client()

    # Whisper requires a recognized extension. If the file has an unrecognized extension,
    # rename it to .webm (the most common browser recording format).
    import shutil
    ext = os.path.splitext(tmp_path)[1].lower()
    valid_exts = {'.flac', '.m4a', '.mp3', '.mp4', '.mpeg', '.mpga', '.oga', '.ogg', '.wav', '.webm'}
    if ext not in valid_exts:
        new_path = tmp_path + '.webm'
        shutil.copy2(tmp_path, new_path)
        tmp_path = new_path

    with open(tmp_path, 'rb') as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json"
        )

    text = transcription.text.strip()
    duration = getattr(transcription, 'duration', 0) or 0

    return {
        "text": text,
        "duration": duration,
        "engine": "whisper",
        "model": "whisper-1",
        "cost": (duration / 60) * 0.006  # ~$0.006/min
    }


def _transcribe_sarvam(tmp_path: str, language_code: str = "unknown") -> Dict[str, Any]:
    """Transcribe using Sarvam AI Saaras model (REST API, config from DB/model_manager)"""
    cfg = _get_sarvam_config()

    headers = {
        "api-subscription-key": cfg["api_key"],
        "Accept": "application/json"
    }

    filename = os.path.basename(tmp_path)
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'webm'
    mime_map = {
        'webm': 'audio/webm', 'mp3': 'audio/mpeg', 'mp4': 'audio/mp4',
        'wav': 'audio/wav', 'ogg': 'audio/ogg', 'm4a': 'audio/mp4'
    }
    mime = mime_map.get(ext, 'audio/webm')

    with open(tmp_path, 'rb') as f:
        files = {"file": (f"audio.{ext}", f, mime)}
        data = {
            "model": cfg["stt_model"],
            "language_code": language_code,
            "with_timestamps": "false"
        }

        response = http_requests.post(
            cfg["stt_url"], headers=headers, files=files, data=data,
            timeout=60
        )

    if response.status_code not in (200, 201):
        raise Exception(f"Sarvam API error {response.status_code}: {response.text[:200]}")

    result = response.json()
    text = result.get("transcript", "").strip()

    if not text:
        raise Exception("Sarvam returned empty transcript")

    return {
        "text": text,
        "duration": 0,
        "engine": "sarvam",
        "model": cfg["stt_model"],
        "cost": 0.0
    }


@require_auth
def transcribe(event, context):
    """
    POST /v1/voice/transcribe - Transcribe audio

    Body: {
        "audio": "<base64 encoded audio>",
        "format": "webm",
        "engine": "whisper" | "sarvam" (default: "whisper"),
        "language": "unknown" (for sarvam language_code)
    }
    Returns: { "text": "transcribed text", "duration": 3.2, "engine": "whisper" }
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        return respond(400, {"error": "Invalid JSON"})

    audio_b64 = body.get('audio', '')
    audio_format = body.get('format', 'webm')
    engine = body.get('engine', 'whisper')  # "whisper" or "sarvam"
    language = body.get('language', 'unknown')

    if not audio_b64:
        return respond(400, {"error": "Missing 'audio' field (base64 encoded)"})

    # Decode base64 audio
    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return respond(400, {"error": "Invalid base64 audio data"})

    if len(audio_bytes) < 100:
        return respond(400, {"error": "Audio too short"})

    # 10MB limit
    if len(audio_bytes) > 10 * 1024 * 1024:
        return respond(400, {"error": "Audio too large (max 10MB)"})

    # Write to temp file
    ext = audio_format if audio_format in ('webm', 'mp3', 'mp4', 'wav', 'ogg', 'm4a') else 'webm'
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Transcribe with selected engine, fallback to other on failure
        result = None
        fallback_used = False

        if engine == "sarvam":
            try:
                result = _transcribe_sarvam(tmp_path, language)
            except Exception as e:
                logger.warning(f"Sarvam transcription failed, falling back to Whisper: {e}")
                result = _transcribe_whisper(tmp_path)
                fallback_used = True
        else:
            try:
                result = _transcribe_whisper(tmp_path)
            except Exception as e:
                logger.warning(f"Whisper transcription failed, falling back to Sarvam: {e}")
                result = _transcribe_sarvam(tmp_path, language)
                fallback_used = True

        text = result["text"]
        duration = result["duration"]
        used_engine = result["engine"]

        logger.info(
            f"Voice transcription for user {user_id}: {len(text)} chars, "
            f"{duration:.1f}s audio, engine={used_engine}"
            f"{' (fallback)' if fallback_used else ''}"
        )

        # Log cost
        try:
            db.write("app_api_costs", [{
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "function_name": "voice_transcribe",
                "category": "voice",
                "model_used": json.dumps({"analyzer": f"{used_engine}-{result.get('model', 'whisper-1')}"}),
                "total_tokens": 0,
                "cost_usd": round(result.get("cost", 0), 6),
                "created_at": utc_now()
            }])
        except Exception as e:
            logger.warning(f"Failed to log voice cost: {e}")

        return respond(200, {
            "text": text,
            "duration": round(duration, 1),
            "engine": used_engine,
        })

    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        return respond(500, {"error": f"Transcription failed: {str(e)}"})

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Text-to-Speech ──────────────────────────────────────────────


@require_auth
def text_to_speech(event, context):
    """
    POST /v1/voice/tts - Convert text to speech using Sarvam AI Bulbul

    Body: {
        "text": "Hello, how are you?",
        "language": "en-IN",
        "speaker": "anushka"
    }
    Returns: { "audio": "<base64 wav>", "format": "wav" }
    """
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        return respond(400, {"error": "Invalid JSON"})

    text = body.get('text', '').strip()
    language = body.get('language', 'en-IN')
    speaker = body.get('speaker', 'anushka')

    if not text:
        return respond(400, {"error": "Missing 'text' field"})

    if len(text) > 2500:
        return respond(400, {"error": "Text too long (max 2500 chars for bulbul:v3)"})

    try:
        cfg = _get_sarvam_config()

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-subscription-key": cfg["api_key"],
        }

        payload = {
            "text": text,
            "target_language_code": language,
            "speaker": speaker,
            "model": cfg["tts_model"],
            "pace": body.get("pace", 1.0),
            "temperature": body.get("temperature", 0.6),
            "speech_sample_rate": 24000,
            "output_audio_codec": "mp3",
        }

        response = http_requests.post(
            cfg["tts_url"], json=payload, headers=headers, timeout=30
        )

        if response.status_code not in (200, 201):
            raise Exception(f"Sarvam TTS error {response.status_code}: {response.text[:200]}")

        result = response.json()
        audios = result.get("audios", [])

        if not audios:
            raise Exception("Sarvam TTS returned no audio")

        logger.info(f"TTS for user {user_id}: {len(text)} chars, lang={language}, speaker={speaker}, model={cfg['tts_model']}")

        return respond(200, {
            "audio": audios[0],  # base64-encoded audio
            "format": "mp3",
            "engine": "sarvam",
            "model": cfg["tts_model"],
        })

    except Exception as e:
        logger.error(f"TTS error: {e}")
        return respond(500, {"error": f"Text-to-speech failed: {str(e)}"})
