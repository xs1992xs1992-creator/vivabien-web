#!/bin/zsh

set -u

PORT=8766
SERVICE="com.vivabien.shop-admin"
ADMIN_URL="https://shop-admin.vivabien.xyz"
LOG_FILE="$HOME/Library/Logs/VivaBien/shop-admin-error.log"

launchctl kickstart -k "gui/$(id -u)/$SERVICE"
sleep 1

if ! curl -fsS --max-time 3 "http://127.0.0.1:$PORT/" >/dev/null; then
  echo "商品后台启动失败，日志如下："
  tail -30 "$LOG_FILE"
  read -k 1 "?按任意键关闭..."
  exit 1
fi

open "$ADMIN_URL"
echo "VivaBien 商品后台已启动：$ADMIN_URL"
echo "本地地址：http://localhost:$PORT"
echo "可以关闭此窗口，后台会继续运行。"
sleep 2
