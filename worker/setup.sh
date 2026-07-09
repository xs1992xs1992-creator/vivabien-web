#!/usr/bin/env bash
# VivaBien 边缘后端一键安装脚本
# 用法：在终端里执行
#   cd ~/vivabien-web/worker && bash setup.sh
# 它会：登录检查 → 建 D1 库 → 自动把库ID填进配置 → 建表 → 设密钥 → 部署
set -u
cd "$(dirname "$0")"
DB_NAME="vivabien-data"

say(){ printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
err(){ printf "\n\033[1;31m❌ %s\033[0m\n" "$1"; }

# 0) 环境检查
if ! command -v node >/dev/null 2>&1; then
  err "没装 Node.js。请先到 https://nodejs.org 下载 LTS 版安装，再重新运行本脚本。"
  exit 1
fi

WR="npx --yes wrangler"

# 1) 登录
say "1/6 检查是否已登录 Cloudflare"
if ! $WR whoami >/dev/null 2>&1; then
  echo "需要登录。浏览器会自动打开 Cloudflare，点绿色的 Allow 授权，然后回到终端。"
  $WR login || { err "登录失败，请重试"; exit 1; }
fi
echo "✓ 已登录"

# 2) 建库（若已存在会提示，忽略即可）
say "2/6 创建数据库 $DB_NAME"
$WR d1 create "$DB_NAME" 2>&1 | grep -v "already exists" || true

# 3) 取数据库ID并写进 wrangler.jsonc
say "3/6 获取数据库ID并写入配置"
DBID=$($WR d1 list --json 2>/dev/null | python3 -c "
import sys,json
try: data=json.load(sys.stdin)
except: data=[]
for d in data:
    if d.get('name')=='$DB_NAME': print(d.get('uuid') or d.get('database_id') or ''); break
")
if [ -z "${DBID:-}" ]; then
  err "没拿到数据库ID。请把上面的输出截图发给 Claude。"
  exit 1
fi
python3 - "$DBID" <<'PY'
import re,sys
dbid=sys.argv[1]
s=open('wrangler.jsonc',encoding='utf-8').read()
s=re.sub(r'("database_id"\s*:\s*")[^"]*(")', lambda m:m.group(1)+dbid+m.group(2), s)
open('wrangler.jsonc','w',encoding='utf-8').write(s)
print('✓ 已把数据库ID写进 wrangler.jsonc:', dbid)
PY

# 4) 建表
say "4/6 创建数据表"
$WR d1 execute "$DB_NAME" --remote --file=schema.sql -y || { err "建表失败"; exit 1; }
echo "✓ 表已建好"

# 5) 设后台密钥（同一串会同时存到后台用的文件里）
say "5/6 设置后台密钥"
echo "请输入一串自定的口令（字母数字，10位以上，别人猜不到即可）。输入时看不见字符是正常的。"
read -r -s -p "口令: " KEY; echo
if [ -z "${KEY:-}" ]; then err "口令为空"; exit 1; fi
printf '%s' "$KEY" > ../worker_admin_key.txt
echo "✓ 已存到 worker_admin_key.txt（后台会用）"
printf '%s' "$KEY" | $WR secret put ADMIN_KEY || { err "设置密钥失败"; exit 1; }
echo "✓ 已把同一串密钥设进 Worker"

# 6) 部署
say "6/6 部署 Worker"
$WR deploy || { err "部署失败"; exit 1; }

printf "\n\033[1;32m🎉 全部完成！\033[0m\n"
echo "接下来还剩两步（不用终端）："
echo "  A. 重启 admin.py（关掉那个终端窗口的 admin.py，重新 python3 admin.py）"
echo "  B. 在后台点「🚀 发布上线」"
echo "然后打开后台顶栏的 🎟️优惠券 / 🔗短链 / 📊数据 试试。"
