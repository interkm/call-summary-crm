import json
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

try:
    from src.db import (
        init_db, save_consultation, save_contact,
        get_duplicates, search_consultations, get_all_contacts,
        delete_contact, search_contacts,
    )
    from src.storage import save_upload, save_transcript, save_summary_md, save_summary_txt
    from src.summarizer import summarize, _get_secret as sum_get_secret
    from src.prompts import OPENROUTER_MODELS, GROQ_MODELS
    from src.transcriber import transcribe
    from src.calendar_utils import detect_appointment, make_google_calendar_url
    from src.telegram_utils import is_configured as tg_ok, send as tg_send, consultation_msg as tg_consultation_msg
    from src.github_store import increment_today, create_gist, _get_secret as gs_get_secret
    from src.card_ocr import extract_phone_from_filename, ocr_business_card
    from src.crm_extractor import extract_crm_info
    from src.grader import grade_consultation, GRADE_COLOR, GRADE_DESC
    from src.checklist import evaluate_checklist, checklist_score
    from src.action_generator import generate_actions
except Exception as _import_err:
    import traceback as _tb
    st.error(f"모듈 로딩 오류: {_import_err}")
    st.code(_tb.format_exc())
    st.stop()

# ── Startup ───────────────────────────────────────────────────────────────────
init_db()

