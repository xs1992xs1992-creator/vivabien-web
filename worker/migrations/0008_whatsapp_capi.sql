-- WhatsApp 成交回传 Meta（CAPI）
-- 背景：大量成交发生在 WhatsApp，不经过网站结账，Meta 看不到，会把这些真实买家
-- 当成"点了没买"的失败案例去学习。这里给订单加来源标记和"已送达并收款"终态，
-- 只有 source='whatsapp' 且确认收款的订单才回传 Purchase（COD 拒收率约 37.6%，
-- 建单时上报会让算法去学"爱下单但不收货"的人）。

ALTER TABLE orders ADD COLUMN source TEXT NOT NULL DEFAULT 'web';          -- web | whatsapp
ALTER TABLE orders ADD COLUMN delivered_paid_at INTEGER DEFAULT NULL;      -- 送达并收款时间（秒）
ALTER TABLE orders ADD COLUMN capi_sent INTEGER NOT NULL DEFAULT 0;        -- 是否已上报 Meta
ALTER TABLE orders ADD COLUMN capi_sent_at INTEGER DEFAULT NULL;
ALTER TABLE orders ADD COLUMN capi_error TEXT DEFAULT NULL;

-- 已有订单全部算网站来源
UPDATE orders SET source='web' WHERE source IS NULL OR source='';

CREATE INDEX IF NOT EXISTS idx_orders_source ON orders(source);
CREATE INDEX IF NOT EXISTS idx_orders_capi ON orders(source, status, capi_sent);
