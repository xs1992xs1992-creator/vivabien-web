// VivaBien 边缘后端 Worker
// 路由：
//   GET  /s/:code                短链跳转 + 记点击 + 种访客cookie
//   POST /api/track              前端埋点上报（view/addcart/checkout）
//   POST /api/coupon/validate    校验优惠券、算折扣
//   /api/admin/*                 受 X-Admin-Key 保护，admin.py 调用
// 存储：D1（env.DB）。密钥：env.ADMIN_KEY。

const SITE = "https://vivabien.xyz";
const VID_COOKIE = "vb_vid";
const LINK_COOKIE = "vb_link";
const CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"; // 去掉易混字符

// ---------- 工具 ----------
const now = () => Date.now();

function randCode(len = 6) {
  const a = new Uint8Array(len);
  crypto.getRandomValues(a);
  let s = "";
  for (const b of a) s += CODE_ALPHABET[b % CODE_ALPHABET.length];
  return s;
}

function getCookie(req, name) {
  const c = req.headers.get("Cookie") || "";
  const m = c.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
  return m ? m[1] : "";
}

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS, ...extraHeaders },
  });
}

// 前端跨路径上报需要 CORS（同域也无妨）
const CORS = {
  "Access-Control-Allow-Origin": SITE,
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,X-Admin-Key",
  "Access-Control-Allow-Credentials": "true",
};

function vidCookieHeader(vid) {
  // 首方 cookie，主域下所有页面共享
  return `${VID_COOKIE}=${vid}; Domain=.vivabien.xyz; Path=/; Max-Age=31536000; SameSite=Lax; Secure`;
}

function linkCookieHeader(code) {
  return LINK_COOKIE + "=" + encodeURIComponent(code) + "; Domain=.vivabien.xyz; Path=/; Max-Age=2592000; SameSite=Lax; Secure";
}

function maskIp(ip) {
  if (!ip) return "";
  if (ip.includes(":")) return ip.split(":").slice(0, 4).join(":") + "::";
  const p = ip.split(".");
  return p.length === 4 ? p[0] + "." + p[1] + "." + p[2] + ".x" : "";
}

async function hashIp(ip, salt) {
  if (!ip) return "";
  const bytes = new TextEncoder().encode((salt || "") + ":" + ip);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function logEvent(env, { vid, code = "", type, sku = "", req }) {
  const country = req?.cf?.country || "";
  const ua = req?.headers.get("User-Agent") || "";
  const ref = req?.headers.get("Referer") || "";
  const ip = req?.headers.get("CF-Connecting-IP") || "";
  const ipMasked = maskIp(ip);
  const ipHash = await hashIp(ip, env.IP_HASH_SALT || env.ADMIN_KEY || "");
  await env.DB.prepare(
    "INSERT INTO events (vid, code, type, sku, ts, country, ua, ref, ip_masked, ip_hash) VALUES (?,?,?,?,?,?,?,?,?,?)"
  ).bind(vid, code, type, sku, now(), country, ua.slice(0, 300), ref.slice(0, 300),
         ipMasked, ipHash).run();
}

// ---------- 路由 ----------
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname;

    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });

    try {
      if (path.startsWith("/s/")) return handleShort(req, env, url);
      if (path === "/api/track") return handleTrack(req, env);
      if (path === "/api/coupon/validate") return handleCouponValidate(req, env);
      if (path === "/api/coupon/redeem") return handleCouponRedeem(req, env);
      if (path.startsWith("/api/admin/")) return handleAdmin(req, env, url);
      return json({ error: "not_found" }, 404);
    } catch (e) {
      return json({ error: "server_error", detail: String(e) }, 500);
    }
  },
};

// GET /s/:code
async function handleShort(req, env, url) {
  const code = url.pathname.slice(3);
  const row = await env.DB.prepare("SELECT target FROM links WHERE code=?").bind(code).first();
  if (!row) return Response.redirect(SITE + "/", 302);

  let vid = getCookie(req, VID_COOKIE);
  const fresh = !vid;
  if (!vid) vid = crypto.randomUUID();

  await env.DB.prepare("UPDATE links SET clicks = clicks + 1 WHERE code=?").bind(code).run();
  await logEvent(env, { vid, code, type: "click", req });

  const target = /^https?:\/\//.test(row.target) ? row.target : SITE + "/" + row.target.replace(/^\//, "");
  const headers = new Headers({ Location: target });
  if (fresh) headers.append("Set-Cookie", vidCookieHeader(vid));
  headers.append("Set-Cookie", linkCookieHeader(code));
  return new Response(null, { status: 302, headers });
}

