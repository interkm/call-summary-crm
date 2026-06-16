import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.db import init_db, save_consultation, save_contact
from src.storage import save_upload, save_transcript, save_summary_md, save_summary_txt
from src.summarizer import summarize, _get_secret as sum_get_secret
from src.prompts import OPENROUTER_MODELS, GROQ_MODELS
from src.transcriber import transcribe
from src.calendar_utils import detect_appointment, make_google_calendar_url
from src.telegram_utils import is_configured as tg_ok, send as tg_send, consultation_msg as tg_consultation_msg
from src.github_store import increment_today, create_gist, _get_secret as gs_get_secret
from src.card_ocr import extract_phone_from_filename, ocr_business_card

# ── Startup ───────────────────────────────────────────────────────────────────
init_db()

st.set_page_config(
    page_title="통화녹음 상담요약기",
    page_icon=None,
    layout="wide",
)

# ── Custom CSS: Paperlogy + 베이지/주황/초록 테마 ─────────────────────────────
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/fonts-archive/Paperlogy/Paperlogy.css');

html, body, [class*="css"], .stApp, .stMarkdown, .stTextArea textarea,
.stSelectbox, .stFileUploader, .stButton > button, .stExpander,
.stSidebar, h1, h2, h3, h4, p, label, span, div {
    font-family: 'Paperlogy', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif !important;
}

