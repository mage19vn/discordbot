"""SQLite storage for problems, user inputs, and submission history."""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("MAGOJ_DB_PATH") or "data.sqlite3")
LEGACY_PATH = Path(os.getenv("MAGOJ_LEGACY_PATH") or "data.json")
_lock = threading.RLock()


def _connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize():
    with _lock:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS problems (
                    name TEXT PRIMARY KEY, body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_inputs (
                    user_id TEXT PRIMARY KEY, input TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL, user_id TEXT NOT NULL,
                    problem TEXT NOT NULL, result TEXT NOT NULL,
                    seed INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS submissions_user
                    ON submissions(platform, user_id, id DESC);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL, user_id TEXT NOT NULL,
                    action TEXT NOT NULL, problem TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(submissions)")}
            for name in ("failure_input", "expected_output"):
                if name not in columns:
                    db.execute(f"ALTER TABLE submissions ADD COLUMN {name} TEXT")
            migrated = db.execute("SELECT 1 FROM metadata WHERE key='legacy_migrated'").fetchone()
            if not migrated and LEGACY_PATH.exists():
                legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
                if not isinstance(legacy.get("de", {}), dict) or not isinstance(legacy.get("inp_data", {}), dict):
                    raise ValueError("Invalid legacy data structure")
                db.executemany("INSERT OR IGNORE INTO problems VALUES (?, ?)",
                               ((name, json.dumps(body, ensure_ascii=False))
                                for name, body in legacy.get("de", {}).items()))
                db.executemany("INSERT OR IGNORE INTO user_inputs VALUES (?, ?)",
                               ((str(uid), value) for uid, value in legacy.get("inp_data", {}).items()))
                db.execute("INSERT INTO metadata VALUES ('legacy_migrated','1')")


def get_problem(name):
    with _connect() as db:
        row = db.execute("SELECT body FROM problems WHERE name=?", (name,)).fetchone()
    return json.loads(row[0]) if row else None


def create_problem(name, author=None):
    body = {"question": "", "solution": "", "gen_test": "",
            "checker": "", "category": "Chưa phân loại",
            "fixed_tests": [], "test_count": 10, "time_limit": 2,
            "memory_limit": 128, "published": True,
            "version": 1, "author": str(author) if author is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat()}
    with _lock, _connect() as db:
        try:
            db.execute("INSERT INTO problems VALUES (?, ?)",
                       (name, json.dumps(body, ensure_ascii=False)))
            return True
        except sqlite3.IntegrityError:
            return False


def import_problems(problems, platform, user_id):
    """Import a validated batch as one transaction; existing names abort all."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connect() as db:
        try:
            for name, fields in problems:
                body = {**fields, "version": 1, "author": str(user_id),
                        "created_at": now}
                db.execute("INSERT INTO problems(name,body) VALUES (?,?)",
                           (name, json.dumps(body, ensure_ascii=False)))
                db.execute("INSERT INTO admin_events(platform,user_id,action,problem) "
                           "VALUES (?,?,?,?)", (platform, str(user_id), "importjson", name))
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError("Có tên bài đã tồn tại; không bài nào trong file được nhập.") from exc


def update_problems(problems, platform, user_id):
    """Replace validated problem content atomically, preserving identity and history."""
    with _lock, _connect() as db:
        names = [name for name, _ in problems]
        rows = db.execute(
            f"SELECT name,body FROM problems WHERE name IN ({','.join('?' for _ in names)})",
            names).fetchall()
        previous = {name: json.loads(raw) for name, raw in rows}
        missing = [name for name in names if name not in previous]
        if missing:
            raise ValueError(f"Bài chưa tồn tại: {', '.join(missing)}. Không bài nào được cập nhật.")
        for name, fields in problems:
            old = previous[name]
            body = {**old, **fields, "version": old.get("version", 1) + 1}
            body.pop("page_url", None)
            body.pop("page_hash", None)
            db.execute("UPDATE problems SET body=? WHERE name=?",
                       (json.dumps(body, ensure_ascii=False), name))
            db.execute("INSERT INTO admin_events(platform,user_id,action,problem) "
                       "VALUES (?,?,?,?)", (platform, str(user_id), "updatejson", name))


def set_field(name, field, value):
    return set_fields(name, {field: value})


def set_fields(name, fields):
    with _lock, _connect() as db:
        row = db.execute("SELECT body FROM problems WHERE name=?", (name,)).fetchone()
        if row is None:
            return False
        body = json.loads(row[0])
        body.update(fields)
        if any(field not in ("page_url", "page_hash") for field in fields):
            body["version"] = body.get("version", 1) + 1
        db.execute("UPDATE problems SET body=? WHERE name=?",
                   (json.dumps(body, ensure_ascii=False), name))
        return True


def append_fixed_test(name, value):
    with _lock, _connect() as db:
        row = db.execute("SELECT body FROM problems WHERE name=?", (name,)).fetchone()
        if row is None:
            return "missing"
        body = json.loads(row[0])
        cases = body.setdefault("fixed_tests", [])
        if len(cases) >= 10:
            return "full"
        cases.append(value)
        body["version"] = body.get("version", 1) + 1
        db.execute("UPDATE problems SET body=? WHERE name=?",
                   (json.dumps(body, ensure_ascii=False), name))
        return "ok"


def list_problems():
    cats = {}
    with _connect() as db:
        rows = db.execute("SELECT name, body FROM problems ORDER BY rowid").fetchall()
    for name, raw in rows:
        body = json.loads(raw)
        cats.setdefault(body.get("category", "Chưa phân loại"), []).append(name)
    return cats


def set_input(user_id, value):
    with _lock, _connect() as db:
        db.execute("INSERT INTO user_inputs VALUES (?, ?) "
                   "ON CONFLICT(user_id) DO UPDATE SET input=excluded.input",
                   (user_id, value))


def get_input(user_id):
    with _connect() as db:
        row = db.execute("SELECT input FROM user_inputs WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else ""


def record_submission(platform, user_id, problem, result, seed, details=None):
    details = details or {}
    failure_input = str(details.get("inp", ""))[:4096] if result == "wa" else None
    expected_output = str(details.get("sol", ""))[:4096] if result == "wa" else None
    with _lock, _connect() as db:
        db.execute("INSERT INTO submissions(platform,user_id,problem,result,seed,"
                   "failure_input,expected_output) VALUES (?,?,?,?,?,?,?)",
                   (platform, str(user_id), problem, result, seed,
                    failure_input, expected_output))


def recent_submissions(platform, user_id, limit=10):
    with _connect() as db:
        return db.execute("SELECT problem,result,seed,created_at FROM submissions "
                          "WHERE platform=? AND user_id=? ORDER BY id DESC LIMIT ?",
                          (platform, str(user_id), limit)).fetchall()


def last_failure(platform, user_id):
    with _connect() as db:
        return db.execute("SELECT problem,seed,failure_input,expected_output "
                          "FROM submissions WHERE platform=? AND user_id=? "
                          "AND result='wa' ORDER BY id DESC LIMIT 1",
                          (platform, str(user_id))).fetchone()


def leaderboard(limit=10):
    with _connect() as db:
        return db.execute("SELECT platform,user_id,COUNT(DISTINCT problem) AS solved "
                          "FROM submissions WHERE result='ac' "
                          "GROUP BY platform,user_id ORDER BY solved DESC, platform,user_id LIMIT ?",
                          (limit,)).fetchall()


def record_admin_event(platform, user_id, action, problem):
    with _lock, _connect() as db:
        db.execute("INSERT INTO admin_events(platform,user_id,action,problem) VALUES (?,?,?,?)",
                   (platform, str(user_id), action, problem))
