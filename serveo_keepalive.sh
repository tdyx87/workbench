#!/bin/bash
# serveo 隧道保活脚本：隧道断开或进程滞留时自动重建
# 说明：
# 1. 必须用 script 提供伪 TTY，否则 serveo 不回显分配的公网 URL
# 2. 仅用 pgrep 无法发现『进程在但服务端转发失效』的假活，故辅以日志地址检查
LOG=/tmp/serveo.log

start_tunnel() {
  rm -f "$LOG"
  setsid script -qfc 'ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
    -R 80:localhost:8000 serveo.net' "$LOG" < /dev/null > /dev/null 2>&1 &
}

while true; do
  if ! pgrep -f 'ssh .*serveo.net' > /dev/null; then
    start_tunnel
  elif ! grep -q 'Forwarding HTTP traffic from https://' "$LOG" 2>/dev/null; then
    # 进程在但没有有效转发地址，视为假活，重建
    pkill -f 'ssh .*serveo.net' 2>/dev/null
    sleep 3
    start_tunnel
  fi
  sleep 20
done
