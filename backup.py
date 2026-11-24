#!/usr/bin/env python3
"""工作台每日自动备份（跨平台，替代 backup.sh）。

调用 /api/export 导出全库 JSON，按时间戳归档到备份目录，保留最近 30 份。
路径从 shared.py 自动探测，无需环境变量；Windows 任务计划程序与 Linux
cron/timer 都能直接执行：

    python backup.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import AUTH_FILE, BACKUP_DIR  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
KEEP = 30


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def read_token():
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            return json.load(f).get("api_token", "")
    except (OSError, ValueError):
        return ""


def rotate(directory, keep):
    files = sorted(
        (os.path.join(directory, n) for n in os.listdir(directory)
         if n.startswith("workbench_") and n.endswith(".json")),
        key=os.path.getmtime, reverse=True)
    for old in files[keep:]:
        try:
            os.remove(old)
            log("rotated out %s" % old)
        except OSError as exc:
            log("rotate failed %s: %s" % (old, exc))


def main():
    token = read_token()
    if not token:
        log("ERROR: api_token not found in %s" % AUTH_FILE)
        return 1

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(BACKUP_DIR, "workbench_%s.json" % stamp)

    req = urllib.request.Request(
        BASE_URL + "/api/export", headers={"X-API-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        log("ERROR: export failed: %s" % exc)
        return 1

    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        log("ERROR: invalid json payload: %s" % exc)
        return 1
    if not isinstance(payload, dict) or "data" not in payload:
        log("ERROR: payload missing 'data' key")
        return 1

    try:
        with open(out, "wb") as f:
            f.write(raw)
    except OSError as exc:
        log("ERROR: write failed: %s" % exc)
        return 1

    log("OK %s (%d bytes)" % (out, len(raw)))
    rotate(BACKUP_DIR, KEEP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
