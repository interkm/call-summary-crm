import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "consultations.sqlite"


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


def save_consultation(
    original_filename: str,
    transcript_path: str,
    summary_path: str,
    transcript_text: str,
    summary_text: str,
) -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO consultations
                (created_at, original_filename, transcript_path, summary_path, transcript_text, summary_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                original_filename,
                str(transcript_path),
                str(summary_path),
                transcript_text,
                summary_text,
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
                info.get("name", ""),
                info.get("title", ""),
                info.get("company", ""),
                info.get("department", ""),
                info.get("phone", ""),
                info.get("mobile", ""),
                info.get("email", ""),
                info.get("address", ""),
                info.get("website", ""),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_all_contacts() -> list:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
