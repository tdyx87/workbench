"""打印机蓝图：机型档案、SNMP 在线探测与耗材监控。"""
import socket
import sqlite3
from datetime import datetime

from flask import (Blueprint, jsonify, redirect, render_template, request,
                   url_for)

from shared import archive_and_delete, get_db, login_required, notify_webhook

bp = Blueprint("printer", __name__)


# ---------- 原生 SNMP（最小 SNMPv2c GET，无需第三方库） ----------

def _snmp_encode_oid(oid):
    parts = [int(x) for x in oid.strip(".").split(".")]
    out = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        if p < 128:
            out += bytes([p])
        else:
            stack = []
            while p:
                stack.append(p & 0x7F)
                p >>= 7
            out += bytes(b | (0x80 if i < len(stack) - 1 else 0)
                         for i, b in enumerate(reversed(stack)))
    return out


def _snmp_tlv(tag, value):
    n = len(value)
    if n < 128:
        return bytes([tag, n]) + value
    if n < 256:
        return bytes([tag, 0x81, n]) + value
    return bytes([tag, 0x82, n >> 8, n & 0xFF]) + value


def snmp_get(ip, oid, community="public", timeout=2.0):
    """发送 SNMPv2c GetRequest，返回 (tag, value_bytes)；失败返回 None。"""
    pkt = _snmp_tlv(0x30,
                    _snmp_tlv(0x02, b"\x01") +
                    _snmp_tlv(0x04, community.encode()) +
                    _snmp_tlv(0xA0,
                              _snmp_tlv(0x02, b"\x01") +
                              _snmp_tlv(0x02, b"\x00") +
                              _snmp_tlv(0x02, b"\x00") +
                              _snmp_tlv(0x30,
                                        _snmp_tlv(0x30,
                                                  _snmp_tlv(0x06, _snmp_encode_oid(oid)) +
                                                  _snmp_tlv(0x05, b"")))))
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(pkt, (ip, 161))
        data, _ = s.recvfrom(4096)
        s.close()
    except OSError:
        return None
    needle = _snmp_tlv(0x06, _snmp_encode_oid(oid))
    idx = data.find(needle)
    if idx < 0:
        return None
    pos = idx + len(needle)
    if pos + 2 > len(data):
        return None
    tag = data[pos]
    ln = data[pos + 1]
    pos += 2
    if ln & 0x80:
        nbytes = ln & 0x7F
        ln = int.from_bytes(data[pos:pos + nbytes], "big")
        pos += nbytes
    return tag, data[pos:pos + ln]


# ---------- 机型档案库 ----------

DUPLEX_TYPES = ["", "自动双面", "手动双面", "仅单面"]


@bp.route("/printers")
@login_required
def printers_page():
    q = request.args.get("q", "").strip()
    db = get_db()
    sql = "SELECT * FROM printers WHERE 1=1"
    params = []
    if q:
        sql += " AND (model LIKE ? OR languages LIKE ? OR location LIKE ? OR owner LIKE ? OR notes LIKE ?)"
        params += [f"%{q}%"] * 5
    sql += " ORDER BY model"
    rows = db.execute(sql, params).fetchall()
    last = {}
    for r in db.execute(
            "SELECT printer_id, ok, checked_at FROM printer_probe_logs "
            "WHERE id IN (SELECT MAX(id) FROM printer_probe_logs "
            "GROUP BY printer_id)").fetchall():
        last[r["printer_id"]] = {"ok": bool(r["ok"]),
                                 "checked_at": r["checked_at"]}
    printers = []
    for r in rows:
        item = dict(r)
        item["last_probe"] = last.get(r["id"])
        printers.append(item)
    return render_template("printers.html", printers=printers,
                           duplex_types=DUPLEX_TYPES, q=q)