st.set_page_config(
    page_title="음성상담 정리 Program",
    page_icon=None,
    layout="wide",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/fonts-archive/Paperlogy/Paperlogy.css');

html, body, .stApp,
h1, h2, h3, h4, h5, h6,
p, label, caption,
.stMarkdown, .stMarkdown p, .stMarkdown li,
.stTextArea textarea, .stTextInput input,
.stSelectbox label, .stRadio label,
.stButton > button,
.stSidebar .stMarkdown,
.stExpander summary {
    font-family: 'Paperlogy', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif !important;
}

h1 { color: #0D47A1 !important; font-weight: 700 !important; }
h2 { color: #1565C0 !important; font-weight: 500 !important; }
h3 { color: #1976D2 !important; }

.stButton > button {
    background-color: #E8640A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    padding: 0.45rem 1.2rem !important;
    transition: background-color 0.2s !important;
}
.stButton > button:hover { background-color: #C8530A !important; }
.stButton > button[kind="secondary"] { background-color: #B71C1C !important; }
.stButton > button[kind="secondary"]:hover { background-color: #7F1010 !important; }

hr { border-color: #D4C4A8 !important; }

section[data-testid="stSidebar"] { background-color: #EDE4D3 !important; }

input:focus, textarea:focus {
    border-color: #E8640A !important;
    box-shadow: 0 0 0 2px rgba(232,100,10,0.2) !important;
}

.grade-badge {
    display: inline-block;
    padding: 0.4rem 1.2rem;
    border-radius: 8px;
    font-size: 1.1rem;
    font-weight: 700;
    color: white;
    margin-bottom: 0.4rem;
}

.checklist-ok {
    background: #E8F5E9;
    border-left: 4px solid #2E7D32;
    padding: 0.3rem 0.8rem;
    border-radius: 4px;
    margin: 2px 0;
}
.checklist-miss {
    background: #FFEBEE;
    border-left: 4px solid #C62828;
    padding: 0.3rem 0.8rem;
    border-radius: 4px;
    margin: 2px 0;
}

.calendar-card {
    background: #E8F5E9;
    border-left: 4px solid #2E7D32;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
}
</style>
""", unsafe_allow_html=True)

st.title("음성상담 정리 Program")
st.caption("통화녹음 전사 · 요약 · CRM · 견적 체크 · 메시지 생성")

# ── Session state ─────────────────────────────────────────────────────────────
_DEFAULTS = {
    "transcript": None, "summary": None,
    "upload_path": None, "stem": None,
    "transcript_path": None, "summary_md_path": None,
    "appointment": None, "caller_phone": "",
    "card_info": None,
    "crm_info": None, "grade": "", "grade_reason": "",
    "checklist": None, "actions": None,
    "duplicate_records": [],
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("설정")
    model_size = st.selectbox(
        "Whisper 모델", ["tiny", "base", "small"], index=0,
        help="tiny: 빠름 | base: 중간 | small: 권장",
    )
    st.caption("처음 실행 시 모델 자동 다운로드.")
    st.caption("GPU 없으면 CPU 자동 전환.")

    from src.transcriber import _get_secret as tr_get_secret
    groq_key = tr_get_secret("GROQ_API_KEY")
    if groq_key:
        st.success("Groq API 연결됨 (전사 + 요약 + CRM) ✓")
    else:
        st.warning("Groq 미설정 → 로컬 모델 사용")
        st.caption("console.groq.com 에서 무료 API 키 발급")

    st.divider()
    st.markdown("**요약 방법**")
    _has_groq = bool(groq_key)
    _has_or = bool(sum_get_secret("OPENROUTER_API_KEY"))
    _default_method_idx = 0 if _has_groq else (1 if _has_or else 2)
    sum_method = st.radio(
        "요약 방법",
        ["Groq LLM (무료, 추천)", "OpenRouter API", "규칙 기반 (무료)"],
        index=_default_method_idx,
        label_visibility="collapsed",
    )
    groq_model_id = or_model_label = or_model_id = None
    if sum_method == "Groq LLM (무료, 추천)":
        groq_model_label = st.selectbox("Groq 모델", list(GROQ_MODELS.keys()), index=0)
        groq_model_id = GROQ_MODELS[groq_model_label]
        st.caption(f"`{groq_model_id}`")
    elif sum_method == "OpenRouter API":
        if _has_or:
            st.success("API 키 연결됨 ✓")
        else:
            st.warning("OPENROUTER_API_KEY 미설정")
        or_model_label = st.selectbox("모델 선택", list(OPENROUTER_MODELS.keys()), index=0)
        or_model_id = OPENROUTER_MODELS[or_model_label]
        st.caption(f"`{or_model_id}`")

    st.divider()
    st.markdown("**텔레그램**")
    if tg_ok():
        st.success("연결됨 ✓")
    else:
        st.warning("미설정")

    st.divider()
    st.markdown("**스케줄 다이제스트**")
    gist_id = gs_get_secret("GIST_ID")
    if gist_id:
        st.success("Gist 연결됨 ✓")
    else:
        st.info("Gist 미설정 (선택)")
        if gs_get_secret("GITHUB_TOKEN"):
            if st.button("Gist 자동 생성", key="btn_create_gist"):
                new_id = create_gist()
                if new_id:
                    st.success("Gist 생성 완료!")
                    st.code(f'GIST_ID = "{new_id}"')
                else:
                    st.error("Gist 생성 실패")

# ── Helper ────────────────────────────────────────────────────────────────────
def _sel_idx(val: str) -> int:
    return {"미확인": 0, "예": 1, "아니오": 2}.get(str(val), 0)


def _plain(text: str) -> str:
    import re as _re
    text = _re.sub(r'^#{1,6}\s*', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = _re.sub(r'\*(.+?)\*', r'\1', text)
    text = _re.sub(r'^[-*]\s*\[.\]\s*', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'^[-*]\s+', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'^>\s*', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'`+', '', text)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "신규 상담", "상담 검색", "견적 체크리스트", "메시지/콘텐츠", "연락처 관리", "설정"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 신규 상담
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── 1. 녹음파일 업로드 ────────────────────────────────────────────────────
    st.header("1. 녹음파일 업로드")
    ALLOWED_EXT = {"m4a", "mp3", "wav", "mp4", "aac", "ogg", "amr", "3gp", "wma", "flac"}
    uploaded = st.file_uploader(
        "통화녹음 파일 선택 (m4a, mp3, wav, amr 등)",
        type=None,
        help="m4a · mp3 · wav · amr · 3gp · aac · ogg 지원. 모바일은 파일 앱에서 선택하세요.",
    )

    if uploaded is not None:
        ext = Path(uploaded.name).suffix.lstrip(".").lower()
        if ext and ext not in ALLOWED_EXT:
            st.warning(f".{ext} 형식은 미검증 — 전사 실패 시 m4a/mp3/wav로 변환하세요.")
        try:
            st.audio(uploaded)
        except Exception:
            st.info(f"미리듣기 미지원 형식 ({Path(uploaded.name).suffix})")

        if st.button("파일 저장", key="btn_save_upload"):
            try:
                path = save_upload(uploaded.getvalue(), uploaded.name)
                st.session_state.upload_path = path
                st.session_state.stem = Path(uploaded.name).stem
                for k in ["transcript","summary","transcript_path","summary_md_path",
                          "appointment","crm_info","grade","grade_reason",
                          "checklist","actions","duplicate_records"]:
                    st.session_state[k] = None if k not in ("grade","grade_reason") else ""
                st.session_state.duplicate_records = []
                phone = extract_phone_from_filename(uploaded.name)
                st.session_state.caller_phone = phone
                st.success(f"저장 완료: `{path}`")
            except Exception as e:
                st.error(f"파일 저장 실패: {e}")

    if st.session_state.caller_phone:
        st.info(f"발신자 번호 (파일명): **{st.session_state.caller_phone}**")

    # ── 명함 스캔 ─────────────────────────────────────────────────────────────
    st.divider()
    st.header("명함 스캔 (선택)")
    with st.expander("명함 사진 업로드 → 자동 연락처 추출", expanded=bool(st.session_state.card_info)):
        if not groq_key:
            st.warning("GROQ_API_KEY 필요")
        else:
            card_file = st.file_uploader(
                "명함 이미지 선택 (jpg, png, webp)",
                type=["jpg", "jpeg", "png", "webp", "heic"],
                key="card_uploader",
            )
            if card_file and st.button("명함 OCR 분석", key="btn_card_ocr"):
                with st.spinner("Groq Vision으로 명함 분석 중..."):
                    try:
                        info = ocr_business_card(card_file.getvalue(), groq_key, card_file.name)
                        st.session_state.card_info = info
                        st.success("명함 분석 완료!")
                    except Exception as e:
                        st.error(f"명함 OCR 실패: {e}")

        if st.session_state.card_info:
            info = st.session_state.card_info
            st.markdown("**추출된 연락처 정보**")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                info["name"] = st.text_input("성명", value=info.get("name",""), key="ci_name")
                info["title"] = st.text_input("직함", value=info.get("title",""), key="ci_title")
                info["company"] = st.text_input("회사명", value=info.get("company",""), key="ci_company")
                info["department"] = st.text_input("부서", value=info.get("department",""), key="ci_dept")
            with col_c2:
                info["phone"] = st.text_input("전화번호", value=info.get("phone",""), key="ci_phone")
                info["mobile"] = st.text_input("휴대폰", value=info.get("mobile",""), key="ci_mobile")
                info["email"] = st.text_input("이메일", value=info.get("email",""), key="ci_email")
                info["website"] = st.text_input("웹사이트", value=info.get("website",""), key="ci_web")
            info["address"] = st.text_input("주소", value=info.get("address",""), key="ci_addr")
            if st.button("연락처 DB 저장", key="btn_save_contact"):
                try:
                    cid = save_contact(info)
                    st.success(f"연락처 저장 완료! (ID: {cid})")
                except Exception as e:
                    st.error(f"연락처 저장 실패: {e}")

    # ── 2. 음성 전사 ──────────────────────────────────────────────────────────
    st.divider()
    st.header("2. 음성 전사")
    transcribe_disabled = st.session_state.upload_path is None
    if transcribe_disabled:
        st.info("먼저 녹음파일을 업로드하고 파일 저장을 눌러주세요.")

    if st.button("전사 시작", disabled=transcribe_disabled, key="btn_transcribe"):
        with st.spinner(f"전사 중... ({model_size})"):
            try:
                text = transcribe(Path(st.session_state.upload_path), model_size)
                if not text.strip():
                    st.warning("전사 결과가 비어 있습니다.")
                else:
                    st.session_state.transcript = text
                    t_path = save_transcript(text, st.session_state.stem)
                    st.session_state.transcript_path = t_path
                    st.session_state.appointment = detect_appointment(text)
                    st.success(f"전사 완료! ({len(text)}자) — 저장: `{t_path}`")
            except Exception as e:
                st.error(f"전사 실패: {e}")

    if st.session_state.transcript:
        st.text_area("전사 결과", value=st.session_state.transcript, height=200, key="ta_transcript")

    # ── 3. 상담 요약 ──────────────────────────────────────────────────────────
    st.divider()
    st.header("3. 상담요약 생성")
    summary_disabled = st.session_state.transcript is None

    if sum_method == "Groq LLM (무료, 추천)":
        _btn_label = f"상담요약 생성 (Groq: {groq_model_id or ''})"
    elif sum_method == "OpenRouter API":
        _btn_label = f"상담요약 생성 ({or_model_label or ''})"
    else:
        _btn_label = "상담요약 생성 (규칙 기반)"

    if st.button(_btn_label, disabled=summary_disabled, key="btn_summarize"):
        if sum_method == "Groq LLM (무료, 추천)":
            method, model = "groq", groq_model_id or "llama-3.3-70b-versatile"
        elif sum_method == "OpenRouter API":
            method, model = "openrouter", or_model_id or "meta-llama/llama-3.1-8b-instruct:free"
        else:
            method, model = "rule", ""
        with st.spinner("요약 생성 중..."):
            try:
                summary_text = summarize(st.session_state.transcript, method=method, model=model)
                st.session_state.summary = summary_text
                if not st.session_state.appointment:
                    st.session_state.appointment = detect_appointment(st.session_state.transcript)
                st.success(f"요약 완료! ({method})")
            except Exception as e:
                st.error(f"요약 실패: {e}")

    if st.session_state.summary:
        with st.expander("요약 결과 보기", expanded=True):
            st.markdown(st.session_state.summary)

    # ── 4. CRM 고객정보 추출 ──────────────────────────────────────────────────
    if st.session_state.summary and st.session_state.transcript:
        st.divider()
        st.header("4. CRM 고객정보 분석")

        if st.button("CRM 분석 시작 (고객정보 + 등급 + 체크리스트)", key="btn_crm"):
            with st.spinner("Groq LLM으로 고객정보 추출 중..."):
                try:
                    crm = extract_crm_info(
                        st.session_state.transcript,
                        st.session_state.summary,
                        groq_key,
                    )
                    st.session_state.crm_info = crm
                    grade, reason = grade_consultation(st.session_state.transcript, crm)
                    st.session_state.grade = grade
                    st.session_state.grade_reason = reason
                    st.session_state.checklist = evaluate_checklist(crm)
                    # 중복 감지
                    phone = crm.get("phone", "")
                    company = crm.get("company_name", "")
                    if phone or company:
                        st.session_state.duplicate_records = get_duplicates(phone, company)
                    st.success("CRM 분석 완료!")
                except Exception as e:
                    st.error(f"CRM 분석 실패: {e}")

        if st.session_state.crm_info:
            crm = st.session_state.crm_info

            # 등급 배지
            grade = st.session_state.grade
            gc = GRADE_COLOR.get(grade, "#333")
            gd = GRADE_DESC.get(grade, "")
            st.markdown(
                f'<div class="grade-badge" style="background:{gc}">{grade}급 — {gd}</div>',
                unsafe_allow_html=True,
            )
            st.caption(st.session_state.grade_reason)

            # 중복 고객 경고
            dups = st.session_state.duplicate_records
            if dups:
                st.warning(f"기존 상담 기록 {len(dups)}건 발견 — 재방문 고객입니다!")
                for dup in dups[:3]:
                    with st.expander(f"이전 상담: {dup['created_at'][:10]} | {dup.get('grade','')}급 | {dup.get('company_name','')}"):
                        st.write(f"등급 사유: {dup.get('grade_reason','')}")
                        st.text(dup.get("summary_text", "")[:400])

            # 고객정보 편집
            st.markdown("**고객정보 확인 및 수정**")
            col1, col2, col3 = st.columns(3)
            with col1:
                crm["customer_name"] = st.text_input("고객명", value=crm.get("customer_name",""), key="crm_customer")
                crm["company_name"] = st.text_input("회사명", value=crm.get("company_name",""), key="crm_company")
                crm["phone"] = st.text_input("전화번호", value=crm.get("phone",""), key="crm_phone")
                crm["region"] = st.text_input("지역", value=crm.get("region",""), key="crm_region")
            with col2:
                crm["facility_type"] = st.text_input("시설유형", value=crm.get("facility_type",""), key="crm_facility")
                crm["consultation_purpose"] = st.text_input("상담목적", value=crm.get("consultation_purpose",""), key="crm_purpose")
                crm["transformer_kva"] = st.text_input("수전용량 (변압기 kVA)", value=crm.get("transformer_kva",""), key="crm_kva")
                crm["contract_kw"] = st.text_input("계약전력 (kW)", value=crm.get("contract_kw",""), key="crm_kw")
            with col3:
                crm["is_urgent"] = st.selectbox("긴급여부", ["미확인","예","아니오"], index=_sel_idx(crm.get("is_urgent","")), key="crm_urgent")
                crm["needs_visit"] = st.selectbox("방문필요", ["미확인","예","아니오"], index=_sel_idx(crm.get("needs_visit","")), key="crm_visit")
                crm["needs_quote"] = st.selectbox("견적필요", ["미확인","예","아니오"], index=_sel_idx(crm.get("needs_quote","")), key="crm_quote")
                crm["wants_change_agency"] = st.selectbox("교체의사", ["미확인","예","아니오"], index=_sel_idx(crm.get("wants_change_agency","")), key="crm_change")
            col4, col5 = st.columns(2)
            with col4:
                crm["contract_expiry"] = st.text_input("계약만료일", value=crm.get("contract_expiry",""), key="crm_expiry")
            with col5:
                crm["current_monthly_fee"] = st.text_input("현재 월 대행비", value=crm.get("current_monthly_fee",""), key="crm_fee")

            st.session_state.crm_info = crm
            # checklist 갱신
            st.session_state.checklist = evaluate_checklist(crm)

        # ── 5. 결과 저장 ──────────────────────────────────────────────────────
        st.divider()
        st.header("5. 결과 저장")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Markdown 저장", key="btn_md"):
                try:
                    p = save_summary_md(st.session_state.summary, st.session_state.stem)
                    st.session_state.summary_md_path = p
                    st.success(f"저장: `{p}`")
                except Exception as e:
                    st.error(f"저장 실패: {e}")

        with col2:
            if st.button("TXT 저장", key="btn_txt"):
                try:
                    p = save_summary_txt(st.session_state.summary, st.session_state.stem)
                    st.success(f"저장: `{p}`")
                except Exception as e:
                    st.error(f"저장 실패: {e}")

        with col3:
            if st.button("DB 저장 + 텔레그램 전송", key="btn_db"):
                try:
                    crm = st.session_state.crm_info or {}
                    t_path = st.session_state.transcript_path or save_transcript(
                        st.session_state.transcript, st.session_state.stem)
                    s_path = st.session_state.summary_md_path or save_summary_md(
                        st.session_state.summary, st.session_state.stem)
                    fname = Path(st.session_state.upload_path).name if st.session_state.upload_path else "unknown"
                    row_id = save_consultation(
                        original_filename=fname,
                        transcript_path=str(t_path),
                        summary_path=str(s_path),
                        transcript_text=st.session_state.transcript,
                        summary_text=st.session_state.summary,
                        grade=st.session_state.grade,
                        grade_reason=st.session_state.grade_reason,
                        customer_name=crm.get("customer_name",""),
                        company_name=crm.get("company_name",""),
                        phone=crm.get("phone",""),
                        region=crm.get("region",""),
                        facility_type=crm.get("facility_type",""),
                        is_urgent=crm.get("is_urgent",""),
                        needs_visit=crm.get("needs_visit",""),
                        needs_quote=crm.get("needs_quote",""),
                        wants_change_agency=crm.get("wants_change_agency",""),
                        contract_expiry=crm.get("contract_expiry",""),
                        current_monthly_fee=crm.get("current_monthly_fee",""),
                        crm_json=json.dumps(crm, ensure_ascii=False),
                    )
                    st.success(f"DB 저장 완료! (ID: {row_id})")

                    if tg_ok():
                        grade_line = f"[{st.session_state.grade}급] " if st.session_state.grade else ""
                        msg = tg_consultation_msg(grade_line + fname, st.session_state.summary)
                        ok = tg_send(msg)
                        if ok:
                            st.success("텔레그램 전송 완료!")
                        else:
                            st.warning("텔레그램 전송 실패")
                    else:
                        st.info("텔레그램 미설정")

                    try:
                        cnt = increment_today()
                        if cnt:
                            st.caption(f"오늘 누적 상담: {cnt}건")
                    except Exception:
                        pass
                except Exception as e:
                    st.error(f"DB 저장 실패: {e}")

    # ── 6. 구글 캘린더 ────────────────────────────────────────────────────────
    if st.session_state.transcript:
        appt = st.session_state.appointment or {}
        st.divider()
        st.header("6. 구글 캘린더 일정 등록")

        if appt.get("detected"):
            st.markdown(
                '<div class="calendar-card"><b>통화에서 일정 약속이 감지되었습니다.</b></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("일정 약속이 자동 감지되지 않았습니다. 직접 입력하세요.")

        with st.form("cal_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                event_title = st.text_input("일정 제목", value="전기안전관리 현장 방문")
                default_date = datetime.now().date()
                if appt.get("date"):
                    try:
                        default_date = datetime.strptime(appt["date"], "%Y-%m-%d").date()
                    except Exception:
                        pass
                event_date = st.date_input("날짜", value=default_date)
            with col_b:
                crm_region = (st.session_state.crm_info or {}).get("region", "")
                event_location = st.text_input("장소", value=appt.get("location") or crm_region or "")
                default_time = None
                if appt.get("time"):
                    try:
                        h, m = map(int, appt["time"].split(":"))
                        from datetime import time as dtime
                        default_time = dtime(h, m)
                    except Exception:
                        pass
                event_time = st.time_input("시간 (없으면 종일)", value=default_time)

            event_details = st.text_area(
                "메모", value=_plain(st.session_state.summary or "")[:800], height=250,
            )
            submitted = st.form_submit_button("구글 캘린더 열기", use_container_width=True)

        if submitted:
            cal_url = make_google_calendar_url(
                title=event_title,
                date_str=event_date.strftime("%Y-%m-%d") if event_date else None,
                time_str=event_time.strftime("%H:%M") if event_time else None,
                details=event_details,
                location=event_location,
            )
            st.markdown(
                f'<div class="cal-section"><a href="{cal_url}" target="_blank" style="'
                f'display:inline-block;background:#2E7D32;color:white;padding:0.6rem 1.4rem;'
                f'border-radius:10px;text-decoration:none;font-family:Paperlogy,sans-serif;'
                f'font-weight:500;font-size:1rem;">구글 캘린더에서 일정 추가하기 →</a></div>',
                unsafe_allow_html=True,
            )

    # ── 7. 원본파일 관리 ──────────────────────────────────────────────────────
    st.divider()
    st.header("7. 원본파일 관리")
    if st.session_state.upload_path:
        upload_path = Path(st.session_state.upload_path)
        if upload_path.exists():
            st.warning(f"원본파일 위치: `{upload_path}`")
            if st.button("원본파일 삭제", type="secondary", key="btn_delete"):
                try:
                    upload_path.unlink()
                    st.session_state.upload_path = None
                    st.success("원본파일 삭제 완료")
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 실패: {e}")
        else:
            st.info("원본파일이 이미 삭제되었거나 존재하지 않습니다.")
    else:
        st.info("업로드된 원본파일 없음")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 상담 검색
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("상담 기록 검색")

    with st.form("search_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            s_phone = st.text_input("전화번호")
            s_customer = st.text_input("고객명")
        with c2:
            s_company = st.text_input("회사명")
            s_region = st.text_input("지역")
        with c3:
            s_grade = st.selectbox("등급", ["전체", "A", "B", "C", "D"])
            s_needs_quote = st.selectbox("견적필요", ["전체", "예", "아니오"])
            s_needs_visit = st.selectbox("방문필요", ["전체", "예", "아니오"])

        cd1, cd2 = st.columns(2)
        with cd1:
            s_date_from = st.date_input("시작일", value=None)
        with cd2:
            s_date_to = st.date_input("종료일", value=None)

        search_btn = st.form_submit_button("검색", use_container_width=True)

    if search_btn:
        results = search_consultations(
            phone=s_phone,
            customer_name=s_customer,
            company_name=s_company,
            region=s_region,
            grade=s_grade if s_grade != "전체" else "",
            needs_quote=s_needs_quote if s_needs_quote != "전체" else "",
            needs_visit=s_needs_visit if s_needs_visit != "전체" else "",
            date_from=s_date_from.isoformat() if s_date_from else "",
            date_to=s_date_to.isoformat() if s_date_to else "",
        )
        st.write(f"검색 결과: **{len(results)}건**")

        for r in results:
            grade_tag = f"[{r.get('grade','?')}급]" if r.get("grade") else ""
            cname = r.get("customer_name","") or ""
            comp = r.get("company_name","") or ""
            label = f"{grade_tag} {cname} {comp} — {r['created_at'][:10]}"
            with st.expander(label.strip()):
                cols = st.columns(3)
                cols[0].write(f"전화번호: {r.get('phone','')}")
                cols[0].write(f"지역: {r.get('region','')}")
                cols[0].write(f"시설: {r.get('facility_type','')}")
                cols[1].write(f"긴급: {r.get('is_urgent','')}")
                cols[1].write(f"견적필요: {r.get('needs_quote','')}")
                cols[1].write(f"방문필요: {r.get('needs_visit','')}")
                cols[2].write(f"교체의사: {r.get('wants_change_agency','')}")
                cols[2].write(f"계약만료: {r.get('contract_expiry','')}")
                cols[2].write(f"월 대행비: {r.get('current_monthly_fee','')}")
                st.text_area(
                    "요약", value=r.get("summary_text","")[:600],
                    height=150, disabled=True, key=f"sr_{r['id']}",
                )
                if r.get("grade_reason"):
                    st.caption(f"등급 사유: {r.get('grade_reason','')}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 견적 체크리스트
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("견적 체크리스트")

    if not st.session_state.checklist:
        st.info("신규 상담 탭 → CRM 분석 후 여기서 체크리스트를 확인하세요.")
    else:
        checklist = st.session_state.checklist
        confirmed, missing = checklist_score(checklist)
        crm = st.session_state.crm_info or {}

        st.write(f"확인됨: **{confirmed}항목** | 추가질문 필요: **{missing}항목**")
        st.progress(confirmed / len(checklist))

        st.markdown("---")
        for item in checklist:
            if item["status"] == "confirmed":
                st.markdown(
                    f'<div class="checklist-ok">확인 &nbsp; <b>{item["item"]}</b>: {item["value"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="checklist-miss">미확인 &nbsp; <b>{item["item"]}</b> — 추가 질문 필요</div>',
                    unsafe_allow_html=True,
                )

        if missing > 0:
            st.markdown("---")
            st.subheader("추가 질문 문자 초안")
            missing_items = [c["item"] for c in checklist if c["status"] == "missing"]
            q_text = f"안녕하세요. 전기안전관리 견적 산정을 위해 아래 사항 확인 부탁드립니다.\n"
            q_text += "\n".join(f"- {item}" for item in missing_items[:5])
            st.text_area("확인 문자 초안", value=q_text, height=150)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — 메시지/콘텐츠 생성
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("메시지/콘텐츠 생성")

    if not st.session_state.summary or not st.session_state.crm_info:
        st.info("신규 상담 탭에서 요약 + CRM 분석을 먼저 완료하세요.")
    else:
        crm = st.session_state.crm_info
        grade = st.session_state.grade

        if st.button("액션 메시지 생성 (Groq LLM)", key="btn_actions"):
            with st.spinner("Groq LLM으로 메시지 생성 중..."):
                try:
                    actions = generate_actions(
                        st.session_state.transcript or "",
                        st.session_state.summary,
                        crm, grade, groq_key,
                    )
                    st.session_state.actions = actions
                    st.success("메시지 생성 완료!")
                except Exception as e:
                    st.error(f"생성 실패: {e}")

        if st.session_state.actions:
            actions = st.session_state.actions

            _labels = [
                ("sms_question", "추가 질문 문자"),
                ("sms_quote", "견적 안내 문자"),
                ("sms_visit", "방문 일정 문자"),
                ("kakao", "카카오톡 답장문"),
                ("telegram", "텔레그램 내부 보고"),
                ("blog_draft", "블로그 사례글 초안 (익명화)"),
                ("thread_draft", "스레드 홍보글 초안 (익명화)"),
            ]

            for key, label in _labels:
                val = actions.get(key, "")
                if val:
                    with st.expander(label, expanded=(key in ("sms_question", "telegram"))):
                        st.text_area(label, value=val, height=120, key=f"act_{key}")
                        if key in ("sms_question", "sms_quote", "sms_visit", "kakao"):
                            st.caption(f"{len(val)}자")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — 연락처 관리
# ═══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("연락처 관리")

    # ── 명함 등록 ────────────────────────────────────────────────────────────
    st.subheader("명함 등록")

    card_file = st.file_uploader(
        "명함 이미지 업로드 (JPG/PNG)", type=["jpg", "jpeg", "png", "webp"],
        key="contact_card_upload",
    )

    if card_file:
        st.image(card_file, width=320)
        if st.button("명함 OCR 분석", key="btn_contact_ocr"):
            with st.spinner("명함 인식 중..."):
                try:
                    info = ocr_business_card(card_file.read(), groq_key, card_file.name)
                    st.session_state["_contact_ocr"] = info
                    st.success("인식 완료!")
                except Exception as e:
                    st.error(f"OCR 실패: {e}")
                    st.session_state["_contact_ocr"] = {}

    if "_contact_ocr" not in st.session_state:
        st.session_state["_contact_ocr"] = {}

    ocr = st.session_state["_contact_ocr"]

    with st.form("form_contact_save"):
        st.markdown("**연락처 정보 확인/수정 후 저장**")
        c1, c2 = st.columns(2)
        name     = c1.text_input("성명",     value=ocr.get("name", ""))
        title    = c2.text_input("직함",     value=ocr.get("title", ""))
        company  = c1.text_input("회사",     value=ocr.get("company", ""))
        dept     = c2.text_input("부서",     value=ocr.get("department", ""))
        phone_c  = c1.text_input("전화",     value=ocr.get("phone", ""))
        mobile_c = c2.text_input("휴대폰",   value=ocr.get("mobile", ""))
        email_c  = c1.text_input("이메일",   value=ocr.get("email", ""))
        addr_c   = c2.text_input("주소",     value=ocr.get("address", ""))
        web_c    = st.text_input("웹사이트", value=ocr.get("website", ""))

        if st.form_submit_button("연락처 저장"):
            if not name and not company and not phone_c:
                st.warning("성명, 회사, 전화 중 하나 이상 입력 필요")
            else:
                try:
                    save_contact({
                        "name": name, "title": title,
                        "company": company, "department": dept,
                        "phone": phone_c, "mobile": mobile_c,
                        "email": email_c, "address": addr_c,
                        "website": web_c,
                    })
                    st.success(f"{name or company} 저장 완료!")
                    st.session_state["_contact_ocr"] = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")

    st.divider()

    # ── 연락처 목록 ──────────────────────────────────────────────────────────
    st.subheader("연락처 목록")

    kw_contact = st.text_input("검색 (이름/회사/전화/이메일)", key="contact_search")

    try:
        contacts = search_contacts(kw_contact)
    except Exception as e:
        st.error(f"조회 오류: {e}")
        contacts = []

    st.caption(f"총 {len(contacts)}건")

    for ct in contacts:
        _cid   = ct.get("id")
        _name  = ct.get("name", "")  or "(이름없음)"
        _co    = ct.get("company", "") or ""
        _title = ct.get("title", "")  or ""
        _phone = ct.get("phone", "")  or ct.get("mobile", "") or ""
        _email = ct.get("email", "") or ""
        _label = f"{_name}  {_co}  {_title}".strip()

        with st.expander(_label, expanded=False):
            d1, d2, d3 = st.columns([2, 2, 1])
            d1.markdown(f"**전화** {_phone}")
            d2.markdown(f"**이메일** {_email}")
            if ct.get("address"):
                st.caption(ct["address"])
            if ct.get("website"):
                st.caption(ct["website"])
            st.caption(f"등록일: {ct.get('created_at','')[:10]}")
            if d3.button("삭제", key=f"del_contact_{_cid}", type="secondary"):
                try:
                    delete_contact(_cid)
                    st.success("삭제됨")
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 실패: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — 설정
# ═══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("설정")

    st.subheader("저장 경로")
    st.code("data/uploads/\ndata/transcripts/\ndata/summaries/\ndb/consultations.sqlite")

    st.subheader("API 키 상태")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if groq_key:
            st.success("Groq API 키 ✓")
        else:
            st.error("Groq API 키 미설정")
            st.caption("Streamlit Cloud Secrets 또는 .streamlit/secrets.toml에 GROQ_API_KEY 추가")
    with col_b:
        if tg_ok():
            st.success("텔레그램 ✓")
        else:
            st.error("텔레그램 미설정")
    with col_c:
        if gist_id:
            st.success("Gist ✓")
        else:
            st.info("Gist 미설정 (선택)")

    st.subheader("DB 통계")
    try:
        all_recs = search_consultations()
        total = len(all_recs)
        grade_counts = {}
        for r in all_recs:
            g = r.get("grade","미분류") or "미분류"
            grade_counts[g] = grade_counts.get(g, 0) + 1
        st.metric("전체 상담 기록", f"{total}건")
        cols = st.columns(5)
        for i, g in enumerate(["A","B","C","D","미분류"]):
            cols[i].metric(f"{g}급", f"{grade_counts.get(g,0)}건")
    except Exception as e:
        st.error(f"DB 통계 오류: {e}")
