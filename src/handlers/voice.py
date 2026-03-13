"""
Voice transcription handler using OpenAI Whisper API
Accepts base64-encoded audio and returns transcribed text.
"""

import json
import uuid
import base64
import tempfile
import os
from typing import Dict, Any

from utils.http import respond, get_user_id
from utils.timestamps import utc_now
from lib.auth_provider import require_auth
from lib.logger import logger
from lib.model_manager import get_model_manager
from openai import OpenAI


def _get_openai_client():
    """Get OpenAI client for Whisper"""
    manager = get_model_manager()
    api_key = manager.get_api_key("openai")
    return OpenAI(api_key=api_key, timeout=60.0, max_retries=2)


@require_auth
def transcribe(event, context):
    """
    POST /v1/voice/transcribe - Transcribe audio using OpenAI Whisper

    Body: { "audio": "<base64 encoded audio>", "format": "webm" }
    Returns: { "text": "transcribed text", "duration": 3.2 }
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        return respond(400, {"error": "Invalid JSON"})

    audio_b64 = body.get('audio', '')
    audio_format = body.get('format', 'webm')

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

    # Write to temp file (Whisper API needs a file)
    ext = audio_format if audio_format in ('webm', 'mp3', 'mp4', 'wav', 'ogg', 'm4a') else 'webm'
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        client = _get_openai_client()

        with open(tmp_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"
            )

        text = transcription.text.strip()
        duration = getattr(transcription, 'duration', 0) or 0

        logger.info(f"Whisper transcription for user {user_id}: {len(text)} chars, {duration:.1f}s audio")

        # Log cost (~$0.006/min for Whisper)
        try:
            cost = (duration / 60) * 0.006
            db.write("app_api_costs", [{
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "function_name": "voice_transcribe",
                "category": "voice",
                "model_used": json.dumps({"analyzer": "whisper-1"}),
                "total_tokens": 0,
                "cost_usd": round(cost, 6),
                "created_at": utc_now()
            }])
        except Exception as e:
            logger.warning(f"Failed to log voice cost: {e}")

        return respond(200, {
            "text": text,
            "duration": round(duration, 1),
        })

    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return respond(500, {"error": f"Transcription failed: {str(e)}"})

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
