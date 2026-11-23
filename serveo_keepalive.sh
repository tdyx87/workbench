#!/bin/bash
# serveo 隧道保活脚本：隧道断开时自动重建
LOG=/tmp/serveo.log
while true; do
  if ! pgrep -f 'ssh .*serveo.net' > /dev/null; then
    nohup ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
      -R 80:localhost:8000 serveo.net > "$LOG" 2>&1 &
  fi
  sleep 20
done
