-- Separate discount components so orders remain auditable while the legacy
-- discount column continues to store the combined discount.
ALTER TABLE orders ADD COLUMN coupon_discount REAL NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN prepaid_discount REAL NOT NULL DEFAULT 0;
