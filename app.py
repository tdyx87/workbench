#!/usr/bin/env python3
"""个人工作台 - Flask + SQLite 单文件应用
模块：概览（快捷记录/复习提醒/打卡热力图）、工作记录（项目/模板）、
      学习笔记（复习计划）、待办事项、每周回顾、登录保护
"""
import functools
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("WORKBENCH_DB", "/root/workbench.db")
AUTH_FILE = os.path.join(BASE_DIR, "auth.json")

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

SCHEMA = """
CREATE TABLE IF NOT EXISTS work_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    category TEXT DEFAULT '未分类',
    content TEXT DEFAULT '',
    link TEXT DEFAULT '',
    mastery INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    priority TEXT DEFAULT '中',
    due_date TEXT DEFAULT '',
    done INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    tags TEXT DEFAULT ''
);
"""

MIGRATIONS = [
    "ALTER TABLE work_logs ADD COLUMN project TEXT DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN project TEXT DEFAULT ''",
    "ALTER TABLE study_notes ADD COLUMN next_review TEXT DEFAULT ''",
    "ALTER TABLE study_notes ADD COLUMN review_stage INTEGER DEFAULT 0",
    "ALTER TABLE study_notes ADD COLUMN last_reviewed TEXT DEFAULT ''",
]

REVIEW_INTERVALS = [1, 3, 7, 15, 30]  # 艾宾浩斯复习间隔（天）

DEFAULT_TEMPLATES = [
    ("日报", "工作日报", "【今日完成】\n\n【明日计划】\n\n【问题与风险】\n", "日报"),
    ("会议纪要", "会议纪要 - ",
     "【会议主题】\n【参会人员】\n【讨论要点】\n1. \n【结论与行动项】\n1. ", "会议"),
    ("周报", "本周工作总结", "【本周重点工作】\n\n【关键进展】\n\n【下周计划】\n\n【需要支持】\n", "周报"),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    for sql in MIGRATIONS:
        try:
            db.execute(sql)
        except sqlite3.OperationalError:
            pass
    if db.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO templates (name, title, content, tags) VALUES (?,?,?,?)",
            DEFAULT_TEMPLATES)
    rows = db.execute(
        "SELECT id FROM study_notes WHERE next_review='' OR next_review IS NULL").fetchall()
    for r in rows:
        nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
        db.execute("UPDATE study_notes SET next_review=?, review_stage=0 WHERE id=?",
                   (nxt, r[0]))
    db.commit()
    db.close()


def _load_auth():
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def verify_password(password):
    stored = _load_auth().get("password_hash", "")
    if not stored:
        return False
    return hashlib.sha256(password.encode()).hexdigest() == stored


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_now():
    return {"now": datetime.now().strftime("%Y-%m-%d %H:%M")}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if verify_password(request.form.get("password", "")):
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "密码错误，请重试"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def get_heatmap(db, days=70):
    today = date.today()
    start = today - timedelta(days=days - 1)
    counts = {}
    for r in db.execute(
            "SELECT log_date d, COUNT(*) c FROM work_logs WHERE log_date>=? GROUP BY log_date",
            (start.isoformat(),)).fetchall():
        counts[r["d"]] = counts.get(r["d"], 0) + r["c"]
    for r in db.execute(
            "SELECT substr(created_at,1,10) d, COUNT(*) c FROM study_notes "
            "WHERE created_at>=? GROUP BY d", (start.isoformat(),)).fetchall():
        counts[r["d"]] = counts.get(r["d"], 0) + r["c"]
    cells = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        c = counts.get(d, 0)
        level = 0 if c == 0 else (1 if c == 1 else (2 if c <= 3 else 3))
        cells.append({"date": d, "count": c, "level": level})
    return cells


