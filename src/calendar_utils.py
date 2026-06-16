"""
Google Calendar URL 생성 + 한국어 일정 감지 (OAuth 불필요).
URL 방식: 클릭 시 구글 캘린더 새 일정 폼 자동 열림.
"""

import re
from datetime import datetime, timedelta
from urllib.parse import urlencode


# ── 일정 감지 ─────────────────────────────────────────────────────────────────

_APPT_KEYWORDS = [
    "방문", "미팅", "약속", "일정", "만나", "뵙겠", "찾아뵙", "방문하겠",
    "방문할게", "오겠습니다", "가겠습니다", "연락드리겠", "전화드리겠",
    "다음주", "내일", "모레", "오전에", "오후에", "시에 뵙", "시에 방문",
]

_WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def detect_appointment(text: str) -> dict:
    """
    Returns dict:
      detected (bool), date (str|None), time (str|None), location (str|None)
    """
    has_intent = any(kw in text for kw in _APPT_KEYWORDS)
    date_str = _extract_date(text)
    time_str = _extract_time(text)
    location = _extract_location(text)

    return {
        "detected": has_intent and (date_str is not None or time_str is not None),
        "date": date_str,
        "time": time_str,
        "location": location,
    }


def _extract_date(text: str) -> str | None:
    today = datetime.now()

    if "오늘" in text:
        return today.strftime("%Y-%m-%d")
    if "모레" in text:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if "내일" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    # 다음주 N요일 / N요일
    for wd, idx in _WEEKDAYS.items():
        if f"{wd}요일" in text:
            days_ahead = (idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            base = today + timedelta(days=days_ahead)
            if "다음주" in text:
                base = base + timedelta(weeks=1)
            return base.strftime("%Y-%m-%d")

    # N월 N일
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        if month < today.month:
            year += 1
        return f"{year}-{month:02d}-{day:02d}"

    # N일 후
    m = re.search(r"(\d+)일\s*(?:후|뒤)", text)
    if m:
        return (today + timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")

    return None


def _extract_time(text: str) -> str | None:
    m = re.search(r"(오전|오후)?\s*(\d{1,2})시(?:\s*(\d{1,2})분)?", text)
    if not m:
        return None
    ampm = m.group(1)
    hour = int(m.group(2))
    minute = int(m.group(3) or 0)
    if ampm == "오후" and hour < 12:
        hour += 12
    elif ampm == "오전" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


_REGIONS = [
    "서울", "부산", "인천", "대구", "대전", "광주", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]


def _extract_location(text: str) -> str | None:
    for region in _REGIONS:
        if region in text:
            return region
    return None


# ── Google Calendar URL 생성 ──────────────────────────────────────────────────

def make_google_calendar_url(
    title: str,
    date_str: str | None,
    time_str: str | None,
    details: str = "",
    location: str = "",
) -> str:
    today = datetime.now()

    if date_str:
        base_date = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        base_date = today

    if time_str:
        h, m = map(int, time_str.split(":"))
        dt_start = base_date.replace(hour=h, minute=m, second=0, microsecond=0)
        dt_end = dt_start + timedelta(hours=1)
        start = dt_start.strftime("%Y%m%dT%H%M%S")
        end = dt_end.strftime("%Y%m%dT%H%M%S")
    else:
        # 종일 이벤트
        next_day = base_date + timedelta(days=1)
        start = base_date.strftime("%Y%m%d")
        end = next_day.strftime("%Y%m%d")

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start}/{end}",
        "details": details[:800],
    }
    if location:
        params["location"] = location

    return "https://calendar.google.com/calendar/render?" + urlencode(params)
