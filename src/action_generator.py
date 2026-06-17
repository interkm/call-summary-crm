"""다음 액션 자동 생성 (Groq LLM) + 개인정보 익명화"""
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


_ACTION_PROMPT = """\
전기안전관리 영업 담당자입니다. 아래 상담 정보를 바탕으로 각 항목의 메시지를 작성하세요.

규칙:
- sms_*와 kakao는 실제 보낼 수 있는 자연스러운 한국어 문자/카카오 메시지
- telegram은 내부 보고용, 줄바꿈 사용, 핵심만
- blog_draft와 thread_draft는 반드시 고객명/회사명/전화번호/상세주소/담당자명을 [고객], [업체명], [지역] 등으로 익명화
- 필요 없는 항목은 빈 문자열("")
- 반드시 아래 JSON 형식으로만 출력

{
  "sms_question": "추가 질문 문자 (80자 이내)",
  "sms_quote": "견적 안내 문자 (100자 이내)",
  "sms_visit": "방문 일정 안내 문자 (100자 이내)",
  "kakao": "카카오톡 답장문 (150자 이내)",
  "telegram": "텔레그램 내부 보고 메시지",
  "blog_draft": "블로그 사례글 초안 (익명화, 500자 이내)",
  "thread_draft": "스레드 홍보글 초안 (익명화, 200자 이내)"
}"""


def generate_actions(
    transcript: str,
    summary: str,
    crm_info: dict,
    grade: str,
    groq_api_key: str = None,
) -> dict:
    if not groq_api_key:
        groq_api_key = _get_secret("GROQ_API_KEY")

    _empty = {
        "sms_question": "", "sms_quote": "", "sms_visit": "",
        "kakao": "", "telegram": "", "blog_draft": "", "thread_draft": "",
    }

    if not groq_api_key:
        return _empty

    context = f"""
상담등급: {grade}급
고객: {crm_info.get('customer_name','미확인')} / {crm_info.get('company_name','미확인')}
지역: {crm_info.get('region','미확인')} | 시설: {crm_info.get('facility_type','미확인')}
상담목적: {crm_info.get('consultation_purpose','미확인')}
긴급: {crm_info.get('is_urgent','미확인')} | 방문필요: {crm_info.get('needs_visit','미확인')} | 견적필요: {crm_info.get('needs_quote','미확인')}
교체의사: {crm_info.get('wants_change_agency','미확인')} | 계약만료: {crm_info.get('contract_expiry','미확인')} | 현재대행비: {crm_info.get('current_monthly_fee','미확인')}
수전용량: {crm_info.get('transformer_kva','미확인')} | 계약전력: {crm_info.get('contract_kw','미확인')}

[요약]
{summary[:600]}
"""

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
                    {"role": "system", "content": _ACTION_PROMPT},
                    {"role": "user", "content": context},
                ],
                "temperature": 0.4,
                "max_tokens": 1500,
            },
            timeout=45,
        )
        if resp.ok:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            m = re.search(r"\{[\s\S]*\}", content)
            if m:
                return json.loads(m.group())
    except Exception:
        pass

    return _empty


def anonymize(text: str, crm_info: dict) -> str:
    """개인정보 제거 — 고객명/회사명/전화번호 치환"""
    result = text
    phone = crm_info.get("phone", "")
    name = crm_info.get("customer_name", "")
    company = crm_info.get("company_name", "")
    phone_re = re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}")

    result = phone_re.sub("[전화번호]", result)
    if phone and len(phone) > 4:
        result = result.replace(phone, "[전화번호]")
    if name and len(name) >= 2:
        result = result.replace(name, "[고객]")
    if company and len(company) >= 2:
        result = result.replace(company, "[업체명]")
    return result
