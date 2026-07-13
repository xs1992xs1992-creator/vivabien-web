-- 会话、广告归因、WhatsApp、互动与数据质量
ALTER TABLE events ADD COLUMN event_id TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN session_id TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN path TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN category TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN duration_ms INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN scroll_depth INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN device_type TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN screen_width INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN utm_source TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN utm_medium TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN utm_campaign TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN utm_content TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN utm_term TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN fbclid TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN gclid TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN whatsapp_location TEXT DEFAULT '';
ALTER TABLE events ADD COLUMN is_bot INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN bot_reason TEXT DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id) WHERE event_id<>'';
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type,ts);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, vid TEXT NOT NULL, link_code TEXT DEFAULT '',
  started_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
  landing_path TEXT DEFAULT '', last_path TEXT DEFAULT '', page_views INTEGER DEFAULT 0,
  engaged_ms INTEGER DEFAULT 0, max_scroll INTEGER DEFAULT 0,
  device_type TEXT DEFAULT '', screen_width INTEGER DEFAULT 0,
  utm_source TEXT DEFAULT '', utm_medium TEXT DEFAULT '', utm_campaign TEXT DEFAULT '',
  utm_content TEXT DEFAULT '', utm_term TEXT DEFAULT '', fbclid TEXT DEFAULT '', gclid TEXT DEFAULT '',
  is_bot INTEGER DEFAULT 0, converted_cart INTEGER DEFAULT 0,
  converted_whatsapp INTEGER DEFAULT 0, converted_order INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_campaign ON sessions(utm_campaign);

CREATE TABLE IF NOT EXISTS campaign_costs (
  day TEXT NOT NULL, campaign TEXT NOT NULL, source TEXT DEFAULT '', spend REAL DEFAULT 0,
  impressions INTEGER DEFAULT 0, ad_clicks INTEGER DEFAULT 0,
  PRIMARY KEY(day,campaign,source)
);
