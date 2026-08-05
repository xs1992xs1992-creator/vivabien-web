ALTER TABLE events ADD COLUMN source_section TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN selected_color TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN offer_qty INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN gallery_index INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN review_index INTEGER DEFAULT -1;
ALTER TABLE events ADD COLUMN calculated_qty INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN wall_width REAL DEFAULT 0;
ALTER TABLE events ADD COLUMN wall_height REAL DEFAULT 0;
ALTER TABLE events ADD COLUMN order_id TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_events_sku_type_ts ON events(sku,type,ts);
CREATE INDEX IF NOT EXISTS idx_events_order_id ON events(order_id);

ALTER TABLE orders ADD COLUMN session_id TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN utm_source TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN utm_medium TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN utm_campaign TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN utm_content TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN utm_term TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN fbclid TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN gclid TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN first_utm_source TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN first_utm_medium TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN first_utm_campaign TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN first_utm_content TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN first_utm_term TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_campaign ON orders(utm_campaign);
