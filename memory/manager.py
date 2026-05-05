"""memory/manager.py - SQLite-backed memory, profile, projects, and knowledge."""

import datetime
import json
import sqlite3
import threading
from pathlib import Path

from config.logger import get_logger
from config.settings import DB_PATH, FALLBACK_DB_PATH, USER_NAME

log = get_logger("memory")

STOP_WORDS = {
    "about", "after", "again", "also", "am", "an", "and", "are", "as", "at",
    "be", "because", "been", "before", "being", "but", "by", "can", "did",
    "do", "does", "for", "from", "had", "has", "have", "here", "how", "i",
    "if", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or",
    "our", "please", "remember", "save", "show", "tell", "that", "the",
    "their", "them", "there", "they", "this", "to", "update", "was", "we",
    "what", "when", "where", "who", "why", "with", "you", "your",
}


class MemoryManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.db_path = None
        self.conn = self._connect()
        try:
            self._init_db()
        except sqlite3.Error as exc:
            if self.db_path == FALLBACK_DB_PATH:
                log.warning(f"Resetting broken fallback memory database: {exc}")
                try:
                    self.conn.close()
                except Exception:
                    pass
                self._cleanup_db_files(FALLBACK_DB_PATH)
                self.conn = self._connect(prefer_fallback=True)
                self._init_db()
            else:
                raise

    def _connect(self, prefer_fallback: bool = False):
        base_candidates = (FALLBACK_DB_PATH,) if prefer_fallback else (DB_PATH, FALLBACK_DB_PATH)
        candidates = []
        for path in base_candidates:
            if path not in candidates:
                candidates.append(path)

        last_error = None
        for path in candidates:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
                conn.execute("PRAGMA journal_mode=MEMORY")
                conn.execute("PRAGMA synchronous=OFF")
                conn.execute("PRAGMA temp_store=MEMORY")
                conn.execute("SELECT 1")
                self.db_path = path
                if path != DB_PATH:
                    log.warning(f"Using fallback memory database at {path}")
                return conn
            except sqlite3.Error as exc:
                last_error = exc
                log.warning(f"Memory DB unavailable at {path}: {exc}")
        raise last_error

    def _cleanup_db_files(self, path: Path):
        for suffix in ("", "-journal", "-wal", "-shm"):
            target = Path(str(path) + suffix)
            try:
                if target.exists():
                    target.unlink()
            except OSError as exc:
                log.warning(f"Could not remove broken SQLite file {target}: {exc}")

    def _init_db(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT,
                created TEXT
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_text TEXT,
                jarvis_text TEXT,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                remind_at TEXT,
                done INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT,
                done INTEGER DEFAULT 0,
                created TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                created TEXT
            );
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'whatsapp',
                created TEXT NOT NULL,
                UNIQUE(name, channel)
            );
            CREATE TABLE IF NOT EXISTS profile_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL DEFAULT 'general',
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                UNIQUE(category, key)
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                next_steps TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_path TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                steps_json TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                last_run TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                objective TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                next_action TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                plan_json TEXT NOT NULL DEFAULT '[]',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return "".join(ch for ch in (phone or "") if ch.isdigit())

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join((text or "").strip().split())

    def _keywords(self, text: str) -> set[str]:
        words = set()
        for token in (text or "").lower().replace("/", " ").replace("-", " ").split():
            clean = "".join(ch for ch in token if ch.isalnum())
            if len(clean) >= 3 and clean not in STOP_WORDS:
                words.add(clean)
        return words

    def _score_text(self, query: str, haystack: str, bonus: int = 0) -> int:
        query_words = self._keywords(query)
        text = (haystack or "").lower()
        if not query_words:
            return 0

        score = bonus
        for word in query_words:
            if word in text:
                score += 3
        phrase = self._normalize_text(query).lower()
        if phrase and len(phrase) > 6 and phrase in text:
            score += 4
        return score

    def _best_key_from_text(self, text: str) -> str:
        cleaned = self._normalize_text(text)
        if " is " in cleaned.lower():
            return cleaned.split(" is ", 1)[0].strip().lower()[:80]
        if ":" in cleaned:
            return cleaned.split(":", 1)[0].strip().lower()[:80]
        words = cleaned.split()
        return " ".join(words[:5]).lower()[:80] if words else "note"

    def _summarize_text(self, text: str, limit: int = 220) -> str:
        cleaned = self._normalize_text(text)
        if len(cleaned) <= limit:
            return cleaned
        cutoff = cleaned[:limit].rsplit(" ", 1)[0].strip()
        return (cutoff or cleaned[:limit]).strip() + "..."

    def store_fact(self, text: str) -> str:
        cleaned = self._normalize_text(text)
        now = datetime.datetime.now().isoformat()
        key = self._best_key_from_text(cleaned)
        with self._lock:
            self.conn.execute(
                "INSERT INTO facts (key, value, created) VALUES (?, ?, ?)",
                (key, cleaned, now),
            )
            self.conn.commit()
        return f"Remembered: {cleaned}"

    def recall_fact(self, query: str) -> str:
        results = self.search_knowledge(query, limit=5)
        if not results:
            return f"Nothing relevant stored yet, {USER_NAME}."
        lines = []
        for item in results:
            label = item["kind"].replace("_", " ").title()
            title = f"{item['title']}: " if item.get("title") else ""
            lines.append(f"- {label}: {title}{item['content']}")
        return "Here's what I found:\n" + "\n".join(lines)

    def forget(self, query: str) -> str:
        with self._lock:
            self.conn.execute("DELETE FROM facts")
            self.conn.execute("DELETE FROM notes")
            self.conn.execute("DELETE FROM profile_entries")
            self.conn.execute("DELETE FROM projects")
            self.conn.execute("DELETE FROM knowledge_docs")
            self.conn.execute("DELETE FROM workflows")
            self.conn.execute("DELETE FROM missions")
            self.conn.execute("DELETE FROM contacts")
            self.conn.commit()
        return f"Advanced memory cleared, {USER_NAME}."

    def get_all_facts(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT key, value, created FROM facts ORDER BY id DESC"
            ).fetchall()
        return [{"key": row[0], "value": row[1], "created": row[2]} for row in rows]

    def find_relevant_facts(self, query: str, limit: int = 5) -> list:
        results = [item for item in self.search_knowledge(query, limit=limit * 2) if item["kind"] == "fact"]
        return [{"value": item["content"], "created": item["created"]} for item in results[:limit]]

    def add_history(self, user: str, jarvis: str):
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute(
                "INSERT INTO history (user_text, jarvis_text, timestamp) VALUES (?, ?, ?)",
                (user, jarvis, now),
            )
            self.conn.commit()

    def get_history(self, limit: int = 50) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT user_text, jarvis_text, timestamp FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"user": row[0], "jarvis": row[1], "time": row[2]} for row in reversed(rows)]

    def add_reminder(self, task: str, time_str: str) -> str:
        with self._lock:
            self.conn.execute("INSERT INTO reminders (task, remind_at) VALUES (?, ?)", (task, time_str))
            self.conn.commit()
        return f"Reminder set: '{task}' at {time_str}."

    def get_pending_reminders(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, task, remind_at FROM reminders WHERE done=0"
            ).fetchall()
        return [{"id": row[0], "task": row[1], "time": row[2]} for row in rows]

    def mark_reminder_done(self, rid: int):
        with self._lock:
            self.conn.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
            self.conn.commit()

    def add_todo(self, item: str) -> str:
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute("INSERT INTO todos (item, created) VALUES (?, ?)", (item, now))
            self.conn.commit()
        return f"Added to your to-do list: '{item}'"

    def get_todos(self) -> list:
        with self._lock:
            rows = self.conn.execute("SELECT id, item, done FROM todos WHERE done=0").fetchall()
        return [{"id": row[0], "item": row[1], "done": row[2]} for row in rows]

    def add_note(self, content: str) -> str:
        cleaned = self._normalize_text(content)
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute("INSERT INTO notes (content, created) VALUES (?, ?)", (cleaned, now))
            self.conn.commit()
        return f"Note saved, {USER_NAME}."

    def get_notes(self) -> list:
        with self._lock:
            rows = self.conn.execute("SELECT content, created FROM notes ORDER BY id DESC").fetchall()
        return [{"content": row[0], "created": row[1]} for row in rows]

    def save_contact(self, name: str, phone: str, channel: str = "whatsapp") -> tuple[bool, str]:
        clean_name = (name or "").strip().lower()
        clean_phone = self._normalize_phone(phone)
        clean_channel = (channel or "whatsapp").strip().lower()
        if not clean_name:
            return False, "Contact name is missing."
        if len(clean_phone) < 8:
            return False, "Phone number looks incomplete."
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO contacts (name, phone, channel, created)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name, channel) DO UPDATE SET
                    phone=excluded.phone,
                    created=excluded.created
                """,
                (clean_name, clean_phone, clean_channel, now),
            )
            self.conn.commit()
        return True, clean_phone

    def get_contact_phone(self, name: str, channel: str = "whatsapp") -> str:
        clean_name = (name or "").strip().lower()
        clean_channel = (channel or "whatsapp").strip().lower()
        if not clean_name:
            return ""
        with self._lock:
            exact = self.conn.execute(
                "SELECT phone FROM contacts WHERE channel=? AND name=?",
                (clean_channel, clean_name),
            ).fetchone()
            if exact:
                return exact[0]
            rows = self.conn.execute(
                "SELECT name, phone FROM contacts WHERE channel=? ORDER BY name",
                (clean_channel,),
            ).fetchall()
        for saved_name, phone in rows:
            if clean_name in saved_name or saved_name in clean_name:
                return phone
        return ""

    def list_contacts(self, channel: str = "whatsapp") -> list:
        clean_channel = (channel or "whatsapp").strip().lower()
        with self._lock:
            rows = self.conn.execute(
                "SELECT name, phone, created FROM contacts WHERE channel=? ORDER BY name",
                (clean_channel,),
            ).fetchall()
        return [{"name": row[0], "phone": row[1], "created": row[2]} for row in rows]

    def save_profile_item(self, text: str, category: str = "general") -> str:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return f"Profile detail was empty, {USER_NAME}."
        key = self._best_key_from_text(cleaned)
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO profile_entries (category, key, value, created, updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value=excluded.value,
                    updated=excluded.updated
                """,
                ((category or "general").strip().lower(), key, cleaned, now, now),
            )
            self.conn.commit()
        return f"Profile memory saved: {cleaned}"

    def get_profile_entries(self, category: str | None = None, limit: int = 20) -> list:
        with self._lock:
            if category:
                rows = self.conn.execute(
                    """
                    SELECT category, key, value, updated
                    FROM profile_entries
                    WHERE category=?
                    ORDER BY updated DESC
                    LIMIT ?
                    """,
                    (category.strip().lower(), limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT category, key, value, updated
                    FROM profile_entries
                    ORDER BY updated DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [{"category": row[0], "key": row[1], "value": row[2], "updated": row[3]} for row in rows]

    def profile_summary(self, limit: int = 10) -> str:
        entries = self.get_profile_entries(limit=limit)
        if not entries:
            return f"No profile memory saved yet, {USER_NAME}."
        lines = [f"- {entry['value']}" for entry in entries]
        return "Profile memory:\n" + "\n".join(lines)

    def save_project(
        self,
        name: str,
        details: str,
        status: str = "",
        next_steps: str = "",
        tags: str = "",
    ) -> str:
        clean_name = self._normalize_text(name)
        clean_details = self._normalize_text(details)
        if not clean_name or not clean_details:
            return f"Project name or details are missing, {USER_NAME}."
        now = datetime.datetime.now().isoformat()
        summary = self._summarize_text(clean_details, limit=180)
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO projects (name, summary, details, status, next_steps, tags, created, updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    summary=excluded.summary,
                    details=excluded.details,
                    status=CASE WHEN excluded.status != '' THEN excluded.status ELSE projects.status END,
                    next_steps=CASE WHEN excluded.next_steps != '' THEN excluded.next_steps ELSE projects.next_steps END,
                    tags=CASE WHEN excluded.tags != '' THEN excluded.tags ELSE projects.tags END,
                    updated=excluded.updated
                """,
                (clean_name, summary, clean_details, status.strip(), next_steps.strip(), tags.strip(), now, now),
            )
            self.conn.commit()
        return f"Project memory saved for {clean_name}."

    def get_project(self, name: str) -> dict | None:
        clean_name = self._normalize_text(name)
        if not clean_name:
            return None
        with self._lock:
            exact = self.conn.execute(
                """
                SELECT name, summary, details, status, next_steps, tags, updated
                FROM projects
                WHERE lower(name)=lower(?)
                """,
                (clean_name,),
            ).fetchone()
            if exact:
                row = exact
            else:
                rows = self.conn.execute(
                    """
                    SELECT name, summary, details, status, next_steps, tags, updated
                    FROM projects
                    ORDER BY updated DESC
                    """
                ).fetchall()
                row = None
                for candidate in rows:
                    project_name = candidate[0].lower()
                    target = clean_name.lower()
                    if target in project_name or project_name in target:
                        row = candidate
                        break
        if not row:
            return None
        return {
            "name": row[0],
            "summary": row[1],
            "details": row[2],
            "status": row[3],
            "next_steps": row[4],
            "tags": row[5],
            "updated": row[6],
        }

    def list_projects(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT name, summary, status, next_steps, updated
                FROM projects
                ORDER BY updated DESC
                """
            ).fetchall()
        return [
            {
                "name": row[0],
                "summary": row[1],
                "status": row[2],
                "next_steps": row[3],
                "updated": row[4],
            }
            for row in rows
        ]

    def save_knowledge_document(self, title: str, source_path: str, content: str) -> str:
        clean_title = self._normalize_text(title) or "Untitled knowledge"
        clean_path = self._normalize_text(source_path)
        clean_content = (content or "").strip()
        if not clean_path or not clean_content:
            return f"Knowledge document data is incomplete, {USER_NAME}."
        now = datetime.datetime.now().isoformat()
        summary = self._summarize_text(clean_content.replace("\n", " "), limit=220)
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO knowledge_docs (title, source_path, content, summary, created, updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    summary=excluded.summary,
                    updated=excluded.updated
                """,
                (clean_title, clean_path, clean_content, summary, now, now),
            )
            self.conn.commit()
        return f"Knowledge saved from {clean_title}."

    def sync_knowledge_files(self, files_controller, knowledge_dir: Path, max_chars: int = 12000) -> dict:
        if not files_controller or not knowledge_dir.exists():
            return {"scanned": 0, "saved": 0}

        allowed = {".txt", ".md", ".py", ".json", ".csv", ".pdf", ".docx", ".doc"}
        scanned = 0
        saved = 0

        for path in knowledge_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            scanned += 1
            resolved, content = files_controller.extract_text(str(path), max_chars=max_chars)
            if not resolved or not content or content.startswith("Couldn't read file:"):
                continue
            self.save_knowledge_document(resolved.stem, str(resolved), content)
            saved += 1

        return {"scanned": scanned, "saved": saved}

    def save_workflow(self, name: str, steps: list[str], description: str = "", tags: str = "") -> str:
        clean_name = self._normalize_text(name)
        normalized_steps = [self._normalize_text(step) for step in steps if self._normalize_text(step)]
        if not clean_name or not normalized_steps:
            return f"Workflow name or steps are missing, {USER_NAME}."
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO workflows (name, description, steps_json, tags, created, updated, last_run)
                VALUES (?, ?, ?, ?, ?, ?, '')
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    steps_json=excluded.steps_json,
                    tags=CASE WHEN excluded.tags != '' THEN excluded.tags ELSE workflows.tags END,
                    updated=excluded.updated
                """,
                (
                    clean_name,
                    self._normalize_text(description),
                    json.dumps(normalized_steps),
                    self._normalize_text(tags),
                    now,
                    now,
                ),
            )
            self.conn.commit()
        return f"Workflow saved: {clean_name}."

    def get_workflow(self, name: str) -> dict | None:
        clean_name = self._normalize_text(name)
        if not clean_name:
            return None
        with self._lock:
            row = self.conn.execute(
                """
                SELECT name, description, steps_json, tags, updated, last_run
                FROM workflows
                WHERE lower(name)=lower(?)
                """,
                (clean_name,),
            ).fetchone()
            if not row:
                rows = self.conn.execute(
                    "SELECT name, description, steps_json, tags, updated, last_run FROM workflows ORDER BY updated DESC"
                ).fetchall()
            else:
                rows = [row]
        match = None
        for candidate in rows:
            workflow_name = candidate[0].lower()
            target = clean_name.lower()
            if target == workflow_name or target in workflow_name or workflow_name in target:
                match = candidate
                break
        if not match:
            return None
        steps = json.loads(match[2]) if match[2] else []
        return {
            "name": match[0],
            "description": match[1],
            "steps": steps,
            "tags": match[3],
            "updated": match[4],
            "last_run": match[5],
        }

    def list_workflows(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT name, description, tags, updated, last_run
                FROM workflows
                ORDER BY updated DESC
                """
            ).fetchall()
        return [
            {
                "name": row[0],
                "description": row[1],
                "tags": row[2],
                "updated": row[3],
                "last_run": row[4],
            }
            for row in rows
        ]

    def mark_workflow_run(self, name: str):
        clean_name = self._normalize_text(name)
        if not clean_name:
            return
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute(
                "UPDATE workflows SET last_run=?, updated=? WHERE lower(name)=lower(?)",
                (now, now, clean_name),
            )
            self.conn.commit()

    def save_mission(
        self,
        name: str,
        objective: str,
        next_action: str = "",
        notes: str = "",
        plan: list[str] | None = None,
        status: str = "active",
    ) -> str:
        clean_name = self._normalize_text(name)
        clean_objective = self._normalize_text(objective)
        if not clean_name or not clean_objective:
            return f"Mission name or objective is missing, {USER_NAME}."
        now = datetime.datetime.now().isoformat()
        plan_json = json.dumps([self._normalize_text(step) for step in (plan or []) if self._normalize_text(step)])
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO missions (name, objective, status, next_action, notes, plan_json, created, updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    objective=excluded.objective,
                    status=excluded.status,
                    next_action=CASE WHEN excluded.next_action != '' THEN excluded.next_action ELSE missions.next_action END,
                    notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE missions.notes END,
                    plan_json=CASE WHEN excluded.plan_json != '[]' THEN excluded.plan_json ELSE missions.plan_json END,
                    updated=excluded.updated
                """,
                (clean_name, clean_objective, status, self._normalize_text(next_action), self._normalize_text(notes), plan_json, now, now),
            )
            self.conn.commit()
        return f"Mission saved: {clean_name}."

    def get_mission(self, name: str) -> dict | None:
        clean_name = self._normalize_text(name)
        if not clean_name:
            return None
        with self._lock:
            row = self.conn.execute(
                """
                SELECT name, objective, status, next_action, notes, plan_json, updated
                FROM missions
                WHERE lower(name)=lower(?)
                """,
                (clean_name,),
            ).fetchone()
            if not row:
                rows = self.conn.execute(
                    "SELECT name, objective, status, next_action, notes, plan_json, updated FROM missions ORDER BY updated DESC"
                ).fetchall()
            else:
                rows = [row]
        match = None
        for candidate in rows:
            mission_name = candidate[0].lower()
            target = clean_name.lower()
            if target == mission_name or target in mission_name or mission_name in target:
                match = candidate
                break
        if not match:
            return None
        return {
            "name": match[0],
            "objective": match[1],
            "status": match[2],
            "next_action": match[3],
            "notes": match[4],
            "plan": json.loads(match[5]) if match[5] else [],
            "updated": match[6],
        }

    def get_active_mission(self) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT name, objective, status, next_action, notes, plan_json, updated
                FROM missions
                WHERE lower(status)='active'
                ORDER BY updated DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return {
            "name": row[0],
            "objective": row[1],
            "status": row[2],
            "next_action": row[3],
            "notes": row[4],
            "plan": json.loads(row[5]) if row[5] else [],
            "updated": row[6],
        }

    def list_missions(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT name, objective, status, next_action, updated
                FROM missions
                ORDER BY updated DESC
                """
            ).fetchall()
        return [
            {
                "name": row[0],
                "objective": row[1],
                "status": row[2],
                "next_action": row[3],
                "updated": row[4],
            }
            for row in rows
        ]

    def complete_mission(self, name: str) -> str:
        clean_name = self._normalize_text(name)
        if not clean_name:
            return f"Which mission should I complete, {USER_NAME}?"
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute(
                "UPDATE missions SET status='completed', updated=? WHERE lower(name)=lower(?)",
                (now, clean_name),
            )
            self.conn.commit()
        return f"Mission completed: {clean_name}."

    def list_knowledge_documents(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT title, source_path, summary, updated
                FROM knowledge_docs
                ORDER BY updated DESC
                """
            ).fetchall()
        return [{"title": row[0], "source_path": row[1], "summary": row[2], "updated": row[3]} for row in rows]

    def search_knowledge(self, query: str, limit: int = 6) -> list:
        query = self._normalize_text(query)
        if not query:
            return []

        scored = []
        with self._lock:
            fact_rows = self.conn.execute("SELECT key, value, created FROM facts ORDER BY id DESC").fetchall()
            note_rows = self.conn.execute("SELECT content, created FROM notes ORDER BY id DESC").fetchall()
            profile_rows = self.conn.execute(
                "SELECT category, key, value, updated FROM profile_entries ORDER BY updated DESC"
            ).fetchall()
            project_rows = self.conn.execute(
                "SELECT name, summary, details, status, next_steps, tags, updated FROM projects ORDER BY updated DESC"
            ).fetchall()
            doc_rows = self.conn.execute(
                "SELECT title, source_path, summary, content, updated FROM knowledge_docs ORDER BY updated DESC"
            ).fetchall()
            workflow_rows = self.conn.execute(
                "SELECT name, description, steps_json, tags, updated, last_run FROM workflows ORDER BY updated DESC"
            ).fetchall()
            mission_rows = self.conn.execute(
                "SELECT name, objective, status, next_action, notes, plan_json, updated FROM missions ORDER BY updated DESC"
            ).fetchall()
            contact_rows = self.conn.execute(
                "SELECT name, phone, channel, created FROM contacts ORDER BY created DESC"
            ).fetchall()

        for key, value, created in fact_rows:
            score = self._score_text(query, f"{key} {value}", bonus=1)
            if score:
                scored.append({
                    "kind": "fact",
                    "title": key,
                    "content": value,
                    "created": created,
                    "score": score,
                })

        for content, created in note_rows:
            score = self._score_text(query, content)
            if score:
                scored.append({
                    "kind": "note",
                    "title": "",
                    "content": self._summarize_text(content, limit=240),
                    "created": created,
                    "score": score,
                })

        for category, key, value, updated in profile_rows:
            score = self._score_text(query, f"{category} {key} {value}", bonus=2)
            if score:
                scored.append({
                    "kind": "profile",
                    "title": f"{category}:{key}",
                    "content": value,
                    "created": updated,
                    "score": score,
                })

        for name, summary, details, status, next_steps, tags, updated in project_rows:
            haystack = " ".join(filter(None, [name, summary, details, status, next_steps, tags]))
            score = self._score_text(query, haystack, bonus=2)
            if score:
                content_parts = [summary]
                if status:
                    content_parts.append(f"Status: {status}")
                if next_steps:
                    content_parts.append(f"Next: {next_steps}")
                scored.append({
                    "kind": "project",
                    "title": name,
                    "content": " | ".join(part for part in content_parts if part),
                    "created": updated,
                    "score": score,
                })

        for title, source_path, summary, content, updated in doc_rows:
            score = self._score_text(query, f"{title} {source_path} {summary} {content}", bonus=1)
            if score:
                scored.append({
                    "kind": "knowledge_doc",
                    "title": title,
                    "content": summary or self._summarize_text(content, limit=240),
                    "created": updated,
                    "score": score,
                })

        for name, description, steps_json, tags, updated, last_run in workflow_rows:
            steps = " ".join(json.loads(steps_json) if steps_json else [])
            score = self._score_text(query, f"{name} {description} {steps} {tags}", bonus=2)
            if score:
                content = description or self._summarize_text(steps, limit=220)
                if steps:
                    content += f" | Steps: {self._summarize_text(steps, limit=140)}"
                scored.append({
                    "kind": "workflow",
                    "title": name,
                    "content": content,
                    "created": updated or last_run,
                    "score": score,
                })

        for name, objective, status, next_action, notes, plan_json, updated in mission_rows:
            plan_text = " ".join(json.loads(plan_json) if plan_json else [])
            score = self._score_text(query, f"{name} {objective} {status} {next_action} {notes} {plan_text}", bonus=3)
            if score:
                content_parts = [objective, f"Status: {status}"]
                if next_action:
                    content_parts.append(f"Next: {next_action}")
                if notes:
                    content_parts.append(f"Notes: {self._summarize_text(notes, limit=120)}")
                scored.append({
                    "kind": "mission",
                    "title": name,
                    "content": " | ".join(part for part in content_parts if part),
                    "created": updated,
                    "score": score,
                })

        for name, phone, channel, created in contact_rows:
            score = self._score_text(query, f"{name} {phone} {channel}", bonus=1)
            if score:
                scored.append({
                    "kind": "contact",
                    "title": name.title(),
                    "content": f"{channel}: +{phone}",
                    "created": created,
                    "score": score,
                })

        scored.sort(key=lambda item: (-item["score"], item["created"]), reverse=False)
        return scored[:limit]

    def build_context(self, query: str, max_items: int = 6) -> str:
        sections = []

        active_mission = self.get_active_mission()
        if active_mission:
            lines = [
                f"- Mission: {active_mission['name']}",
                f"- Objective: {active_mission['objective']}",
            ]
            if active_mission["next_action"]:
                lines.append(f"- Next action: {active_mission['next_action']}")
            if active_mission["plan"]:
                lines.append("- Plan: " + " | ".join(active_mission["plan"][:5]))
            sections.append("Active mission:\n" + "\n".join(lines))

        profile_entries = self.get_profile_entries(limit=6)
        if profile_entries:
            lines = "\n".join(f"- {item['value']}" for item in profile_entries)
            sections.append("Profile memory:\n" + lines)

        project_rows = self.list_projects()[:4]
        if project_rows:
            lines = []
            for item in project_rows:
                base = f"- {item['name']}: {item['summary']}"
                if item["status"]:
                    base += f" | Status: {item['status']}"
                if item["next_steps"]:
                    base += f" | Next: {item['next_steps']}"
                lines.append(base)
            sections.append("Tracked projects:\n" + "\n".join(lines))

        workflow_rows = self.list_workflows()[:4]
        if workflow_rows:
            lines = []
            for item in workflow_rows:
                base = f"- {item['name']}"
                if item["description"]:
                    base += f": {item['description']}"
                if item["last_run"]:
                    base += f" | Last run: {item['last_run']}"
                lines.append(base)
            sections.append("Saved workflows:\n" + "\n".join(lines))

        relevant = self.search_knowledge(query, limit=max_items)
        if relevant:
            lines = []
            for item in relevant:
                label = item["kind"].replace("_", " ").title()
                title = f"{item['title']}: " if item["title"] else ""
                lines.append(f"- {label}: {title}{item['content']}")
            sections.append("Relevant memory:\n" + "\n".join(lines))

        return "\n\n".join(section for section in sections if section.strip())

    def brain_overview(self) -> dict:
        with self._lock:
            counts = {
                "facts": self.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
                "notes": self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0],
                "profile_entries": self.conn.execute("SELECT COUNT(*) FROM profile_entries").fetchone()[0],
                "projects": self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
                "knowledge_docs": self.conn.execute("SELECT COUNT(*) FROM knowledge_docs").fetchone()[0],
                "workflows": self.conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0],
                "missions": self.conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0],
                "contacts": self.conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],
                "history": self.conn.execute("SELECT COUNT(*) FROM history").fetchone()[0],
            }
        counts["db_path"] = str(self.db_path)
        active = self.get_active_mission()
        counts["active_mission"] = active["name"] if active else ""
        return counts
