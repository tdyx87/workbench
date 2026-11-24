#!/usr/bin/env python3
"""打印机定时巡检（跨平台，替代 printer_probe.sh）。

库中没有配置 IP 的打印机时直接跳过；否则调用 /api/printers/probe_all，
耗材不足由服务端触发 Webhook 通知。路径从 shared.py 自动探测，无需
环境变量；Linux timer 与 Windows 任务计划程序都能直接执行：

    python printer_probe.py
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import AUTH_FILE, DB_PATH  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def read_token():
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            return json.load(f).get("api_token", "")
    except (OSError, ValueError):
        return ""


def printer_count():
    """返回配置了 IP 的打印机数量；库或表缺失时按 0 处理。"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM printers WHERE ip!='' ").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return 0


def main():
    if printer_count() == 0:
        log("SKIP: no printer with ip configured")
        return 0

    token = read_token()
    if not token:
        log("ERROR: api_token not found in %s" % AUTH_FILE)
        return 1

    req = urllib.request.Request(
        BASE_URL + "/api/printers/probe_all", data=b"", method="POST",
        headers={"X-API-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        log("ERROR: probe_all failed: %s" % exc)
        return 1

    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        log("ERROR: invalid json payload: %s" % exc)
        return 1

    results = data.get("results") or []
    low = [x for x in results
           if x.get("ok") and (x.get("items") or {}).get("低耗材告警")]
    log("OK total=%s online=%s low=%s" % (
        data.get("total"), data.get("online"), len(low)))
    for x in low:
        log("  LOW %s %s %s" % (x.get("model"), x.get("ip"),
                                 (x.get("items") or {}).get("低耗材告警")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
