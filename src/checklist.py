"""전기안전관리 견적 체크리스트"""

# (표시명, crm_info 키)
_ITEMS = [
    ("수전용량 (변압기 kVA)", "transformer_kva"),
    ("계약전력 (한전 kW)", "contract_kw"),
    ("비상발전기 유무", "has_generator"),
    ("태양광 용량", "solar_capacity"),
    ("시설유형", "facility_type"),
    ("지역", "region"),
    ("직무고시 포함 여부", "needs_jobjosi"),
    ("월 점검 횟수", "inspection_count"),
    ("비상출동 필요 여부", "needs_emergency"),
    ("기존 대행비", "current_monthly_fee"),
    ("계약 만료일", "contract_expiry"),
    ("긴급 점검 여부", "is_urgent"),
]

_DEFINITIVE = {"예", "아니오"}


def evaluate_checklist(crm_info: dict) -> list:
    """
    Returns list of dicts:
      {item: str, status: "confirmed"|"missing", value: str}
    """
    results = []
    for label, key in _ITEMS:
        val = crm_info.get(key, "")
        if val and val != "미확인":
            status = "confirmed"
        else:
            status = "missing"
        results.append({"item": label, "status": status, "value": val or ""})
    return results


def checklist_score(checklist: list) -> tuple:
    """Returns (confirmed_count, missing_count)"""
    confirmed = sum(1 for c in checklist if c["status"] == "confirmed")
    missing = len(checklist) - confirmed
    return confirmed, missing
