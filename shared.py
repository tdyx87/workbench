"""共享层：数据库连接、鉴权、通知与通用工具（供 app.py 与各蓝图共用）。"""
import functools
import hashlib
import json
import os
import secrets
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime

from flask import g, jsonify, redirect, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_path(name, default):
    """路径配置：环境变量优先，否则落到项目目录内，保证换机器可直接运行。"""
    value = os.environ.get(name)
    if value:
        return value
    return os.path.join(BASE_DIR, default)


# 数据库文件；服务器上用 WORKBENCH_DB 指向项目外路径，本地默认落在项目内
DB_PATH = _env_path("WORKBENCH_DB", "workbench.db")
# JSON 备份归档目录（/api/export 产物）
BACKUP_DIR = _env_path("WORKBENCH_BACKUP_DIR", "backups")
# 数据导入前的数据库快照目录
SNAPSHOT_DIR = _env_path("WORKBENCH_SNAPSHOT_DIR", "db_backups")
# 按表导入的预演临时文件目录
IMPORT_TMP_DIR = _env_path("WORKBENCH_IMPORT_TMP", "tmp_import")
AUTH_FILE = os.path.join(BASE_DIR, "auth.json")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        # WAL 提升读写并发，busy_timeout 避免瞬时写冲突直接抛 database is locked
        try:
            g.db.execute("PRAGMA busy_timeout=5000")
            g.db.execute("PRAGMA journal_mode=WAL")
            g.db.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _load_auth():
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_auth(data):
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_api_token():
    """惰性生成并返回 API Token（存入 auth.json）。"""
    auth = _load_auth()
    token = auth.get("api_token")
    if not token:
        token = secrets.token_hex(20)
        auth["api_token"] = token
        _save_auth(auth)
    return token


def verify_api_token(token):
    stored = _load_auth().get("api_token", "")
    return bool(token and stored and secrets.compare_digest(token, stored))


def notify_webhook(title, text):
    """向配置的 Webhook（Server酱/通用 JSON）发送通知。"""
    auth = _load_auth()
    url = auth.get("notify_webhook", "")
    if not (auth.get("notify_enabled") and url):
        return False
    try:
        if "sctapi.ftqq.com" in url or "serverchan" in url:
            body = urllib.parse.urlencode({"title": title, "desp": text}).encode()
        else:
            body = json.dumps({"title": title, "text": text}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        return True
    except (OSError, ValueError):
        return False


def log_edit(db, module, ref_id, action, detail=""):
    """记录一条变更历史；失败不影响主流程。"""
    try:
        db.execute(
            "INSERT INTO edit_history (module, ref_id, action, detail, created_at) "
            "VALUES (?,?,?,?,?)",
            (module, ref_id, action, str(detail)[:500],
             datetime.now().isoformat(timespec="seconds")))
    except sqlite3.DatabaseError:
        pass


def archive_and_delete(db, table, item_id):
    """删除前先把整行归档到 trash（回收站），再执行物理删除。"""
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
    if row:
        payload = json.dumps(dict(row), ensure_ascii=False)
        db.execute(
            "INSERT INTO trash (table_name, ref_id, payload, deleted_at) "
            "VALUES (?,?,?,?)",
            (table, item_id, payload,
             datetime.now().isoformat(timespec="seconds")))
        log_edit(db, table, item_id, "删除", "已归档到回收站")
    db.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))


def verify_password(password):
    stored = _load_auth().get("password_hash", "")
    if not stored:
        return False
    return hashlib.sha256(password.encode()).hexdigest() == stored


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            if verify_api_token(request.headers.get("X-API-Token", "")):
                return view(*args, **kwargs)
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


IMPORT_TABLES = {
    "work_logs": ["log_date", "title", "content", "project", "tags", "created_at"],
    "study_notes": ["topic", "category", "content", "mastery", "next_review",
                    "review_stage", "last_reviewed", "created_at"],
    "todos": ["title", "priority", "due_date", "done", "project", "created_at"],
    "diaries": ["diary_date", "mood", "content", "created_at"],
    "bugs": ["title", "platform", "severity", "phenomenon", "root_cause",
             "solution", "status", "driver_version", "model", "created_at"],
    "snippets": ["title", "language", "code", "tags", "created_at"],
    "commands": ["category", "name", "command", "description", "created_at"],
    "compile_errors": ["compiler", "error_msg", "cause", "solution", "created_at"],
    "interview_questions": ["question", "answer", "category", "mastery",
                            "next_review", "review_stage", "created_at"],
    "perf_records": ["title", "target", "detail", "created_at"],
    "books": ["title", "author", "note", "progress", "created_at"],
    "crashes": ["title", "module", "signal", "stack", "root_cause", "fix",
                "status", "created_at"],
    "releases": ["version", "release_date", "platform", "changes", "issues",
                 "created_at"],
    "drivers": ["model", "driver_version", "firmware_version", "release_date",
                "changes", "known_issues", "recommend", "created_at"],
    "protocols": ["title", "protocol", "summary", "commands", "notes", "created_at"],
    "test_matrix": ["driver_version", "model", "test_item", "result", "tester",
                    "note", "created_at"],
    "error_codes": ["brand", "code", "title", "description", "solution", "created_at"],
    "log_patterns": ["title", "source", "pattern", "interpretation", "action",
                     "created_at"],
    "printers": ["model", "languages", "duplex", "trays", "memory", "ip",
                 "location", "owner", "notes", "created_at"],
    "printer_probe_logs": ["printer_id", "ok", "detail", "checked_at"],
    "roadmap_topics": ["topic", "category", "status", "progress", "note", "created_at"],
    "habits": ["name", "target_days", "created_at"],
    "habit_logs": ["habit_id", "log_date", "created_at"],
    "templates": ["name", "content", "created_at"],
    "checklists": ["title", "model", "cycle_days", "last_done", "note", "created_at"],
    "edit_history": ["module", "ref_id", "action", "detail", "created_at"],
    "trash": ["table_name", "ref_id", "payload", "deleted_at"],
}


PLATFORMS = ["通用", "Linux 服务端", "嵌入式", "Qt", "Windows", "macOS",
             "Android", "iOS", "Web", "Flutter", "HarmonyOS"]

COMPILERS = ["GCC", "Clang", "MSVC", "CMake", "通用"]

REVIEW_INTERVALS = [1, 3, 7, 15, 30]
