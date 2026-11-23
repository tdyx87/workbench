#!/usr/bin/env python3
"""个人工作台 - Flask + SQLite 单文件应用
通用模块：概览、工作记录、学习笔记、待办事项、日记、习惯打卡、每周回顾、周报
客户端程序员模块：Bug 追踪、技术学习路线、代码片段库、版本发布记录、面试题集
"""
import functools
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta

import markdown as md_lib
from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)
from markupsafe import Markup

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
CREATE TABLE IF NOT EXISTS diaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    diary_date TEXT NOT NULL UNIQUE,
    mood TEXT DEFAULT '',
    content TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL,
    check_date TEXT NOT NULL,
    UNIQUE (habit_id, check_date)
);
CREATE TABLE IF NOT EXISTS bugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    platform TEXT DEFAULT '通用',
    severity TEXT DEFAULT '中',
    phenomenon TEXT DEFAULT '',
    root_cause TEXT DEFAULT '',
    solution TEXT DEFAULT '',
    status TEXT DEFAULT '待解决',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS roadmap_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT DEFAULT '通用',
    progress INTEGER DEFAULT 0,
    status TEXT DEFAULT '未开始',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    language TEXT DEFAULT '',
    code TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    release_date TEXT NOT NULL,
    platform TEXT DEFAULT '',
    changes TEXT DEFAULT '',
    issues TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interview_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT DEFAULT '',
    category TEXT DEFAULT '通用',
    mastery INTEGER DEFAULT 0,
    next_review TEXT DEFAULT '',
    review_stage INTEGER DEFAULT 0,
    last_reviewed TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""

MIGRATIONS = [
    "ALTER TABLE work_logs ADD COLUMN project TEXT DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN project TEXT DEFAULT ''",
    "ALTER TABLE study_notes ADD COLUMN next_review TEXT DEFAULT ''",
    "ALTER TABLE study_notes ADD COLUMN review_stage INTEGER DEFAULT 0",
    "ALTER TABLE study_notes ADD COLUMN last_reviewed TEXT DEFAULT ''",
]

REVIEW_INTERVALS = [1, 3, 7, 15, 30]

DEFAULT_TEMPLATES = [
    ("日报", "工作日报", "【今日完成】\n\n【明日计划】\n\n【问题与风险】\n", "日报"),
    ("会议纪要", "会议纪要 - ",
     "【会议主题】\n【参会人员】\n【讨论要点】\n1. \n【结论与行动项】\n1. ", "会议"),
    ("周报", "本周工作总结", "【本周重点工作】\n\n【关键进展】\n\n【下周计划】\n\n【需要支持】\n", "周报"),
]

MOODS = ["😊", "😐", "😔", "😤", "🤔"]
PLATFORMS = ["通用", "Android", "iOS", "Windows", "macOS", "Linux", "Web", "Flutter", "HarmonyOS"]


@app.template_filter("md")
def render_markdown(text):
    return Markup(md_lib.markdown(
        text or "", extensions=["fenced_code", "tables", "nl2br"]))


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
    rows = db.execute(
        "SELECT id FROM interview_questions WHERE next_review='' OR next_review IS NULL").fetchall()
    for r in rows:
        nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
        db.execute("UPDATE interview_questions SET next_review=? WHERE id=?",
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
    for r in db.execute(
            "SELECT check_date d, COUNT(*) c FROM habit_logs WHERE check_date>=? "
            "GROUP BY check_date", (start.isoformat(),)).fetchall():
        counts[r["d"]] = counts.get(r["d"], 0) + r["c"]
    for r in db.execute(
            "SELECT diary_date d, COUNT(*) c FROM diaries WHERE diary_date>=? "
            "GROUP BY diary_date", (start.isoformat(),)).fetchall():
        counts[r["d"]] = counts.get(r["d"], 0) + r["c"]
    cells = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        c = counts.get(d, 0)
        level = 0 if c == 0 else (1 if c == 1 else (2 if c <= 3 else 3))
        cells.append({"date": d, "count": c, "level": level})
    return cells


def habit_streak(db, habit_id):
    rows = db.execute(
        "SELECT check_date FROM habit_logs WHERE habit_id=? ORDER BY check_date DESC",
        (habit_id,)).fetchall()
    dates = {r["check_date"] for r in rows}
    today = date.today()
    d = today if today.isoformat() in dates else today - timedelta(days=1)
    streak = 0
    while d.isoformat() in dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


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
        "bug_open": db.execute(
            "SELECT COUNT(*) c FROM bugs WHERE status='待解决'").fetchone()["c"],
    }
    recent_logs = db.execute(
        "SELECT * FROM work_logs ORDER BY log_date DESC, id DESC LIMIT 5").fetchall()
    recent_notes = db.execute(
        "SELECT * FROM study_notes ORDER BY id DESC LIMIT 5").fetchall()
    open_todos = db.execute(
        "SELECT * FROM todos WHERE done=0 ORDER BY CASE priority WHEN '高' THEN 0 "
        "WHEN '中' THEN 1 ELSE 2 END, due_date LIMIT 8").fetchall()
    due_reviews = db.execute(
        "SELECT * FROM study_notes WHERE next_review!='' AND next_review<=? "
        "ORDER BY next_review", (today,)).fetchall()
    due_interviews = db.execute(
        "SELECT * FROM interview_questions WHERE next_review!='' AND next_review<=? "
        "ORDER BY next_review", (today,)).fetchall()
    heatmap = get_heatmap(db)
    return render_template(
        "index.html", stats=stats, recent_logs=recent_logs, recent_notes=recent_notes,
        open_todos=open_todos, due_reviews=due_reviews, due_interviews=due_interviews,
        heatmap=heatmap, today=today)


