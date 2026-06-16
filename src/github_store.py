"""
GitHub Gist를 이용한 일별 상담 건수 저장.
Streamlit Cloud에서 실행되는 앱이 카운터를 기록하면,
GitHub Actions에서 읽어 Telegram 다이제스트에 활용.
"""

import json
import os
import requests
from datetime import datetime

_FILENAME = "crm_daily_count.json"


def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, "")


def _is_configured() -> bool:
    return bool(_get_secret("GITHUB_TOKEN") and _get_secret("GIST_ID"))


def _headers() -> dict:
    return {
        "Authorization": f"token {_get_secret('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
    }


def _read_gist() -> dict:
    gist_id = _get_secret("GIST_ID")
    r = requests.get(
        f"https://api.github.com/gists/{gist_id}",
        headers=_headers(),
        timeout=10,
    )
    if not r.ok:
        return {}
    files = r.json().get("files", {})
    if _FILENAME not in files:
        return {}
    try:
        return json.loads(files[_FILENAME]["content"])
    except Exception:
        return {}


def _write_gist(content: dict) -> bool:
    gist_id = _get_secret("GIST_ID")
    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers=_headers(),
        json={"files": {_FILENAME: {"content": json.dumps(content, indent=2, ensure_ascii=False)}}},
        timeout=10,
    )
    return r.ok


def increment_today() -> int:
    """오늘 상담 카운트 +1 후 반환. 미설정이면 0 반환."""
    if not _is_configured():
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    data = _read_gist()
    data[today] = data.get(today, 0) + 1
    # 30일 초과 항목 정리
    keys = sorted(data.keys())
    for old in keys[:-30]:
        del data[old]
    _write_gist(data)
    return data[today]


def get_today_count() -> int:
    """오늘 상담 건수 반환."""
    if not _is_configured():
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    data = _read_gist()
    return data.get(today, 0)


def create_gist() -> str | None:
    """Private Gist 신규 생성. Gist ID 반환."""
    token = _get_secret("GITHUB_TOKEN")
    if not token:
        return None
    r = requests.post(
        "https://api.github.com/gists",
        headers=_headers(),
        json={
            "description": "CRM Daily Consultation Count",
            "public": False,
            "files": {_FILENAME: {"content": "{}"}},
        },
        timeout=10,
    )
    return r.json().get("id") if r.ok else None
