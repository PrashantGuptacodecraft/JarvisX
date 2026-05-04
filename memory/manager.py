"""memory/manager.py — SQLite memory: facts, history, reminders, todos, notes."""
import sqlite3, datetime, threading, json
from config.settings import DB_PATH, USER_NAME
from config.logger import get_logger
log = get_logger("memory")


class MemoryManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT, value TEXT, created TEXT
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_text TEXT, jarvis_text TEXT, timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT, remind_at TEXT, done INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT, done INTEGER DEFAULT 0, created TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT, created TEXT
            );
        """)
        self.conn.commit()

    def store_fact(self, text: str) -> str:
        now = datetime.datetime.now().isoformat()
        key = text.split("is")[0].strip() if " is " in text else "note"
        with self._lock:
            self.conn.execute("INSERT INTO facts (key, value, created) VALUES (?,?,?)", (key, text, now))
            self.conn.commit()
        return f"Remembered: {text}"

    def recall_fact(self, query: str) -> str:
        with self._lock:
            rows = self.conn.execute("SELECT value FROM facts ORDER BY id DESC").fetchall()
        if not rows:
            return f"Nothing stored yet, {USER_NAME}."
        words = [w for w in query.lower().split() if len(w) > 3]
        for row in rows:
            if any(w in row[0].lower() for w in words):
                return f"I remember: {row[0]}"
        return "Recent memories:\n" + "\n".join(f"• {r[0]}" for r in rows[:5])

    def forget(self, query: str) -> str:
        with self._lock:
            self.conn.execute("DELETE FROM facts")
            self.conn.commit()
        return f"Memory cleared, {USER_NAME}."

    def get_all_facts(self) -> list:
        with self._lock:
            rows = self.conn.execute("SELECT key, value, created FROM facts ORDER BY id DESC").fetchall()
        return [{"key": r[0], "value": r[1], "created": r[2]} for r in rows]

    def add_history(self, user: str, jarvis: str):
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute("INSERT INTO history (user_text, jarvis_text, timestamp) VALUES (?,?,?)",
                              (user, jarvis, now))
            self.conn.commit()

    def get_history(self, limit: int = 50) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT user_text, jarvis_text, timestamp FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"user": r[0], "jarvis": r[1], "time": r[2]} for r in reversed(rows)]

    def add_reminder(self, task: str, time_str: str) -> str:
        with self._lock:
            self.conn.execute("INSERT INTO reminders (task, remind_at) VALUES (?,?)", (task, time_str))
            self.conn.commit()
        return f"Reminder set: '{task}' at {time_str}."

    def get_pending_reminders(self) -> list:
        with self._lock:
            rows = self.conn.execute("SELECT id, task, remind_at FROM reminders WHERE done=0").fetchall()
        return [{"id": r[0], "task": r[1], "time": r[2]} for r in rows]

    def mark_reminder_done(self, rid: int):
        with self._lock:
            self.conn.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
            self.conn.commit()

    def add_todo(self, item: str) -> str:
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute("INSERT INTO todos (item, created) VALUES (?,?)", (item, now))
            self.conn.commit()
        return f"Added to your to-do list: '{item}'"

    def get_todos(self) -> list:
        with self._lock:
            rows = self.conn.execute("SELECT id, item, done FROM todos WHERE done=0").fetchall()
        return [{"id": r[0], "item": r[1], "done": r[2]} for r in rows]

    def add_note(self, content: str) -> str:
        now = datetime.datetime.now().isoformat()
        with self._lock:
            self.conn.execute("INSERT INTO notes (content, created) VALUES (?,?)", (content, now))
            self.conn.commit()
        return f"Note saved, {USER_NAME}."

    def get_notes(self) -> list:
        with self._lock:
            rows = self.conn.execute("SELECT content, created FROM notes ORDER BY id DESC").fetchall()
        return [{"content": r[0], "created": r[1]} for r in rows]