# ---------- 工作记录 ----------

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


# ---------- 学习笔记 ----------

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


# ---------- 待办 ----------

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


# ---------- 日记 ----------

@app.route("/diary")
@login_required
def diary_page():
    db = get_db()
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    rows = db.execute(
        "SELECT * FROM diaries WHERE diary_date LIKE ? ORDER BY diary_date DESC",
        (month + "%",)).fetchall()
    months = [r["m"] for r in db.execute(
        "SELECT DISTINCT substr(diary_date,1,7) m FROM diaries ORDER BY m DESC").fetchall()]
    today_diary = db.execute(
        "SELECT * FROM diaries WHERE diary_date=?",
        (date.today().isoformat(),)).fetchone()
    return render_template("diary.html", diaries=rows, months=months,
                           active_month=month, today_diary=today_diary,
                           moods=MOODS, today=date.today().isoformat())


@app.route("/api/diary", methods=["POST"])
@login_required
def save_diary():
    f = request.form
    d = f.get("diary_date") or date.today().isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO diaries (diary_date, mood, content, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(diary_date) DO UPDATE SET mood=excluded.mood, content=excluded.content",
        (d, f.get("mood", ""), f.get("content", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("diary_page", month=d[:7]))


@app.route("/api/diary/<int:diary_id>/delete", methods=["POST"])
@login_required
def del_diary(diary_id):
    db = get_db()
    db.execute("DELETE FROM diaries WHERE id=?", (diary_id,))
    db.commit()
    return redirect(url_for("diary_page"))


# ---------- 习惯打卡 ----------

@app.route("/habit")
@login_required
def habit_page():
    db = get_db()
    today = date.today().isoformat()
    habits = db.execute("SELECT * FROM habits ORDER BY id").fetchall()
    items = []
    for h in habits:
        checked = db.execute(
            "SELECT 1 FROM habit_logs WHERE habit_id=? AND check_date=?",
            (h["id"], today)).fetchone() is not None
        total = db.execute(
            "SELECT COUNT(*) c FROM habit_logs WHERE habit_id=?",
            (h["id"],)).fetchone()["c"]
        recent = [r["check_date"] for r in db.execute(
            "SELECT check_date FROM habit_logs WHERE habit_id=? "
            "ORDER BY check_date DESC LIMIT 7", (h["id"],)).fetchall()]
        items.append({
            "id": h["id"], "name": h["name"], "checked": checked,
            "total": total, "streak": habit_streak(db, h["id"]), "recent": recent,
        })
    return render_template("habit.html", habits=items, today=today)


@app.route("/api/habit", methods=["POST"])
@login_required
def add_habit():
    name = request.form.get("name", "").strip()
    if name:
        db = get_db()
        db.execute("INSERT INTO habits (name, created_at) VALUES (?,?)",
                   (name, datetime.now().isoformat(timespec="seconds")))
        db.commit()
    return redirect(url_for("habit_page"))


@app.route("/api/habit/<int:habit_id>/check", methods=["POST"])
@login_required
def check_habit(habit_id):
    db = get_db()
    today = date.today().isoformat()
    existing = db.execute(
        "SELECT id FROM habit_logs WHERE habit_id=? AND check_date=?",
        (habit_id, today)).fetchone()
    if existing:
        db.execute("DELETE FROM habit_logs WHERE id=?", (existing["id"],))
    else:
        db.execute("INSERT INTO habit_logs (habit_id, check_date) VALUES (?,?)",
                   (habit_id, today))
    db.commit()
    return redirect(url_for("habit_page"))


@app.route("/api/habit/<int:habit_id>/delete", methods=["POST"])
@login_required
def del_habit(habit_id):
    db = get_db()
    db.execute("DELETE FROM habit_logs WHERE habit_id=?", (habit_id,))
    db.execute("DELETE FROM habits WHERE id=?", (habit_id,))
    db.commit()
    return redirect(url_for("habit_page"))


# ---------- Bug 追踪 ----------

@app.route("/bugs")
@login_required
def bugs_page():
    platform = request.args.get("platform", "").strip()
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM bugs WHERE 1=1"
    params = []
    if platform:
        sql += " AND platform=?"
        params.append(platform)
    if status:
        sql += " AND status=?"
        params.append(status)
    if q:
        sql += " AND (title LIKE ? OR phenomenon LIKE ? OR solution LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY CASE status WHEN '待解决' THEN 0 ELSE 1 END, " \
           "CASE severity WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END, id DESC"
    rows = db.execute(sql, params).fetchall()
    return render_template("bugs.html", bugs=rows, platforms=PLATFORMS,
                           active_platform=platform, active_status=status, q=q)


@app.route("/api/bugs", methods=["POST"])
@login_required
def add_bug():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO bugs (title, platform, severity, phenomenon, root_cause, "
        "solution, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (f["title"], f.get("platform", "通用"), f.get("severity", "中"),
         f.get("phenomenon", ""), f.get("root_cause", ""), f.get("solution", ""),
         f.get("status", "待解决"), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("bugs_page"))


@app.route("/api/bugs/<int:bug_id>/resolve", methods=["POST"])
@login_required
def resolve_bug(bug_id):
    db = get_db()
    db.execute("UPDATE bugs SET status = CASE status WHEN '待解决' THEN '已解决' "
               "ELSE '待解决' END WHERE id=?", (bug_id,))
    db.commit()
    return redirect(request.referrer or url_for("bugs_page"))


@app.route("/api/bugs/<int:bug_id>/delete", methods=["POST"])
@login_required
def del_bug(bug_id):
    db = get_db()
    db.execute("DELETE FROM bugs WHERE id=?", (bug_id,))
    db.commit()
    return redirect(url_for("bugs_page"))


# ---------- 技术学习路线 ----------

@app.route("/roadmap")
@login_required
def roadmap_page():
    db = get_db()
    topics = db.execute(
        "SELECT * FROM roadmap_topics ORDER BY CASE status WHEN '进行中' THEN 0 "
        "WHEN '未开始' THEN 1 ELSE 2 END, category, id").fetchall()
    categories = [r["category"] for r in db.execute(
        "SELECT DISTINCT category FROM roadmap_topics ORDER BY category").fetchall()]
    grouped = {}
    for t in topics:
        grouped.setdefault(t["category"], []).append(t)
    return render_template("roadmap.html", grouped=grouped, categories=categories)


@app.route("/api/roadmap", methods=["POST"])
@login_required
def add_topic():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO roadmap_topics (name, category, progress, status, note, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f["name"], f.get("category") or "通用", int(f.get("progress") or 0),
         f.get("status", "未开始"), f.get("note", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("roadmap_page"))


@app.route("/api/roadmap/<int:topic_id>/progress", methods=["POST"])
@login_required
def update_topic_progress(topic_id):
    db = get_db()
    progress = max(0, min(100, int(request.form.get("progress", 0))))
    status = "已掌握" if progress >= 100 else ("进行中" if progress > 0 else "未开始")
    db.execute("UPDATE roadmap_topics SET progress=?, status=? WHERE id=?",
               (progress, status, topic_id))
    db.commit()
    return redirect(url_for("roadmap_page"))


@app.route("/api/roadmap/<int:topic_id>/delete", methods=["POST"])
@login_required
def del_topic(topic_id):
    db = get_db()
    db.execute("DELETE FROM roadmap_topics WHERE id=?", (topic_id,))
    db.commit()
    return redirect(url_for("roadmap_page"))


# ---------- 代码片段库 ----------

@app.route("/snippets")
@login_required
def snippets_page():
    lang = request.args.get("language", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    languages = [r["language"] for r in db.execute(
        "SELECT DISTINCT language FROM snippets WHERE language!='' ORDER BY language").fetchall()]
    sql = "SELECT * FROM snippets WHERE 1=1"
    params = []
    if lang:
        sql += " AND language=?"
        params.append(lang)
    if q:
        sql += " AND (title LIKE ? OR code LIKE ? OR tags LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()
    return render_template("snippets.html", snippets=rows, languages=languages,
                           active_lang=lang, q=q)


@app.route("/api/snippets", methods=["POST"])
@login_required
def add_snippet():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO snippets (title, language, code, tags, created_at) "
        "VALUES (?,?,?,?,?)",
        (f["title"], f.get("language", ""), f.get("code", ""),
         f.get("tags", ""), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("snippets_page"))


@app.route("/api/snippets/<int:snippet_id>/delete", methods=["POST"])
@login_required
def del_snippet(snippet_id):
    db = get_db()
    db.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))
    db.commit()
    return redirect(url_for("snippets_page"))


# ---------- 版本发布记录 ----------

@app.route("/releases")
@login_required
def releases_page():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM releases ORDER BY release_date DESC, id DESC").fetchall()
    return render_template("releases.html", releases=rows,
                           today=date.today().isoformat())


@app.route("/api/releases", methods=["POST"])
@login_required
def add_release():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO releases (version, release_date, platform, changes, issues, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f["version"], f.get("release_date") or date.today().isoformat(),
         f.get("platform", ""), f.get("changes", ""), f.get("issues", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("releases_page"))


@app.route("/api/releases/<int:release_id>/delete", methods=["POST"])
@login_required
def del_release(release_id):
    db = get_db()
    db.execute("DELETE FROM releases WHERE id=?", (release_id,))
    db.commit()
    return redirect(url_for("releases_page"))


# ---------- 面试题集 ----------

@app.route("/interview")
@login_required
def interview_page():
    cat = request.args.get("category", "").strip()
    db = get_db()
    today = date.today().isoformat()
    categories = [r["category"] for r in db.execute(
        "SELECT DISTINCT category FROM interview_questions ORDER BY category").fetchall()]
    if cat:
        rows = db.execute(
            "SELECT * FROM interview_questions WHERE category=? ORDER BY id DESC",
            (cat,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM interview_questions ORDER BY id DESC").fetchall()
    return render_template("interview.html", questions=rows, categories=categories,
                           active_cat=cat, today=today)


@app.route("/api/interview", methods=["POST"])
@login_required
def add_interview():
    f = request.form
    nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO interview_questions (question, answer, category, mastery, "
        "next_review, review_stage, created_at) VALUES (?,?,?,?,?,?,?)",
        (f["question"], f.get("answer", ""), f.get("category") or "通用",
         int(f.get("mastery") or 0), nxt, 0,
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("interview_page"))


@app.route("/api/interview/<int:qid>/review", methods=["POST"])
@login_required
def review_interview(qid):
    db = get_db()
    row = db.execute(
        "SELECT * FROM interview_questions WHERE id=?", (qid,)).fetchone()
    if row:
        stage = min(row["review_stage"] + 1, len(REVIEW_INTERVALS) - 1)
        nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[stage])).isoformat()
        mastery = min(100, row["mastery"] + 10)
        db.execute(
            "UPDATE interview_questions SET review_stage=?, next_review=?, "
            "last_reviewed=?, mastery=? WHERE id=?",
            (stage, nxt, date.today().isoformat(), mastery, qid))
        db.commit()
    return redirect(request.referrer or url_for("interview_page"))


@app.route("/api/interview/<int:qid>/delete", methods=["POST"])
@login_required
def del_interview(qid):
    db = get_db()
    db.execute("DELETE FROM interview_questions WHERE id=?", (qid,))
    db.commit()
    return redirect(url_for("interview_page"))


# ---------- 回顾与周报 ----------

@app.route("/review/weekly")
@login_required
def weekly_review():
    db = get_db()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    ws, we = week_start.isoformat(), today.isoformat()
    logs = db.execute(
        "SELECT * FROM work_logs WHERE log_date BETWEEN ? AND ? "
        "ORDER BY log_date DESC, id DESC", (ws, we)).fetchall()
    notes = db.execute(
        "SELECT * FROM study_notes WHERE substr(created_at,1,10) BETWEEN ? AND ? "
        "ORDER BY id DESC", (ws, we)).fetchall()
    done_todos = db.execute("SELECT * FROM todos WHERE done=1").fetchall()
    open_todos = db.execute("SELECT * FROM todos WHERE done=0 ORDER BY due_date").fetchall()
    reviewed = db.execute(
        "SELECT * FROM study_notes WHERE last_reviewed BETWEEN ? AND ?", (ws, we)).fetchall()
    return render_template("review.html", logs=logs, notes=notes,
                           done_todos=done_todos, open_todos=open_todos,
                           reviewed=reviewed, week_start=ws, week_end=we)


@app.route("/report/weekly")
@login_required
def weekly_report():
    db = get_db()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    ws, we = week_start.isoformat(), today.isoformat()
    logs = db.execute(
        "SELECT * FROM work_logs WHERE log_date BETWEEN ? AND ? ORDER BY log_date, id",
        (ws, we)).fetchall()
    open_todos = db.execute(
        "SELECT * FROM todos WHERE done=0 ORDER BY CASE priority WHEN '高' THEN 0 "
        "WHEN '中' THEN 1 ELSE 2 END, due_date").fetchall()
    resolved_bugs = db.execute(
        "SELECT * FROM bugs WHERE status='已解决' AND substr(created_at,1,10) "
        "BETWEEN ? AND ?", (ws, we)).fetchall()
    lines = [f"工作周报（{ws} ~ {we}）", "", "一、本周工作内容"]
    if logs:
        for i, log in enumerate(logs, 1):
            proj = f"[{log['project']}] " if log["project"] else ""
            lines.append(f"{i}. {log['log_date']} {proj}{log['title']}")
            if log["content"]:
                for cl in log["content"].splitlines():
                    if cl.strip():
                        lines.append(f"   {cl.strip()}")
    else:
        lines.append("（本周暂无工作记录）")
    if resolved_bugs:
        lines += ["", "二、本周解决的 Bug"]
        for i, b in enumerate(resolved_bugs, 1):
            lines.append(f"{i}. [{b['platform']}] {b['title']}")
    lines += ["", "三、下周工作计划（待办跟进）"]
    if open_todos:
        for i, t in enumerate(open_todos, 1):
            due = f"（截止 {t['due_date']}）" if t["due_date"] else ""
            lines.append(f"{i}. [{t['priority']}] {t['title']}{due}")
    else:
        lines.append("（无遗留待办）")
    report = "\n".join(lines)
    return render_template("report.html", report=report, week_start=ws, week_end=we)


# ---------- 快捷记录与其他 ----------

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
        elif text.startswith("#日记"):
            body = text.split(" ", 1)[-1] if " " in text else text.lstrip("#日记 ")
            db.execute(
                "INSERT INTO diaries (diary_date, mood, content, created_at) VALUES (?,?,?,?) "
                "ON CONFLICT(diary_date) DO UPDATE SET content=excluded.content",
                (today, "", body, now))
        elif text.startswith(("#bug", "#Bug", "#BUG")):
            body = text.split(" ", 1)[-1] if " " in text else text[4:].strip()
            db.execute(
                "INSERT INTO bugs (title, platform, severity, status, created_at) "
                "VALUES (?,?,?,?,?)", (body, "通用", "中", "待解决", now))
        else:
            body = text.split(" ", 1)[-1] if text.startswith("#工作") and " " in text else text
            db.execute(
                "INSERT INTO work_logs (log_date, title, content, tags, created_at) "
                "VALUES (?,?,?,?,?)", (today, body[:80], body, "速记", now))
        db.commit()
    return redirect(url_for("index"))


@app.route("/api/stats")
@login_required
def api_stats():
    db = get_db()
    return jsonify({
        "work_logs": db.execute("SELECT COUNT(*) c FROM work_logs").fetchone()["c"],
        "study_notes": db.execute("SELECT COUNT(*) c FROM study_notes").fetchone()["c"],
        "todos_open": db.execute("SELECT COUNT(*) c FROM todos WHERE done=0").fetchone()["c"],
        "todos_done": db.execute("SELECT COUNT(*) c FROM todos WHERE done=1").fetchone()["c"],
        "diaries": db.execute("SELECT COUNT(*) c FROM diaries").fetchone()["c"],
        "habits": db.execute("SELECT COUNT(*) c FROM habits").fetchone()["c"],
        "bugs_open": db.execute(
            "SELECT COUNT(*) c FROM bugs WHERE status='待解决'").fetchone()["c"],
        "snippets": db.execute("SELECT COUNT(*) c FROM snippets").fetchone()["c"],
        "interview_questions": db.execute(
            "SELECT COUNT(*) c FROM interview_questions").fetchone()["c"],
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(timespec="seconds")})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