@app.route("/")
@login_required
def index():
    db = get_db()
    today = date.today().isoformat()
    stats = {
        "work_count": db.execute("SELECT COUNT(*) c FROM work_logs").fetchone()["c"],
        "study_count": db.execute("SELECT COUNT(*) c FROM study_notes").fetchone()["c"],
        "todo_open": db.execute("SELECT COUNT(*) c FROM todos WHERE done=0").fetchone()["c"],
        "todo_done": db.execute("SELECT COUNT(*) c FROM todos WHERE done=1").fetchone()["c"],
    }
    recent_logs = db.execute(
        "SELECT * FROM work_logs ORDER BY log_date DESC, id DESC LIMIT 5").fetchall()
    recent_notes = db.execute(
        "SELECT * FROM study_notes ORDER BY id DESC LIMIT 5").fetchall()
    open_todos = db.execute(
        "SELECT * FROM todos WHERE done=0 ORDER BY CASE priority WHEN '高' THEN 0 "
        "WHEN '中' THEN 1 ELSE 2 END, due_date LIMIT 8").fetchall()
    due_reviews = db.execute(
        "SELECT * FROM study_notes WHERE next_review!='' AND next_review<=? ORDER BY next_review",
        (today,)).fetchall()
    heatmap = get_heatmap(db)
    return render_template(
        "index.html", stats=stats, recent_logs=recent_logs, recent_notes=recent_notes,
        open_todos=open_todos, due_reviews=due_reviews, heatmap=heatmap, today=today)


@app.route("/work")
@login_required
def work_page():
    q = request.args.get("q", "").strip()
    project = request.args.get("project", "").strip()
    tpl = request.args.get("tpl", "")
    db = get_db()
    projects = [r["project"] for r in db.execute(
        "SELECT DISTINCT project FROM work_logs WHERE project!='' ORDER BY project").fetchall()]
    templates = db.execute("SELECT * FROM templates ORDER BY id").fetchall()
    sql = "SELECT * FROM work_logs WHERE 1=1"
    params = []
    if q:
        sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        params += [f"%{q}%"] * 3
    if project:
        sql += " AND project=?"
        params.append(project)
    sql += " ORDER BY log_date DESC, id DESC"
    rows = db.execute(sql, params).fetchall()
    tpl_data = None
    if tpl:
        tpl_data = db.execute("SELECT * FROM templates WHERE id=?", (tpl,)).fetchone()
    return render_template("work.html", logs=rows, q=q, project=project,
                           projects=projects, templates=templates, tpl_data=tpl_data,
                           today=date.today().isoformat())


