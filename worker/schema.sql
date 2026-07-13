-- VivaBien 边缘后端 D1 库结构
-- 三块：短链(links) / 访问事件(events) / 优惠券(coupons + coupon_uses)
-- 迁移：wrangler d1 execute vivabien-data --file=worker/schema.sql

-- 短链
CREATE TABLE IF NOT EXISTS links (
  code       TEXT PRIMARY KEY,        -- 短码，例 a1B2c3
  target     TEXT NOT NULL,           -- 跳转目标（站内相对或绝对 URL）
  note       TEXT DEFAULT '',         -- 备注：发给谁
  created_at INTEGER NOT NULL,        -- 毫秒时间戳
  clicks     INTEGER NOT NULL DEFAULT 0
);

-- 访问事件（点击/浏览/加购/结算）
CREATE TABLE IF NOT EXISTS events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  vid     TEXT NOT NULL,              -- 访客ID（首方 cookie）
  code    TEXT DEFAULT '',            -- 关联的短链码（若来自短链）
  type    TEXT NOT NULL,              -- click | view | addcart | checkout
  sku     TEXT DEFAULT '',            -- 涉及的商品SKU（浏览/加购时）
  ts      INTEGER NOT NULL,           -- 毫秒时间戳
  country TEXT DEFAULT '',
  ua      TEXT DEFAULT '',
  ref     TEXT DEFAULT '',
  ip_masked TEXT DEFAULT '',          -- 仅显示网段，如 190.80.12.x
  ip_hash   TEXT DEFAULT '',
  ip_full   TEXT DEFAULT '',
  city      TEXT DEFAULT '',
  region    TEXT DEFAULT '',
  postal_code TEXT DEFAULT '',
  latitude  TEXT DEFAULT '',
  longitude TEXT DEFAULT '',
  asn       INTEGER DEFAULT 0,
  as_org    TEXT DEFAULT '',
  qty       INTEGER DEFAULT 0,
  price     REAL DEFAULT 0,
  cart_total REAL DEFAULT 0,
  product_title TEXT DEFAULT '',
  product_img TEXT DEFAULT '',
  event_id TEXT DEFAULT '',
  session_id TEXT DEFAULT '',
  path TEXT DEFAULT '',
  category TEXT DEFAULT '',
  duration_ms INTEGER DEFAULT 0,
  scroll_depth INTEGER DEFAULT 0,
  device_type TEXT DEFAULT '',
  screen_width INTEGER DEFAULT 0,
  utm_source TEXT DEFAULT '',
  utm_medium TEXT DEFAULT '',
  utm_campaign TEXT DEFAULT '',
  utm_content TEXT DEFAULT '',
  utm_term TEXT DEFAULT '',
  fbclid TEXT DEFAULT '',
  gclid TEXT DEFAULT '',
  whatsapp_location TEXT DEFAULT '',
  is_bot INTEGER DEFAULT 0,
  bot_reason TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_vid  ON events(vid);
CREATE INDEX IF NOT EXISTS idx_events_code ON events(code);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_ip_hash ON events(ip_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id) WHERE event_id<>'';
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type,ts);

-- 优惠券
CREATE TABLE IF NOT EXISTS coupons (
  code       TEXT PRIMARY KEY,        -- 券码
  kind       TEXT NOT NULL,           -- percent（百分比）| amount（固定金额，RD$）
  value      REAL NOT NULL,           -- percent: 1-100；amount: RD$ 金额
  active      INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  expires_at INTEGER DEFAULT 0,       -- 0=永不过期，否则毫秒时间戳
  max_uses   INTEGER DEFAULT 0,       -- 0=不限
  used_count INTEGER NOT NULL DEFAULT 0,
  min_order  REAL DEFAULT 0,          -- 最低订单额，0=无门槛
  scope      TEXT DEFAULT 'all'       -- all | cat:<分类> | sku:<SKU>
);

-- 券核销记录
CREATE TABLE IF NOT EXISTS coupon_uses (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  code     TEXT NOT NULL,
  order_id TEXT DEFAULT '',
  vid      TEXT DEFAULT '',
  ts       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uses_code ON coupon_uses(code);

-- 客户提交的订单（点击确认订单时先保存，再打开 WhatsApp）
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  vid TEXT DEFAULT '',
  link_code TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  customer_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  province TEXT DEFAULT '',
  zone TEXT DEFAULT '',
  address TEXT NOT NULL,
  note TEXT DEFAULT '',
  payment_method TEXT DEFAULT 'cod',
  subtotal REAL NOT NULL DEFAULT 0,
  discount REAL NOT NULL DEFAULT 0,
  total REAL NOT NULL DEFAULT 0,
  coupon_code TEXT DEFAULT '',
  ip_full TEXT DEFAULT '',
  ip_masked TEXT DEFAULT '',
  ip_hash TEXT DEFAULT '',
  country TEXT DEFAULT '',
  city TEXT DEFAULT '',
  region TEXT DEFAULT '',
  postal_code TEXT DEFAULT '',
  latitude TEXT DEFAULT '',
  longitude TEXT DEFAULT '',
  asn INTEGER DEFAULT 0,
  as_org TEXT DEFAULT '',
  ua TEXT DEFAULT '',
  ref TEXT DEFAULT '',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_vid ON orders(vid);

CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  sku TEXT NOT NULL,
  title TEXT NOT NULL,
  image TEXT DEFAULT '',
  unit_price REAL NOT NULL DEFAULT 0,
  quantity INTEGER NOT NULL DEFAULT 1,
  line_total REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  vid TEXT NOT NULL,
  link_code TEXT DEFAULT '',
  started_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  landing_path TEXT DEFAULT '',
  last_path TEXT DEFAULT '',
  page_views INTEGER DEFAULT 0,
  engaged_ms INTEGER DEFAULT 0,
  max_scroll INTEGER DEFAULT 0,
  device_type TEXT DEFAULT '',
  screen_width INTEGER DEFAULT 0,
  utm_source TEXT DEFAULT '',
  utm_medium TEXT DEFAULT '',
  utm_campaign TEXT DEFAULT '',
  utm_content TEXT DEFAULT '',
  utm_term TEXT DEFAULT '',
  fbclid TEXT DEFAULT '',
  gclid TEXT DEFAULT '',
  is_bot INTEGER DEFAULT 0,
  converted_cart INTEGER DEFAULT 0,
  converted_whatsapp INTEGER DEFAULT 0,
  converted_order INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_campaign ON sessions(utm_campaign);

CREATE TABLE IF NOT EXISTS campaign_costs (
  day TEXT NOT NULL,
  campaign TEXT NOT NULL,
  source TEXT DEFAULT '',
  spend REAL DEFAULT 0,
  impressions INTEGER DEFAULT 0,
  ad_clicks INTEGER DEFAULT 0,
  PRIMARY KEY(day,campaign,source)
);
