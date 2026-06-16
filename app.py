import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.db import init_db, save_consultation
from src.storage import save_upload, save_transcript, save_summary_md, save_summary_txt
from src.summarizer import summarize
from src.transcriber import transcribe

# ── Startup ───────────────────────────────────────────────────────────────────
init_db()

st.set_page_config(
    page_title="통화녹음 상담요약기",
    page_icon="📞",
    layout="wide",
)

st.title("📞 통화녹음 상담요약기")
st.caption("통화녹음 파일을 올리면 전사하고 전기안전관리 상담기록으로 요약합니다.")

# ── Session state ─────────────────────────────────────────────────────────────
_DEFAULTS = {
    "transcript": None,
    "summary": None,
    "upload_path": None,
    "stem": None,
    "transcript_path": None,
    "summary_md_path": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")
    model_size = st.selectbox(
        "Whisper 모델",
        ["tiny", "base", "small"],
        index=2,
        help="tiny: 빠름/낮은정확도 | base: 중간 | small: 권장",
    )
    st.caption("처음 실행 시 모델을 자동 다운로드합니다.")
    st.caption("GPU 없으면 CPU로 자동 전환됩니다.")
    st.divider()
    st.markdown("**저장 경로**")
    st.code("data/uploads/\ndata/transcripts/\ndata/summaries/\ndb/consultations.sqlite")

# ── 1. 파일 업로드 ─────────────────────────────────────────────────────────────
st.header("1️⃣ 녹음파일 업로드")

ALLOWED_EXT = {"m4a", "mp3", "wav", "mp4", "aac", "ogg", "amr", "3gp", "wma", "flac"}

uploaded = st.file_uploader(
    "통화녹음 파일 선택 (m4a, mp3, wav, amr 등)",
    type=None,  # 모바일 호환성: 브라우저 필터 제거, 수동 검증
    help="m4a · mp3 · wav · amr · 3gp · aac · ogg 지원. 모바일에서 파일 앱 또는 갤러리에서 선택하세요.",
)

if uploaded is not None:
    ext = Path(uploaded.name).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXT:
        st.error(f"지원하지 않는 형식: .{ext} — 오디오 파일을 선택해주세요.")
        uploaded = None

if uploaded is not None:
    try:
        st.audio(uploaded)
    except Exception:
        st.info(f"미리듣기 미지원 형식 ({Path(uploaded.name).suffix}) — 업로드는 가능합니다.")
    if st.button("💾 파일 저장", key="btn_save_upload"):
        try:
            path = save_upload(uploaded.getvalue(), uploaded.name)
            st.session_state.upload_path = path
            st.session_state.stem = Path(uploaded.name).stem
            st.session_state.transcript = None
            st.session_state.summary = None
            st.session_state.transcript_path = None
            st.session_state.summary_md_path = None
            st.success(f"저장 완료: `{path}`")
        except Exception as e:
            st.error(f"파일 저장 실패: {e}")

# ── 2. 음성 전사 ──────────────────────────────────────────────────────────────
st.divider()
st.header("2️⃣ 음성 전사")

transcribe_disabled = st.session_state.upload_path is None

if transcribe_disabled:
    st.info("먼저 녹음파일을 업로드하고 💾 파일 저장을 눌러주세요.")

if st.button("🎙️ 전사 시작", disabled=transcribe_disabled, key="btn_transcribe"):
    with st.spinner(f"전사 중... 모델: **{model_size}** (GPU 없으면 CPU 자동 전환, 수 분 소요 가능)"):
        try:
            text = transcribe(Path(st.session_state.upload_path), model_size)
            if not text.strip():
                st.warning("전사 결과가 비어 있습니다. 파일이 정상인지 확인하세요.")
            else:
                st.session_state.transcript = text
                t_path = save_transcript(text, st.session_state.stem)
                st.session_state.transcript_path = t_path
                st.success(f"전사 완료! ({len(text)}자) — 저장: `{t_path}`")
        except Exception as e:
            st.error(f"전사 실패: {e}")
            st.error("해결 방법: 더 작은 모델(tiny)을 선택하거나 파일 형식을 wav로 변환해보세요.")

if st.session_state.transcript:
    st.text_area(
        "전사 결과",
        value=st.session_state.transcript,
        height=200,
        key="ta_transcript",
    )

# ── 3. 상담요약 생성 ───────────────────────────────────────────────────────────
st.divider()
st.header("3️⃣ 상담요약 생성")

summary_disabled = st.session_state.transcript is None

if summary_disabled and not transcribe_disabled:
    st.info("전사를 먼저 완료하세요.")

if st.button("📝 상담요약 생성", disabled=summary_disabled, key="btn_summarize"):
    with st.spinner("요약 생성 중..."):
        try:
            summary_text = summarize(st.session_state.transcript, method="rule")
            st.session_state.summary = summary_text
            st.success("요약 생성 완료!")
        except Exception as e:
            st.error(f"요약 실패: {e}")

if st.session_state.summary:
    with st.expander("요약 결과 보기", expanded=True):
        st.markdown(st.session_state.summary)

# ── 4. 결과 저장 ──────────────────────────────────────────────────────────────
if st.session_state.summary:
    st.divider()
    st.header("4️⃣ 결과 저장")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 Markdown 저장", key="btn_md"):
            try:
                p = save_summary_md(st.session_state.summary, st.session_state.stem)
                st.session_state.summary_md_path = p
                st.success(f"저장: `{p}`")
            except Exception as e:
                st.error(f"저장 실패: {e}")

    with col2:
        if st.button("📄 TXT 저장", key="btn_txt"):
            try:
                p = save_summary_txt(st.session_state.summary, st.session_state.stem)
                st.success(f"저장: `{p}`")
            except Exception as e:
                st.error(f"저장 실패: {e}")

    with col3:
        if st.button("🗄️ DB 저장", key="btn_db"):
            try:
                t_path = st.session_state.transcript_path or save_transcript(
                    st.session_state.transcript, st.session_state.stem
                )
                s_path = st.session_state.summary_md_path or save_summary_md(
                    st.session_state.summary, st.session_state.stem
                )
                row_id = save_consultation(
                    original_filename=Path(st.session_state.upload_path).name
                    if st.session_state.upload_path
                    else "unknown",
                    transcript_path=str(t_path),
                    summary_path=str(s_path),
                    transcript_text=st.session_state.transcript,
                    summary_text=st.session_state.summary,
                )
                st.success(f"DB 저장 완료! (ID: {row_id})")
            except Exception as e:
                st.error(f"DB 저장 실패: {e}")

# ── 5. 원본파일 관리 ──────────────────────────────────────────────────────────
st.divider()
st.header("5️⃣ 원본파일 관리")

if st.session_state.upload_path:
    upload_path = Path(st.session_state.upload_path)
    if upload_path.exists():
        st.warning(f"원본파일 위치: `{upload_path}`")
        if st.button("🗑️ 원본파일 삭제", type="secondary", key="btn_delete"):
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
