-- Optional exact location and preferred delivery window for Gran Santo Domingo orders.
ALTER TABLE orders ADD COLUMN map_url TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN location_followup INTEGER NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN preferred_delivery_date TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN preferred_delivery_window TEXT DEFAULT '';
