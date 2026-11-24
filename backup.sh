#!/usr/bin/env bash
# 工作台每日自动备份：调用 /api/export，按日期归档，保留最近 30 份
set -uo pipefail

APP_DIR="/root/workbench"
BACKUP_DIR="$APP_DIR/backups"
AUTH_FILE="$APP_DIR/auth.json"
BASE_URL="http://127.0.0.1:8000"
KEEP=30

mkdir -p "$BACKUP_DIR"

stamp=$(date +%Y%m%d_%H%M%S)
out="$BACKUP_DIR/workbench_${stamp}.json"

TOKEN=$(python3 -c "import json;print(json.load(open('$AUTH_FILE')).get('api_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "[$(date '+%F %T')] ERROR: api_token not found in $AUTH_FILE" >&2
  exit 1
fi

code=$(curl -sS -o "$out" -w '%{http_code}' \
  -H "X-API-Token: $TOKEN" \
  --max-time 120 \
  "$BASE_URL/api/export" || echo "000")

if [ "$code" != "200" ]; then
  echo "[$(date '+%F %T')] ERROR: export failed http=$code" >&2
  rm -f "$out"
  exit 1
fi

if ! python3 -c "import json,sys;d=json.load(open('$out'));assert 'data' in d" 2>/dev/null; then
  echo "[$(date '+%F %T')] ERROR: invalid json payload" >&2
  rm -f "$out"
  exit 1
fi

size=$(stat -c %s "$out")
echo "[$(date '+%F %T')] OK $out (${size} bytes)"

# 轮转：只保留最近 KEEP 份
ls -1t "$BACKUP_DIR"/workbench_*.json 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old"
  echo "[$(date '+%F %T')] rotated out $old"
done

exit 0
