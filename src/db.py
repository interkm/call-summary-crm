import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "consultations.sqlite"


def _add_col(conn, table: str, col: str, col_type: str = "TEXT DEFAULT ''"):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
    except Exception:
        pass  # 이미 존재


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                original_filename TEXT,
                transcript_path TEXT,
                summary_path TEXT,
                transcript_text TEXT,
                summary_text TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT DEFAULT '',
                title TEXT DEFAULT '',
                company TEXT DEFAULT '',
                department TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                mobile TEXT DEFAULT '',
                email TEXT DEFAULT '',
                address TEXT DEFAULT '',
                website TEXT DEFAULT ''
            )
        """)
        conn.commit()
    migrate_db()


def migrate_db() -> None:
    """기존 DB에 CRM 컬럼 추가 (없으면)"""
    crm_cols = [
        ("grade", "TEXT DEFAULT ''"),
        ("grade_reason", "TEXT DEFAULT ''"),
        ("customer_name", "TEXT DEFAULT ''"),
        ("company_name", "TEXT DEFAULT ''"),
        ("phone", "TEXT DEFAULT ''"),
        ("region", "TEXT DEFAULT ''"),
        ("facility_type", "TEXT DEFAULT ''"),
        ("is_urgent", "TEXT DEFAULT ''"),
        ("needs_visit", "TEXT DEFAULT ''"),
        ("needs_quote", "TEXT DEFAULT ''"),
        ("wants_change_agency", "TEXT DEFAULT ''"),
        ("contract_expiry", "TEXT DEFAULT ''"),
        ("current_monthly_fee", "TEXT DEFAULT ''"),
        ("crm_json", "TEXT DEFAULT ''"),
    ]
    with sqlite3.connect(DB_PATH) as conn:
        for col, col_type in crm_cols:
            _add_col(conn, "consultations", col, col_type)
        conn.commit()


def save_consultation(
    original_filename: str,
    transcript_path: str,
    summary_path: str,
    transcript_text: str,
    summary_text: str,
    grade: str = "",
    grade_reason: str = "",
    customer_name: str = "",
    company_name: str = "",
    phone: str = "",
    region: str = "",
    facility_type: str = "",
    is_urgent: str = "",
    needs_visit: str = "",
    needs_quote: str = "",
    wants_change_agency: str = "",
    contract_expiry: str = "",
    current_monthly_fee: str = "",
    crm_json: str = "",
) -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO consultations (
                created_at, original_filename, transcript_path, summary_path,
                transcript_text, summary_text,
                grade, grade_reason, customer_name, company_name, phone,
                region, facility_type, is_urgent, needs_visit, needs_quote,
                wants_change_agency, contract_expiry, current_monthly_fee, crm_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                datetime.now().isoformat(),
                original_filename, str(transcript_path), str(summary_path),
                transcript_text, summary_text,
                grade, grade_reason, customer_name, company_name, phone,
                region, facility_type, is_urgent, needs_visit, needs_quote,
                wants_change_agency, contract_expiry, current_monthly_fee, crm_json,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def save_contact(info: dict) -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO contacts
               (created_at, name, title, company, department, phone, mobile, email, address, website)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                info.get("name", ""), info.get("title", ""),
                info.get("company", ""), info.get("department", ""),
                info.get("phone", ""), info.get("mobile", ""),
                info.get("email", ""), info.get("address", ""),
                info.get("website", ""),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_duplicates(phone: str = "", company_name: str = "", exclude_id: int = None) -> list:
    """전화번호 또는 회사명이 같은 기존 상담 기록"""
    init_db()
    if not phone and not company_name:
        return []
    conditions, params = [], []
    if phone:
        conditions.append("phone = ?")
        params.append(phone)
    if company_name:
        conditions.append("company_name = ?")
        params.append(company_name)
    where = " OR ".join(conditions)
    if exclude_id:
        where = f"({where}) AND id != ?"
        params.append(exclude_id)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM consultations WHERE {where} ORDER BY created_at DESC LIMIT 5",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def search_consultations(
    phone: str = "",
    customer_name: str = "",
    company_name: str = "",
    region: str = "",
    grade: str = "",
    needs_quote: str = "",
    needs_visit: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list:
    init_db()
    conditions, params = [], []

    def _like(col, val):
        if val:
            conditions.append(f"{col} LIKE ?")
            params.append(f"%{val}%")

    _like("phone", phone)
    _like("customer_name", customer_name)
    _like("company_name", company_name)
    _like("region", region)
    if grade:
        conditions.append("grade = ?")
        params.append(grade)
    if needs_quote:
        conditions.append("needs_quote = ?")
        params.append(needs_quote)
    if needs_visit:
        conditions.append("needs_visit = ?")
        params.append(needs_visit)
    if date_from:
        conditions.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= ?")
        params.append(date_to + "T23:59:59")

    where = " AND ".join(conditions) if conditions else "1=1"
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM consultations WHERE {where} ORDER BY created_at DESC LIMIT 200",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_contacts() -> list:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM contacts ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_contact(contact_id: int) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()


def search_contacts(keyword: str = "") -> list:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if keyword:
            rows = conn.execute(
                """SELECT * FROM contacts WHERE
                   name LIKE ? OR company LIKE ? OR phone LIKE ? OR mobile LIKE ? OR email LIKE ?
                   ORDER BY created_at DESC""",
                tuple(f"%{keyword}%" for _ in range(5)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_all_consultations() -> list:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM consultations ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
