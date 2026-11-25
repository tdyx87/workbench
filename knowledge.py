"""知识库蓝图：Bug、学习路线、片段、发版、面试题、编译错误、性能、命令、读书、崩溃。"""
import re
from datetime import date, datetime, timedelta

from flask import (Blueprint, jsonify, redirect, render_template, request,
                   url_for)

from shared import (COMPILERS, PLATFORMS, REVIEW_INTERVALS,
                    archive_and_delete, get_db, log_edit, login_required)

bp = Blueprint("knowledge", __name__)


# ---------- Bug 追踪 ----------

@bp.route("/bugs")
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
        sql += " AND (title LIKE ? OR phenomenon LIKE ? OR solution LIKE ? OR model LIKE ? OR driver_version LIKE ?)"
        params += [f"%{q}%"] * 5
    sql += " ORDER BY CASE status WHEN '待解决' THEN 0 ELSE 1 END, " \
           "CASE severity WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END, id DESC"
    rows = db.execute(sql, params).fetchall()
    driver_versions = [r[0] for r in db.execute(
        "SELECT DISTINCT driver_version FROM drivers WHERE driver_version!='' "
        "ORDER BY driver_version DESC").fetchall()]
    printer_models = [r[0] for r in db.execute(
        "SELECT model FROM printers ORDER BY model").fetchall()]
    return render_template("bugs.html", bugs=rows, platforms=PLATFORMS,
                           driver_versions=driver_versions, printer_models=printer_models,
                           active_platform=platform, active_status=status, q=q)


