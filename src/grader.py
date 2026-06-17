"""상담등급 자동 분류 A/B/C/D"""

_A_KW = [
    "업체 바꾸", "바꾸려고", "계약 끝", "계약 만료", "견적", "방문",
    "급해", "급합", "차단기", "정전", "지적", "대행 교체",
    "직무고시", "선임", "대행", "교체", "해지", "트립", "누전",
]
_C_KW = ["그냥", "한번", "물어보", "궁금", "참고"]

GRADE_COLOR = {
    "A": "#C62828",
    "B": "#E65100",
    "C": "#1565C0",
    "D": "#546E7A",
}
GRADE_DESC = {
    "A": "즉시 견적·방문·계약 가능",
    "B": "추가 정보 확인 후 견적",
    "C": "단순 문의 / 정보 탐색",
    "D": "장기 관리 / 홍보 대상",
}


def grade_consultation(transcript: str, crm_info: dict) -> tuple:
    """Returns (grade: str, reason: str)"""
    text = transcript

    a_hits = [kw for kw in _A_KW if kw in text]
    is_urgent = crm_info.get("is_urgent") == "예"
    needs_quote = crm_info.get("needs_quote") == "예"
    needs_visit = crm_info.get("needs_visit") == "예"
    wants_change = crm_info.get("wants_change_agency") == "예"

    score = (
        len(a_hits)
        + (2 if is_urgent else 0)
        + (2 if wants_change else 0)
        + (1 if needs_quote else 0)
    )

    if score >= 3 or (is_urgent and needs_quote) or wants_change:
        grade = "A"
        reason = (
            f"즉시 계약 가능성 높음 — "
            f"키워드: {', '.join(a_hits[:3]) or '없음'} | "
            f"긴급:{is_urgent} | 교체의사:{wants_change}"
        )
    elif score >= 1 or needs_quote or needs_visit:
        grade = "B"
        reason = (
            f"추가 확인 후 견적 가능 — "
            f"키워드: {', '.join(a_hits[:2]) or '없음'} | "
            f"견적:{needs_quote} | 방문:{needs_visit}"
        )
    elif any(kw in text for kw in _C_KW):
        grade = "C"
        reason = "단순 문의 / 정보 탐색"
    else:
        grade = "D"
        reason = "장기 관리 또는 홍보 대상"

    return grade, reason
