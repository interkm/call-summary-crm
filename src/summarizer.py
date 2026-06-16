"""
Summarizer: rule-based (기본) + OpenRouter API (선택).
method="rule"        → 규칙 기반 (무료, 오프라인)
method="openrouter"  → OpenRouter API (OPENROUTER_API_KEY 필요)
"""

import re
import os


# ── Secret helper ─────────────────────────────────────────────────────────────

def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, "")


# ── Public interface ──────────────────────────────────────────────────────────

def summarize(
    transcript: str,
    method: str = "rule",
    model: str = "llama-3.3-70b-versatile",
) -> str:
    if method == "groq":
        return _groq_llm(transcript, model)
    if method == "openrouter":
        return _openrouter(transcript, model)
    return _rule_based(transcript)


# ── Groq LLM (무료) ──────────────────────────────────────────────────────────

def _groq_llm(transcript: str, model: str) -> str:
    import requests
    try:
        from src.prompts import OPENROUTER_SYSTEM_PROMPT
    except ImportError:
        from .prompts import OPENROUTER_SYSTEM_PROMPT

    api_key = _get_secret("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 설정되지 않았습니다. Streamlit Secrets에 추가하세요.")

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": OPENROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"[통화 전사 텍스트]\n\n{transcript}"},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        },
        timeout=60,
    )

    if not resp.ok:
        raise RuntimeError(f"Groq LLM 오류 {resp.status_code}: {resp.text[:300]}")

    return resp.json()["choices"][0]["message"]["content"].strip()


# ── OpenRouter API ────────────────────────────────────────────────────────────

def _openrouter(transcript: str, model: str) -> str:
    import requests
    try:
        from src.prompts import OPENROUTER_SYSTEM_PROMPT
    except ImportError:
        from .prompts import OPENROUTER_SYSTEM_PROMPT

    api_key = _get_secret("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다. Streamlit Secrets에 추가하세요.")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://call-summary-crm.streamlit.app",
            "X-Title": "Call Summary CRM",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": OPENROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"[통화 전사 텍스트]\n\n{transcript}"},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        },
        timeout=60,
    )

    if not resp.ok:
        raise RuntimeError(f"OpenRouter 오류 {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return content.strip()


# ── Rule-based (fallback) ─────────────────────────────────────────────────────

_REGIONS = [
    "서울", "부산", "인천", "대구", "대전", "광주", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]
_FACILITIES = {
    "공장": "공장", "창고": "창고", "물류": "물류센터", "아파트": "아파트",
    "빌딩": "빌딩", "건물": "건물", "병원": "병원", "학교": "학교",
    "호텔": "호텔", "마트": "마트", "주유소": "주유소", "사업장": "사업장", "현장": "현장",
}
_CAP_RE = re.compile(r"(\d[\d,]*)\s*(kw|kva|킬로와트|킬로볼트)", re.IGNORECASE)
_TRANS_RE = re.compile(r"변압기.{0,15}?(\d[\d,]*)\s*(kva|kw)", re.IGNORECASE)
_GEN_KWS = ["비상발전기", "발전기", "비상전원"]
_SOLAR_KWS = ["태양광", "솔라", "ess", "ESS"]
_PROB_KWS = ["문제", "고장", "오류", "경보", "트립", "정전", "누전", "이상", "불량", "점검"]
_REQ_KWS = ["요청", "부탁", "원합니다", "해주세요", "문의", "견적", "방문", "계약"]


def _extract(text, keywords, limit=3):
    sentences = re.split(r"[.。\n]", text)
    found = [s.strip() for s in sentences if any(kw in s for kw in keywords) and s.strip()]
    return ("\n- ".join(found[:limit])) if found else "미확인"


def _rule_based(transcript: str) -> str:
    region = next((r for r in _REGIONS if r in transcript), "미확인")
    facility = next((v for k, v in _FACILITIES.items() if k in transcript), "미확인")
    m = _CAP_RE.search(transcript)
    capacity = f"{m.group(1)} {m.group(2).upper()}" if m else "미확인"
    m2 = _TRANS_RE.search(transcript)
    transformer = f"{m2.group(1)} {m2.group(2).upper()}" if m2 else "미확인"
    gen = "있음" if any(k in transcript for k in _GEN_KWS) else "미확인"
    solar = "있음" if any(k in transcript for k in _SOLAR_KWS) else "미확인"
    problems = _extract(transcript, _PROB_KWS)
    requests_ = _extract(transcript, _REQ_KWS)

    return f"""# 전기안전관리 상담 요약

## 통화 핵심 요약
> 전사 텍스트 {len(transcript)}자 기반 규칙 추출. API 요약 사용 시 더 정확합니다.

## 고객 요청사항
- {requests_}

## 현장 정보
- **지역**: {region}
- **시설유형**: {facility}
- **수전용량**: {capacity}
- **변압기 용량**: {transformer}
- **비상발전기**: {gen}
- **태양광**: {solar}
- **현재 문제**:
  - {problems}

## 견적 산정에 필요한 추가 질문
- [ ] 수전용량 확인 (변압기 뱅크 수 포함)
- [ ] 설치 연도 및 설비 노후도
- [ ] 현재 전기안전관리자 유무
- [ ] 계약 형태 (위탁 / 선임 대행)
- [ ] 점검 횟수 요구사항

## 다음 액션
- [ ] 현장 방문 일정 협의
- [ ] 견적서 작성 및 발송
- [ ] 계약서 준비

## 영업 메모
(추가 메모 입력)

## 블로그/스레드 홍보 소재
- 지역: {region} | 시설: {facility}
- 해당 시설 전기안전관리 필요성 콘텐츠
"""