// POST /api/track  { type, sku?, code? }
async function handleTrack(req, env) {
  const body = await req.json().catch(() => ({}));
  const type = body.type;
  if (!["view", "addcart", "checkout"].includes(type)) return json({ ok: false }, 400);

  let vid = getCookie(req, VID_COOKIE);
  const fresh = !vid;
  if (!vid) vid = crypto.randomUUID();

  const linkCode = body.code || getCookie(req, LINK_COOKIE) || "";
  await logEvent(env, { vid, code: linkCode, type, sku: body.sku || "", req });
  const headers = fresh ? { "Set-Cookie": vidCookieHeader(vid) } : {};
  return json({ ok: true }, 200, headers);
}

// POST /api/coupon/validate  { code, subtotal }
async function handleCouponValidate(req, env) {
  const body = await req.json().catch(() => ({}));
  const code = (body.code || "").trim();
  const subtotal = Number(body.subtotal) || 0;
  if (!code) return json({ valid: false, reason: "empty" });

  const c = await env.DB.prepare("SELECT * FROM coupons WHERE code=?").bind(code).first();
  if (!c || !c.active) return json({ valid: false, reason: "invalid" });
  if (c.expires_at && now() > c.expires_at) return json({ valid: false, reason: "expired" });
  if (c.max_uses && c.used_count >= c.max_uses) return json({ valid: false, reason: "used_up" });
  if (c.min_order && subtotal < c.min_order)
    return json({ valid: false, reason: "min_order", min_order: c.min_order });

  let discount = c.kind === "percent" ? subtotal * (c.value / 100) : c.value;
  discount = Math.min(discount, subtotal);
  discount = Math.round(discount * 100) / 100;

  return json({
    valid: true,
    code: c.code,
    kind: c.kind,
    value: c.value,
    discount,
    total: Math.round((subtotal - discount) * 100) / 100,
  });
}

// POST /api/coupon/redeem  { code, order_id?, vid? }  —— 下单时核销：used_count+1
async function handleCouponRedeem(req, env) {
  const body = await req.json().catch(() => ({}));
  const code = (body.code || "").trim();
  if (!code) return json({ ok: false, reason: "empty" });

  // 原子递增：仅当启用/未过期/未达上限时才 +1
  const upd = await env.DB.prepare(
    `UPDATE coupons SET used_count = used_count + 1
     WHERE code=? AND active=1
       AND (expires_at=0 OR expires_at>?)
       AND (max_uses=0 OR used_count<max_uses)`
  ).bind(code, now()).run();

  const changed = (upd.meta && (upd.meta.changes ?? upd.meta.rows_written)) || 0;
  if (!changed) return json({ ok: false, reason: "not_redeemable" });

  const vid = body.vid || getCookie(req, VID_COOKIE) || "";
  await env.DB.prepare(
    "INSERT INTO coupon_uses (code, order_id, vid, ts) VALUES (?,?,?,?)"
  ).bind(code, body.order_id || "", vid, now()).run();

  return json({ ok: true });
}

