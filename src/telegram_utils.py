"""
Telegram Bot API wrapper.
Works in both Streamlit context (st.secrets) and standalone (os.environ).
"""

import html
import os
import requests
from datetime import datetime


def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, "")


def is_configured() -> bool:
    return bool(_get_secret("TELEGRAM_BOT_TOKEN") and _get_secret("TELEGRAM_CHAT_ID"))


def send(text: str) -> bool:
    token = _get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = _get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.ok
    except Exception:
        return False


def consultation_msg(filename: str, summary: str, ts: datetime | None = None) -> str:
    ts_str = (ts or datetime.now()).strftime("%Y-%m-%d %H:%M")
    body = html.escape(summary[:3500]) + ("..." if len(summary) > 3500 else "")
    return (
        f"📞 <b>새 상담 요약</b>\n"
        f"🕐 {ts_str}\n"
        f"📁 {html.escape(filename)}\n"
        f"{'─' * 30}\n"
        f"{body}"
    )


def digest_msg(count: int, period: str, date_str: str) -> str:
    if count == 0:
        body = "오늘은 아직 등록된 상담 기록이 없습니다."
    else:
        body = (
            f"✅ 오늘 총 <b>{count}건</b> 상담 완료\n"
            f"위 채팅에서 각 상담 요약을 확인하세요."
        )
    return (
        f"⏰ <b>{period} 체크인</b>\n"
        f"📅 {date_str}\n"
        f"{'─' * 30}\n"
        f"{body}"
    )
