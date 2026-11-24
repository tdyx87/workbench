"""后台管理蓝图：导入、变更历史、回收站与设置。"""
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime

from flask import (Blueprint, jsonify, redirect, render_template, request,
                   url_for)

from shared import (IMPORT_TABLES, _load_auth, _save_auth, get_api_token,
                    get_db, login_required, notify_webhook)

bp = Blueprint("admin", __name__)


# ---------- 数据导入 ----------



@bp.route("/api/import", methods=["POST"])
@login_required
def import_data():
    """从导出 JSON 恢复数据（INSERT OR IGNORE 幂等，已有记录不覆盖）。"""
    f = request.files.get("file")
    if not f:
        return redirect(url_for("index"))
    try:
        payload = json.loads(f.read().decode("utf-8"))
        data = payload.get("data", {})
    except (ValueError, UnicodeDecodeError):
        return redirect(url_for("index"))
    db = get_db()
    imported = 0
    for table in IMPORT_TABLES:
        rows = data.get(table, [])
        if not isinstance(rows, list):
            continue
        table_cols = [r[1] for r in db.execute(
            f"PRAGMA table_info({table})").fetchall()]
        for row in rows:
            if not row.get("id"):
                continue
            cols = [c for c in table_cols if c in row]
            vals = [str(row[c]) if row[c] is not None else "" for c in cols]
            placeholders = ",".join("?" * len(cols))
            db.execute(
                f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
                f"VALUES ({placeholders})", vals)
            imported += 1
    db.commit()
    return redirect(url_for("index"))


# ---------- 按表导入（预演 + 执行） ----------

IMPORT_TMP_DIR = "/root/workbench/tmp_import"
IMPORT_TTL_SECONDS = 3600


def _ensure_import_tmp():
    os.makedirs(IMPORT_TMP_DIR, exist_ok=True)
    now = datetime.now().timestamp()
    try:
        for fn in os.listdir(IMPORT_TMP_DIR):
            fp = os.path.join(IMPORT_TMP_DIR, fn)
            if not os.path.isfile(fp):
                continue
            if now - os.path.getmtime(fp) > IMPORT_TTL_SECONDS:
                os.remove(fp)
    except OSError:
        pass
    return IMPORT_TMP_DIR


def _analyze_import(db, data):
    """逐表统计：将新增 / 将覆盖 / 无变化 / 跳过。"""
    report = []
    for table in IMPORT_TABLES:
        rows = data.get(table)
        if not isinstance(rows, list):
            continue
        try:
            cols = [r[1] for r in db.execute(
                f"PRAGMA table_info({table})").fetchall()]
            existing = {}
            for r in db.execute(f"SELECT * FROM {table}").fetchall():
                existing[r["id"]] = dict(r)
        except sqlite3.DatabaseError:
            continue
        if not cols:
            continue
        add = upd = same = skip = 0
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                skip += 1
                continue
            usable = [c for c in cols if c in row]
            if not usable:
                skip += 1
                continue
            cur = existing.get(row["id"])
            if cur is None:
                add += 1
                continue
            changed = False
            for c in usable:
                old = cur.get(c)
                new = row[c]
                if str(old if old is not None else "") != str(
                        new if new is not None else ""):
                    changed = True
                    break
            if changed:
                upd += 1
            else:
                same += 1
        report.append({"table": table, "rows": len(rows), "add": add,
                       "update": upd, "same": same, "skip": skip})
    return report


@bp.route("/import")
@login_required
def import_page():
    return render_template("import.html", report=None, token="",
                           exported_at="", totals=None,
                           msg=request.args.get("msg", ""))


@bp.route("/api/import/preview", methods=["POST"])
@login_required
def import_preview():
    f = request.files.get("file")
    if not f:
        return redirect(url_for("admin.import_page", msg="请选择要导入的 JSON 文件"))
    try:
        payload = json.loads(f.read().decode("utf-8"))
        data = payload.get("data", {})
        if not isinstance(data, dict) or not data:
            raise ValueError("empty")
    except (ValueError, UnicodeDecodeError):
        return redirect(url_for(
            "import_page", msg="文件解析失败：请上传由导出功能生成的 JSON"))
    db = get_db()
    report = _analyze_import(db, data)
    if not report:
        return redirect(url_for(
            "import_page", msg="JSON 中没有可识别的数据表"))
    d = _ensure_import_tmp()
    token = secrets.token_hex(8)
    try:
        with open(os.path.join(d, token + ".json"), "w",
                  encoding="utf-8") as fp:
            json.dump({"data": data}, fp, ensure_ascii=False)
    except OSError:
        return redirect(url_for("admin.import_page", msg="临时文件写入失败"))
    totals = {"add": sum(r["add"] for r in report),
              "update": sum(r["update"] for r in report),
              "same": sum(r["same"] for r in report),
              "skip": sum(r["skip"] for r in report)}
    return render_template(
        "import.html", report=report, token=token,
        exported_at=payload.get("exported_at", ""), msg="", totals=totals)