// ---------- 后台接口（X-Admin-Key）----------
async function handleAdmin(req, env, url) {
  const key = req.headers.get("X-Admin-Key") || "";
  if (!env.ADMIN_KEY || key !== env.ADMIN_KEY) return json({ error: "unauthorized" }, 401);

  const sub = url.pathname.replace("/api/admin/", "");

  // 短链
  if (sub === "link/create" && req.method === "POST") {
    const b = await req.json().catch(() => ({}));
    if (!b.target) return json({ error: "target_required" }, 400);
    let code = b.code || randCode();
    // 保证唯一
    for (let i = 0; i < 5; i++) {
      const exist = await env.DB.prepare("SELECT 1 FROM links WHERE code=?").bind(code).first();
      if (!exist) break;
      code = randCode();
    }
    await env.DB.prepare(
      "INSERT INTO links (code, target, note, created_at, clicks) VALUES (?,?,?,?,0)"
    ).bind(code, b.target, b.note || "", now()).run();
    return json({ ok: true, code, url: `${SITE}/s/${code}` });
  }

  if (sub === "links" && req.method === "GET") {
    const rows = await env.DB.prepare(
      `SELECT l.code, l.target, l.note, l.created_at, l.clicks,
              (SELECT COUNT(DISTINCT vid) FROM events e WHERE e.code=l.code) AS visitors,
              (SELECT COUNT(*) FROM events e WHERE e.code=l.code AND e.type='view') AS views,
              (SELECT COUNT(*) FROM events e WHERE e.code=l.code AND e.type='addcart') AS addcarts,
              (SELECT COUNT(*) FROM events e WHERE e.code=l.code AND e.type='checkout') AS checkouts
       FROM links l ORDER BY l.created_at DESC`
    ).all();
    return json({ ok: true, links: rows.results || [] });
  }

  // 访客时间线
  if (sub === "timeline" && req.method === "GET") {
    const vid = url.searchParams.get("vid") || "";
    const code = url.searchParams.get("code") || "";
    let stmt;
    if (vid) stmt = env.DB.prepare("SELECT * FROM events WHERE vid=? ORDER BY ts ASC").bind(vid);
    else if (code) stmt = env.DB.prepare("SELECT * FROM events WHERE code=? ORDER BY ts ASC").bind(code);
    else return json({ error: "vid_or_code_required" }, 400);
    const rows = await stmt.all();
    return json({ ok: true, events: rows.results || [] });
  }

  // 优惠券
  if (sub === "coupon/create" && req.method === "POST") {
    const b = await req.json().catch(() => ({}));
    const kind = b.kind === "amount" ? "amount" : "percent";
    const value = Number(b.value) || 0;
    if (value <= 0) return json({ error: "value_required" }, 400);
    if (kind === "percent" && value > 100) return json({ error: "percent_gt_100" }, 400);
    let code = (b.code || randCode(8)).toUpperCase();
    for (let i = 0; i < 5; i++) {
      const exist = await env.DB.prepare("SELECT 1 FROM coupons WHERE code=?").bind(code).first();
      if (!exist) break;
      code = randCode(8).toUpperCase();
    }
    await env.DB.prepare(
      `INSERT INTO coupons (code, kind, value, active, created_at, expires_at, max_uses, used_count, min_order, scope)
       VALUES (?,?,?,1,?,?,?,0,?,?)`
    ).bind(code, kind, value, now(), Number(b.expires_at) || 0, Number(b.max_uses) || 0,
           Number(b.min_order) || 0, b.scope || "all").run();
    return json({ ok: true, code, kind, value });
  }

  if (sub === "coupons" && req.method === "GET") {
    const rows = await env.DB.prepare("SELECT * FROM coupons ORDER BY created_at DESC").all();
    return json({ ok: true, coupons: rows.results || [] });
  }

  if (sub === "coupon/toggle" && req.method === "POST") {
    const b = await req.json().catch(() => ({}));
    if (!b.code) return json({ error: "code_required" }, 400);
    await env.DB.prepare("UPDATE coupons SET active = 1 - active WHERE code=?").bind(b.code).run();
    return json({ ok: true });
  }

  // 概览统计
  if (sub === "overview" && req.method === "GET") {
    const since = now() - 30 * 864e5;
    const totals = await env.DB.prepare(
      `SELECT
         (SELECT COUNT(*) FROM links) AS links,
         (SELECT COUNT(*) FROM events WHERE type='click' AND ts>?) AS clicks30,
         (SELECT COUNT(DISTINCT vid) FROM events WHERE ts>?) AS visitors30,
         (SELECT COUNT(*) FROM events WHERE type='addcart' AND ts>?) AS addcarts30,
         (SELECT COUNT(*) FROM events WHERE type='checkout' AND ts>?) AS checkouts30,
         (SELECT COUNT(*) FROM coupon_uses WHERE ts>?) AS coupon_uses30,
         (SELECT COUNT(*) FROM coupons WHERE active=1) AS active_coupons`
    ).bind(since, since, since, since, since).first();
    return json({ ok: true, ...totals });
  }

  return json({ error: "unknown_admin_route" }, 404);
}