@bp.route("/api/printers", methods=["POST"])
@login_required
def add_printer():
    f = request.form
    db = get_db()
    db.execute(
        "INSERT INTO printers (model, languages, duplex, trays, memory, ip, location, "
        "owner, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (f["model"], f.get("languages", ""), f.get("duplex", ""), f.get("trays", ""),
         f.get("memory", ""), f.get("ip", ""), f.get("location", ""), f.get("owner", ""),
         f.get("notes", ""), datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return redirect(url_for("printer.printers_page"))


@bp.route("/api/printers/<int:printer_id>/delete", methods=["POST"])
@login_required
def del_printer(printer_id):
    db = get_db()
    archive_and_delete(db, "printers", printer_id)
    db.commit()
    return redirect(url_for("printer.printers_page"))


# ---------- SNMP 打印机在线检测 ----------

PRINTER_OIDS = {
    "设备描述": "1.3.6.1.2.1.1.1.0",
    "总打印页数": "1.3.6.1.2.1.43.10.2.1.4.1.1",
}

# 打印机耗材相关 OID（43.11.1.1.x.1.<index>）
SUPPLY_OIDS = {
    "desc": "1.3.6.1.2.1.43.11.1.1.6.1.",
    "max": "1.3.6.1.2.1.43.11.1.1.8.1.",
    "level": "1.3.6.1.2.1.43.11.1.1.9.1.",
}
SUPPLY_MAX_INDEX = 4
SUPPLY_LOW_PERCENT = 15


def _snmp_value(ip, oid):
    """取单个 OID 的值：INTEGER 返回 int，其余返回去空白字符串；失败返回 None。"""
    got = snmp_get(ip, oid)
    if not got:
        return None
    tag, raw = got
    if tag == 0x02 and raw:
        return int.from_bytes(raw, "big")
    if not raw:
        return ""
    return raw.decode("utf-8", "replace").strip()


def _collect_supplies(ip):
    """按索引遍历耗材，返回 [{'name','level','max','percent'}]。"""
    supplies = []
    seen = set()
    for idx in range(1, SUPPLY_MAX_INDEX + 1):
        name = _snmp_value(ip, SUPPLY_OIDS["desc"] + str(idx))
        level = _snmp_value(ip, SUPPLY_OIDS["level"] + str(idx))
        total = _snmp_value(ip, SUPPLY_OIDS["max"] + str(idx))
        name = name.strip() if isinstance(name, str) else ""
        # 无名称且无量值的索引视为设备不支持，直接跳过
        if not name and not isinstance(level, int):
            continue
        label = name or ("耗材" + str(idx))
        key = (label, level if isinstance(level, int) else None)
        if key in seen:
            continue
        seen.add(key)
        item = {"name": label}
        if isinstance(level, int):
            item["level"] = level
        if isinstance(total, int):
            item["max"] = total
        if isinstance(level, int) and isinstance(total, int) and total > 0:
            item["percent"] = max(0, min(100, round(level * 100 / total)))
        supplies.append(item)
    return supplies


def _probe_once(ip):
    """探测单台设备，成功返回 items 字典，无响应返回 None。"""
    desc = _snmp_value(ip, PRINTER_OIDS["设备描述"])
    if desc is None:
        return None
    items = {"设备描述": desc if isinstance(desc, str) else str(desc)}
    pages = _snmp_value(ip, PRINTER_OIDS["总打印页数"])
    if pages not in (None, ""):
        items["总打印页数"] = str(pages)
    supplies = _collect_supplies(ip)
    if supplies:
        items["耗材"] = supplies
    return items


def _record_probe(db, printer_id, ok, detail):
    """记录一次探测结果，失败不影响主流程。"""
    try:
        db.execute(
            "INSERT INTO printer_probe_logs (printer_id, ok, detail, checked_at) "
            "VALUES (?,?,?,?)",
            (printer_id, 1 if ok else 0, str(detail)[:2000],
             datetime.now().isoformat(timespec="seconds")))
        db.commit()
    except sqlite3.DatabaseError:
        pass


@bp.route("/api/printers/<int:printer_id>/probe", methods=["POST"])
@login_required
def probe_printer(printer_id):
    db = get_db()
    p = db.execute("SELECT * FROM printers WHERE id=?", (printer_id,)).fetchone()
    if not p:
        return jsonify({"ok": False, "error": "机型不存在"})
    if not p["ip"]:
        _record_probe(db, printer_id, False, "未配置 IP")
        return jsonify({"ok": False, "error": "该机型未配置 IP 地址"})
    items = _probe_once(p["ip"])
    if items is None:
        _record_probe(db, printer_id, False, "SNMP 无响应")
        return jsonify({"ok": False,
                        "error": "SNMP 无响应（设备离线、未开启 SNMP 或网络不可达）"})
    low = [s for s in items.get("耗材", [])
           if s.get("percent") is not None
           and s["percent"] <= SUPPLY_LOW_PERCENT]
    if low:
        names = "、".join(
            "%s(%d%%)" % (s["name"], s["percent"]) for s in low)
        items["低耗材告警"] = names
        notify_webhook("打印机耗材不足",
                       "%s（%s）：%s" % (p["model"], p["ip"], names))
    _record_probe(db, printer_id, True, str(items)[:1000])
    return jsonify({"ok": True, "ip": p["ip"], "items": items})


@bp.route("/api/printers/probe_all", methods=["POST"])
@login_required
def probe_all_printers():
    db = get_db()
    rows = db.execute(
        "SELECT id, model, ip FROM printers WHERE ip != '' ORDER BY id"
    ).fetchall()
    results = []
    online = 0
    for r in rows:
        items = _probe_once(r["ip"])
        if items is None:
            _record_probe(db, r["id"], False, "SNMP 无响应")
            results.append({"id": r["id"], "model": r["model"],
                            "ip": r["ip"], "ok": False,
                            "error": "SNMP 无响应"})
            continue
        online += 1
        low = [s for s in items.get("耗材", [])
               if s.get("percent") is not None
               and s["percent"] <= SUPPLY_LOW_PERCENT]
        if low:
            items["低耗材告警"] = "、".join(
                "%s(%d%%)" % (s["name"], s["percent"]) for s in low)
        _record_probe(db, r["id"], True, str(items)[:1000])
        results.append({"id": r["id"], "model": r["model"],
                        "ip": r["ip"], "ok": True, "items": items})
    low_all = [x for x in results
               if x.get("ok") and x.get("items", {}).get("低耗材告警")]
    if low_all:
        notify_webhook(
            "打印机批量巡检：%d 台耗材不足" % len(low_all),
            "\n".join("%s（%s）：%s" % (x["model"], x["ip"],
                                       x["items"]["低耗材告警"])
                      for x in low_all))
    return jsonify({"ok": True, "total": len(rows), "online": online,
                    "results": results})
