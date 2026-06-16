from pathlib import Path


def transcribe(audio_path: Path, model_size: str = "small") -> str:
    from faster_whisper import WhisperModel

    model = _load_model(model_size)
    segments, _ = model.transcribe(str(audio_path), language="ko", beam_size=5)
    return "\n".join(seg.text.strip() for seg in segments if seg.text.strip())


def _load_model(model_size: str):
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception:
        return WhisperModel(model_size, device="cpu", compute_type="int8")
