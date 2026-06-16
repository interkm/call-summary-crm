"""
Daily Telegram digest.
Run by GitHub Actions 5x daily or locally via Windows Task Scheduler.

Usage:
  python scripts/digest.py

Env vars required:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  GITHUB_TOKEN  (optional, for Gist count)
  GIST_ID       (optional)
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.telegram_utils import is_configured, send, digest_msg
from src.github_store import get_today_count

_KST_PERIODS = {
    6:  "🌅 아침 6시",
    11: "🍱 점심 11시",
    15: "☀️ 오후 3시",
    18: "🌆 저녁 6시",
    22: "🌙 밤 10시",
}


def _kst_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=9)


def main():
    if not is_configured():
        print("[digest] TELEGRAM 미설정 — 종료")
        sys.exit(0)

    kst = _kst_now()
    kst_hour = kst.hour
    period = _KST_PERIODS.get(kst_hour, f"{kst_hour}시 체크인")
    date_str = kst.strftime("%Y년 %m월 %d일 (%a)")

    count = get_today_count()
    msg = digest_msg(count, period, date_str)
    ok = send(msg)
    print(f"[digest] {period} | 상담 {count}건 | 전송: {'✓' if ok else '✗'}")


if __name__ == "__main__":
    main()
