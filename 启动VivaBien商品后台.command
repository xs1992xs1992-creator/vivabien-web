#!/bin/zsh
# 后台打不开时，双击这个文件即可修复。
# 依次检查并恢复：① 商品后台进程 ② Cloudflare 隧道 ③ 公网地址
# 不需要输入任何命令。

set -u

PORT=8766
SERVICE="com.vivabien.shop-admin"
TUNNEL="vivabien-review"
ADMIN_URL="https://shop-admin.vivabien.xyz"
LOCAL_URL="http://127.0.0.1:$PORT"
LOG_DIR="$HOME/Library/Logs/VivaBien"
LOG_FILE="$LOG_DIR/shop-admin-error.log"
REPO="$HOME/vivabien-web"
UID_NUM="$(id -u)"

# cloudflared / python 可能不在精简 PATH 里
export PATH="$HOME/.hermes/node/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "🩺 VivaBien 商品后台 · 一键检修"
echo "────────────────────────────────"

alive() { curl -fsS --max-time 3 "$LOCAL_URL/ping" >/dev/null 2>&1; }
wait_alive() { for i in {1..15}; do alive && return 0; sleep 1; done; return 1; }

# ── ① 后台进程 ─────────────────────────────
if alive; then
  echo "① 商品后台：本来就在运行 ✓"
else
  echo "① 商品后台：没响应，正在拉起…"
  if launchctl print "gui/$UID_NUM/$SERVICE" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$UID_NUM/$SERVICE" >/dev/null 2>&1
  else
    echo "   （没找到常驻服务，改为直接启动）"
    cd "$REPO" 2>/dev/null || { echo "   ❌ 找不到 $REPO"; read -k 1 "?按任意键关闭…"; exit 1; }
    mkdir -p "$LOG_DIR"
    VIVABIEN_NO_BROWSER=1 nohup python3 admin.py >>"$LOG_FILE" 2>&1 &
  fi
  if wait_alive; then
    echo "   已恢复 ✓"
  else
    echo "   ❌ 还是起不来，日志最后 30 行："
    echo "────────────────────────────────"
    tail -30 "$LOG_FILE" 2>/dev/null || echo "   （没有日志文件）"
    echo "────────────────────────────────"
    echo "   把上面这段发给 Claude，就能定位原因。"
    read -k 1 "?按任意键关闭…"
    exit 1
  fi
fi

# ── ② Cloudflare 隧道（公网地址靠它）────────
if pgrep -f cloudflared >/dev/null 2>&1; then
  echo "② 网络隧道：运行中 ✓"
else
  echo "② 网络隧道：没在跑，正在启动…"
  if launchctl print "gui/$UID_NUM/com.cloudflare.cloudflared" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$UID_NUM/com.cloudflare.cloudflared" >/dev/null 2>&1
  elif command -v cloudflared >/dev/null 2>&1; then
    mkdir -p "$LOG_DIR"
    nohup cloudflared tunnel run "$TUNNEL" >>"$LOG_DIR/cloudflared.log" 2>&1 &
  else
    echo "   ⚠️ 找不到 cloudflared，公网地址暂时用不了，先用本机地址：$LOCAL_URL"
  fi
  sleep 4
  if pgrep -f cloudflared >/dev/null 2>&1; then echo "   已启动 ✓"; else echo "   ⚠️ 仍未启动"; fi
fi

# ── ③ 公网地址 ─────────────────────────────
if curl -fsS --max-time 8 "$ADMIN_URL/ping" >/dev/null 2>&1; then
  echo "③ 公网地址：可以访问 ✓"
  OPEN_URL="$ADMIN_URL"
else
  echo "③ 公网地址：暂时打不开（隧道可能还在重连，1 分钟后再试）"
  echo "   现在先用本机地址进后台。"
  OPEN_URL="$LOCAL_URL"
fi

echo "────────────────────────────────"
echo "✅ 检修完成，正在打开：$OPEN_URL"
open "$OPEN_URL"
echo "（这个窗口可以直接关掉，后台会继续运行）"
sleep 3
