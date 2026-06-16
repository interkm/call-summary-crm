"""
Summarizer: rule-based by default.
To add API summarization: implement _summarize_with_openai() below,
then dispatch on method="openai" or "openrouter" in summarize().
"""

import re

# ── Public interface ──────────────────────────────────────────────────────────

def summarize(transcript: str, method: str = "rule") -> str:
    if method == "rule":
        return _rule_based(transcript)
    # elif method == "openai":
    #     return _summarize_with_openai(transcript)
    raise ValueError(f"지원하지 않는 요약 방법: {method}")


# ── Keyword tables ────────────────────────────────────────────────────────────

_REGIONS = [
    "서울", "부산", "인천", "대구", "대전", "광주", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

_FACILITIES = {
    "공장": "공장", "창고": "창고", "물류": "물류센터", "아파트": "아파트",
    "빌딩": "빌딩", "건물": "건물", "병원": "병원", "학교": "학교",
    "호텔": "호텔", "마트": "마트", "주유소": "주유소", "사업장": "사업장",
    "현장": "현장",
}

_CAP_RE = re.compile(r"(\d[\d,]*)\s*(kw|kva|킬로와트|킬로볼트)", re.IGNORECASE)
_TRANS_RE = re.compile(r"변압기.{0,15}?(\d[\d,]*)\s*(kva|kw)", re.IGNORECASE)
_GEN_KWS = ["비상발전기", "발전기", "비상전원"]
_SOLAR_KWS = ["태양광", "솔라", "ess", "ESS"]
_PROB_KWS = ["문제", "고장", "오류", "경보", "트립", "정전", "누전", "이상", "불량", "점검"]
_REQ_KWS = ["요청", "부탁", "원합니다", "해주세요", "해주십시오", "알고 싶", "문의", "견적", "방문", "계약"]


# ── Extractor helpers ─────────────────────────────────────────────────────────

def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"[.。\n]", text) if s.strip()]


def _extract_sentences(text: str, keywords: list, limit: int = 3) -> str:
    found = [s for s in _sentences(text) if any(kw in s for kw in keywords)]
    return ("\n- ".join(found[:limit])) if found else "미확인"


def _find_first(text: str, items: list) -> str:
    return next((item for item in items if item in text), "미확인")


def _re_find(text: str, pattern: re.Pattern) -> str:
    m = pattern.search(text)
    return f"{m.group(1)} {m.group(2).upper()}" if m else "미확인"


def _flag(text: str, keywords: list) -> str:
    return "있음" if any(kw in text for kw in keywords) else "미확인"


# ── Rule-based summarizer ─────────────────────────────────────────────────────

def _rule_based(transcript: str) -> str:
    region = _find_first(transcript, _REGIONS)
    facility = next((v for k, v in _FACILITIES.items() if k in transcript), "미확인")
    capacity = _re_find(transcript, _CAP_RE)
    transformer = _re_find(transcript, _TRANS_RE)
    gen = _flag(transcript, _GEN_KWS)
    solar = _flag(transcript, _SOLAR_KWS)
    problems = _extract_sentences(transcript, _PROB_KWS)
    requests = _extract_sentences(transcript, _REQ_KWS)

    return f"""# 전기안전관리 상담 요약

## 통화 핵심 요약
> 전사 텍스트 {len(transcript)}자 기반 자동 추출 (규칙 기반)
> API 연동 시 더 정확한 요약을 제공할 수 있습니다.

## 고객 요청사항
- {requests}

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
- [ ] 비상발전기 용량 및 제조사

## 다음 액션
- [ ] 현장 방문 일정 협의
- [ ] 견적서 작성 및 발송
- [ ] 계약서 준비
- [ ] 담당자 연락처 확보

## 영업 메모
(추가 메모를 직접 입력하세요)

## 블로그/스레드 홍보 소재
- 지역: {region} | 시설: {facility}
- 해당 시설 유형의 전기안전관리 필요성 콘텐츠
- 고객 문의 키워드 기반 블로그 포스팅 소재
- 실제 상담 사례 익명화 후 홍보 활용 가능
"""


# ── Future: API-based summarizer (uncomment to activate) ─────────────────────
# def _summarize_with_openai(transcript: str) -> str:
#     import os
#     import openai
#     from src.prompts import OPENAI_SYSTEM_PROMPT
#
#     client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
#             {"role": "user", "content": f"전사 텍스트:\n\n{transcript}"},
#         ],
#     )
#     return response.choices[0].message.content
