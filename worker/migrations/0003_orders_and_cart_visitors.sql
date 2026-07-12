-- 完整加购轨迹与订单后台
ALTER TABLE events ADD COLUMN ip_full TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN city TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN region TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN postal_code TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN latitude TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN longitude TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN asn INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN as_org TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN qty INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN price REAL DEFAULT 0;
ALTER TABLE events ADD COLUMN cart_total REAL DEFAULT 0;
ALTER TABLE events ADD COLUMN product_title TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN product_img TEXT DEFAULT '';

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY, vid TEXT DEFAULT '', link_code TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending', customer_name TEXT NOT NULL, phone TEXT NOT NULL,
  province TEXT DEFAULT '', zone TEXT DEFAULT '', address TEXT NOT NULL, note TEXT DEFAULT '',
  payment_method TEXT DEFAULT 'cod', subtotal REAL NOT NULL DEFAULT 0,
  discount REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0, coupon_code TEXT DEFAULT '',
  ip_full TEXT DEFAULT '', ip_masked TEXT DEFAULT '', ip_hash TEXT DEFAULT '', country TEXT DEFAULT '',
  city TEXT DEFAULT '', region TEXT DEFAULT '', postal_code TEXT DEFAULT '', latitude TEXT DEFAULT '',
  longitude TEXT DEFAULT '', asn INTEGER DEFAULT 0, as_org TEXT DEFAULT '', ua TEXT DEFAULT '',
  ref TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_vid ON orders(vid);

CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, sku TEXT NOT NULL,
  title TEXT NOT NULL, image TEXT DEFAULT '', unit_price REAL NOT NULL DEFAULT 0,
  quantity INTEGER NOT NULL DEFAULT 1, line_total REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
