"""
Persistence, Audit Logging, and Suppression Tracking Engine
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional, Any


class OutreachTracker:
    """Manages SQLite campaign history, duplicate prevention, and opt-out suppression."""

    def __init__(self, db_path: Path, suppression_path: Path):
        self.db_path = Path(db_path)
        self.suppression_path = Path(suppression_path)
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.suppression_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._init_suppression()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outreach_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    company TEXT,
                    job_title TEXT,
                    status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED, DRAFTED, SENT, FAILED
                    tier INTEGER DEFAULT 1,
                    template_key TEXT,
                    subject TEXT,
                    gmail_draft_id TEXT,
                    gmail_message_id TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cursor.execute("ALTER TABLE outreach_log ADD COLUMN tier INTEGER DEFAULT 1")
            except Exception:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_quota_tracker (
                    send_date TEXT PRIMARY KEY,
                    drafts_count INTEGER DEFAULT 0,
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def _init_suppression(self):
        if not self.suppression_path.exists():
            with open(self.suppression_path, "w", encoding="utf-8") as f:
                json.dump({"opt_outs": [], "bounced": []}, f, indent=2)

    def is_suppressed(self, email: str) -> bool:
        """Check if an email is in the suppression list."""
        email_clean = email.strip().lower()
        try:
            with open(self.suppression_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                suppressed = set(data.get("opt_outs", []) + data.get("bounced", []))
                return email_clean in suppressed
        except Exception:
            return False

    def add_to_suppression(self, email: str, category: str = "opt_outs"):
        """Add an email address to the suppression list."""
        email_clean = email.strip().lower()
        with open(self.suppression_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if email_clean not in data.setdefault(category, []):
            data[category].append(email_clean)
            with open(self.suppression_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    def is_already_contacted(self, email: str) -> bool:
        """Check if an email has already been drafted or sent."""
        email_clean = email.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM outreach_log WHERE email = ? AND status IN ('DRAFTED', 'SENT')",
                (email_clean,)
            )
            return cursor.fetchone() is not None

    def upsert_contact_status(
        self,
        email: str,
        name: str = "",
        company: str = "",
        job_title: str = "",
        status: str = "PENDING",
        tier: int = 1,
        template_key: Optional[str] = None,
        subject: Optional[str] = None,
        draft_id: Optional[str] = None,
        message_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update or insert contact outreach status in SQLite."""
        email_clean = email.strip().lower()
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO outreach_log (
                    email, name, company, job_title, status, tier, template_key, 
                    subject, gmail_draft_id, gmail_message_id, error_message, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    status=excluded.status,
                    tier=COALESCE(excluded.tier, outreach_log.tier),
                    template_key=COALESCE(excluded.template_key, outreach_log.template_key),
                    subject=COALESCE(excluded.subject, outreach_log.subject),
                    gmail_draft_id=COALESCE(excluded.gmail_draft_id, outreach_log.gmail_draft_id),
                    gmail_message_id=COALESCE(excluded.gmail_message_id, outreach_log.gmail_message_id),
                    error_message=excluded.error_message,
                    updated_at=excluded.updated_at
            """, (
                email_clean, name, company, job_title, status, tier, template_key,
                subject, draft_id, message_id, error_message, now
            ))
            conn.commit()

    def get_approved_contacts(self, tier: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch approved contacts, optionally filtered by tier."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT email, name, company, job_title, tier, template_key FROM outreach_log WHERE status = 'APPROVED'"
            params = []
            if tier is not None:
                query += " AND tier = ?"
                params.append(tier)
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def increment_daily_counter(self, counter_type: str = "drafts_count"):
        """Track daily activity counts."""
        today_str = date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_quota_tracker (send_date, drafts_count, sent_count, failed_count)
                VALUES (?, 0, 0, 0)
                ON CONFLICT(send_date) DO NOTHING
            """, (today_str,))
            
            if counter_type in ["drafts_count", "sent_count", "failed_count"]:
                cursor.execute(f"""
                    UPDATE daily_quota_tracker
                    SET {counter_type} = {counter_type} + 1
                    WHERE send_date = ?
                """, (today_str,))
            conn.commit()

    def get_daily_count(self, counter_type: str = "sent_count") -> int:
        """Get today's count for a given metric."""
        today_str = date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {counter_type} FROM daily_quota_tracker WHERE send_date = ?", (today_str,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_summary_stats(self) -> Dict[str, Any]:
        """Return aggregate summary metrics across the campaign."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM outreach_log GROUP BY status")
            status_counts = dict(cursor.fetchall())
            
            cursor.execute("SELECT COUNT(*) FROM outreach_log")
            total = cursor.fetchone()[0]

        suppressed_count = 0
        try:
            with open(self.suppression_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                suppressed_count = len(set(data.get("opt_outs", []) + data.get("bounced", [])))
        except Exception:
            pass

        return {
            "total_logged": total,
            "status_breakdown": status_counts,
            "suppressed_contacts": suppressed_count,
            "drafts_today": self.get_daily_count("drafts_count"),
            "sent_today": self.get_daily_count("sent_count")
        }

    def delete_contact(self, email: str) -> bool:
        """Permanently delete a contact from outreach_log."""
        email_clean = email.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM outreach_log WHERE email = ?", (email_clean,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    def get_contact(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch single contact details by email."""
        email_clean = email.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM outreach_log WHERE email = ?", (email_clean,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_contacts(self) -> List[Dict[str, Any]]:
        """Fetch all tracked contacts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM outreach_log")
            return [dict(r) for r in cursor.fetchall()]
