# 통화녹음 상담요약기

전기안전관리 영업용 통화녹음 상담요약 도구.
m4a / mp3 / wav 녹음파일을 업로드하면 한국어 전사 후 전기안전관리 상담 형식으로 요약합니다.

---

## 실행 방법

```powershell
cd C:\Projects\call-summary-crm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 자동 열림.

---

## PowerShell 실행정책 오류 발생 시

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

이후 다시 `.\.venv\Scripts\Activate.ps1` 실행.

---

## 기능

| 단계 | 기능 |
|------|------|
| 1 | m4a / mp3 / wav 파일 업로드 및 저장 |
| 2 | faster-whisper 한국어 음성 전사 |
| 3 | 전기안전관리 형식 자동 요약 |
| 4 | Markdown / TXT 저장 + SQLite DB 저장 |
| 5 | 원본 녹음파일 삭제 |

---

## 모델 선택

| 모델 | 속도 | 정확도 | 비고 |
|------|------|--------|------|
| tiny | 가장 빠름 | 낮음 | 테스트/빠른 확인용 |
| base | 중간 | 중간 | - |
| small | 느림 | 높음 | 기본값 (권장) |

- 처음 실행 시 선택 모델을 자동 다운로드합니다 (수백 MB).
- GPU 없는 환경에서는 CPU로 자동 전환됩니다.

---

## 프로젝트 구조

```
call-summary-crm/
  app.py                   # Streamlit 메인 앱
  requirements.txt
  README.md
  data/
    uploads/YYYYMMDD/      # 업로드 녹음파일 (날짜별)
    transcripts/YYYYMMDD/  # 전사 텍스트 (날짜별)
    summaries/YYYYMMDD/    # 요약 결과 MD/TXT (날짜별)
  db/
    consultations.sqlite   # 상담 기록 DB
  src/
    transcriber.py         # faster-whisper 전사
    summarizer.py          # 요약 (규칙 기반 / API 확장 가능)
    storage.py             # 날짜별 파일 저장
    db.py                  # SQLite CRUD
    prompts.py             # 프롬프트 템플릿
```

---

## 요약 출력 항목

- 통화 핵심 요약
- 고객 요청사항
- 현장 정보 (지역 / 시설유형 / 수전용량 / 변압기 용량 / 비상발전기 / 태양광 / 현재 문제)
- 견적 산정에 필요한 추가 질문
- 다음 액션
- 영업 메모
- 블로그/스레드 홍보 소재

---

## API 요약 연동 (향후)

`src/summarizer.py` 하단의 `_summarize_with_openai()` 주석을 해제하고
`OPENAI_API_KEY` 환경변수를 설정하면 OpenAI / OpenRouter 기반 요약으로 전환할 수 있습니다.
