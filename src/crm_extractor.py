"""CRM 고객정보 자동 추출 — Groq LLM 우선, 규칙 기반 폴백"""
import json
import os
import re
import requests


def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, "")


_CRM_PROMPT = """\
전사 텍스트와 요약문을 분석해서 아래 JSON 형식으로만 출력하세요.
값이 없으면 빈 문자열(""), 예/아니오로 답할 수 없으면 "미확인"으로 쓰세요.

{
  "customer_name": "고객 성함",
  "company_name": "회사명 또는 기관명",
  "phone": "전화번호",
  "region": "지역 (시/군/구 수준)",
  "facility_type": "시설유형 (공장/학교/아파트/병원/빌딩 등)",
  "consultation_purpose": "상담 목적 한 줄 요약",
  "is_urgent": "예/아니오/미확인",
  "needs_visit": "예/아니오/미확인",
  "needs_quote": "예/아니오/미확인",
  "wants_change_agency": "기존 대행업체 교체 의사 예/아니오/미확인",
  "contract_expiry": "계약 만료 시기 (예: 2024년 12월) 또는 미확인",
  "current_monthly_fee": "현재 월 대행비 (예: 30만원) 또는 미확인",
  "transformer_kva": "수전용량/변압기 kVA (예: 500kVA) 또는 미확인",
  "contract_kw": "계약전력 kW (예: 300kW) 또는 미확인",
  "has_generator": "비상발전기 유무 예/아니오/미확인",
  "solar_capacity": "태양광 용량 (예: 100kW) 또는 미확인",
  "inspection_count": "월 점검 횟수 (예: 월 1회) 또는 미확인",
  "needs_jobjosi": "직무고시 포함 여부 예/아니오/미확인",
  "needs_emergency": "비상출동 필요 여부 예/아니오/미확인"
}"""


def extract_crm_info(
    transcript: str, summary: str, groq_api_key: str = None
) -> dict:
    if not groq_api_key:
        groq_api_key = _get_secret("GROQ_API_KEY")

    combined = f"[전사 텍스트]\n{transcript}\n\n[요약문]\n{summary}"

    if groq_api_key:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": _CRM_PROMPT},
                        {"role": "user", "content": combined},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 800,
                },
                timeout=30,
            )
            if resp.ok:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    return json.loads(m.group())
        except Exception:
            pass

    return _rule_based(transcript + "\n" + summary)


_PHONE_RE = re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}")
_REGIONS = [
    "서울", "부산", "인천", "대구", "대전", "광주", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]
_FACILITIES = {
    "공장": "공장", "창고": "창고", "물류": "물류센터", "아파트": "아파트",
    "빌딩": "빌딩", "건물": "건물", "병원": "병원", "학교": "학교",
    "호텔": "호텔", "마트": "마트", "주유소": "주유소", "현장": "현장",
}


def _rule_based(text: str) -> dict:
    phone_m = _PHONE_RE.search(text)
    phone = ""
    if phone_m:
        d = re.sub(r"[^\d]", "", phone_m.group())
        phone = f"{d[:3]}-{d[3:7]}-{d[7:]}" if len(d) == 11 else phone_m.group()

    return {
        "customer_name": "",
        "company_name": "",
        "phone": phone,
        "region": next((r for r in _REGIONS if r in text), ""),
        "facility_type": next((v for k, v in _FACILITIES.items() if k in text), ""),
        "consultation_purpose": "",
        "is_urgent": "예" if any(k in text for k in ["급해", "긴급", "정전", "트립", "차단기", "누전"]) else "미확인",
        "needs_visit": "예" if any(k in text for k in ["방문", "현장 확인", "나와"]) else "미확인",
        "needs_quote": "예" if any(k in text for k in ["견적", "가격", "비용", "금액", "얼마"]) else "미확인",
        "wants_change_agency": "예" if any(k in text for k in ["바꾸", "교체", "변경", "다른 업체", "해지"]) else "미확인",
        "contract_expiry": "",
        "current_monthly_fee": "",
        "transformer_kva": "",
        "contract_kw": "",
        "has_generator": "예" if any(k in text for k in ["발전기", "비상전원"]) else "미확인",
        "solar_capacity": "",
        "inspection_count": "",
        "needs_jobjosi": "예" if "직무고시" in text else "미확인",
        "needs_emergency": "예" if any(k in text for k in ["비상출동", "출동"]) else "미확인",
    }
