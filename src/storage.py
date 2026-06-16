from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).parent.parent / "data"


def _date_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_dir() -> Path:
    return _ensure(_BASE / "uploads" / _date_str())


def transcript_dir() -> Path:
    return _ensure(_BASE / "transcripts" / _date_str())


def summary_dir() -> Path:
    return _ensure(_BASE / "summaries" / _date_str())


def save_upload(file_bytes: bytes, filename: str) -> Path:
    dest = upload_dir() / filename
    dest.write_bytes(file_bytes)
    return dest


def save_transcript(text: str, stem: str) -> Path:
    dest = transcript_dir() / f"{stem}_transcript.txt"
    dest.write_text(text, encoding="utf-8")
    return dest


def save_summary_md(text: str, stem: str) -> Path:
    dest = summary_dir() / f"{stem}_summary.md"
    dest.write_text(text, encoding="utf-8")
    return dest


def save_summary_txt(text: str, stem: str) -> Path:
    dest = summary_dir() / f"{stem}_summary.txt"
    dest.write_text(text, encoding="utf-8")
    return dest
