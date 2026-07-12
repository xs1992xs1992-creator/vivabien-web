-- 营销留存追踪：现有线上 D1 执行一次
ALTER TABLE events ADD COLUMN ip_masked TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN ip_hash TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_events_ip_hash ON events(ip_hash);
