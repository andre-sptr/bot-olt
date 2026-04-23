"""
database.py — Modul manajemen SQLite + FTS5 untuk penyimpanan pesan Telegram.

Menyediakan fungsi CRUD dan full-text search yang di-index untuk pencarian
cepat meskipun data pesan mencapai ratusan ribu record.
"""

import sqlite3
import os
import sys
import io
import json
from datetime import datetime
from typing import Optional

# Fix encoding untuk Windows console
if sys.platform == "win32" and not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "messages.db")


def get_connection() -> sqlite3.Connection:
    """Membuat koneksi SQLite dengan WAL mode untuk performa concurrency."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Inisialisasi skema database dan FTS5 index."""
    conn = get_connection()
    try:
        conn.executescript("""
            -- Tabel utama pesan
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id      INTEGER UNIQUE NOT NULL,
                sender_name     TEXT DEFAULT 'Unknown',
                sender_id       INTEGER,
                text            TEXT NOT NULL,
                date            DATETIME NOT NULL,
                reply_to_msg_id INTEGER,
                category        TEXT DEFAULT 'BELUM_DIPROSES',
                summary         TEXT,
                keywords        TEXT,
                importance      INTEGER DEFAULT 0,
                is_processed    INTEGER DEFAULT 0,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- FTS5 Virtual Table untuk full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                text,
                summary,
                keywords,
                sender_name,
                content='messages',
                content_rowid='id',
                tokenize='unicode61'
            );

            -- Trigger untuk menjaga sinkronisasi FTS dengan tabel utama
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, text, summary, keywords, sender_name)
                VALUES (new.id, new.text, new.summary, new.keywords, new.sender_name);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, text, summary, keywords, sender_name)
                VALUES ('delete', old.id, old.text, old.summary, old.keywords, old.sender_name);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, text, summary, keywords, sender_name)
                VALUES ('delete', old.id, old.text, old.summary, old.keywords, old.sender_name);
                INSERT INTO messages_fts(rowid, text, summary, keywords, sender_name)
                VALUES (new.id, new.text, new.summary, new.keywords, new.sender_name);
            END;

            -- Tabel log sesi scraping
            CREATE TABLE IF NOT EXISTS scrape_sessions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id        INTEGER NOT NULL,
                last_msg_id     INTEGER,
                scraped_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_msgs      INTEGER DEFAULT 0,
                mode            TEXT DEFAULT 'history'
            );

            -- Index untuk query umum
            CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
            CREATE INDEX IF NOT EXISTS idx_messages_category ON messages(category);
            CREATE INDEX IF NOT EXISTS idx_messages_processed ON messages(is_processed);
            CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
        """)
        conn.commit()
        print("[DB] ✅ Database berhasil diinisialisasi.")
    except Exception as e:
        print(f"[DB] ❌ Error inisialisasi: {e}")
        raise
    finally:
        conn.close()


def insert_message(
    message_id: int,
    sender_name: str,
    sender_id: int,
    text: str,
    date: datetime,
    reply_to_msg_id: Optional[int] = None,
) -> bool:
    """Menyimpan satu pesan ke database. Return True jika berhasil."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO messages
               (message_id, sender_name, sender_id, text, date, reply_to_msg_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (message_id, sender_name, sender_id, text, date.isoformat(), reply_to_msg_id),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] ❌ Insert error msg_id={message_id}: {e}")
        return False
    finally:
        conn.close()


def insert_messages_batch(messages: list[dict]) -> int:
    """Batch insert pesan. Return jumlah pesan yang berhasil disimpan."""
    conn = get_connection()
    inserted = 0
    try:
        cursor = conn.executemany(
            """INSERT OR IGNORE INTO messages
               (message_id, sender_name, sender_id, text, date, reply_to_msg_id)
               VALUES (:message_id, :sender_name, :sender_id, :text, :date, :reply_to_msg_id)""",
            messages,
        )
        inserted = cursor.rowcount
        conn.commit()
    except Exception as e:
        print(f"[DB] ❌ Batch insert error: {e}")
        conn.rollback()
    finally:
        conn.close()
    return inserted


def get_unprocessed_messages(limit: int = 50) -> list[sqlite3.Row]:
    """Ambil pesan yang belum diproses oleh Gemini."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, message_id, sender_name, text, date FROM messages "
            "WHERE is_processed = 0 ORDER BY date ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return rows
    except Exception as e:
        print(f"[DB] ❌ Query error: {e}")
        return []
    finally:
        conn.close()


def update_processed_message(
    msg_db_id: int,
    category: str,
    summary: str,
    keywords: list[str],
    importance: int,
) -> None:
    """Update pesan setelah diproses oleh Gemini."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE messages
               SET category = ?, summary = ?, keywords = ?,
                   importance = ?, is_processed = 1
               WHERE id = ?""",
            (category, summary, json.dumps(keywords, ensure_ascii=False), importance, msg_db_id),
        )
        conn.commit()
    except Exception as e:
        print(f"[DB] ❌ Update error id={msg_db_id}: {e}")
    finally:
        conn.close()