@bp.route("/api/import/apply", methods=["POST"])
@login_required
def import_apply():
    token = (request.form.get("token") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{16}", token):
        return redirect(url_for("admin.import_page", msg="导入令牌无效，请重新上传"))
    chosen = set(request.form.getlist("tables"))
    path = os.path.join(IMPORT_TMP_DIR, token + ".json")
    if not os.path.isfile(path):
        return redirect(url_for(
            "import_page", msg="预演数据已过期（超过 1 小时），请重新上传"))
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp).get("data", {})
    except (ValueError, OSError):
        return redirect(url_for("admin.import_page", msg="预演数据读取失败"))
    if not data:
        return redirect(url_for("admin.import_page", msg="预演数据为空"))
    db = get_db()
    snap_name = ""
    try:
        os.makedirs("/root/db_backups", exist_ok=True)
        snap_name = "pre_import_%s.db" % datetime.now().strftime(
            "%Y%m%d_%H%M%S")
        dst = sqlite3.connect(os.path.join("/root/db_backups", snap_name))
        with dst:
            db.backup(dst)
        dst.close()
    except (sqlite3.DatabaseError, OSError):
        snap_name = ""
    added = updated = 0
    touched = []
    for table in IMPORT_TABLES:
        if chosen and table not in chosen:
            continue
        rows = data.get(table, [])
        if not isinstance(rows, list):
            continue
        try:
            cols = [r[1] for r in db.execute(
                f"PRAGMA table_info({table})").fetchall()]
        except sqlite3.DatabaseError:
            continue
        if not cols:
            continue
        cnt_a = cnt_u = cnt_s = 0
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            usable = [c for c in cols if c in row]
            if not usable:
                continue
            cur = db.execute(
                f"SELECT * FROM {table} WHERE id=?", (row["id"],)).fetchone()
            changed = cur is None
            if cur is not None:
                for c in usable:
                    old = cur[c]
                    new = row[c]
                    if str(old if old is not None else "") != str(
                            new if new is not None else ""):
                        changed = True
                        break
            if not changed:
                # 内容完全一致，跳过写入，避免无意义的覆盖
                cnt_s += 1
                continue
            vals = [str(row[c]) if row[c] is not None else ""
                    for c in usable]
            db.execute(
                f"INSERT OR REPLACE INTO {table} ({','.join(usable)}) "
                f"VALUES ({','.join('?' * len(usable))})", vals)
            if cur is None:
                cnt_a += 1
            else:
                cnt_u += 1
        if cnt_a or cnt_u:
            touched.append("%s(+%d/~%d)" % (table, cnt_a, cnt_u))
        added += cnt_a
        updated += cnt_u
    db.commit()
    try:
        os.remove(path)
    except OSError:
        pass
    msg = "导入完成：新增 %d 条，覆盖 %d 条" % (added, updated)
    if touched:
        msg += "（%s）" % "、".join(touched[:6])
    if snap_name:
        msg += "；执行前已生成库快照 %s" % snap_name
    else:
        msg += "；警告：库快照生成失败，请人工确认"
    return redirect(url_for("admin.import_page", msg=msg))


# ---------- 变更历史 ----------

EDIT_MODULE_LABELS = {
    "work_logs": "工作记录", "study_notes": "学习笔记", "todos": "待办",
    "diaries": "日记", "habits": "习惯", "bugs": "Bug",
    "roadmap_topics": "学习路线", "snippets": "代码片段",
    "releases": "发版", "interview_questions": "面试题",
    "compile_errors": "编译错误", "perf_records": "性能",
    "commands": "命令", "books": "读书", "crashes": "崩溃",
    "drivers": "驱动", "protocols": "协议", "test_matrix": "测试矩阵",
    "error_codes": "错误码", "log_patterns": "日志模式",
    "printers": "机型", "checklists": "巡检",
}


