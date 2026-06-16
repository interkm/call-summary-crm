"""
Transcription:
  1. GROQ_API_KEY 있으면 → Groq Whisper API (무료, 한국어 최고)
  2. 없으면 → local faster-whisper (GPU→CPU 자동 폴백)
"""

import os
from pathlib import Path


def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, "")


def transcribe(audio_path: Path, model_size: str = "tiny") -> str:
    groq_key = _get_secret("GROQ_API_KEY")
    if groq_key:
        return _groq(audio_path, groq_key)
    return _local(audio_path, model_size)


# ── Groq Whisper API ──────────────────────────────────────────────────────────

def _groq(audio_path: Path, api_key: str) -> str:
    import requests

    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, f)},
            data={
                "model": "whisper-large-v3-turbo",
                "language": "ko",
                "response_format": "text",
            },
            timeout=120,
        )

    if not resp.ok:
        raise RuntimeError(f"Groq API 오류 {resp.status_code}: {resp.text[:300]}")
    return resp.text.strip()


# ── Local faster-whisper ──────────────────────────────────────────────────────

def _local(audio_path: Path, model_size: str) -> str:
    from faster_whisper import WhisperModel

    last_err = None
    for device, compute_type in [("cuda", "float16"), ("cpu", "int8")]:
        try:
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
            segments, _ = model.transcribe(str(audio_path), language="ko", beam_size=5)
            return "\n".join(seg.text.strip() for seg in segments if seg.text.strip())
        except Exception as e:
            last_err = e
            if device == "cuda":
                continue
    raise RuntimeError(f"로컬 전사 실패: {last_err}")
