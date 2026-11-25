#!/usr/bin/env python3
"""个人工作台 - Flask + SQLite 单文件应用
通用模块：概览、工作记录、学习笔记、待办事项、日记、习惯打卡、每周回顾、周报
客户端程序员模块：Bug 追踪、技术学习路线、代码片段库、版本发布记录、面试题集
"""
import functools
import hashlib
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import markdown as md_lib
from flask import (Flask, Response, g, jsonify, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup, escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
CREATE TABLE IF NOT EXISTS compile_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compiler TEXT DEFAULT 'GCC',
    error_msg TEXT NOT NULL,
    root_cause TEXT DEFAULT '',
    solution TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS perf_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    target TEXT DEFAULT '',
    before_metric TEXT DEFAULT '',
    after_metric TEXT DEFAULT '',
    technique TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT DEFAULT '通用',
    name TEXT NOT NULL,
    command TEXT NOT NULL,
    description TEXT DEFAULT '',
    use_count INTEGER DEFAULT 0,
    last_used TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT DEFAULT '',
    category TEXT DEFAULT '技术',
    total_pages INTEGER DEFAULT 0,
    read_pages INTEGER DEFAULT 0,
    status TEXT DEFAULT '在读',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    module TEXT DEFAULT '',
    signal TEXT DEFAULT '',
    stack TEXT DEFAULT '',
    root_cause TEXT DEFAULT '',
    fix TEXT DEFAULT '',
    status TEXT DEFAULT '待分析',
    error_code_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    driver_version TEXT DEFAULT '',
    firmware_version TEXT DEFAULT '',
    release_date TEXT DEFAULT '',
    changes TEXT DEFAULT '',
    known_issues TEXT DEFAULT '',
    recommend TEXT DEFAULT '待验证',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protocols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    protocol TEXT DEFAULT 'IPP',
    summary TEXT DEFAULT '',
    commands TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS test_matrix (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_version TEXT NOT NULL,
    model TEXT NOT NULL,
    test_item TEXT NOT NULL,
    result TEXT DEFAULT '未测',
    tester TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS error_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT DEFAULT '通用/CUPS',
    code TEXT NOT NULL,
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    solution TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS log_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source TEXT DEFAULT 'CUPS error_log',
    pattern TEXT DEFAULT '',
    interpretation TEXT DEFAULT '',
    action TEXT DEFAULT '',
    error_code_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS printers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    languages TEXT DEFAULT '',
    duplex TEXT DEFAULT '',
    trays TEXT DEFAULT '',
    memory TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    location TEXT DEFAULT '',
    owner TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    model TEXT DEFAULT '',
    cycle_days INTEGER DEFAULT 30,
    last_done TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    deleted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS printer_probe_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    printer_id INTEGER NOT NULL,
    ok INTEGER DEFAULT 0,
    detail TEXT DEFAULT '',
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_probe_logs_printer
    ON printer_probe_logs (printer_id, id DESC);
"""

MIGRATIONS = [
    "ALTER TABLE work_logs ADD COLUMN project TEXT DEFAULT ''",
    "ALTER TABLE todos ADD COLUMN project TEXT DEFAULT ''",
    "ALTER TABLE study_notes ADD COLUMN next_review TEXT DEFAULT ''",
    "ALTER TABLE study_notes ADD COLUMN review_stage INTEGER DEFAULT 0",
    "ALTER TABLE study_notes ADD COLUMN last_reviewed TEXT DEFAULT ''",
]


DEFAULT_TEMPLATES = [
    ("日报", "工作日报", "【今日完成】\n\n【明日计划】\n\n【问题与风险】\n", "日报"),
    ("会议纪要", "会议纪要 - ",
     "【会议主题】\n【参会人员】\n【讨论要点】\n1. \n【结论与行动项】\n1. ", "会议"),
    ("周报", "本周工作总结", "【本周重点工作】\n\n【关键进展】\n\n【下周计划】\n\n【需要支持】\n", "周报"),
]

# C++ 预置面试题库（题库为空时自动导入）
CPP_INTERVIEW_QUESTIONS = [
    ("虚函数的实现机制是什么？",
     "- 每个含虚函数的类生成一张**虚函数表（vtable）**，编译期确定\n- 对象头部隐藏一个 **vptr 指针**指向该表\n- 调用虚函数时通过 vptr 间接寻址，实现运行时多态\n- 多重继承下有多个 vptr；虚析构保证 delete 基类指针正确析构",
     "C++ 基础"),
    ("shared_ptr 和 unique_ptr 的区别与使用场景？",
     "- **unique_ptr**：独占所有权，不可拷贝只能 move，零开销，默认首选\n- **shared_ptr**：引用计数共享所有权，计数归零析构；有原子操作开销\n- 注意 shared_ptr 循环引用问题，用 weak_ptr 打破\n- make_shared/make_unique 创建，异常安全且减少一次内存分配",
     "C++ 基础"),
    ("什么是 RAII？举例说明",
     "- Resource Acquisition Is Initialization：资源获取即初始化\n- 利用**栈对象析构函数自动执行**的特性管理资源\n- 典型应用：lock_guard 管理锁、智能指针管理内存、fstream 管理文件句柄\n- 核心思想：资源的获取与释放绑定到对象生命周期，异常安全",
     "C++ 基础"),
    ("移动语义和完美转发的原理？",
     "- 移动语义：通过**右值引用（T&&）**将资源从临时对象『偷』过来，避免深拷贝\n- std::move 只是强制转换为右值引用，本身不移动任何东西\n- 完美转发：模板参数 T&&（万能引用）+ std::forward 保持参数的左值/右值属性\n- 引用折叠规则：& + & = &，&& + & = &，&& + && = &&",
     "C++11/14/17/20"),
    ("vector 的扩容机制？push_back 的复杂度？",
     "- 容量不足时分配新内存（通常 **2 倍或 1.5 倍**增长），移动/拷贝旧元素，释放旧内存\n- push_back 均摊 O(1)，最坏 O(n)\n- reserve 预分配避免扩容；扩容会使迭代器、指针、引用失效\n- C++11 后元素有 noexcept 移动构造时优先移动，否则拷贝",
     "STL"),
    ("C++ 中如何保证线程安全？常见同步原语有哪些？",
     "- **互斥锁**：mutex / lock_guard / unique_lock（可 defer、try_lock）\n- **读写锁**：shared_mutex（C++17），读共享写独占\n- **条件变量**：condition_variable 配合 unique_lock，注意虚假唤醒要用 while 判断\n- **原子操作**：atomic<T>，memory_order 控制内存序\n- 无锁队列、thread_local 也是常见手段",
     "多线程并发"),
    ("内存泄漏如何排查？",
     "- **工具**：Valgrind（memcheck）、AddressSanitizer（编译加 -fsanitize=address）、LeakSanitizer\n- **代码层面**：new/delete 配对；优先用智能指针和 RAII\n- **排查思路**：ASan 报告直接给分配栈回溯；Valgrind 的 definitely lost 优先处理\n- 长稳服务观察 RSS 趋势定位泄漏模块",
     "内存管理"),
    ("select / poll / epoll 的区别？",
     "- **select**：fd 集合位图（FD_SETSIZE 限制 1024），每次调用整体拷贝，O(n) 遍历\n- **poll**：链表结构无数量上限，但仍 O(n) 遍历，每次全量拷贝\n- **epoll**：内核维护就绪链表，epoll_wait 只返回就绪 fd，O(1)；支持 LT（水平触发）和 ET（边缘触发）\n- ET 模式必须配合非阻塞 IO 循环读写直到 EAGAIN",
     "网络编程"),
    ("什么是内存碎片？如何缓解？",
     "- 频繁分配释放不同大小内存，导致空闲内存不连续，总量够但大块分配失败\n- 缓解手段：**内存池**（固定大小块快速分配）、对象池、jemalloc/tcmalloc 替换默认分配器\n- slab/slub 是内核中的同类思想",
     "内存管理"),
    ("static 关键字在 C++ 中的几种用法？",
     "1. 函数内静态局部变量：只初始化一次（C++11 起线程安全），生命周期贯穿程序\n2. 全局静态变量/函数：限制在本翻译单元可见（内部链接）\n3. 类静态成员变量：全类共享一份，需在类外定义\n4. 类静态成员函数：无 this 指针，只能访问静态成员",
     "C++ 基础"),
]

# C++ 预置代码片段（片段库为空时自动导入）
CPP_SNIPPETS = [
    ("线程安全单例（Meyers Singleton）", "cpp",
     "class Singleton {\npublic:\n    static Singleton& instance() {\n        static Singleton inst;  // C++11 起线程安全\n        return inst;\n    }\n    Singleton(const Singleton&) = delete;\n    Singleton& operator=(const Singleton&) = delete;\nprivate:\n    Singleton() = default;\n};",
     "设计模式,单例"),
    ("RAII 文件句柄封装", "cpp",
     "class FileGuard {\npublic:\n    explicit FileGuard(const char* path, const char* mode)\n        : fp_(fopen(path, mode)) {\n        if (!fp_) throw std::runtime_error(\"open failed\");\n    }\n    ~FileGuard() { if (fp_) fclose(fp_); }\n    FileGuard(const FileGuard&) = delete;\n    FileGuard& operator=(const FileGuard&) = delete;\n    FILE* get() { return fp_; }\nprivate:\n    FILE* fp_;\n};",
     "RAII,资源管理"),
    ("读写锁封装（C++17 shared_mutex）", "cpp",
     "class RWLock {\npublic:\n    void readLock()  { m_.lock_shared(); }\n    void readUnlock() { m_.unlock_shared(); }\n    void writeLock() { m_.lock(); }\n    void writeUnlock() { m_.unlock(); }\nprivate:\n    std::shared_mutex m_;\n};\n\n// 使用：读多写少场景\n// std::shared_lock<std::shared_mutex> lk(mtx);  // 读\n// std::unique_lock<std::shared_mutex> lk(mtx);  // 写",
     "多线程,锁"),
    ("chrono 耗时统计（Scope Timer）", "cpp",
     "class ScopeTimer {\npublic:\n    explicit ScopeTimer(std::string tag) : tag_(std::move(tag)),\n        start_(std::chrono::steady_clock::now()) {}\n    ~ScopeTimer() {\n        auto us = std::chrono::duration_cast<std::chrono::microseconds>(\n            std::chrono::steady_clock::now() - start_).count();\n        printf(\"[%s] cost %.3f ms\\n\", tag_.c_str(), us / 1000.0);\n    }\nprivate:\n    std::string tag_;\n    std::chrono::steady_clock::time_point start_;\n};",
     "性能,工具"),
]

# C++ 程序员预置命令速查（命令库为空时自动导入）
CPP_COMMANDS = [
    ("GDB", "启动调试", "gdb ./program", "加载可执行文件开始调试"),
    ("GDB", "分析 core 文件", "gdb ./program core.1234", "事后分析崩溃现场，配合 bt full 查看完整堆栈"),
    ("GDB", "条件断点", "break main.cpp:42 if count > 100", "仅在条件满足时中断"),
    ("GDB", "观察点", "watch g_state", "变量被写入时立即中断，排查野写"),
    ("GDB", "完整调用栈", "bt full", "显示调用栈及每帧局部变量"),
    ("GDB", "线程切换", "thread apply all bt", "查看所有线程堆栈，排查死锁/竞态"),
    ("perf", "CPU 热点分析", "perf record -g ./program && perf report", "采样调用图，定位 CPU 热点函数"),
    ("perf", "实时热点", "perf top -p $(pgrep program)", "实时查看运行中进程的热点"),
    ("Valgrind", "内存泄漏检测", "valgrind --leak-check=full --show-leak-kinds=all ./program", "优先处理 definitely lost 项"),
    ("Sanitizer", "地址检测", "g++ -fsanitize=address -g main.cpp -o main", "ASan：越界访问、use-after-free、内存泄漏"),
    ("Sanitizer", "线程竞态检测", "g++ -fsanitize=thread -g main.cpp -o main", "TSan：检测数据竞争，注意不能与 ASan 同开"),
    ("CMake", "Debug 构建", "cmake -B build -DCMAKE_BUILD_TYPE=Debug && cmake --build build -j", "标准 out-of-source 构建"),
    ("CMake", "导出编译命令", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "生成 compile_commands.json，供 clangd 代码补全使用"),
    ("binutils", "查看符号表", "nm -C libxxx.a | grep symbol_name", "-C 反修饰 C++ 符号名，排查 undefined reference"),
    ("binutils", "查看动态库依赖", "ldd ./program", "排查运行时找不到 so 的问题"),
    ("binutils", "反汇编", "objdump -d -C ./program > asm.txt", "查看编译产物汇编，验证内联/优化效果"),
]

MOODS = ["😊", "😐", "😔", "😤", "🤔"]
@app.template_filter("md")
def render_markdown(text):
    return Markup(md_lib.markdown(
        text or "", extensions=["fenced_code", "tables", "nl2br"]))


from shared import get_db, close_db, DB_PATH, BASE_DIR  # noqa: E402
app.teardown_appcontext(close_db)


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
    now = datetime.now().isoformat(timespec="seconds")
    if db.execute("SELECT COUNT(*) FROM interview_questions").fetchone()[0] == 0:
        nxt = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
        db.executemany(
            "INSERT INTO interview_questions (question, answer, category, mastery, "
            "next_review, review_stage, created_at) VALUES (?,?,?,0,?,0,?)",
            [(q, a, c, nxt, now) for q, a, c in CPP_INTERVIEW_QUESTIONS])
    if db.execute("SELECT COUNT(*) FROM snippets").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO snippets (title, language, code, tags, created_at) "
            "VALUES (?,?,?,?,?)",
            [(t, l, c, g, now) for t, l, c, g in CPP_SNIPPETS])
    if db.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO commands (category, name, command, description, created_at) "
            "VALUES (?,?,?,?,?)",
            [(c, n, cmd, d, now) for c, n, cmd, d in CPP_COMMANDS])
    for c, n, cmd, d in PRINT_COMMANDS:
        if not db.execute(
                "SELECT 1 FROM commands WHERE name=? AND category=?",
                (n, c)).fetchone():
            db.execute(
                "INSERT INTO commands (category, name, command, description, created_at) "
                "VALUES (?,?,?,?,?)", (c, n, cmd, d, now))
    for col in ("driver_version", "model"):
        try:
            db.execute(f"ALTER TABLE bugs ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    for table_name, cols in IMPORT_TABLES.items():
        info = {r[1] for r in db.execute(f"PRAGMA table_info({table_name})").fetchall()}
        for col in cols:
            if col not in info:
                db.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} TEXT DEFAULT ''")
    for b, code, t, desc, sol in ERROR_CODES_SEED:
        if not db.execute(
                "SELECT 1 FROM error_codes WHERE brand=? AND code=?",
                (b, code)).fetchone():
            db.execute(
                "INSERT INTO error_codes (brand, code, title, description, solution, created_at) "
                "VALUES (?,?,?,?,?,?)", (b, code, t, desc, sol, now))
    for c, n, cmd, d in DEV_AI_COMMANDS:
        if not db.execute(
                "SELECT 1 FROM commands WHERE name=? AND category=?",
                (n, c)).fetchone():
            db.execute(
                "INSERT INTO commands (category, name, command, description, created_at) "
                "VALUES (?,?,?,?,?)", (c, n, cmd, d, now))
    nxt_review = (date.today() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
    for q, a, cat in DEV_AI_QUESTIONS:
        if not db.execute(
                "SELECT 1 FROM interview_questions WHERE question=?", (q,)).fetchone():
            db.execute(
                "INSERT INTO interview_questions (question, answer, category, mastery, "
                "next_review, review_stage, created_at) VALUES (?,?,?,0,?,0,?)",
                (q, a, cat, nxt_review, now))
    for t, lang, code, tags in DEV_AI_SNIPPETS:
        if not db.execute(
                "SELECT 1 FROM snippets WHERE title=?", (t,)).fetchone():
            db.execute(
                "INSERT INTO snippets (title, language, code, tags, created_at) "
                "VALUES (?,?,?,?,?)", (t, lang, code, tags, now))
    for name, cat, note in ROADMAP_SEED:
        if not db.execute(
                "SELECT 1 FROM roadmap_topics WHERE name=?", (name,)).fetchone():
            db.execute(
                "INSERT INTO roadmap_topics (name, category, progress, status, note, created_at) "
                "VALUES (?,?,0,'未开始',?,?)", (name, cat, note, now))
    db.commit()
    db.close()


from shared import IMPORT_TABLES  # noqa: E402
from shared import (COMPILERS, PLATFORMS, REVIEW_INTERVALS)  # noqa: E402
from shared import (_load_auth, _save_auth, get_api_token,
                    verify_api_token, notify_webhook,
                    log_edit, archive_and_delete)  # noqa: E402


from shared import verify_password, login_required  # noqa: E402


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
        "driver_pending": db.execute(
            "SELECT COUNT(*) c FROM drivers WHERE recommend='待验证'").fetchone()["c"],
        "test_untested": db.execute(
            "SELECT COUNT(*) c FROM test_matrix WHERE result='未测'").fetchone()["c"],
        "crash_pending": db.execute(
            "SELECT COUNT(*) c FROM crashes WHERE status='待分析'").fetchone()["c"],
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
    archive_and_delete(db, "work_logs", log_id)
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
    old = db.execute("SELECT mastery FROM study_notes WHERE id=?",
                     (note_id,)).fetchone()
    db.execute("UPDATE study_notes SET mastery=? WHERE id=?", (mastery, note_id))
    if old:
        log_edit(db, "study_notes", note_id, "掌握度变更",
                 f"{old['mastery']} → {mastery}")
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
        log_edit(db, "study_notes", note_id, "复习打卡",
                 f"阶段 {stage}，下次 {nxt}")
        db.commit()
    return redirect(request.referrer or url_for("study_page"))


@app.route("/api/study/<int:note_id>/delete", methods=["POST"])
@login_required
def del_study(note_id):
    db = get_db()
    archive_and_delete(db, "study_notes", note_id)
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
    old = db.execute("SELECT done FROM todos WHERE id=?",
                     (todo_id,)).fetchone()
    db.execute("UPDATE todos SET done = 1 - done WHERE id=?", (todo_id,))
    if old:
        arrow = "未完成 → 已完成" if not old["done"] else "已完成 → 未完成"
        log_edit(db, "todos", todo_id, "完成状态切换", arrow)
    db.commit()
    return redirect(url_for("todo_page"))


@app.route("/api/todo/<int:todo_id>/delete", methods=["POST"])
@login_required
def del_todo(todo_id):
    db = get_db()
    archive_and_delete(db, "todos", todo_id)
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
    archive_and_delete(db, "diaries", diary_id)
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
    archive_and_delete(db, "habits", habit_id)
    db.commit()
    return redirect(url_for("habit_page"))


# ---------- 打印调试命令（预置） ----------

PRINT_COMMANDS = [
    ("打印调试", "查看打印队列", "lpstat -o", "CUPS：列出当前所有打印任务及状态"),
    ("打印调试", "清空打印队列", "cancel -a", "CUPS：取消全部排队任务，队列卡死时使用"),
    ("打印调试", "开启 CUPS 调试日志", "cupsctl --debug-logging", "开启后日志写入 /var/log/cups/error_log，排查驱动问题必备"),
    ("打印调试", "查看 CUPS 错误日志", "tail -50 /var/log/cups/error_log", "过滤 [Job N] 可定位某个打印任务的完整流程"),
    ("打印调试", "IPP 属性探测", "ipptool -tv ipp://printer-ip/ ipp-everywhere.test", "探测打印机支持的 IPP 属性与能力集"),
    ("打印调试", "抓取 9100 端口原始数据", "tcpdump -i any -w /tmp/p9100.pcap port 9100", "抓 JetDirect/RAW 协议数据流，分析驱动下发的 PCL/PJL 指令"),
    ("打印调试", "Wireshark 过滤 IPP", "tcp.port == 631 || ipp", "IPP 走 631 端口；配合抓包分析属性协商过程"),
    ("打印调试", "重启打印服务(Linux)", "systemctl restart cups", "驱动安装/卸载后需重启 CUPS 生效"),
    ("打印调试", "重启打印服务(Windows)", "net stop spooler && net start spooler", "假脱机假死、队列卡住的通用修复"),
    ("打印调试", "Windows 清理 spool 目录", "del /q %SystemRoot%\\System32\\spool\\PRINTERS\\*", "停 spooler 后执行，清除损坏的排队任务"),
    ("打印调试", "CUPS 添加打印机", "lpadmin -p name -E -v ipp://ip/ipp -m everywhere", "用 IPP Everywhere 无驱动模式添加网络打印机"),
    ("打印调试", "发送原始打印数据", "lp -d printer -o raw file.pcl", "绕过过滤器直接下发，验证打印机对语言的解析"),
    ("打印调试", "查看打印机属性", "lpoptions -p printer -l", "列出驱动注册的所有可配置项（纸张/双面/分辨率等）"),
    ("打印调试", "PPD 语法检查", "cupstestppd -v driver.ppd", "验证自定义 PPD 文件是否符合规范"),
    ("打印调试", "Windows 驱动包管理", "printbrm -b -f backup.cab", "备份/还原打印机驱动与端口配置"),
    ("打印调试", "PJL 状态查询", "@PJL INFO STATUS", "向 9100 端口发送 PJL 指令查询打印机状态（USTATUS 可订阅事件）"),
]

# ---------- 开发进阶 + AI 开发命令（预置） ----------

DEV_AI_COMMANDS = [
    ("构建", "Ninja 并行构建", "cmake --build build -j$(nproc)", "全核并行编译，大项目显著提速"),
    ("构建", "ccache 缓存加速", "export CXX='ccache g++'", "重复编译命中缓存，二次构建提速 5-10 倍"),
    ("构建", "查看编译耗时", "time make -j$(nproc)", "评估构建优化前后的收益"),
    ("静态分析", "clang-tidy 检查", "clang-tidy -p build src/*.cpp", "依赖 compile_commands.json，发现潜在缺陷与风格问题"),
    ("静态分析", "cppcheck 全量检查", "cppcheck --enable=all --std=c++17 src/ 2>&1 | tee report.txt", "轻量级静态分析，无需编译数据库"),
    ("静态分析", "编译警告全开", "-Wall -Wextra -Werror -Wconversion", "Werror 把警告当错误处理，CI 中防止代码劣化"),
    ("性能剖析", "perf 采样分析", "perf record -g ./program && perf report", "定位 CPU 热点函数，-g 保留完整调用链"),
    ("性能剖析", "valgrind 内存检查", "valgrind --leak-check=full --track-origins=yes ./program", "查内存泄漏与未初始化读取，程序会慢 10-50 倍"),
    ("性能剖析", "heaptrack 堆分析", "heaptrack ./program && heaptrack_gui", "分析内存分配热点与峰值曲线"),
    ("调试进阶", "addr2line 地址转行号", "addr2line -e ./program -f -C 0x00401234", "配合崩溃日志中的地址直接定位源码行号"),
    ("调试进阶", "strace 跟踪系统调用", "strace -f -e trace=openat,connect ./program", "排查程序卡在哪个系统调用，驱动联调常用"),
    ("调试进阶", "ltrace 跟踪库调用", "ltrace -f ./program", "跟踪动态库函数调用，定位第三方库传参问题"),
    ("AI 开发", "Ollama 运行本地模型", "ollama run qwen2.5:7b", "一条命令拉取并启动对话，自动管理模型文件"),
    ("AI 开发", "Ollama 查看模型", "ollama list && ollama ps", "查看已下载模型与运行中实例的显存占用"),
    ("AI 开发", "llama.cpp 启动服务", "llama-server -m model.gguf -c 4096 -ngl 99 --port 8080", "提供 OpenAI 兼容接口，-ngl 99 全量卸载到 GPU"),
    ("AI 开发", "GGUF 模型量化", "llama-quantize model-f16.gguf model-q4_k_m.gguf Q4_K_M", "量化到 Q4_K_M，7B 模型约 4GB 显存即可运行"),
    ("AI 开发", "HF 模型转 GGUF", "python convert_hf_to_gguf.py ./hf_model --outfile model-f16.gguf", "llama.cpp 自带转换脚本，先转 F16 再量化"),
    ("AI 开发", "下载 HuggingFace 模型", "huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir ./qwen2.5-7b", "支持断点续传，国内可配 HF_ENDPOINT 镜像加速"),
    ("AI 开发", "查看 GPU 状态", "nvidia-smi -l 2", "每 2 秒刷新显存/利用率，推理压测时持续监控"),
    ("AI 开发", "验证 PyTorch CUDA", "python3 -c \"import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))\"", "环境安装后的冒烟检查"),
    ("AI 开发", "测试 OpenAI 兼容接口", "curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{\"model\":\"local\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'", "本地推理服务部署后的接口验证"),
    ("AI 开发", "推理性能基准", "llama-bench -m model.gguf -ngl 99", "输出 Prefill/Decode 的 token/s，评估量化与 GPU 卸载收益"),
]

# ---------- 开发进阶 + AI 方向面试题（预置） ----------

DEV_AI_QUESTIONS = [
    ("C++11 内存模型中 memory_order 各取值的含义？",
     "- **relaxed**：仅保证原子性不保证顺序，适合计数器场景\n- **acquire（读）/ release（写）**：配对形成 synchronizes-with 关系，常用于自旋锁与标志位\n- **acq_rel**：读改写操作同时具备两者语义\n- **seq_cst（默认）**：全局顺序一致，最严格也最慢\n- 原则：先写对（seq_cst），确认是热点后再放松序",
     "并发编程"),
    ("什么是 SFINAE？C++20 concepts 如何改进它？",
     "- SFINAE：替换失败不是错误，模板参数替换失败时仅从重载候选集中移除\n- 经典工具：std::enable_if、decltype、void_t\n- 缺点：语法晦涩、编译报错冗长难读\n- C++20 concepts：用 requires 表达式和 concept 直接声明约束，编译错误直指不满足的条件，可读性和诊断性大幅提升",
     "模板元编程"),
    ("什么是 false sharing（伪共享）？如何避免？",
     "- 不同线程修改同一缓存行（通常 64 字节）中的不同变量，导致缓存一致性协议频繁失效\n- 现象：逻辑上无竞争但性能骤降\n- 避免：alignas(64) 对齐填充、线程局部存储、按线程分桶计数后归并\n- C++17 提供 std::hardware_destructive_interference_size 获取缓存行大小",
     "并发编程"),
    ("std::move 的本质是什么？移动构造何时被调用？",
     "- std::move 只是 static_cast<T&&>，本身不移动任何东西\n- 移动语义靠移动构造/移动赋值实现；标记 noexcept 才会被 vector 扩容等场景采用\n- 触发时机：实参为将亡值（临时对象或 move 的结果）\n- 移动后的源对象处于有效但未指定状态，只能析构或重新赋值",
     "C++ 基础"),
    ("什么是 ABI 兼容性？动态库升级为什么可能导致崩溃？",
     "- ABI 涵盖调用约定、符号修饰、类布局、vtable 布局、STL 容器二进制表示\n- 破坏 ABI 的常见操作：增删虚函数、改变成员变量顺序/类型、切换 _GLIBCXX_USE_CXX11_ABI\n- 打印驱动场景：厂商 .so 升级后未重新编译的调用方，可能因 vtable 偏移错乱直接崩溃\n- 对策：C 接口封装隔离 ABI、版本号检查、统一 ABI 标签重新编译",
     "工程实践"),
    ("LLM 推理的 Prefill 与 Decode 阶段有何区别？",
     "- Prefill：并行处理全部输入 token，算力 bound，一次完成\n- Decode：逐 token 自回归生成，每步只算 1 个 token，显存带宽 bound（反复读取全量权重与 KV Cache）\n- 优化方向不同：Prefill 靠算力与并行度；Decode 靠量化、KV Cache 压缩、投机采样\n- 首 token 延迟取决于 Prefill，后续生成速度取决于 Decode",
     "AI 推理"),
    ("常见模型量化方案有哪些取舍？",
     "- PTQ（训练后量化）：Q8_0/Q6_K/Q4_K_M，位数越低显存越小速度越快，精度损失递增\n- Q4_K_M 是社区公认甜点：7B 模型约 4GB，困惑度损失通常小于 1%\n- GPTQ/AWQ：按校准数据最小化量化误差，比朴素舍入更稳定\n- 注意：量化主要省显存与带宽，对 Prefill 阶段加速有限",
     "AI 推理"),
    ("RAG 的基本流程与关键优化点？",
     "- 流程：文档切块 → embedding 向量化 → 向量检索 top-k → 拼入 prompt → 生成\n- 优化点：切块策略（按语义/标题边界）、混合检索（向量+BM25）、reranker 重排序、查询改写\n- 常见坑：块太大稀释关键信息、embedding 模型与语料语言不匹配\n- 评估：检索命中率与最终回答质量要分开度量",
     "AI 应用"),
    ("KV Cache 的作用是什么？显存开销如何估算？",
     "- 自回归生成时缓存每层每个 token 的 K/V，避免重复计算\n- 显存约等于 2 × 层数 × hidden_size × 上下文长度 × 精度字节数\n- 长上下文下 KV Cache 可超过模型权重本身，是 vLLM PagedAttention 等优化的核心目标\n- GQA/MQA 通过共享 KV 头直接削减该项开销",
     "AI 推理"),
    ("Function Calling 的原理与典型工作流？",
     "- 模型按 schema 输出结构化 JSON，指定要调用的工具与参数，由宿主程序真正执行\n- 流程：用户输入 → 模型决策调用工具 → 执行并回灌结果 → 模型生成最终回答\n- Agent = LLM + 工具调用 + 循环规划（ReAct 等模式）\n- 注意：参数校验与幂等设计必须在宿主侧兜底，不能信任模型输出",
     "AI 应用"),
]

# ---------- 开发进阶 + AI 代码片段（预置） ----------

DEV_AI_SNIPPETS = [
    ("Python 调用 OpenAI 兼容接口（流式）", "python",
     "import json\nimport requests\n\n\ndef chat_stream(prompt, base_url=\"http://127.0.0.1:8080\"):\n    \"\"\"调用 llama.cpp / vLLM 等本地推理服务，逐 token 产出\"\"\"\n    r = requests.post(\n        f\"{base_url}/v1/chat/completions\",\n        json={\"model\": \"local\",\n              \"messages\": [{\"role\": \"user\", \"content\": prompt}],\n              \"stream\": True},\n        stream=True, timeout=120)\n    for line in r.iter_lines():\n        if not line or not line.startswith(b\"data: \"):\n            continue\n        if line == b\"data: [DONE]\":\n            break\n        delta = json.loads(line[6:])[\"choices\"][0][\"delta\"]\n        if delta.get(\"content\"):\n            yield delta[\"content\"]\n\n\n# 使用\n# for chunk in chat_stream(\"解释什么是 KV Cache\"):\n#     print(chunk, end=\"\", flush=True)",
     "AI,LLM,流式输出"),
    ("C++ libcurl 调用本地 LLM 服务", "cpp",
     "// g++ llm_call.cpp -o llm_call -lcurl\n#include <curl/curl.h>\n#include <string>\n\nstatic size_t write_cb(void* data, size_t size, size_t nmemb, std::string* out) {\n    out->append((char*)data, size * nmemb);\n    return size * nmemb;\n}\n\nstd::string chat(const std::string& prompt) {\n    CURL* curl = curl_easy_init();\n    std::string resp;\n    std::string body = std::string(\n        \"{\\\"model\\\":\\\"local\\\",\\\"messages\\\":[{\\\"role\\\":\\\"user\\\",\\\"content\\\":\\\"\"\n        ) + prompt + \"\\\"}]}\";\n    struct curl_slist* hdrs = nullptr;\n    hdrs = curl_slist_append(hdrs, \"Content-Type: application/json\");\n    curl_easy_setopt(curl, CURLOPT_URL,\n                     \"http://127.0.0.1:8080/v1/chat/completions\");\n    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hdrs);\n    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());\n    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);\n    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &resp);\n    curl_easy_perform(curl);\n    curl_slist_free_all(hdrs);\n    curl_easy_cleanup(curl);\n    return resp;  // 解析 choices[0].message.content\n}",
     "AI,HTTP,libcurl"),
    ("C++ 极简线程池", "cpp",
     "#include <condition_variable>\n#include <functional>\n#include <mutex>\n#include <queue>\n#include <thread>\n#include <vector>\n\nclass ThreadPool {\npublic:\n    explicit ThreadPool(size_t n) {\n        for (size_t i = 0; i < n; ++i)\n            workers_.emplace_back([this] {\n                while (true) {\n                    std::function<void()> task;\n                    {\n                        std::unique_lock<std::mutex> lk(mtx_);\n                        cv_.wait(lk, [this] { return stop_ || !tasks_.empty(); });\n                        if (stop_ && tasks_.empty()) return;\n                        task = std::move(tasks_.front());\n                        tasks_.pop();\n                    }\n                    task();\n                }\n            });\n    }\n    template <class F> void submit(F&& f) {\n        {\n            std::lock_guard<std::mutex> lk(mtx_);\n            tasks_.emplace(std::forward<F>(f));\n        }\n        cv_.notify_one();\n    }\n    ~ThreadPool() {\n        { std::lock_guard<std::mutex> lk(mtx_); stop_ = true; }\n        cv_.notify_all();\n        for (auto& w : workers_) w.join();\n    }\nprivate:\n    std::vector<std::thread> workers_;\n    std::queue<std::function<void()>> tasks_;\n    std::mutex mtx_;\n    std::condition_variable cv_;\n    bool stop_ = false;\n};",
     "并发,线程池"),
    ("CMake 现代目标式模板", "cmake",
     "cmake_minimum_required(VERSION 3.20)\nproject(myapp LANGUAGES CXX)\n\nset(CMAKE_CXX_STANDARD 20)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)\nset(CMAKE_EXPORT_COMPILE_COMMANDS ON)  # 供 clangd/clang-tidy 使用\n\nadd_executable(myapp\n    src/main.cpp\n    src/printer_driver.cpp\n)\n\ntarget_include_directories(myapp PRIVATE include)\ntarget_compile_options(myapp PRIVATE -Wall -Wextra -Werror)\ntarget_link_libraries(myapp PRIVATE pthread curl)\n\n# Debug 构建默认开启 AddressSanitizer\nif(CMAKE_BUILD_TYPE STREQUAL \"Debug\")\n    target_compile_options(myapp PRIVATE -fsanitize=address)\n    target_link_options(myapp PRIVATE -fsanitize=address)\nendif()",
     "CMake,构建"),
    ("nlohmann/json 配置读取", "cpp",
     "#include <fstream>\n#include <nlohmann/json.hpp>\n#include <string>\n\nstruct AppConfig {\n    std::string listen = \"0.0.0.0\";\n    int port = 8080;\n    int workers = 2;\n\n    static AppConfig load(const std::string& path) {\n        std::ifstream ifs(path);\n        nlohmann::json j;\n        ifs >> j;\n        AppConfig cfg;\n        cfg.listen = j.value(\"listen\", cfg.listen);\n        cfg.port = j.value(\"port\", cfg.port);\n        cfg.workers = j.value(\"workers\", cfg.workers);\n        return cfg;  // j.value 提供默认值，字段缺失不抛异常\n    }\n};",
     "JSON,配置"),
]

# ---------- 学习路线主题（预置） ----------

ROADMAP_SEED = [
    ("C++20 协程（coroutines）实战", "开发进阶",
     "理解 promise_type/co_await 机制，把一个回调链改写为协程形式"),
    ("CMake 工程化与依赖管理", "开发进阶",
     "对比 FetchContent/vcpkg/conan 三种方案，统一项目构建规范"),
    ("Sanitizer 全家桶接入 CI", "开发进阶",
     "ASan/TSan/UBSan 分别跑核心测试用例，与崩溃档案模块联动记录"),
    ("ABI 兼容性与动态库发布规范", "开发进阶",
     "结合打印驱动 .so 分发场景，制定 C 接口封装与版本管理规范"),
    ("本地部署 7B 推理服务并压测", "AI 工程",
     "用 llama.cpp 或 vLLM 部署 Qwen2.5-7B，llama-bench 记录吞吐基线"),
    ("RAG 最小可用实现", "AI 工程",
     "embedding + 向量检索 + prompt 组装，把排障手册做成可问答的知识库"),
    ("Function Calling 与 Agent 实践", "AI 工程",
     "让模型调用本地工具（查错误码库/登记测试项），跑通一个完整工作流"),
]


# ---------- 驱动/固件版本台账 ----------

DRIVER_RECOMMENDS = ["待验证", "推荐", "有坑"]


@app.route("/drivers")
@login_required
def drivers_page():
    recommend = request.args.get("recommend", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM drivers WHERE 1=1"
    params = []
    if recommend:
        sql += " AND recommend=?"
        params.append(recommend)
    if q:
        sql += " AND (model LIKE ? OR driver_version LIKE ? OR changes LIKE ? OR known_issues LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY id DESC"
    drivers = db.execute(sql, params).fetchall()
    return render_template("drivers.html", drivers=drivers, q=q,
                           active_recommend=recommend,
                           recommends=DRIVER_RECOMMENDS)


@app.route("/api/drivers", methods=["POST"])
@login_required
def add_driver():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO drivers (model, driver_version, firmware_version, release_date, "
        "changes, known_issues, recommend, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (f["model"], f.get("driver_version", ""), f.get("firmware_version", ""),
         f.get("release_date", ""), f.get("changes", ""), f.get("known_issues", ""),
         f.get("recommend", "待验证"), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("drivers_page"))


@app.route("/api/drivers/<int:driver_id>/recommend", methods=["POST"])
@login_required
def cycle_driver_recommend(driver_id):
    db = get_db()
    old = db.execute("SELECT recommend FROM drivers WHERE id=?",
                     (driver_id,)).fetchone()
    db.execute(
        "UPDATE drivers SET recommend = CASE recommend "
        "WHEN '待验证' THEN '推荐' WHEN '推荐' THEN '有坑' ELSE '待验证' END "
        "WHERE id=?", (driver_id,))
    if old:
        nxt = {"待验证": "推荐", "推荐": "有坑"}.get(old["recommend"], "待验证")
        log_edit(db, "drivers", driver_id, "推荐状态",
                 f"{old['recommend']} → {nxt}")
    db.commit()
    return redirect(request.referrer or url_for("drivers_page"))


@app.route("/api/drivers/<int:driver_id>/delete", methods=["POST"])
@login_required
def del_driver(driver_id):
    db = get_db()
    archive_and_delete(db, "drivers", driver_id)
    db.commit()
    return redirect(url_for("drivers_page"))


# ---------- 打印协议笔记库 ----------

PROTOCOL_LIST = ["IPP", "LPR", "JetDirect/9100", "PCL", "PJL", "PostScript", "USB打印类", "SMB", "WSD", "AirPrint/mDNS"]


@app.route("/protocols")
@login_required
def protocols_page():
    proto = request.args.get("protocol", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM protocols WHERE 1=1"
    params = []
    if proto:
        sql += " AND protocol=?"
        params.append(proto)
    if q:
        sql += " AND (title LIKE ? OR summary LIKE ? OR commands LIKE ? OR notes LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY id DESC"
    protocols = db.execute(sql, params).fetchall()
    return render_template("protocols.html", protocols=protocols, q=q,
                           active_protocol=proto, protocol_list=PROTOCOL_LIST)


@app.route("/api/protocols", methods=["POST"])
@login_required
def add_protocol():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO protocols (title, protocol, summary, commands, notes, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f["title"], f.get("protocol", "IPP"), f.get("summary", ""),
         f.get("commands", ""), f.get("notes", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("protocols_page"))


@app.route("/api/protocols/<int:proto_id>/delete", methods=["POST"])
@login_required
def del_protocol(proto_id):
    db = get_db()
    archive_and_delete(db, "protocols", proto_id)
    db.commit()
    return redirect(url_for("protocols_page"))


# ---------- 打印测试矩阵 ----------

TEST_RESULTS = ["未测", "通过", "失败", "阻塞"]


@app.route("/test_matrix")
@login_required
def test_matrix_page():
    version = request.args.get("version", "").strip()
    result = request.args.get("result", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM test_matrix WHERE 1=1"
    params = []
    if version:
        sql += " AND driver_version=?"
        params.append(version)
    if result:
        sql += " AND result=?"
        params.append(result)
    if q:
        sql += " AND (model LIKE ? OR test_item LIKE ? OR note LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY driver_version DESC, model, id DESC"
    items = db.execute(sql, params).fetchall()
    versions = [r[0] for r in db.execute(
        "SELECT DISTINCT driver_version FROM test_matrix ORDER BY driver_version DESC").fetchall()]
    return render_template("test_matrix.html", items=items, q=q,
                           active_version=version, active_result=result,
                           versions=versions, results=TEST_RESULTS)


@app.route("/api/test_matrix", methods=["POST"])
@login_required
def add_test_item():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO test_matrix (driver_version, model, test_item, result, tester, note, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (f["driver_version"], f["model"], f["test_item"],
         f.get("result", "未测"), f.get("tester", ""), f.get("note", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("test_matrix_page"))


@app.route("/api/test_matrix/<int:item_id>/result", methods=["POST"])
@login_required
def cycle_test_result(item_id):
    db = get_db()
    old = db.execute("SELECT result FROM test_matrix WHERE id=?",
                     (item_id,)).fetchone()
    db.execute(
        "UPDATE test_matrix SET result = CASE result "
        "WHEN '未测' THEN '通过' WHEN '通过' THEN '失败' WHEN '失败' THEN '阻塞' ELSE '未测' END "
        "WHERE id=?", (item_id,))
    if old:
        nxt = {"未测": "通过", "通过": "失败", "失败": "阻塞"}.get(
            old["result"], "未测")
        log_edit(db, "test_matrix", item_id, "测试结果",
                 f"{old['result']} → {nxt}")
    db.commit()
    return redirect(request.referrer or url_for("test_matrix_page"))


@app.route("/api/test_matrix/<int:item_id>/delete", methods=["POST"])
@login_required
def del_test_item(item_id):
    db = get_db()
    archive_and_delete(db, "test_matrix", item_id)
    db.commit()
    return redirect(url_for("test_matrix_page"))


# ---------- 错误码速查库 ----------

ERROR_BRANDS = ["HP", "佳能", "爱普生", "兄弟", "理光", "京瓷", "富士施乐", "通用/CUPS"]

ERROR_CODES_SEED = [
    ("HP", "49.4C02", "固件数据处理错误",
     "多由特定打印任务中的异常数据触发，队列中残留任务会反复复发",
     "清空打印队列后重试；升级固件；换用 PCL6/PS 驱动交叉验证是否为驱动生成的数据问题"),
    ("HP", "50.x", "定影组件热故障",
     "50.1 低温 / 50.2 预热超时 / 50.9 高温，多为定影组件老化或供电异常",
     "断电冷却后重试；确认电源电压；必要时更换定影组件"),
    ("HP", "79", "固件服务错误",
     "常由网络环境中的异常任务或广播流量触发",
     "升级固件；改 USB 直连隔离验证；排查网络中的异常任务源"),
    ("HP", "59.F0", "主电机/转印组件故障",
     "ITB 转印组件或主电机驱动异常",
     "检查转印组件安装；执行组件自检；必要时更换转印带"),
    ("佳能", "E000/E001", "定影温度异常",
     "定影加热器温度未达到或超过阈值",
     "关机冷却后重试；检查热敏电阻与加热灯；进维修模式清除错误计数"),
    ("爱普生", "0x97", "主板/打印头故障",
     "WF 系列常见，多为打印头短路或主板损坏",
     "断电静置后重试；检查打印头排线；多数情况需更换打印头或主板"),
    ("爱普生", "W-11", "墨盒未识别",
     "墨盒芯片接触不良或非原装芯片被固件屏蔽",
     "重新安装墨盒；清洁芯片触点；确认固件版本是否屏蔽兼容芯片"),
    ("兄弟", "Unable to Print 4F", "打印头/进纸机构故障",
     "打印头驱动电路或进纸机构异常",
     "断电重启；检查进纸通道异物；故障持续需检修打印头"),
    ("理光", "SC542", "定影温度错误",
     "定影温度未达到待机温度",
     "进 SP 模式用 5810 复位；检查热敏电阻；必要时更换定影单元"),
    ("理光", "SC995", "序列号不匹配",
     "更换主板后机器序列号未同步",
     "进 SP 模式 5811 写入正确序列号"),
    ("通用/CUPS", "PCL XL Error", "驱动语言解析错误",
     "驱动生成的 PCL XL 数据流含打印机无法解析的指令",
     "换用 PCL5e 或 PS 驱动；升级打印机固件；定位触发错误的具体文档"),
    ("通用/CUPS", "Filter failed", "CUPS 过滤器崩溃",
     "驱动 filter 进程异常退出，任务中断在过滤阶段",
     "查看 /var/log/cups/error_log 对应 Job 的 filter 报错；用 -o raw 绕过过滤器区分驱动问题与数据问题"),
]


@app.route("/error_codes")
@login_required
def error_codes_page():
    brand = request.args.get("brand", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM error_codes WHERE 1=1"
    params = []
    if brand:
        sql += " AND brand=?"
        params.append(brand)
    if q:
        sql += " AND (code LIKE ? OR title LIKE ? OR description LIKE ? OR solution LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY brand, code"
    codes = db.execute(sql, params).fetchall()
    # 反向关联：每个错误码下挂了多少崩溃档案与日志模式
    linked = {}
    for c in codes:
        cid = c["id"]
        try:
            crash_cnt = db.execute(
                "SELECT COUNT(*) FROM crashes WHERE error_code_id=?",
                (cid,)).fetchone()[0]
        except sqlite3.DatabaseError:
            crash_cnt = 0
        try:
            pat_cnt = db.execute(
                "SELECT COUNT(*) FROM log_patterns WHERE error_code_id=?",
                (cid,)).fetchone()[0]
        except sqlite3.DatabaseError:
            pat_cnt = 0
        if crash_cnt or pat_cnt:
            linked[cid] = {"crash": crash_cnt, "pattern": pat_cnt}
    return render_template("error_codes.html", codes=codes, brands=ERROR_BRANDS,
                           active_brand=brand, q=q, linked=linked)


@app.route("/api/error_codes", methods=["POST"])
@login_required
def add_error_code():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO error_codes (brand, code, title, description, solution, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f.get("brand", "通用/CUPS"), f["code"], f.get("title", ""),
         f.get("description", ""), f.get("solution", ""),
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("error_codes_page"))


@app.route("/api/error_codes/<int:code_id>/delete", methods=["POST"])
@login_required
def del_error_code(code_id):
    db = get_db()
    archive_and_delete(db, "error_codes", code_id)
    db.commit()
    return redirect(url_for("error_codes_page"))


# ---------- 打印日志分析笔记 ----------

LOG_SOURCES = ["CUPS error_log", "CUPS access_log", "Windows PrintService",
               "Windows PrintOperational", "打印机面板/EWS", "驱动调试输出"]


@app.route("/log_analysis")
@login_required
def log_analysis_page():
    source = request.args.get("source", "").strip()
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM log_patterns WHERE 1=1"
    params = []
    if source:
        sql += " AND source=?"
        params.append(source)
    if q:
        sql += " AND (title LIKE ? OR pattern LIKE ? OR interpretation LIKE ? OR action LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY id DESC"
    patterns = db.execute(sql, params).fetchall()
    err_codes = db.execute(
        "SELECT id, brand, code, title FROM error_codes "
        "ORDER BY brand, code").fetchall()
    code_map = {r["id"]: r for r in err_codes}
    linked_codes = {}
    for p in patterns:
        keys = p.keys()
        if "error_code_id" in keys and p["error_code_id"]:
            hit = code_map.get(p["error_code_id"])
            if hit:
                linked_codes[p["id"]] = hit
    return render_template("log_analysis.html", patterns=patterns, sources=LOG_SOURCES,
                           active_source=source, q=q, err_codes=err_codes,
                           linked_codes=linked_codes)


@app.route("/api/log_analysis", methods=["POST"])
@login_required
def add_log_pattern():
    f = request.form
    db = get_db()
    ecid = f.get("error_code_id", "").strip()
    error_code_id = int(ecid) if ecid.isdigit() else None
    db.execute(
        "INSERT INTO log_patterns (title, source, pattern, interpretation, action, "
        "error_code_id, created_at) VALUES (?,?,?,?,?,?,?)",
        (f["title"], f.get("source", "CUPS error_log"), f.get("pattern", ""),
         f.get("interpretation", ""), f.get("action", ""), error_code_id,
         datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("log_analysis_page"))


@app.route("/api/log_analysis/<int:pattern_id>/delete", methods=["POST"])
@login_required
def del_log_pattern(pattern_id):
    db = get_db()
    archive_and_delete(db, "log_patterns", pattern_id)
    db.commit()
    return redirect(url_for("log_analysis_page"))


# ---------- 统计分析 ----------

@app.route("/analytics")
@login_required
def analytics_page():
    db = get_db()
    stats = {}
    stats["bug_platform"] = db.execute(
        "SELECT platform k, COUNT(*) c FROM bugs GROUP BY platform ORDER BY c DESC").fetchall()
    stats["bug_severity"] = db.execute(
        "SELECT severity k, COUNT(*) c FROM bugs GROUP BY severity ORDER BY "
        "CASE severity WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END").fetchall()
    stats["crash_signal"] = db.execute(
        "SELECT COALESCE(NULLIF(signal,''),'未知') k, COUNT(*) c FROM crashes "
        "GROUP BY k ORDER BY c DESC").fetchall()
    stats["test_result"] = db.execute(
        "SELECT result k, COUNT(*) c FROM test_matrix GROUP BY result ORDER BY "
        "CASE result WHEN '通过' THEN 0 WHEN '失败' THEN 1 WHEN '阻塞' THEN 2 ELSE 3 END").fetchall()
    stats["test_by_version"] = db.execute(
        "SELECT driver_version k, "
        "SUM(CASE WHEN result='通过' THEN 1 ELSE 0 END) pass_c, COUNT(*) total_c "
        "FROM test_matrix GROUP BY driver_version ORDER BY k DESC LIMIT 10").fetchall()
    stats["driver_recommend"] = db.execute(
        "SELECT recommend k, COUNT(*) c FROM drivers GROUP BY recommend").fetchall()
    stats["error_brand"] = db.execute(
        "SELECT brand k, COUNT(*) c FROM error_codes GROUP BY brand ORDER BY c DESC").fetchall()
    stats["activity_30d"] = db.execute(
        "SELECT d, (SELECT COUNT(*) FROM work_logs WHERE log_date=d) + "
        "(SELECT COUNT(*) FROM study_notes WHERE substr(created_at,1,10)=d) c FROM "
        "(SELECT date('now', '-' || n || ' days') d FROM "
        "(SELECT 0 n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 "
        "UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9 "
        "UNION SELECT 10 UNION SELECT 11 UNION SELECT 12 UNION SELECT 13 UNION SELECT 14 "
        "UNION SELECT 15 UNION SELECT 16 UNION SELECT 17 UNION SELECT 18 UNION SELECT 19 "
        "UNION SELECT 20 UNION SELECT 21 UNION SELECT 22 UNION SELECT 23 UNION SELECT 24 "
        "UNION SELECT 25 UNION SELECT 26 UNION SELECT 27 UNION SELECT 28 UNION SELECT 29)) "
        "ORDER BY d").fetchall()
    return render_template("analytics.html", stats=stats)


# ---------- 巡检与到期提醒 ----------

@app.route("/checklist")
@login_required
def checklist_page():
    db = get_db()
    today = date.today()
    rows = db.execute("SELECT * FROM checklists ORDER BY last_done, id").fetchall()
    items = []
    for r in rows:
        item = dict(r)
        if item["last_done"]:
            try:
                due = date.fromisoformat(item["last_done"]) + timedelta(days=item["cycle_days"])
                item["next_due"] = due.isoformat()
                item["overdue"] = due <= today
            except ValueError:
                item["next_due"] = ""
                item["overdue"] = True
        else:
            item["next_due"] = "从未执行"
            item["overdue"] = True
        items.append(item)
    items.sort(key=lambda x: (not x["overdue"], x["next_due"]))
    overdue_titles = [x["title"] for x in items if x["overdue"]]
    auth = _load_auth()
    if overdue_titles and auth.get("last_notify_date") != today.isoformat():
        if notify_webhook("巡检到期提醒",
                          "以下巡检项已到期：\n" + "\n".join(overdue_titles)):
            auth["last_notify_date"] = today.isoformat()
            _save_auth(auth)
    return render_template("checklist.html", items=items, today=today.isoformat())


@app.route("/api/checklist", methods=["POST"])
@login_required
def add_checklist():
    f = request.form
    db = get_db()
    try:
        cycle = int(f.get("cycle_days", 30) or 30)
    except ValueError:
        cycle = 30
    db.execute(
        "INSERT INTO checklists (title, model, cycle_days, last_done, note, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (f["title"], f.get("model", ""), cycle, f.get("last_done", ""),
         f.get("note", ""), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("checklist_page"))


@app.route("/api/checklist/<int:item_id>/done", methods=["POST"])
@login_required
def done_checklist(item_id):
    db = get_db()
    today = date.today().isoformat()
    db.execute("UPDATE checklists SET last_done=? WHERE id=?",
               (today, item_id))
    log_edit(db, "checklists", item_id, "巡检完成", today)
    db.commit()
    return redirect(request.referrer or url_for("checklist_page"))


@app.route("/api/checklist/<int:item_id>/delete", methods=["POST"])
@login_required
def del_checklist(item_id):
    db = get_db()
    archive_and_delete(db, "checklists", item_id)
    db.commit()
    return redirect(url_for("checklist_page"))


# ---------- 排障手册（知识库索引） ----------

@app.route("/handbook")
@login_required
def handbook_page():
    db = get_db()
    sections = {
        "protocols": db.execute(
            "SELECT * FROM protocols ORDER BY protocol, id DESC").fetchall(),
        "error_codes": db.execute(
            "SELECT * FROM error_codes ORDER BY brand, code").fetchall(),
        "log_patterns": db.execute(
            "SELECT * FROM log_patterns ORDER BY source, id DESC").fetchall(),
        "crashes": db.execute(
            "SELECT * FROM crashes WHERE status='已修复' ORDER BY id DESC").fetchall(),
    }
    return render_template("handbook.html", sections=sections)


# ---------- 发版报告生成 ----------

@app.route("/report/release")
@login_required
def release_report_page():
    db = get_db()
    version = request.args.get("version", "").strip()
    versions = [r[0] for r in db.execute(
        "SELECT DISTINCT driver_version FROM test_matrix WHERE driver_version!='' "
        "ORDER BY driver_version DESC").fetchall()]
    report = ""
    if version:
        tests = db.execute(
            "SELECT * FROM test_matrix WHERE driver_version=? ORDER BY model, id",
            (version,)).fetchall()
        bugs = db.execute(
            "SELECT * FROM bugs WHERE driver_version=? ORDER BY status, id", (version,)).fetchall()
        driver = db.execute(
            "SELECT * FROM drivers WHERE driver_version=? ORDER BY id DESC LIMIT 1",
            (version,)).fetchone()
        pass_c = sum(1 for t in tests if t["result"] == "通过")
        fail_items = [t for t in tests if t["result"] in ("失败", "阻塞")]
        untested = [t for t in tests if t["result"] == "未测"]
        open_bugs = [b for b in bugs if b["status"] == "待解决"]
        lines = [f"# 驱动版本 {version} 发版报告", ""]
        if driver:
            lines += [f"- 机型：{driver['model']}"]
            if driver["release_date"]:
                lines.append(f"- 发布日期：{driver['release_date']}")
            lines.append(f"- 推荐状态：{driver['recommend']}")
            if driver["changes"]:
                lines += ["", "## 变更摘要", "", driver["changes"]]
            if driver["known_issues"]:
                lines += ["", "## 已知问题", "", driver["known_issues"]]
        lines += ["", f"## 测试情况（通过 {pass_c}/{len(tests)}）", ""]
        if tests:
            for t in tests:
                mark = {"通过": "✅", "失败": "❌", "阻塞": "⛔"}.get(t["result"], "⬜")
                note = f"（{t['note']}）" if t["note"] else ""
                lines.append(f"- {mark} {t['model']} / {t['test_item']} {note}")
        else:
            lines.append("（该版本无测试记录）")
        if fail_items:
            lines += ["", "## ⚠️ 未通过项", ""]
            for t in fail_items:
                lines.append(f"- [{t['result']}] {t['model']} / {t['test_item']}")
        if untested:
            lines += ["", "## 未测项", ""]
            for t in untested:
                lines.append(f"- {t['model']} / {t['test_item']}")
        lines += ["", f"## 关联 Bug（共 {len(bugs)} 个，待解决 {len(open_bugs)} 个）", ""]
        for b in bugs:
            mark = "✅" if b["status"] == "已解决" else "🔴"
            lines.append(f"- {mark} [{b['severity']}] {b['title']}")
        report = "\n".join(lines)
    return render_template("release_report.html", versions=versions,
                           version=version, report=report)


# ---------- 全局搜索（多关键词加权打分 + 高亮片段） ----------

SEARCH_TARGETS = [
    ('work_logs', '工作记录', '📋', 'work_page',
     [('title', 10), ('tags', 6), ('content', 3)], 'log_date'),
    ('study_notes', '学习笔记', '📚', 'study_page',
     [('topic', 10), ('category', 5), ('content', 3)], 'category'),
    ('todos', '待办事项', '✅', 'todo_page',
     [('title', 10), ('priority', 3)], 'due_date'),
    ('diaries', '日记', '📔', 'diary_page',
     [('content', 10), ('mood', 4)], 'diary_date'),
    ('bugs', 'Bug 追踪', '🐛', 'knowledge.bugs_page',
     [('title', 10), ('phenomenon', 6), ('root_cause', 5), ('solution', 5),
      ('platform', 4), ('severity', 2)], 'status'),
    ('snippets', '代码片段', '✂️', 'knowledge.snippets_page',
     [('title', 10), ('tags', 6), ('language', 4), ('code', 3)], 'language'),
    ('commands', '命令速查', '⌨️', 'knowledge.commands_page',
     [('name', 10), ('command', 7), ('description', 4), ('category', 3)], 'category'),
    ('compile_errors', '编译错误', '🔧', 'knowledge.compile_errors_page',
     [('error_msg', 10), ('solution', 6), ('root_cause', 5), ('compiler', 3)], 'compiler'),
    ('interview_questions', '面试题集', '💼', 'knowledge.interview_page',
     [('question', 10), ('answer', 6), ('category', 3)], 'category'),
    ('perf_records', '性能优化', '⚡', 'knowledge.perf_page',
     [('title', 10), ('detail', 6), ('technique', 5), ('target', 3)], 'target'),
    ('books', '读书笔记', '📖', 'knowledge.books_page',
     [('title', 10), ('author', 5), ('note', 4), ('category', 3)], 'author'),
    ('crashes', '崩溃档案', '💥', 'knowledge.crashes_page',
     [('title', 10), ('stack', 6), ('root_cause', 5), ('signal', 3)], 'status'),
    ('drivers', '驱动记录', '🧩', 'drivers_page',
     [('model', 10), ('driver_version', 6), ('changes', 5),
      ('known_issues', 4)], 'driver_version'),
    ('protocols', '协议笔记', '📡', 'protocols_page',
     [('title', 10), ('summary', 6), ('commands', 4), ('notes', 4)], 'category'),
    ('test_matrix', '测试矩阵', '🧪', 'test_matrix_page',
     [('test_item', 10), ('model', 6), ('driver_version', 5), ('note', 4)], 'result'),
    ('error_codes', '错误码', '🔢', 'error_codes_page',
     [('code', 10), ('title', 8), ('description', 6), ('solution', 5),
      ('brand', 3)], 'brand'),
    ('log_patterns', '日志模式', '🧾', 'log_analysis_page',
     [('title', 10), ('pattern', 7), ('interpretation', 5), ('action', 4)], ''),
    ('printers', '机型档案', '🖨', 'printer.printers_page',
     [('model', 10), ('location', 5), ('owner', 4), ('notes', 4),
      ('languages', 3), ('ip', 3)], 'location'),
]

_COLUMN_CACHE = {}


def _table_columns(db, table):
    if table not in _COLUMN_CACHE:
        try:
            _COLUMN_CACHE[table] = [r[1] for r in db.execute(
                f'PRAGMA table_info({table})').fetchall()]
        except sqlite3.DatabaseError:
            _COLUMN_CACHE[table] = []
    return _COLUMN_CACHE[table]


def _search_tokens(q):
    return [t for t in (q or '').split() if t]


def _highlight(text, tokens, limit=None):
    s = '' if text is None else str(text)
    if limit and len(s) > limit:
        s = s[:limit] + '…'
    out = str(escape(s))
    for t in sorted({t for t in tokens if t}, key=len, reverse=True):
        pat = re.compile(re.escape(str(escape(t))), re.IGNORECASE)
        out = pat.sub(lambda m: '<mark>' + m.group(0) + '</mark>', out)
    return Markup(out)


def _snippet(text, tokens, width=100):
    s = '' if text is None else str(text).replace('\n', ' ')
    if not s.strip():
        return Markup('')
    low = s.lower()
    pos = -1
    for t in tokens:
        p = low.find(t.lower())
        if p >= 0 and (pos < 0 or p < pos):
            pos = p
    if pos < 0:
        return _highlight(s, tokens, width)
    start = max(0, pos - width // 3)
    end = min(len(s), start + width)
    frag = s[start:end]
    if start > 0:
        frag = '…' + frag
    if end < len(s):
        frag = frag + '…'
    return _highlight(frag, tokens)


@app.route('/search')
@login_required
def global_search():
    q = request.args.get('q', '').strip()
    tokens = _search_tokens(q)
    groups = []
    total = 0
    if tokens:
        db = get_db()
        for table, label, icon, endpoint, fields, meta_col in SEARCH_TARGETS:
            cols = _table_columns(db, table)
            usable = [(f, w) for f, w in fields if f in cols]
            if not usable or 'id' not in cols:
                continue
            primary = usable[0][0]
            one = ' OR '.join(f'{f} LIKE ?' for f, _w in usable)
            where = ' OR '.join(f'({one})' for _t in tokens)
            params = []
            for _t in tokens:
                for f, _w in usable:
                    params.append('%' + _t + '%')
            picked = ['id']
            for f, _w in usable:
                if f not in picked:
                    picked.append(f)
            has_meta = bool(meta_col) and meta_col in cols
            if has_meta and meta_col not in picked:
                picked.append(meta_col)
            sql = ('SELECT ' + ', '.join(picked) + f' FROM {table} '
                   f'WHERE {where} ORDER BY id DESC LIMIT 200')
            try:
                rows = db.execute(sql, params).fetchall()
            except sqlite3.DatabaseError:
                continue
            hits = []
            for row in rows:
                score = 0
                best = (0, '')
                matched = set()
                for f, w in usable:
                    val = row[f]
                    if not val:
                        continue
                    vs = str(val)
                    low = vs.lower()
                    cnt = 0
                    for t in tokens:
                        c = low.count(t.lower())
                        cnt += c
                        if c:
                            matched.add(t)
                    if not cnt:
                        continue
                    fs = cnt * w
                    if f == primary:
                        fs += 15 * len(matched)
                    score += fs
                    if f != primary and fs > best[0]:
                        best = (fs, vs)
                if score <= 0:
                    continue
                # 同时命中多个关键词的记录优先展示
                score += 30 * len(matched)
                raw_title = row[primary]
                hits.append({
                    'id': row['id'],
                    'title': _highlight(raw_title if raw_title else '(无标题)',
                                        tokens, 80),
                    'snippet': _snippet(best[1], tokens) if best[1] else Markup(''),
                    'meta': (str(row[meta_col])
                             if has_meta and row[meta_col] else ''),
                    'score': score,
                })
            if not hits:
                continue
            hits.sort(key=lambda h: (-h['score'], -h['id']))
            top = hits[:10]
            groups.append({'label': label, 'icon': icon,
                           'endpoint': endpoint, 'items': top})
            total += len(top)
    return render_template('search.html', q=q, results=groups, total=total)


# ---------- PWA ----------

@app.route("/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "个人工作台",
        "short_name": "工作台",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f0f2f5",
        "theme_color": "#2c3e50",
        "description": "个人工作台：工作记录、学习笔记、待办与知识管理",
    })


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
    week_crashes = db.execute(
        "SELECT COUNT(*) c FROM crashes WHERE substr(created_at,1,10) BETWEEN ? AND ?",
        (ws, we)).fetchone()["c"]
    week_tests = db.execute(
        "SELECT COUNT(*) c FROM test_matrix WHERE substr(created_at,1,10) BETWEEN ? AND ?",
        (ws, we)).fetchone()["c"]
    week_drivers = db.execute(
        "SELECT COUNT(*) c FROM drivers WHERE substr(created_at,1,10) BETWEEN ? AND ?",
        (ws, we)).fetchone()["c"]
    lines = [f"工作周报（{ws} ~ {we}）", "",
             f"本周概览：新增崩溃档案 {week_crashes} 条，执行测试项 {week_tests} 项，"
             f"登记驱动版本 {week_drivers} 个", "", "一、本周工作内容"]
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
        elif text.startswith("#错误码"):
            body = text.split(" ", 1)[-1] if " " in text else text.lstrip("#错误码 ")
            db.execute(
                "INSERT INTO error_codes (brand, code, title, created_at) VALUES (?,?,?,?)",
                ("通用/CUPS", body[:40], body, now))
        elif text.startswith("#协议"):
            body = text.split(" ", 1)[-1] if " " in text else text.lstrip("#协议 ")
            db.execute(
                "INSERT INTO protocols (title, protocol, summary, created_at) "
                "VALUES (?,?,?,?)", (body[:80], "IPP", body, now))
        elif text.startswith("#测试"):
            body = text.split(" ", 1)[-1] if " " in text else text.lstrip("#测试 ")
            db.execute(
                "INSERT INTO test_matrix (driver_version, model, test_item, created_at) "
                "VALUES (?,?,?,?)", ("未指定", "未指定", body, now))
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
        "compile_errors": db.execute(
            "SELECT COUNT(*) c FROM compile_errors").fetchone()["c"],
        "perf_records": db.execute("SELECT COUNT(*) c FROM perf_records").fetchone()["c"],
        "commands": db.execute("SELECT COUNT(*) c FROM commands").fetchone()["c"],
        "books": db.execute("SELECT COUNT(*) c FROM books").fetchone()["c"],
    })


@app.route("/api/export")
@login_required
def export_data():
    """一键导出全部数据为 JSON 备份文件。"""
    db = get_db()
    tables = ["work_logs", "study_notes", "todos", "templates", "diaries",
              "drivers", "protocols", "test_matrix", "error_codes", "log_patterns", "printers",
              "checklists", "edit_history", "trash", "printer_probe_logs",
              "habits", "habit_logs", "bugs", "roadmap_topics", "snippets",
              "releases", "interview_questions", "compile_errors",
              "perf_records", "commands", "books"]
    data = {}
    for t in tables:
        try:
            data[t] = [dict(r) for r in db.execute(f"SELECT * FROM {t}").fetchall()]
        except sqlite3.OperationalError:
            data[t] = []
    payload = json.dumps({
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "data": data,
    }, ensure_ascii=False, indent=2)
    return Response(
        payload, mimetype="application/json",
        headers={"Content-Disposition":
                 "attachment; filename=workbench_backup_"
                 + date.today().isoformat() + ".json"})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(timespec="seconds")})


# ---------- 运维看板 ----------

from shared import BACKUP_DIR  # noqa: E402

STATUS_UNITS = [
    ("workbench.service", "主服务"),
    ("workbench-backup.timer", "每日备份"),
    ("workbench-printer-probe.timer", "打印机巡检"),
]


def _unit_state(unit):
    """读取 systemd 单元状态，失败时返回降级信息而不抛错。"""
    try:
        out = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveState", "-p", "Result",
             "-p", "NextElapseUSecRealtime"],
            capture_output=True, text=True, timeout=5).stdout
        info = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v
        return {"unit": unit, "active": info.get("ActiveState", "unknown"),
                "result": info.get("Result", ""),
                "next": info.get("NextElapseUSecRealtime", "")}
    except (OSError, subprocess.SubprocessError):
        return {"unit": unit, "active": "unknown", "result": "", "next": ""}


@app.route("/status")
@login_required
def status_page():
    db = get_db()
    info = {}

    # 数据库状态
    try:
        info["journal_mode"] = db.execute("PRAGMA journal_mode").fetchone()[0]
    except sqlite3.DatabaseError:
        info["journal_mode"] = "unknown"
    db_file = DB_PATH
    if os.path.exists(db_file):
        info["db_size"] = os.path.getsize(db_file)
        info["db_mtime"] = datetime.fromtimestamp(
            os.path.getmtime(db_file)).strftime("%Y-%m-%d %H:%M")
    else:
        info["db_size"] = 0
        info["db_mtime"] = "-"

    # 各表行数
    tables = []
    try:
        names = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        for name in names:
            try:
                cnt = db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            except sqlite3.DatabaseError:
                cnt = -1
            tables.append({"name": name, "count": cnt})
    except sqlite3.DatabaseError:
        pass

    # 备份归档
    backups = []
    if os.path.isdir(BACKUP_DIR):
        try:
            files = sorted(os.listdir(BACKUP_DIR), reverse=True)[:8]
            for fn in files:
                fp = os.path.join(BACKUP_DIR, fn)
                if os.path.isfile(fp):
                    backups.append({
                        "name": fn,
                        "size": os.path.getsize(fp),
                        "mtime": datetime.fromtimestamp(
                            os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M"),
                    })
        except OSError:
            pass
    total_backups = 0
    if os.path.isdir(BACKUP_DIR):
        try:
            total_backups = len([f for f in os.listdir(BACKUP_DIR)
                                 if f.endswith(".json")])
        except OSError:
            pass

    # systemd 单元
    units = []
    for unit, label in STATUS_UNITS:
        st = _unit_state(unit)
        st["label"] = label
        units.append(st)

    # 最近探测日志
    probes = []
    try:
        rows = db.execute(
            "SELECT l.printer_id, l.ok, l.checked_at, p.model "
            "FROM printer_probe_logs l "
            "LEFT JOIN printers p ON p.id = l.printer_id "
            "ORDER BY l.id DESC LIMIT 10").fetchall()
        for r in rows:
            probes.append({"printer_id": r["printer_id"],
                           "model": r["model"] or "(已删除)",
                           "ok": bool(r["ok"]),
                           "checked_at": r["checked_at"]})
    except sqlite3.DatabaseError:
        pass

    # 关键计数的概览
    summary = {}
    for key in ("edit_history", "trash", "printer_probe_logs"):
        try:
            summary[key] = db.execute(
                f"SELECT COUNT(*) FROM {key}").fetchone()[0]
        except sqlite3.DatabaseError:
            summary[key] = -1

    return render_template("status.html", info=info, tables=tables,
                           backups=backups, total_backups=total_backups,
                           units=units, probes=probes, summary=summary,
                           checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


from printer import bp as printer_bp  # noqa: E402
app.register_blueprint(printer_bp)


from admin import bp as admin_bp  # noqa: E402
app.register_blueprint(admin_bp)
from knowledge import bp as knowledge_bp  # noqa: E402
app.register_blueprint(knowledge_bp)
if __name__ == "__main__":
    import sys

    # 新环境初始化登录口令：python3 app.py --set-password [明文密码]
    # 不传密码时自动生成随机口令并打印一次
    if "--set-password" in sys.argv:
        from shared import _load_auth, _save_auth

        idx = sys.argv.index("--set-password")
        pwd = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
        generated = not pwd
        if generated:
            pwd = secrets.token_urlsafe(12)
        meta = _load_auth()
        meta["password_hash"] = hashlib.sha256(
            pwd.encode()).hexdigest()
        _save_auth(meta)
        print("登录口令已写入 %s" % AUTH_FILE)
        print("密码%s：%s" % ("（随机生成）" if generated else "", pwd))
        sys.exit(0)

    init_db()
    # 零配置启动：Windows 下 gunicorn 不可用，自动切 waitress
    # Linux/macOS 保持内置服务器；服务器上生产部署仍由 gunicorn 接管
    if os.name == "nt":
        try:
            from waitress import serve
        except ImportError:
            print("提示：pip install waitress 可用生产级服务器，当前回退开发服务器")
            app.run(host="0.0.0.0", port=8000)
        else:
            print("waitress 已启动，访问 http://127.0.0.1:8000")
            serve(app, host="0.0.0.0", port=8000, threads=8)
    else:
        app.run(host="0.0.0.0", port=8000)
