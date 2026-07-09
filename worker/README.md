# VivaBien 边缘后端（Worker + D1）

短链跳转、自有埋点、优惠券校验。与站点静态部署分开，独立部署为 Worker `vivabien-api`。
配套后台：`admin.py` 通过共享密钥 `X-Admin-Key` 调 `/api/admin/*`。

## 首次部署

```bash
cd ~/vivabien-web/worker

# 1) 建 D1 库（记下输出的 database_id）
npx wrangler d1 create vivabien-data
#   把 database_id 填进 wrangler.jsonc 的 "database_id"

# 2) 建表
npx wrangler d1 execute vivabien-data --remote --file=schema.sql

# 3) 设后台密钥（随便一串强口令，同一串也要填进 admin.py 的 WORKER_ADMIN_KEY）
npx wrangler secret put ADMIN_KEY

# 4) 部署
npx wrangler deploy
```

部署后确认路由 `vivabien.xyz/s/*`、`vivabien.xyz/api/*` 指向本 Worker（wrangler.jsonc 的 routes，
zone 需为 vivabien.xyz；其余路径仍走 Pages 静态资源）。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/s/:code` | 短链跳转 + 记点击 + 种访客 cookie(vb_vid) |
| POST | `/api/track` | 前端埋点 `{type:view/addcart/checkout, sku?, code?}` |
| POST | `/api/coupon/validate` | `{code, subtotal}` → `{valid, kind, value, discount, total}` |
| POST | `/api/admin/link/create` | `{target, note?, code?}` → 新短链 |
| GET | `/api/admin/links` | 短链列表 + 点击/访客/加购统计 |
| GET | `/api/admin/timeline?vid=` 或 `?code=` | 事件时间线 |
| POST | `/api/admin/coupon/create` | `{kind:percent/amount, value, expires_at?, max_uses?, min_order?, scope?}` |
| GET | `/api/admin/coupons` | 券列表 |
| POST | `/api/admin/coupon/toggle` | `{code}` 启用/停用 |
| GET | `/api/admin/overview` | 30天概览 |

`/api/admin/*` 需请求头 `X-Admin-Key: <ADMIN_KEY>`。

## 本地联调

```bash
npx wrangler dev --remote   # 用远程 D1
# 另开一窗测试：
curl -X POST localhost:8787/api/admin/coupon/create \
  -H 'X-Admin-Key: 你的KEY' -H 'Content-Type: application/json' \
  -d '{"kind":"percent","value":10}'
```

## 已知限制
- 订单成交在站外（WhatsApp/COD），Worker 收不到「真实付款」信号：券的 `used_count`
  目前不会自动+1，`checkout` 事件只记录「进入结算并应用了券」。核销以人工/后台为准。