def search_messages_fts(query: str, limit: int = 30) -> list[sqlite3.Row]:
    """Full-text search menggunakan FTS5 index."""
    conn = get_connection()
    try:
        # Escape query untuk FTS5 safety
        safe_query = query.replace('"', '""')
        rows = conn.execute(
            """SELECT m.id, m.message_id, m.sender_name, m.text, m.date,
                      m.category, m.summary, m.keywords, m.importance,
                      rank
               FROM messages_fts fts
               JOIN messages m ON m.id = fts.rowid
               WHERE messages_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (f'"{safe_query}"', limit),
        ).fetchall()
        return rows
    except Exception as e:
        print(f"[DB] ❌ FTS search error: {e}")
        return []
    finally:
        conn.close()


def search_messages_like(query: str, limit: int = 30) -> list[sqlite3.Row]:
    """Fallback search menggunakan LIKE jika FTS tidak memberikan hasil."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, message_id, sender_name, text, date,
                      category, summary, keywords, importance
               FROM messages
               WHERE text LIKE ? OR summary LIKE ? OR keywords LIKE ?
               ORDER BY date DESC
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return rows
    except Exception as e:
        print(f"[DB] ❌ LIKE search error: {e}")
        return []
    finally:
        conn.close()


def get_recent_messages(limit: int = 50) -> list[sqlite3.Row]:
    """Ambil pesan terbaru yang sudah diproses."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, message_id, sender_name, text, date,
                      category, summary, keywords, importance
               FROM messages
               WHERE is_processed = 1
               ORDER BY date DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return rows
    except Exception as e:
        print(f"[DB] ❌ Query error: {e}")
        return []
    finally:
        conn.close()


def get_messages_by_category(category: str, limit: int = 30) -> list[sqlite3.Row]:
    """Ambil pesan berdasarkan kategori."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, message_id, sender_name, text, date,
                      summary, keywords, importance
               FROM messages
               WHERE category = ? AND is_processed = 1
               ORDER BY date DESC
               LIMIT ?""",
            (category.upper(), limit),
        ).fetchall()
        return rows
    except Exception as e:
        print(f"[DB] ❌ Query error: {e}")
        return []
    finally:
        conn.close()


def get_db_stats() -> dict:
    """Statistik database untuk command /status."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        processed = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_processed = 1"
        ).fetchone()[0]
        unprocessed = total - processed

        categories = conn.execute(
            """SELECT category, COUNT(*) as cnt
               FROM messages WHERE is_processed = 1
               GROUP BY category ORDER BY cnt DESC"""
        ).fetchall()

        latest = conn.execute(
            "SELECT date FROM messages ORDER BY date DESC LIMIT 1"
        ).fetchone()
        oldest = conn.execute(
            "SELECT date FROM messages ORDER BY date ASC LIMIT 1"
        ).fetchone()

        return {
            "total": total,
            "processed": processed,
            "unprocessed": unprocessed,
            "categories": {row["category"]: row["cnt"] for row in categories},
            "latest_date": latest["date"] if latest else None,
            "oldest_date": oldest["date"] if oldest else None,
        }
    except Exception as e:
        print(f"[DB] ❌ Stats error: {e}")
        return {}
    finally:
        conn.close()


def log_scrape_session(group_id: int, last_msg_id: int, total_msgs: int, mode: str = "history") -> None:
    """Catat sesi scraping."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO scrape_sessions (group_id, last_msg_id, total_msgs, mode) VALUES (?, ?, ?, ?)",
            (group_id, last_msg_id, total_msgs, mode),
        )
        conn.commit()
    except Exception as e:
        print(f"[DB] ❌ Log session error: {e}")
    finally:
        conn.close()


def get_last_scraped_msg_id(group_id: int) -> Optional[int]:
    """Ambil message_id terakhir yang di-scrape untuk incremental scraping."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT last_msg_id FROM scrape_sessions WHERE group_id = ? ORDER BY scraped_at DESC LIMIT 1",
            (group_id,),
        ).fetchone()
        return row["last_msg_id"] if row else None
    except Exception as e:
        print(f"[DB] ❌ Query error: {e}")
        return None
    finally:
        conn.close()


# ==================== SELF-TEST ====================
if __name__ == "__main__":
    print("🔧 Menginisialisasi database...")
    init_db()

    stats = get_db_stats()
    print(f"\n📊 Statistik DB:")
    print(f"   Total pesan  : {stats.get('total', 0)}")
    print(f"   Diproses     : {stats.get('processed', 0)}")
    print(f"   Belum proses : {stats.get('unprocessed', 0)}")
    print(f"\n✅ Database siap digunakan: {DB_PATH}")