@app.route("/study")
@login_required
def study_page():
    cat = request.args.get("category", "").strip()
    db = get_db()
    today = date.today().isoformat()
    categories = [r["category"] for r in db.execute(
        "SELECT DISTINCT category FROM study_notes ORDER BY category").fetchall()]
    if cat:
        rows = db.execute(
            "SELECT * FROM study_notes WHERE category=? ORDER BY id DESC", (cat,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM study_notes ORDER BY id DESC").fetchall()
    return render_template("study.html", notes=rows, categories=categories,
                           active_cat=cat, today=today)


@app.route("/todo")
@login_required
def todo_page():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM todos ORDER BY done, CASE priority WHEN '高' THEN 0 "
        "WHEN '中' THEN 1 ELSE 2 END, due_date, id").fetchall()
    projects = [r["project"] for r in db.execute(
        "SELECT DISTINCT project FROM todos WHERE project!='' ORDER BY project").fetchall()]
    return render_template("todo.html", todos=rows, projects=projects,
                           now_str=date.today().isoformat())


@app.route("/review/weekly")
@login_required
def weekly_review():
    db = get_db()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    ws, we = week_start.isoformat(), today.isoformat()
    logs = db.execute(
        "SELECT * FROM work_logs WHERE log_date BETWEEN ? AND ? ORDER BY log_date DESC, id DESC",
        (ws, we)).fetchall()
    notes = db.execute(
        "SELECT * FROM study_notes WHERE substr(created_at,1,10) BETWEEN ? AND ? ORDER BY id DESC",
        (ws, we)).fetchall()
    done_todos = db.execute("SELECT * FROM todos WHERE done=1").fetchall()
    open_todos = db.execute("SELECT * FROM todos WHERE done=0 ORDER BY due_date").fetchall()
    reviewed = db.execute(
        "SELECT * FROM study_notes WHERE last_reviewed BETWEEN ? AND ?", (ws, we)).fetchall()
    return render_template("review.html", logs=logs, notes=notes,
                           done_todos=done_todos, open_todos=open_todos,
                           reviewed=reviewed, week_start=ws, week_end=we)


@app.route("/api/quick", methods=["POST"])
@login_required
def quick_capture():
    text = request.form.get("text", "").strip()
    if text:
        db = get_db()
        now = datetime.now().isoformat(timespec="seconds")
        today = date.today().isoformat()
        if text.startswith(("#学习", "#笔记")):
            body = text.split(" ", 1)[-1] if " " in text else text.lstrip("#学习#笔记 ")
            nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
            db.execute(
                "INSERT INTO study_notes (topic, category, content, next_review, created_at) "
                "VALUES (?,?,?,?,?)", (body[:80], "未分类", body, nxt, now))
        elif text.startswith("#待办"):
            body = text.split(" ", 1)[-1] if " " in text else text.lstrip("#待办 ")
            db.execute("INSERT INTO todos (title, priority, created_at) VALUES (?,?,?)",
                       (body, "中", now))
        else:
            body = text.split(" ", 1)[-1] if text.startswith("#工作") and " " in text else text
            db.execute(
                "INSERT INTO work_logs (log_date, title, content, tags, created_at) "
                "VALUES (?,?,?,?,?)", (today, body[:80], body, "速记", now))
        db.commit()
    return redirect(url_for("index"))


@app.route("/api/work", methods=["POST"])
@login_required
def add_work():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO work_logs (log_date, title, content, tags, project, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f.get("log_date") or date.today().isoformat(), f["title"],
         f.get("content", ""), f.get("tags", ""), f.get("project", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("work_page"))


@app.route("/api/work/<int:log_id>/delete", methods=["POST"])
@login_required
def del_work(log_id):
    db = get_db()
    db.execute("DELETE FROM work_logs WHERE id=?", (log_id,))
    db.commit()
    return redirect(url_for("work_page"))


@app.route("/api/study", methods=["POST"])
@login_required
def add_study():
    f = request.form
    nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO study_notes (topic, category, content, link, mastery, "
        "next_review, review_stage, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (f["topic"], f.get("category") or "未分类", f.get("content", ""),
         f.get("link", ""), int(f.get("mastery") or 0), nxt, 0,
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("study_page"))


@app.route("/api/study/<int:note_id>/mastery", methods=["POST"])
@login_required
def update_mastery(note_id):
    db = get_db()
    mastery = max(0, min(100, int(request.form.get("mastery", 0))))
    db.execute("UPDATE study_notes SET mastery=? WHERE id=?", (mastery, note_id))
    db.commit()
    return redirect(url_for("study_page"))


@app.route("/api/study/<int:note_id>/review", methods=["POST"])
@login_required
def mark_reviewed(note_id):
    db = get_db()
    row = db.execute("SELECT * FROM study_notes WHERE id=?", (note_id,)).fetchone()
    if row:
        stage = min(row["review_stage"] + 1, len(REVIEW_INTERVALS) - 1)
        nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[stage])).isoformat()
        mastery = min(100, row["mastery"] + 10)
        db.execute(
            "UPDATE study_notes SET review_stage=?, next_review=?, last_reviewed=?, "
            "mastery=? WHERE id=?",
            (stage, nxt, date.today().isoformat(), mastery, note_id))
        db.commit()
    return redirect(request.referrer or url_for("study_page"))


@app.route("/api/study/<int:note_id>/delete", methods=["POST"])
@login_required
def del_study(note_id):
    db = get_db()
    db.execute("DELETE FROM study_notes WHERE id=?", (note_id,))
    db.commit()
    return redirect(url_for("study_page"))


@app.route("/api/todo", methods=["POST"])
@login_required
def add_todo():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO todos (title, priority, due_date, project, created_at) "
        "VALUES (?,?,?,?,?)",
        (f["title"], f.get("priority", "中"), f.get("due_date", ""),
         f.get("project", ""), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("todo_page"))


@app.route("/api/todo/<int:todo_id>/toggle", methods=["POST"])
@login_required
def toggle_todo(todo_id):
    db = get_db()
    db.execute("UPDATE todos SET done = 1 - done WHERE id=?", (todo_id,))
    db.commit()
    return redirect(url_for("todo_page"))


@app.route("/api/todo/<int:todo_id>/delete", methods=["POST"])
@login_required
def del_todo(todo_id):
    db = get_db()
    db.execute("DELETE FROM todos WHERE id=?", (todo_id,))
    db.commit()
    return redirect(url_for("todo_page"))


@app.route("/api/stats")
@login_required
def api_stats():
    db = get_db()
    return jsonify({
        "work_logs": db.execute("SELECT COUNT(*) c FROM work_logs").fetchone()["c"],
        "study_notes": db.execute("SELECT COUNT(*) c FROM study_notes").fetchone()["c"],
        "todos_open": db.execute("SELECT COUNT(*) c FROM todos WHERE done=0").fetchone()["c"],
        "todos_done": db.execute("SELECT COUNT(*) c FROM todos WHERE done=1").fetchone()["c"],
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(timespec="seconds")})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
