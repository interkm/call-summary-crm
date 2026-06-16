"""
Business card OCR via Groq Vision API + phone extraction from filename.
"""

import re
import base64
import json
import requests


_PHONE_RE = re.compile(r'01[016789][-\s]?\d{3,4}[-\s]?\d{4}')


def extract_phone_from_filename(filename: str) -> str:
    m = _PHONE_RE.search(filename)
    if not m:
        return ""
    digits = re.sub(r'[^\d]', '', m.group())
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return m.group()


_CARD_PROMPT = """\
이 명함 이미지에서 아래 정보를 추출하세요.
없는 항목은 빈 문자열("")로 두세요.
JSON만 출력하세요 (설명 없이):

{
  "name": "",
  "title": "",
  "company": "",
  "department": "",
  "phone": "",
  "mobile": "",
  "email": "",
  "address": "",
  "website": ""
}"""

_VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
]


def ocr_business_card(image_bytes: bytes, api_key: str, filename: str = "card.jpg") -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "heic": "image/jpeg", "heif": "image/jpeg"}.get(ext, "image/jpeg")
    b64 = base64.b64encode(image_bytes).decode()

    last_err = None
    for model in _VISION_MODELS:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                            {"type": "text", "text": _CARD_PROMPT},
                        ],
                    }],
                    "max_tokens": 600,
                    "temperature": 0.1,
                },
                timeout=60,
            )
            if resp.ok:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                try:
                    m = re.search(r'\{[\s\S]*\}', content)
                    if m:
                        return json.loads(m.group())
                except Exception:
                    pass
                return {"name": "", "company": "", "phone": "", "_raw": content}
            last_err = f"{resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"Groq Vision 오류: {last_err}")