h1 { color: #E8640A !important; font-weight: 700 !important; }
h2 { color: #C8530A !important; font-weight: 500 !important; }
h3 { color: #2E7D32 !important; }

.stButton > button {
    background-color: #E8640A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    padding: 0.45rem 1.2rem !important;
    transition: background-color 0.2s !important;
}
.stButton > button:hover {
    background-color: #C8530A !important;
    color: #FFFFFF !important;
}
.stButton > button[kind="secondary"] {
    background-color: #B71C1C !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: #7F1010 !important;
}

.cal-section .stLinkButton a {
    background-color: #2E7D32 !important;
    color: white !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
}
.cal-section .stLinkButton a:hover {
    background-color: #1B5E20 !important;
}

hr { border-color: #D4C4A8 !important; }

section[data-testid="stSidebar"] {
    background-color: #EDE4D3 !important;
}

input:focus, textarea:focus {
    border-color: #E8640A !important;
    box-shadow: 0 0 0 2px rgba(232,100,10,0.2) !important;
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

st.title("통화녹음 상담요약기")
st.caption("통화녹음 파일을 올리면 전사하고 전기안전관리 상담기록으로 요약합니다.")

# ── Session state ─────────────────────────────────────────────────────────────
_DEFAULTS = {
    "transcript": None,
    "summary": None,
    "upload_path": None,
    "stem": None,
    "transcript_path": None,
    "summary_md_path": None,
    "appointment": None,
    "caller_phone": "",
    "card_info": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("설정")
    model_size = st.selectbox(
        "Whisper 모델",
        ["tiny", "base", "small"],
        index=0,
        help="tiny: 빠름/낮은정확도 | base: 중간 | small: 권장",
    )
    st.caption("처음 실행 시 모델 자동 다운로드.")
    st.caption("GPU 없으면 CPU 자동 전환.")

    from src.transcriber import _get_secret as tr_get_secret
    groq_key = tr_get_secret("GROQ_API_KEY")
    if groq_key:
        st.success("Groq Whisper API 사용 중 ✓")
        st.caption("whisper-large-v3-turbo (한국어 최고 정확도)")
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
    groq_model_id = None
    or_model_label = None
    or_model_id = None
    if sum_method == "Groq LLM (무료, 추천)":
        if _has_groq:
            st.success("Groq API 키 연결됨 ✓")
        else:
            st.warning("GROQ_API_KEY 미설정")
        groq_model_label = st.selectbox(
            "Groq 모델",
            list(GROQ_MODELS.keys()),
            index=0,
        )
        groq_model_id = GROQ_MODELS[groq_model_label]
        st.caption(f"`{groq_model_id}`")
    elif sum_method == "OpenRouter API":
        if _has_or:
            st.success("API 키 연결됨 ✓")
        else:
            st.warning("OPENROUTER_API_KEY 미설정")
            st.caption("secrets.toml에 추가 필요")
        or_model_label = st.selectbox(
            "모델 선택",
            list(OPENROUTER_MODELS.keys()),
            index=0,
        )
        or_model_id = OPENROUTER_MODELS[or_model_label]
        st.caption(f"`{or_model_id}`")
    st.divider()

    st.markdown("**텔레그램**")
    if tg_ok():
        st.success("연결됨 ✓")
    else:
        st.warning("미설정")
        st.caption("secrets.toml에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 추가 필요")
        with st.expander("설정 방법"):
            st.markdown("""
1. [@BotFather](https://t.me/BotFather) → `/newbot` → 토큰 발급
2. 봇에 메시지 1개 전송
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` 접속 → `chat.id` 확인
4. `.streamlit/secrets.toml` 에 입력
            """)

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
                    st.code(f"GIST_ID = \"{new_id}\"")
                    st.caption("위 값을 secrets.toml 및 GitHub Actions Secrets에 추가하세요.")
                else:
                    st.error("Gist 생성 실패. GITHUB_TOKEN 권한(gist)을 확인하세요.")
        else:
            st.caption("GITHUB_TOKEN 추가 후 Gist 생성 가능")

    st.divider()
    st.markdown("**저장 경로**")
    st.code("data/uploads/\ndata/transcripts/\ndata/summaries/\ndb/consultations.sqlite")

# ── 1. 파일 업로드 ─────────────────────────────────────────────────────────────
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
        st.warning(f".{ext} 형식은 미검증 — 전사 실패 시 m4a/mp3/wav로 변환하세요. 그래도 시도합니다.")

if uploaded is not None:
    try:
        st.audio(uploaded)
    except Exception:
        st.info(f"미리듣기 미지원 형식 ({Path(uploaded.name).suffix}) — 업로드는 가능합니다.")
    if st.button("파일 저장", key="btn_save_upload"):
        try:
            path = save_upload(uploaded.getvalue(), uploaded.name)
            st.session_state.upload_path = path
            st.session_state.stem = Path(uploaded.name).stem
            st.session_state.transcript = None
            st.session_state.summary = None
            st.session_state.transcript_path = None
            st.session_state.summary_md_path = None
            st.session_state.appointment = None
            phone = extract_phone_from_filename(uploaded.name)
            st.session_state.caller_phone = phone
            st.success(f"저장 완료: `{path}`")
        except Exception as e:
            st.error(f"파일 저장 실패: {e}")

if st.session_state.caller_phone:
    st.info(f"발신자 번호 (파일명): **{st.session_state.caller_phone}**")

# ── 명함 스캔 ─────────────────────────────────────────────────────────────────
st.divider()
st.header("명함 스캔 (선택)")

_card_groq_key = groq_key
with st.expander("명함 사진 업로드 → 자동 연락처 추출", expanded=bool(st.session_state.card_info)):
    if not _card_groq_key:
        st.warning("GROQ_API_KEY 필요 — Streamlit Secrets에 추가 후 사용 가능")
    else:
        card_file = st.file_uploader(
            "명함 이미지 선택 (jpg, png, webp)",
            type=["jpg", "jpeg", "png", "webp", "heic"],
            key="card_uploader",
        )
        if card_file and st.button("명함 OCR 분석", key="btn_card_ocr"):
            with st.spinner("Groq Vision으로 명함 분석 중..."):
                try:
                    info = ocr_business_card(card_file.getvalue(), _card_groq_key, card_file.name)
                    st.session_state.card_info = info
                    st.success("명함 분석 완료!")
                except Exception as e:
                    st.error(f"명함 OCR 실패: {e}")

    if st.session_state.card_info:
        info = st.session_state.card_info
        st.markdown("**추출된 연락처 정보**")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            info["name"] = st.text_input("성명", value=info.get("name", ""), key="ci_name")
            info["title"] = st.text_input("직함", value=info.get("title", ""), key="ci_title")
            info["company"] = st.text_input("회사명", value=info.get("company", ""), key="ci_company")
            info["department"] = st.text_input("부서", value=info.get("department", ""), key="ci_dept")
        with col_c2:
            info["phone"] = st.text_input("전화번호", value=info.get("phone", ""), key="ci_phone")
            info["mobile"] = st.text_input("휴대폰", value=info.get("mobile", ""), key="ci_mobile")
            info["email"] = st.text_input("이메일", value=info.get("email", ""), key="ci_email")
            info["website"] = st.text_input("웹사이트", value=info.get("website", ""), key="ci_web")
        info["address"] = st.text_input("주소", value=info.get("address", ""), key="ci_addr")

        if st.button("연락처 DB 저장", key="btn_save_contact"):
            try:
                cid = save_contact(info)
                st.success(f"연락처 저장 완료! (ID: {cid})")
            except Exception as e:
                st.error(f"연락처 저장 실패: {e}")

# ── 2. 음성 전사 ──────────────────────────────────────────────────────────────
st.divider()
st.header("2. 음성 전사")

transcribe_disabled = st.session_state.upload_path is None
if transcribe_disabled:
    st.info("먼저 녹음파일을 업로드하고 파일 저장을 눌러주세요.")

if st.button("전사 시작", disabled=transcribe_disabled, key="btn_transcribe"):
    with st.spinner(f"전사 중... 모델: {model_size} (GPU 없으면 CPU 자동 전환)"):
        try:
            text = transcribe(Path(st.session_state.upload_path), model_size)
            if not text.strip():
                st.warning("전사 결과가 비어 있습니다. 파일을 확인하세요.")
            else:
                st.session_state.transcript = text
                t_path = save_transcript(text, st.session_state.stem)
                st.session_state.transcript_path = t_path
                st.session_state.appointment = detect_appointment(text)
                st.success(f"전사 완료! ({len(text)}자) — 저장: `{t_path}`")
        except Exception as e:
            st.error(f"전사 실패: {e}")
            st.error("해결: 더 작은 모델(tiny) 선택 또는 wav로 변환 후 재시도.")

if st.session_state.transcript:
    st.text_area("전사 결과", value=st.session_state.transcript, height=200, key="ta_transcript")

# ── 3. 상담요약 생성 ───────────────────────────────────────────────────────────
st.divider()
st.header("3. 상담요약 생성")

summary_disabled = st.session_state.transcript is None
if summary_disabled and not transcribe_disabled:
    st.info("전사를 먼저 완료하세요.")

if sum_method == "Groq LLM (무료, 추천)":
    _btn_label = f"상담요약 생성 (Groq: {groq_model_id or ''})"
elif sum_method == "OpenRouter API":
    _btn_label = f"상담요약 생성 ({or_model_label or ''})"
else:
    _btn_label = "상담요약 생성 (규칙 기반)"

if st.button(_btn_label, disabled=summary_disabled, key="btn_summarize"):
    if sum_method == "Groq LLM (무료, 추천)":
        _spinner_msg = f"Groq LLM 요약 중... ({groq_model_id})"
        method = "groq"
        model = groq_model_id or "llama-3.3-70b-versatile"
    elif sum_method == "OpenRouter API":
        _spinner_msg = f"OpenRouter API 요약 중... ({or_model_id})"
        method = "openrouter"
        model = or_model_id or "meta-llama/llama-3.1-8b-instruct:free"
    else:
        _spinner_msg = "규칙 기반 요약 생성 중..."
        method = "rule"
        model = ""
    with st.spinner(_spinner_msg):
        try:
            summary_text = summarize(st.session_state.transcript, method=method, model=model)
            st.session_state.summary = summary_text
            if st.session_state.appointment is None:
                st.session_state.appointment = detect_appointment(st.session_state.transcript)
            st.success(f"요약 완료! ({method}: {model})")
        except Exception as e:
            st.error(f"요약 실패: {e}")

if st.session_state.summary:
    with st.expander("요약 결과 보기", expanded=True):
        st.markdown(st.session_state.summary)

# ── 4. 결과 저장 ──────────────────────────────────────────────────────────────
if st.session_state.summary:
    st.divider()
    st.header("4. 결과 저장")
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
                t_path = st.session_state.transcript_path or save_transcript(
                    st.session_state.transcript, st.session_state.stem
                )
                s_path = st.session_state.summary_md_path or save_summary_md(
                    st.session_state.summary, st.session_state.stem
                )
                fname = Path(st.session_state.upload_path).name if st.session_state.upload_path else "unknown"
                row_id = save_consultation(
                    original_filename=fname,
                    transcript_path=str(t_path),
                    summary_path=str(s_path),
                    transcript_text=st.session_state.transcript,
                    summary_text=st.session_state.summary,
                )
                st.success(f"DB 저장 완료! (ID: {row_id})")

                if tg_ok():
                    msg = tg_consultation_msg(fname, st.session_state.summary)
                    ok = tg_send(msg)
                    if ok:
                        st.success("텔레그램 전송 완료!")
                    else:
                        st.warning("텔레그램 전송 실패. 봇 토큰/Chat ID 확인.")
                else:
                    st.info("텔레그램 미설정 — 사이드바에서 설정하세요.")

                try:
                    cnt = increment_today()
                    if cnt:
                        st.caption(f"오늘 누적 상담: {cnt}건")
                except Exception:
                    pass

            except Exception as e:
                st.error(f"DB 저장 실패: {e}")

# ── 5. 구글 캘린더 연동 ───────────────────────────────────────────────────────
if st.session_state.transcript:
    appt = st.session_state.appointment or {}
    st.divider()
    st.header("5. 구글 캘린더 일정 등록")

    if appt.get("detected"):
        st.markdown(
            '<div class="calendar-card"><b>통화에서 일정 약속이 감지되었습니다.</b> 아래 내용을 확인하고 등록하세요.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("일정 약속이 자동 감지되지 않았습니다. 직접 입력해서 등록할 수 있습니다.")

    with st.form("cal_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            event_title = st.text_input(
                "일정 제목",
                value="전기안전관리 현장 방문",
            )
            default_date = datetime.now().date()
            if appt.get("date"):
                try:
                    from datetime import date
                    default_date = datetime.strptime(appt["date"], "%Y-%m-%d").date()
                except Exception:
                    pass
            event_date = st.date_input("날짜", value=default_date)

        with col_b:
            event_location = st.text_input(
                "장소",
                value=appt.get("location") or "",
                placeholder="예: 경기도 화성시 공장",
            )
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
            "메모",
            value=(st.session_state.summary or "")[:500],
            height=80,
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

# ── 6. 원본파일 관리 ──────────────────────────────────────────────────────────
st.divider()
st.header("6. 원본파일 관리")

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
