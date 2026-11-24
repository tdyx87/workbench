#!/usr/bin/env bash
# 打印机定时巡检：调用 /api/printers/probe_all，耗材不足会自动触发 Webhook 通知
set -uo pipefail

APP_DIR="/root/workbench"
AUTH_FILE="$APP_DIR/auth.json"
BASE_URL="http://127.0.0.1:8000"

TOKEN=$(python3 -c "import json;print(json.load(open('$AUTH_FILE')).get('api_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "[$(date '+%F %T')] ERROR: api_token not found" >&2
  exit 1
fi

count=$(sqlite3 /root/workbench.db "SELECT COUNT(*) FROM printers WHERE ip!='';" 2>/dev/null || echo 0)
if [ "$count" = "0" ]; then
  echo "[$(date '+%F %T')] SKIP: no printer with ip configured"
  exit 0
fi

body=$(curl -sS -X POST -H "X-API-Token: $TOKEN" --max-time 180 -w '\n%{http_code}' "$BASE_URL/api/printers/probe_all" 2>&1 || echo 'curl_failed')

code=$(printf '%s' "$body" | tail -1)
payload=$(printf '%s' "$body" | sed '$d')

if [ "$code" != "200" ]; then
  echo "[$(date '+%F %T')] ERROR: http=$code body=${payload:0:300}" >&2
  exit 1
fi

summary=$(printf '%s' "$payload" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    low = [x for x in d.get('results', []) if x.get('ok') and x.get('items', {}).get('低耗材告警')]
    print('total=%s online=%s low=%s' % (d.get('total'), d.get('online'), len(low)))
    for x in low:
        print('  LOW', x.get('model'), x.get('ip'), x.get('items', {}).get('低耗材告警'))
except Exception as exc:
    print('parse_error', exc)
")

echo "[$(date '+%F %T')] OK $summary"
exit 0