@bp.route("/history")
@login_required
def history_page():
    db = get_db()
    module = request.args.get("module", "").strip()
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 50
    sql = "SELECT * FROM edit_history"
    params = []
    if module:
        sql += " WHERE module=?"
        params.append(module)
    total = db.execute(
        sql.replace("SELECT *", "SELECT COUNT(*)"), params).fetchone()[0]
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [per_page, (page - 1) * per_page]
    rows = db.execute(sql, params).fetchall()
    modules = [r[0] for r in db.execute(
        "SELECT DISTINCT module FROM edit_history ORDER BY module").fetchall()]
    items = [{"id": r["id"], "module": r["module"],
              "label": EDIT_MODULE_LABELS.get(r["module"], r["module"]),
              "ref_id": r["ref_id"], "action": r["action"],
              "detail": r["detail"], "created_at": r["created_at"]}
             for r in rows]
    pages = max(1, (total + per_page - 1) // per_page)
    return render_template("history.html", items=items, total=total,
                           module=module, modules=modules, page=page,
                           pages=pages, labels=EDIT_MODULE_LABELS)


# ---------- 回收站 ----------

TRASH_TITLE_KEYS = ["title", "name", "topic", "code", "model", "test_item",
                    "question", "error_msg", "version", "content"]


@bp.route("/recycle")
@login_required
def recycle_page():
    db = get_db()
    rows = db.execute("SELECT * FROM trash ORDER BY id DESC").fetchall()
    items = []
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except ValueError:
            payload = {}
        title = ""
        for k in TRASH_TITLE_KEYS:
            if payload.get(k):
                title = str(payload[k])[:60]
                break
        items.append({"id": r["id"], "table": r["table_name"],
                      "ref_id": r["ref_id"], "title": title,
                      "deleted_at": r["deleted_at"]})
    return render_template("recycle.html", items=items)


@bp.route("/api/recycle/<int:trash_id>/restore", methods=["POST"])
@login_required
def restore_trash(trash_id):
    db = get_db()
    r = db.execute("SELECT * FROM trash WHERE id=?", (trash_id,)).fetchone()
    if r and r["table_name"] in IMPORT_TABLES:
        try:
            payload = json.loads(r["payload"])
            table = r["table_name"]
            cols = [c[1] for c in db.execute(
                f"PRAGMA table_info({table})").fetchall()]
            use = [c for c in cols if c in payload]
            vals = [str(payload[c]) if payload[c] is not None else "" for c in use]
            db.execute(
                f"INSERT OR REPLACE INTO {table} ({','.join(use)}) "
                f"VALUES ({','.join('?' * len(use))})", vals)
            db.execute("DELETE FROM trash WHERE id=?", (trash_id,))
            db.commit()
        except ValueError:
            pass
    return redirect(request.referrer or url_for("admin.recycle_page"))


@bp.route("/api/recycle/<int:trash_id>/purge", methods=["POST"])
@login_required
def purge_trash(trash_id):
    db = get_db()
    db.execute("DELETE FROM trash WHERE id=?", (trash_id,))
    db.commit()
    return redirect(request.referrer or url_for("admin.recycle_page"))


# ---------- 设置（API Token / 通知） ----------

@bp.route("/settings")
@login_required
def settings_page():
    auth = _load_auth()
    return render_template(
        "settings.html", token=get_api_token(),
        webhook=auth.get("notify_webhook", ""),
        notify_enabled=bool(auth.get("notify_enabled")),
        msg=request.args.get("msg", ""))


@bp.route("/api/settings/token/regenerate", methods=["POST"])
@login_required
def regenerate_token():
    auth = _load_auth()
    auth["api_token"] = secrets.token_hex(20)
    _save_auth(auth)
    return redirect(url_for("admin.settings_page", msg="API Token 已重新生成，旧 Token 立即失效"))


@bp.route("/api/settings/notify", methods=["POST"])
@login_required
def save_notify():
    auth = _load_auth()
    auth["notify_webhook"] = request.form.get("webhook", "").strip()
    auth["notify_enabled"] = bool(request.form.get("enabled"))
    _save_auth(auth)
    return redirect(url_for("admin.settings_page", msg="通知配置已保存"))


@bp.route("/api/settings/notify/test", methods=["POST"])
@login_required
def test_notify():
    ok = notify_webhook(
        "工作台测试通知",
        "发送时间 " + datetime.now().isoformat(timespec="seconds"))
    return redirect(url_for(
        "settings_page",
        msg="测试通知已发送" if ok else "发送失败：请检查 Webhook 地址与启用开关"))