@bp.route("/api/bugs", methods=["POST"])
@login_required
def add_bug():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO bugs (title, platform, severity, phenomenon, root_cause, "
        "solution, status, driver_version, model, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (f["title"], f.get("platform", "通用"), f.get("severity", "中"),
         f.get("phenomenon", ""), f.get("root_cause", ""), f.get("solution", ""),
         f.get("status", "待解决"), f.get("driver_version", ""), f.get("model", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("knowledge.bugs_page"))


@bp.route("/api/bugs/<int:bug_id>/resolve", methods=["POST"])
@login_required
def resolve_bug(bug_id):
    db = get_db()
    old = db.execute("SELECT status FROM bugs WHERE id=?", (bug_id,)).fetchone()
    db.execute("UPDATE bugs SET status = CASE status WHEN '待解决' THEN '已解决' "
               "ELSE '待解决' END WHERE id=?", (bug_id,))
    if old:
        new_status = "已解决" if old["status"] == "待解决" else "待解决"
        db.execute(
            "INSERT INTO edit_history (module, ref_id, action, detail, created_at) "
            "VALUES ('bugs', ?, '状态变更', ?, ?)",
            (bug_id, f"{old['status']} → {new_status}",
             datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(request.referrer or url_for("knowledge.bugs_page"))


@bp.route("/api/bugs/<int:bug_id>/delete", methods=["POST"])
@login_required
def del_bug(bug_id):
    db = get_db()
    archive_and_delete(db, "bugs", bug_id)
    db.commit()
    return redirect(url_for("knowledge.bugs_page"))


# ---------- 技术学习路线 ----------

@bp.route("/roadmap")
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


@bp.route("/api/roadmap", methods=["POST"])
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
    return redirect(url_for("knowledge.roadmap_page"))


@bp.route("/api/roadmap/<int:topic_id>/progress", methods=["POST"])
@login_required
def update_topic_progress(topic_id):
    db = get_db()
    progress = max(0, min(100, int(request.form.get("progress", 0))))
    status = "已掌握" if progress >= 100 else ("进行中" if progress > 0 else "未开始")
    old = db.execute("SELECT progress FROM roadmap_topics WHERE id=?",
                     (topic_id,)).fetchone()
    db.execute("UPDATE roadmap_topics SET progress=?, status=? WHERE id=?",
               (progress, status, topic_id))
    if old:
        log_edit(db, "roadmap_topics", topic_id, "进度变更",
                 f"{old['progress']}% → {progress}%")
    db.commit()
    return redirect(url_for("knowledge.roadmap_page"))


@bp.route("/api/roadmap/<int:topic_id>/delete", methods=["POST"])
@login_required
def del_topic(topic_id):
    db = get_db()
    archive_and_delete(db, "roadmap_topics", topic_id)
    db.commit()
    return redirect(url_for("knowledge.roadmap_page"))


# ---------- 代码片段库 ----------

@bp.route("/snippets")
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


@bp.route("/api/snippets", methods=["POST"])
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
    return redirect(url_for("knowledge.snippets_page"))


@bp.route("/api/snippets/<int:snippet_id>/delete", methods=["POST"])
@login_required
def del_snippet(snippet_id):
    db = get_db()
    archive_and_delete(db, "snippets", snippet_id)
    db.commit()
    return redirect(url_for("knowledge.snippets_page"))


# ---------- 版本发布记录 ----------

@bp.route("/releases")
@login_required
def releases_page():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM releases ORDER BY release_date DESC, id DESC").fetchall()
    pending_tests = db.execute(
        "SELECT * FROM test_matrix WHERE result!='通过' ORDER BY "
        "CASE result WHEN '失败' THEN 0 WHEN '阻塞' THEN 1 ELSE 2 END, id DESC").fetchall()
    return render_template("releases.html", releases=rows, pending_tests=pending_tests,
                           today=date.today().isoformat())


@bp.route("/api/releases", methods=["POST"])
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
    return redirect(url_for("knowledge.releases_page"))


@bp.route("/api/releases/<int:release_id>/delete", methods=["POST"])
@login_required
def del_release(release_id):
    db = get_db()
    archive_and_delete(db, "releases", release_id)
    db.commit()
    return redirect(url_for("knowledge.releases_page"))


# ---------- 面试题集 ----------

@bp.route("/interview")
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


@bp.route("/api/interview", methods=["POST"])
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
    return redirect(url_for("knowledge.interview_page"))


@bp.route("/api/interview/<int:qid>/review", methods=["POST"])
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
        log_edit(db, "interview_questions", qid, "复习打卡",
                 f"阶段 {stage}，下次 {nxt}")
        db.commit()
    return redirect(request.referrer or url_for("knowledge.interview_page"))


@bp.route("/api/interview/<int:qid>/delete", methods=["POST"])
@login_required
def del_interview(qid):
    db = get_db()
    archive_and_delete(db, "interview_questions", qid)
    db.commit()
    return redirect(url_for("knowledge.interview_page"))


# ---------- 编译错误速查库 ----------

@bp.route("/compile_errors")
@login_required
def compile_errors_page():
    compiler = request.args.get("compiler", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM compile_errors WHERE 1=1"
    params = []
    if compiler:
        sql += " AND compiler=?"
        params.append(compiler)
    if q:
        sql += " AND (error_msg LIKE ? OR root_cause LIKE ? OR solution LIKE ? OR tags LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()
    return render_template("compile_errors.html", errors=rows, compilers=COMPILERS,
                           active_compiler=compiler, q=q)


@bp.route("/api/compile_errors", methods=["POST"])
@login_required
def add_compile_error():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO compile_errors (compiler, error_msg, root_cause, solution, tags, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f.get("compiler", "GCC"), f["error_msg"], f.get("root_cause", ""),
         f.get("solution", ""), f.get("tags", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("knowledge.compile_errors_page"))


@bp.route("/api/compile_errors/<int:err_id>/delete", methods=["POST"])
@login_required
def del_compile_error(err_id):
    db = get_db()
    archive_and_delete(db, "compile_errors", err_id)
    db.commit()
    return redirect(url_for("knowledge.compile_errors_page"))


# ---------- 性能优化记录 ----------

@bp.route("/perf")
@login_required
def perf_page():
    db = get_db()
    rows = db.execute("SELECT * FROM perf_records ORDER BY id DESC").fetchall()
    return render_template("perf.html", records=rows)


@bp.route("/api/perf", methods=["POST"])
@login_required
def add_perf():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO perf_records (title, target, before_metric, after_metric, "
        "technique, detail, created_at) VALUES (?,?,?,?,?,?,?)",
        (f["title"], f.get("target", ""), f.get("before_metric", ""),
         f.get("after_metric", ""), f.get("technique", ""), f.get("detail", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("knowledge.perf_page"))


@bp.route("/api/perf/<int:record_id>/delete", methods=["POST"])
@login_required
def del_perf(record_id):
    db = get_db()
    archive_and_delete(db, "perf_records", record_id)
    db.commit()
    return redirect(url_for("knowledge.perf_page"))


# ---------- 命令速查 ----------

@bp.route("/commands")
@login_required
def commands_page():
    cat = request.args.get("category", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    categories = [r["category"] for r in db.execute(
        "SELECT DISTINCT category FROM commands ORDER BY category").fetchall()]
    sql = "SELECT * FROM commands WHERE 1=1"
    params = []
    if cat:
        sql += " AND category=?"
        params.append(cat)
    if q:
        sql += " AND (name LIKE ? OR command LIKE ? OR description LIKE ?)"
        params += [f"%{q}%"] * 3
    sort = request.args.get("sort", "").strip()
    if sort == "hot":
        sql += " ORDER BY COALESCE(use_count,0) DESC, category, id"
    else:
        sql += " ORDER BY category, id"
    rows = db.execute(sql, params).fetchall()
    hot = db.execute(
        "SELECT * FROM commands WHERE COALESCE(use_count,0) > 0 "
        "ORDER BY use_count DESC, last_used DESC LIMIT 6").fetchall()
    return render_template("commands.html", commands=rows, categories=categories,
                           active_cat=cat, q=q, sort=sort, hot=hot)


@bp.route("/api/commands", methods=["POST"])
@login_required
def add_command():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO commands (category, name, command, description, created_at) "
        "VALUES (?,?,?,?,?)",
        (f.get("category") or "通用", f["name"], f["command"],
         f.get("description", ""), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("knowledge.commands_page"))


@bp.route("/api/commands/<int:cmd_id>/use", methods=["POST"])
@login_required
def use_command(cmd_id):
    """记录一次使用：频次 +1，写入最后使用时间。"""
    db = get_db()
    db.execute(
        "UPDATE commands SET use_count = COALESCE(use_count,0) + 1, "
        "last_used = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), cmd_id))
    db.commit()
    row = db.execute("SELECT use_count FROM commands WHERE id=?",
                     (cmd_id,)).fetchone()
    return jsonify({"ok": True,
                    "use_count": row["use_count"] if row else 0})


@bp.route("/api/commands/<int:cmd_id>/delete", methods=["POST"])
@login_required
def del_command(cmd_id):
    db = get_db()
    archive_and_delete(db, "commands", cmd_id)
    db.commit()
    return redirect(url_for("knowledge.commands_page"))


# ---------- 读书笔记 ----------

@bp.route("/books")
@login_required
def books_page():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM books ORDER BY CASE status WHEN '在读' THEN 0 WHEN '想读' THEN 1 "
        "WHEN '读完' THEN 2 ELSE 3 END, id DESC").fetchall()
    books = []
    for r in rows:
        d = dict(r)
        d["percent"] = (min(100, round(d["read_pages"] * 100 / d["total_pages"]))
                        if d["total_pages"] else 0)
        books.append(d)
    return render_template("books.html", books=books)


@bp.route("/api/books", methods=["POST"])
@login_required
def add_book():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO books (title, author, category, total_pages, read_pages, "
        "status, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (f["title"], f.get("author", ""), f.get("category") or "技术",
         int(f.get("total_pages") or 0), int(f.get("read_pages") or 0),
         f.get("status", "在读"), f.get("note", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("knowledge.books_page"))


@bp.route("/api/books/<int:book_id>/progress", methods=["POST"])
@login_required
def update_book_progress(book_id):
    db = get_db()
    row = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if row:
        read_pages = max(0, int(request.form.get("read_pages", 0)))
        status = request.form.get("status", row["status"])
        if row["total_pages"] and read_pages >= row["total_pages"]:
            read_pages = row["total_pages"]
            status = "读完"
        db.execute("UPDATE books SET read_pages=?, status=? WHERE id=?",
                   (read_pages, status, book_id))
        log_edit(db, "books", book_id, "阅读进度",
                 f"{row['read_pages']} → {read_pages} 页（{status}）")
        db.commit()
    return redirect(url_for("knowledge.books_page"))


@bp.route("/api/books/<int:book_id>/delete", methods=["POST"])
@login_required
def del_book(book_id):
    db = get_db()
    archive_and_delete(db, "books", book_id)
    db.commit()
    return redirect(url_for("knowledge.books_page"))


# ---------- 崩溃分析档案 ----------

CRASH_SIGNALS = ["SIGSEGV", "SIGABRT", "SIGBUS", "SIGFPE", "SIGILL", "其他"]


@bp.route("/crashes")
@login_required
def crashes_page():
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM crashes WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if q:
        sql += " AND (title LIKE ? OR stack LIKE ? OR root_cause LIKE ? OR module LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY CASE status WHEN '待分析' THEN 0 ELSE 1 END, id DESC"
    rows = db.execute(sql, params).fetchall()
    # 错误码下拉数据 + 已关联错误码回填（打通 error_codes 链路）
    err_codes = db.execute(
        "SELECT id, brand, code, title FROM error_codes "
        "ORDER BY brand, code").fetchall()
    code_map = {r["id"]: r for r in err_codes}
    linked_codes = {}
    for r in rows:
        keys = r.keys()
        if "error_code_id" in keys and r["error_code_id"]:
            hit = code_map.get(r["error_code_id"])
            if hit:
                linked_codes[r["id"]] = hit
    return render_template("crashes.html", crashes=rows, signals=CRASH_SIGNALS,
                           active_status=status, q=q, err_codes=err_codes,
                           linked_codes=linked_codes)


@bp.route("/api/crashes", methods=["POST"])
@login_required
def add_crash():
    f = request.form
    db = get_db()
    ecid = f.get("error_code_id", "").strip()
    error_code_id = int(ecid) if ecid.isdigit() else None
    db.execute(
        "INSERT INTO crashes (title, module, signal, stack, root_cause, fix, "
        "status, error_code_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (f["title"], f.get("module", ""), f.get("signal", ""),
         f.get("stack", ""), f.get("root_cause", ""), f.get("fix", ""),
         f.get("status", "待分析"), error_code_id,
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("knowledge.crashes_page"))


@bp.route("/api/crashes/<int:crash_id>/resolve", methods=["POST"])
@login_required
def resolve_crash(crash_id):
    db = get_db()
    old = db.execute("SELECT status FROM crashes WHERE id=?",
                     (crash_id,)).fetchone()
    db.execute("UPDATE crashes SET status = CASE status WHEN '待分析' THEN '已修复' "
               "ELSE '待分析' END WHERE id=?", (crash_id,))
    if old:
        nxt = "已修复" if old["status"] == "待分析" else "待分析"
        log_edit(db, "crashes", crash_id, "状态变更",
                 f"{old['status']} → {nxt}")
    db.commit()
    return redirect(request.referrer or url_for("knowledge.crashes_page"))


# ---------- 崩溃日志自动解析 ----------

CRASH_SIGNAL_RE = re.compile(
    r"SIG(?:SEGV|ABRT|BUS|FPE|ILL|TERM|KILL|TRAP|SYS)"
    r"|Segmentation fault|Aborted|core dumped"
    r"|Access violation|EXCEPTION_ACCESS_VIOLATION",
    re.IGNORECASE)

CRASH_FRAME_RE = re.compile(
    r"#(?:0|[1-9][0-9]{0,2})\s+0x[0-9a-fA-F]+\s+in\s+([^\s(]+)")

CRASH_PATH_RE = re.compile(
    r"([A-Za-z0-9_.\-]+)\.(?:c|cc|cpp|cxx|h|hpp|m|mm|rs|go|py|java|kt)"
    r":([0-9]+)")

CRASH_ERRCODE_RE = re.compile(
    r"\bSC[0-9]{3}\b|\b[0-9]{2}\.[0-9A-Z][0-9A-Z]{2,4}\b"
    r"|\bE[0-9]{3}\b|\bERR[0-9]{1,4}\b")

CRASH_HINTS = [
    ("空指针 / 无效地址", ["null pointer", "nullptr", "address 0x0",
                          "0x0000000000000000", "null dereference"]),
    ("数组越界 / 缓冲区溢出", ["buffer overflow", "out of bounds",
                              "stack smashing", "heap-buffer-overflow"]),
    ("堆内存损坏 / 重复释放", ["double free", "invalid pointer",
                              "free(): ", "heap corruption", "use-after-free"]),
    ("栈溢出 / 递归过深", ["stack overflow", "stack-overflow",
                           "infinite recursion"]),
    ("除零 / 算术异常", ["division by zero", "divide by zero", "integer divide"]),
    ("断言失败", ["assertion", "assert failed", "Assertion `"]),
    ("依赖库缺失 / 加载失败", ["cannot open shared object", "undefined symbol",
                               "library not found", "ImportError", "DLL load failed"]),
    ("线程竞态 / 死锁", ["deadlock", "race condition", "mutex",
                         "resource deadlock"]),
]


def parse_crash_log(text):
    """从原始崩溃日志中提取结构化字段，供前端预填后人工确认。"""
    raw = (text or "").strip()
    if not raw:
        return {"ok": False, "error": "日志内容为空"}

    lines = raw.splitlines()
    signal = ""
    m = CRASH_SIGNAL_RE.search(raw)
    if m:
        token = m.group(0)
        upper = token.upper()
        if upper.startswith("SIG"):
            signal = upper
        elif "SEGMENTATION" in upper or "ACCESS VIOLATION" in upper:
            signal = "SIGSEGV"
        elif "ABORT" in upper:
            signal = "SIGABRT"
        elif "CORE DUMPED" in upper:
            signal = "SIGSEGV"

    frames = CRASH_FRAME_RE.findall(raw)
    stack = "\n".join(lines[:80]) if len(lines) > 1 else raw[:2000]

    # 模块：优先取出现次数最多的源文件名
    paths = CRASH_PATH_RE.findall(raw)
    module = ""
    if paths:
        counts = {}
        for name, _ln in paths:
            counts[name] = counts.get(name, 0) + 1
        module = max(counts, key=counts.get)
    elif frames:
        top = frames[0]
        if "::" in top:
            module = top.split("::")[0]
        elif "_" in top:
            module = top.split("_")[0]
        else:
            module = top

    codes = CRASH_ERRCODE_RE.findall(raw)
    error_code = codes[0] if codes else ""

    low = raw.lower()
    hint = ""
    for label, keys in CRASH_HINTS:
        if any(k.lower() in low for k in keys):
            hint = label
            break

    # 标题建议：信号 + 顶层帧，便于直接采用
    title = ""
    if frames:
        title = "%s: %s" % (signal or "崩溃", frames[0][:60])
    elif signal:
        title = "%s 崩溃" % signal

    return {
        "ok": True,
        "signal": signal,
        "module": module[:60],
        "stack": stack,
        "title": title[:120],
        "error_code": error_code,
        "root_hint": hint,
        "frames": frames[:8],
        "path_count": len(paths),
        "line_count": len(lines),
    }


@bp.route("/api/crashes/parse", methods=["POST"])
@login_required
def parse_crash_api():
    """粘贴原始崩溃日志，返回自动解析出的字段供人工确认。"""
    data = request.get_json(silent=True) or {}
    raw = data.get("raw") or request.form.get("raw", "")
    return jsonify(parse_crash_log(raw))


@bp.route("/api/crashes/<int:crash_id>/delete", methods=["POST"])
@login_required
def del_crash(crash_id):
    db = get_db()
    archive_and_delete(db, "crashes", crash_id)
    db.commit()
    return redirect(url_for("knowledge.crashes_page"))
