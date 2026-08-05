// VivaBien 边缘后端 Worker
// 路由：
//   GET  /s/:code                短链跳转 + 记点击 + 种访客cookie
//   POST /api/track              前端埋点上报（view/addcart/checkout）
//   POST /api/coupon/validate    校验优惠券、算折扣
//   /api/admin/*                 受 X-Admin-Key 保护，admin.py 调用
// 存储：D1（env.DB）。密钥：env.ADMIN_KEY。

import SHIPPING_CONFIG from "../../data/shipping_zones.json";

const SITE = "https://vivabien.xyz";
const VID_COOKIE = "vb_vid";
const LINK_COOKIE = "vb_link";
const CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"; // 去掉易混字符

const SHIPPING_REMOTE = new Set(["Pedernales", "Independencia", "Elías Piña", "Dajabón", "Monte Cristi"]);
const SHIPPING_MAJOR = new Set(["Santiago", "La Altagracia", "La Vega", "Puerto Plata", "Duarte", "Espaillat", "Monseñor Nouel"]);
const SHIPPING_NEAR = new Set(["San Cristóbal", "Monte Plata", "San Pedro de Macorís", "La Romana", "Peravia"]);

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

function requestMeta(req) {
  const cf = req?.cf || {};
  const ip = req?.headers.get("CF-Connecting-IP") || "";
  return {
    ip, ipMasked: maskIp(ip), country: cf.country || "", city: cf.city || "",
    region: cf.region || "", postalCode: cf.postalCode || "", latitude: cf.latitude || "",
    longitude: cf.longitude || "", asn: Number(cf.asn) || 0, asOrg: cf.asOrganization || "",
    ua: req?.headers.get("User-Agent") || "", ref: req?.headers.get("Referer") || "",
  };
}

function botReason(meta) {
  const ua = (meta.ua || "").toLowerCase();
  if (!ua) return "empty_user_agent";
  const hit = ua.match(/bot|crawler|spider|facebookexternalhit|facebot|preview|slurp|bingpreview/);
  return hit ? hit[0] : "";
}

function shippingQuote(province = "", zone = "") {
  const p = String(province).trim(), z = String(zone).trim();
  const metro = p.startsWith("Distrito Nacional") || p.startsWith("Santo Domingo (provincia)");
  if (metro) {
    const exact = (SHIPPING_CONFIG.zones || []).find((item) => (item.sectors || []).includes(z));
    if (exact) {
      const fee = Math.max(0, Number(exact.price) || 0);
      return { ok:true, ready:true, zone:String(exact.id), label:z, fee,
        fee_min:fee, fee_max:fee, delivery:String(exact.eta || "por confirmar"), cod_allowed:true };
    }
    return { ok:true, ready:false, zone:"otro", label:"Otro sector",
      fee:0, fee_min:150, fee_max:600, delivery:"por confirmar", cod_allowed:true };
  }
  if (p.startsWith("Santo Domingo (provincia)") || SHIPPING_NEAR.has(p))
    return { ok:true, ready:true, zone:"cercana", label:"Zona cercana", fee:250, fee_min:250, fee_max:250,
      delivery:"1-3 días laborables", cod_allowed:false };
  if (SHIPPING_MAJOR.has(p)) return { ok:true, ready:true, zone:"ciudades_principales", label:"Ciudades principales", fee:300, fee_min:300, fee_max:300,
    delivery:"2-4 días laborables", cod_allowed:false };
  if (SHIPPING_REMOTE.has(p)) return { ok:true, ready:true, zone:"remota", label:"Zona remota", fee:450, fee_min:450, fee_max:450,
    delivery:"4-7 días laborables", cod_allowed:false };
  return { ok:true, ready:true, zone:"nacional", label:"Resto del país", fee:350, fee_min:350, fee_max:350,
    delivery:"3-5 días laborables", cod_allowed:false };
}

async function logEvent(env, { vid, code = "", type, sku = "", req, details = {} }) {
  const m = requestMeta(req);
  const ipHash = await hashIp(m.ip, env.IP_HASH_SALT || env.ADMIN_KEY || "");
  const reason = botReason(m);
  const eventId = String(details.event_id || "").slice(0, 80);
  const sessionId = String(details.session_id || "").slice(0, 80);
  const inserted = await env.DB.prepare(
    `INSERT OR IGNORE INTO events (vid,code,type,sku,ts,country,ua,ref,ip_masked,ip_hash,ip_full,
     city,region,postal_code,latitude,longitude,asn,as_org,qty,price,cart_total,product_title,product_img,
     event_id,session_id,path,category,duration_ms,scroll_depth,device_type,screen_width,utm_source,
     utm_medium,utm_campaign,utm_content,utm_term,fbclid,gclid,whatsapp_location,is_bot,bot_reason,
     site_version,search_query,result_count,sort_mode,filter_group,filter_sub,shipping_fee,shipping_zone,delivery_estimate,
     source_section,selected_color,offer_qty,gallery_index,review_index,calculated_qty,wall_width,wall_height,order_id)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`
  ).bind(vid, code, type, sku, now(), m.country, m.ua.slice(0, 300), m.ref.slice(0, 300),
         m.ipMasked, ipHash, m.ip, m.city, m.region, m.postalCode, m.latitude, m.longitude,
         m.asn, m.asOrg.slice(0, 160), Math.max(0, Number(details.qty) || 0),
         Math.max(0, Number(details.price) || 0), Math.max(0, Number(details.cart_total) || 0),
         String(details.product_title || "").slice(0, 240), String(details.product_img || "").slice(0, 240),
         eventId, sessionId, String(details.path || "").slice(0, 300), String(details.category || "").slice(0, 160),
         Math.max(0, Number(details.duration_ms) || 0), Math.max(0, Math.min(100, Number(details.scroll_depth) || 0)),
         String(details.device_type || "").slice(0, 20), Math.max(0, Number(details.screen_width) || 0),
         String(details.utm_source || "").slice(0, 120), String(details.utm_medium || "").slice(0, 120),
         String(details.utm_campaign || "").slice(0, 180), String(details.utm_content || "").slice(0, 180),
         String(details.utm_term || "").slice(0, 180), String(details.fbclid || "").slice(0, 300),
         String(details.gclid || "").slice(0, 300), String(details.whatsapp_location || "").slice(0, 80),
         reason ? 1 : 0, reason, String(details.site_version || "").slice(0,80),
         String(details.search_query || "").slice(0,240), Math.max(0, Number(details.result_count) || 0),
         String(details.sort_mode || "").slice(0,40), String(details.filter_group || "").slice(0,160),
         String(details.filter_sub || "").slice(0,160), Math.max(0, Number(details.shipping_fee) || 0),
         String(details.shipping_zone || "").slice(0,80), String(details.delivery_estimate || "").slice(0,120),
         String(details.source_section || "").slice(0,100), String(details.selected_color || details.color || "").slice(0,120),
         Math.max(0, Number(details.offer_qty) || 0), Math.max(0, Number(details.gallery_index) || 0),
         Number.isFinite(Number(details.review_index)) ? Number(details.review_index) : -1,
         Math.max(0, Number(details.calculated_qty) || 0), Math.max(0, Number(details.wall_width) || 0),
         Math.max(0, Number(details.wall_height) || 0), String(details.order_id || "").slice(0,40)).run();
  const changed = (inserted.meta && (inserted.meta.changes ?? inserted.meta.rows_written)) || 0;
  if (!changed || !sessionId) return;
  const t = now(), isView = type === "view" ? 1 : 0, isCart = type === "addcart" ? 1 : 0;
  const isWhatsApp = type === "whatsapp" ? 1 : 0, isOrder = type === "order" ? 1 : 0;
  await env.DB.prepare(
    `INSERT INTO sessions (session_id,vid,link_code,started_at,last_seen_at,landing_path,last_path,page_views,
     engaged_ms,max_scroll,device_type,screen_width,utm_source,utm_medium,utm_campaign,utm_content,utm_term,
     fbclid,gclid,is_bot,converted_cart,converted_whatsapp,converted_order)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(session_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,last_path=excluded.last_path,
     page_views=sessions.page_views+excluded.page_views,engaged_ms=sessions.engaged_ms+excluded.engaged_ms,
     max_scroll=MAX(sessions.max_scroll,excluded.max_scroll),is_bot=MAX(sessions.is_bot,excluded.is_bot),
     converted_cart=MAX(sessions.converted_cart,excluded.converted_cart),
     converted_whatsapp=MAX(sessions.converted_whatsapp,excluded.converted_whatsapp),
     converted_order=MAX(sessions.converted_order,excluded.converted_order)`
  ).bind(sessionId, vid, code, t, t, String(details.path || "").slice(0, 300),
    String(details.path || "").slice(0, 300), isView, Math.max(0, Number(details.duration_ms) || 0),
    Math.max(0, Math.min(100, Number(details.scroll_depth) || 0)), String(details.device_type || "").slice(0,20),
    Math.max(0, Number(details.screen_width) || 0), String(details.utm_source || "").slice(0,120),
    String(details.utm_medium || "").slice(0,120), String(details.utm_campaign || "").slice(0,180),
    String(details.utm_content || "").slice(0,180), String(details.utm_term || "").slice(0,180),
    String(details.fbclid || "").slice(0,300), String(details.gclid || "").slice(0,300),
    reason ? 1 : 0, isCart, isWhatsApp, isOrder).run();
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
      if (path === "/api/shipping/quote") return handleShippingQuote(req);
      if (path === "/api/order") return handleOrder(req, env);
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
  if (!["view", "addcart", "checkout", "whatsapp", "engagement", "scroll", "search", "filter", "shipping_quote",
        "gallery_view", "color_select", "tier_select", "quantity_change", "review_open", "calculator_success",
        "section_view", "cart_update", "cart_remove", "checkout_start", "checkout_error"].includes(type))
    return json({ ok: false }, 400);

  const clientId = String(body.client_id || "").slice(0, 80);
  let vid = /^c-[A-Za-z0-9-]{12,78}$/.test(clientId) ? clientId : getCookie(req, VID_COOKIE);
  const fresh = !vid;
  if (!vid) vid = crypto.randomUUID();

  const linkCode = body.code || getCookie(req, LINK_COOKIE) || "";
  await logEvent(env, { vid, code: linkCode, type, sku: body.sku || "", req, details: body });
  const headers = fresh ? { "Set-Cookie": vidCookieHeader(vid) } : {};
  return json({ ok: true }, 200, headers);
}

async function handleShippingQuote(req) {
  if (req.method !== "POST") return json({ error:"method_not_allowed" },405);
  const b = await req.json().catch(() => ({}));
  if (!b.province) return json({ error:"province_required" },400);
  return json(shippingQuote(b.province, b.zone));
}

// POST /api/order —— 客户确认购物车后保存完整订单，再由前端打开 WhatsApp
async function handleOrder(req, env) {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  const b = await req.json().catch(() => ({}));
  const items = Array.isArray(b.items) ? b.items.slice(0, 50) : [];
  if (!b.customer_name || !b.phone || !b.address || !items.length)
    return json({ error: "missing_order_fields" }, 400);

  const orderId = String(b.order_id || ("VB-" + randCode(8).toUpperCase())).slice(0, 32);
  const exists = await env.DB.prepare("SELECT order_id FROM orders WHERE order_id=?").bind(orderId).first();
  if (exists) return json({ ok: true, order_id: orderId, duplicate: true });

  const tracking = b.tracking && typeof b.tracking === "object" ? b.tracking : {};
  const clientId = String(tracking.client_id || "").slice(0, 80);
  const vid = /^c-[A-Za-z0-9-]{12,78}$/.test(clientId) ? clientId : (getCookie(req, VID_COOKIE) || crypto.randomUUID());
  const linkCode = getCookie(req, LINK_COOKIE) || "";
  const m = requestMeta(req);
  const ipHash = await hashIp(m.ip, env.IP_HASH_SALT || env.ADMIN_KEY || "");
  const cleanItems = items.map((raw) => {
    const quantity = Math.max(1, Math.min(99, Number(raw.quantity) || 1));
    const unitPrice = Math.max(0, Number(raw.unit_price) || 0);
    return { sku: String(raw.sku || "").slice(0, 100), title: String(raw.title || "Producto").slice(0, 240),
      image: String(raw.image || "").slice(0, 240), quantity, unitPrice,
      lineTotal: Math.round(unitPrice * quantity * 100) / 100 };
  });
  const subtotal = Math.round(cleanItems.reduce((sum, item) => sum + item.lineTotal, 0) * 100) / 100;
  const couponCode = String(b.coupon_code || "").trim();
  let discount = 0;
  if (couponCode) {
    const coupon = await env.DB.prepare("SELECT * FROM coupons WHERE code=?").bind(couponCode).first();
    if (coupon && coupon.active && (!coupon.expires_at || coupon.expires_at > now()) &&
        (!coupon.max_uses || coupon.used_count < coupon.max_uses) && subtotal >= (coupon.min_order || 0)) {
      discount = coupon.kind === "percent" ? subtotal * coupon.value / 100 : coupon.value;
      discount = Math.round(Math.min(subtotal, discount) * 100) / 100;
    }
  }
  const shipping = shippingQuote(b.province, b.zone);
  const paymentMethod = b.payment_method === "cod" ? "cod" : "transfer";
  let mapUrl = String(b.map_url || "").trim().slice(0, 500);
  const mapAllowed = /^(https:\/\/)?(maps\.app\.goo\.gl|www\.google\.[^/]+\/maps|goo\.gl\/maps|waze\.com\/ul|www\.waze\.com\/live-map|ul\.waze\.com)/i;
  if (mapUrl && !mapAllowed.test(mapUrl)) return json({ error:"invalid_location_link" },400);
  if (mapUrl && !/^https?:\/\//i.test(mapUrl)) mapUrl = `https://${mapUrl}`;
  const locationFollowup = b.location_followup ? 1 : 0;
  const preferredDate = String(b.preferred_delivery_date || "").trim().slice(0, 10);
  const preferredWindow = String(b.preferred_delivery_window || "").trim().slice(0, 40);
  if (preferredDate && !/^\d{4}-\d{2}-\d{2}$/.test(preferredDate))
    return json({ error:"invalid_delivery_date" },400);
  const allowedWindows = new Set(["09:00-12:00","12:00-15:00","15:00-19:00","09:00-19:00"]);
  if (preferredWindow && !allowedWindows.has(preferredWindow))
    return json({ error:"invalid_delivery_window" },400);
  if (paymentMethod === "cod" && !shipping.cod_allowed)
    return json({ error:"cod_not_available" },400);
  const productTotal = Math.max(0, subtotal - discount);
  const shippingMin = Math.max(0, Number(shipping.fee_min) || 0);
  const shippingMax = Math.max(shippingMin, Number(shipping.fee_max) || shippingMin);
  const totalMin = productTotal + shippingMin, totalMax = productTotal + shippingMax;
  const total = shippingMin === shippingMax ? totalMin : productTotal;
  const created = now();
  const statements = [env.DB.prepare(
   `INSERT INTO orders (order_id,vid,link_code,status,customer_name,phone,province,zone,address,note,
     map_url,location_followup,preferred_delivery_date,preferred_delivery_window,
    payment_method,shipping_zone,shipping_fee,shipping_fee_min,shipping_fee_max,delivery_estimate,
     subtotal,discount,total,total_min,total_max,coupon_code,
     session_id,utm_source,utm_medium,utm_campaign,utm_content,utm_term,fbclid,gclid,
     first_utm_source,first_utm_medium,first_utm_campaign,first_utm_content,first_utm_term,
     ip_full,ip_masked,ip_hash,country,city,region,postal_code,latitude,longitude,asn,as_org,ua,ref,created_at,updated_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`
  ).bind(orderId, vid, linkCode, "pending", String(b.customer_name).slice(0,160),
    String(b.phone).slice(0,80), String(b.province || "").slice(0,120), String(b.zone || "").slice(0,120),
   String(b.address).slice(0,500), String(b.note || "").slice(0,500),
    mapUrl, locationFollowup, preferredDate, preferredWindow,
   paymentMethod, shipping.zone, shipping.fee, shippingMin, shippingMax, shipping.delivery,
    subtotal, discount, total, totalMin, totalMax,
    couponCode.slice(0,80), String(tracking.session_id || "").slice(0,80),
    String(tracking.utm_source || "").slice(0,120), String(tracking.utm_medium || "").slice(0,120),
    String(tracking.utm_campaign || "").slice(0,180), String(tracking.utm_content || "").slice(0,180),
    String(tracking.utm_term || "").slice(0,180), String(tracking.fbclid || "").slice(0,300),
    String(tracking.gclid || "").slice(0,300), String(tracking.first_utm_source || "").slice(0,120),
    String(tracking.first_utm_medium || "").slice(0,120), String(tracking.first_utm_campaign || "").slice(0,180),
    String(tracking.first_utm_content || "").slice(0,180), String(tracking.first_utm_term || "").slice(0,180),
    m.ip, m.ipMasked, ipHash, m.country, m.city, m.region,
    m.postalCode, m.latitude, m.longitude, m.asn, m.asOrg.slice(0,160), m.ua.slice(0,300),
    m.ref.slice(0,300), created, created)];
  for (const item of cleanItems) {
    statements.push(env.DB.prepare(
      `INSERT INTO order_items (order_id,sku,title,image,unit_price,quantity,line_total)
       VALUES (?,?,?,?,?,?,?)`
    ).bind(orderId, item.sku, item.title, item.image, item.unitPrice, item.quantity, item.lineTotal));
  }
  await env.DB.batch(statements);
  for (const item of cleanItems) {
    await logEvent(env, { vid, code: linkCode, type: "order", sku:item.sku, req,
      details: { ...tracking, order_id:orderId, qty:item.quantity, price:item.unitPrice,
        cart_total:totalMin, product_title:item.title, product_img:item.image,
        shipping_fee:shipping.fee, shipping_zone:shipping.zone, delivery_estimate:shipping.delivery } });
  }
  return json({ ok:true, order_id:orderId, subtotal, discount, shipping_fee:shipping.fee,
    shipping_fee_min:shippingMin, shipping_fee_max:shippingMax, shipping_zone:shipping.zone,
    delivery_estimate:shipping.delivery, total, total_min:totalMin, total_max:totalMax }, 201,
    { "Set-Cookie":vidCookieHeader(vid) });
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

  if (sub === "orders" && req.method === "GET") {
    const status = url.searchParams.get("status") || "";
    const base = `SELECT * FROM orders ${status ? "WHERE status=?" : ""} ORDER BY created_at DESC LIMIT 300`;
    const orderRows = status ? await env.DB.prepare(base).bind(status).all() : await env.DB.prepare(base).all();
    const orders = orderRows.results || [];
    if (orders.length) {
      const itemRows = await env.DB.prepare(
        `SELECT * FROM order_items WHERE order_id IN (${orders.map(() => "?").join(",")}) ORDER BY id ASC`
      ).bind(...orders.map((o) => o.order_id)).all();
      const grouped = {};
      for (const item of itemRows.results || []) (grouped[item.order_id] ||= []).push(item);
      for (const order of orders) order.items = grouped[order.order_id] || [];
    }
    return json({ ok: true, orders });
  }

  if (sub === "order/status" && req.method === "POST") {
    const b = await req.json().catch(() => ({}));
    const allowed = ["pending", "confirmed", "shipping", "completed", "cancelled"];
    if (!b.order_id || !allowed.includes(b.status)) return json({ error: "invalid_status" }, 400);
    await env.DB.prepare("UPDATE orders SET status=?,updated_at=? WHERE order_id=?")
      .bind(b.status, now(), b.order_id).run();
    return json({ ok: true });
  }

  if (sub === "cart-visitors" && req.method === "GET") {
    const since = Number(url.searchParams.get("since")) || now() - 30 * 864e5;
    const rows = await env.DB.prepare(
      `SELECT * FROM events
       WHERE type='addcart' AND ts>=? AND qty>0 AND cart_total>0
       ORDER BY ts DESC LIMIT 500`
    ).bind(since).all();
    const legacy = await env.DB.prepare(
      `SELECT COUNT(*) count FROM events
       WHERE type='addcart' AND ts>=? AND (qty<=0 OR cart_total<=0)`
    ).bind(since).first();
    return json({ ok: true, events: rows.results || [], filtered_invalid: Number(legacy?.count) || 0 });
  }

  if (sub === "product-analytics" && req.method === "GET") {
    const sku = String(url.searchParams.get("sku") || "").slice(0, 100);
    if (!sku) return json({ error: "sku_required" }, 400);
    const days = Math.max(1, Math.min(365, Number(url.searchParams.get("days")) || 30));
    const since = now() - days * 864e5;

    const summary = await env.DB.prepare(
      `WITH target_sessions AS (
         SELECT DISTINCT session_id FROM events
         WHERE sku=? AND ts>=? AND is_bot=0 AND session_id<>''
       ), target_events AS (
         SELECT e.* FROM events e JOIN target_sessions t ON t.session_id=e.session_id
         WHERE e.ts>=? AND e.is_bot=0
       )
       SELECT
         (SELECT COUNT(*) FROM target_sessions) visitors,
         COUNT(DISTINCT CASE WHEN type='view' AND sku=? THEN session_id END) product_viewers,
         COUNT(DISTINCT CASE WHEN type='addcart' AND sku=? THEN session_id END) addcart_visitors,
         COALESCE(SUM(CASE WHEN type='addcart' AND sku=? THEN qty ELSE 0 END),0) addcart_units,
         COUNT(DISTINCT CASE WHEN type='whatsapp' THEN session_id END) whatsapp_sessions,
         COUNT(DISTINCT CASE WHEN type='checkout_start' AND sku=? THEN session_id END) checkout_sessions,
         COUNT(DISTINCT CASE WHEN type='order' AND sku=? THEN session_id END) tracked_order_sessions,
         COUNT(DISTINCT CASE WHEN type='color_select' AND sku=? THEN session_id END) color_sessions,
         COUNT(DISTINCT CASE WHEN type='tier_select' AND sku=? THEN session_id END) offer_sessions,
         COUNT(DISTINCT CASE WHEN type='calculator_success' AND sku=? THEN session_id END) calculator_sessions,
         COUNT(DISTINCT CASE WHEN type='review_open' AND sku=? THEN session_id END) review_sessions,
         COUNT(DISTINCT CASE WHEN type='engagement' OR scroll_depth>=25 THEN session_id END) engaged_sessions,
         COUNT(DISTINCT CASE WHEN sku=? AND (ip_full LIKE '2a03:2880:%' OR UPPER(as_org) LIKE '%META%' OR UPPER(as_org) LIKE '%FACEBOOK%') THEN session_id END) meta_network_visitors,
         (SELECT ROUND(AVG(s.engaged_ms)/1000.0,1) FROM sessions s JOIN target_sessions t ON t.session_id=s.session_id) avg_seconds,
         (SELECT ROUND(AVG(s.max_scroll),1) FROM sessions s JOIN target_sessions t ON t.session_id=s.session_id) avg_scroll
       FROM target_events`
    ).bind(sku, since, since, sku, sku, sku, sku, sku, sku, sku, sku, sku, sku).first();

    const orderSummary = await env.DB.prepare(
      `SELECT COUNT(DISTINCT o.order_id) orders,COALESCE(SUM(oi.quantity),0) units,
       COALESCE(SUM(oi.line_total),0) revenue
       FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
       WHERE oi.sku=? AND o.created_at>=? AND o.status<>'cancelled'`
    ).bind(sku, since).first();

    const orderStatus = await env.DB.prepare(
      `SELECT o.status,COUNT(DISTINCT o.order_id) orders,COALESCE(SUM(oi.quantity),0) units,
       COALESCE(SUM(oi.line_total),0) revenue
       FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
       WHERE oi.sku=? AND o.created_at>=? GROUP BY o.status ORDER BY orders DESC`
    ).bind(sku, since).all();

    const channels = await env.DB.prepare(
      `WITH target_sessions AS (
         SELECT DISTINCT session_id FROM events
         WHERE sku=? AND ts>=? AND is_bot=0 AND session_id<>''
       )
       SELECT COALESCE(NULLIF(s.utm_campaign,''),NULLIF(s.link_code,''),
              NULLIF(s.utm_source,''),'直接访问') channel,
         COUNT(*) sessions,SUM(s.converted_cart) carts,
         SUM(s.converted_whatsapp) whatsapps,SUM(s.converted_order) orders,
         ROUND(AVG(s.engaged_ms)/1000.0,1) avg_seconds,
         ROUND(AVG(s.max_scroll),1) avg_scroll
       FROM sessions s JOIN target_sessions t ON t.session_id=s.session_id
       WHERE s.started_at>=? AND s.is_bot=0
       GROUP BY channel ORDER BY sessions DESC LIMIT 30`
    ).bind(sku, since, since).all();

    const costs = await env.DB.prepare(
      `SELECT campaign,SUM(spend) spend,SUM(impressions) impressions,SUM(ad_clicks) ad_clicks
       FROM campaign_costs WHERE day>=date(?/1000,'unixepoch') GROUP BY campaign`
    ).bind(since).all();
    const costMap = Object.fromEntries((costs.results || []).map((x) => [x.campaign, x]));
    const channelRevenue = await env.DB.prepare(
      `SELECT CASE WHEN o.utm_campaign<>'' THEN o.utm_campaign WHEN o.link_code<>'' THEN o.link_code
       WHEN o.utm_source<>'' THEN o.utm_source WHEN o.session_id<>'' THEN '直接访问' ELSE '未归因订单' END channel,
       COUNT(DISTINCT o.order_id) actual_orders,COALESCE(SUM(oi.line_total),0) revenue
       FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
       WHERE oi.sku=? AND o.created_at>=? AND o.status<>'cancelled' GROUP BY channel`
    ).bind(sku, since).all();
    const revenueMap = Object.fromEntries((channelRevenue.results || []).map((x) => [x.channel, x]));
    const unattributedOrders = revenueMap["未归因订单"] || { actual_orders:0, revenue:0 };
    for (const row of channels.results || []) {
      const c = costMap[row.channel] || {};
      const sales = revenueMap[row.channel] || {};
      row.spend = Number(c.spend) || 0;
      row.impressions = Number(c.impressions) || 0;
      row.ad_clicks = Number(c.ad_clicks) || 0;
      row.cost_per_cart = row.carts ? row.spend / row.carts : 0;
      row.actual_orders = Number(sales.actual_orders) || 0;
      row.revenue = Number(sales.revenue) || 0;
      row.cost_per_order = row.actual_orders ? row.spend / row.actual_orders : 0;
      row.roas = row.spend ? row.revenue / row.spend : 0;
    }

    const daily = await env.DB.prepare(
      `SELECT date((ts/1000)-14400,'unixepoch') day,
       COUNT(DISTINCT CASE WHEN type='view' THEN session_id END) visitors,
       COUNT(DISTINCT CASE WHEN type='addcart' THEN session_id END) addcarts,
       COALESCE(SUM(CASE WHEN type='addcart' THEN qty ELSE 0 END),0) units
       FROM events WHERE sku=? AND ts>=? AND is_bot=0
       GROUP BY day ORDER BY day ASC`
    ).bind(sku, since).all();

    const colors = await env.DB.prepare(
      `SELECT selected_color color,
       COUNT(DISTINCT CASE WHEN type='color_select' THEN session_id END) selectors,
       COUNT(DISTINCT CASE WHEN type='addcart' THEN session_id END) carts,
       COALESCE(SUM(CASE WHEN type='addcart' THEN qty ELSE 0 END),0) units
       FROM events WHERE sku=? AND ts>=? AND is_bot=0 AND selected_color<>''
       GROUP BY selected_color ORDER BY carts DESC,selectors DESC`
    ).bind(sku, since).all();
    const addSources = await env.DB.prepare(
      `SELECT COALESCE(NULLIF(source_section,''),'未标记') source,
       COUNT(DISTINCT session_id) sessions,COUNT(*) actions,COALESCE(SUM(qty),0) units
       FROM events WHERE sku=? AND type='addcart' AND ts>=? AND is_bot=0
       GROUP BY source ORDER BY sessions DESC`
    ).bind(sku, since).all();
    const offers = await env.DB.prepare(
      `SELECT offer_qty quantity,COUNT(DISTINCT session_id) sessions
       FROM events WHERE sku=? AND type='tier_select' AND ts>=? AND is_bot=0 AND offer_qty>0
       GROUP BY offer_qty ORDER BY quantity`
    ).bind(sku, since).all();
    const devices = await env.DB.prepare(
      `WITH target_sessions AS (SELECT DISTINCT session_id FROM events WHERE sku=? AND ts>=? AND is_bot=0 AND session_id<>'')
       SELECT COALESCE(NULLIF(s.device_type,''),'未知') device,COUNT(*) sessions,SUM(s.converted_cart) carts,
       SUM(s.converted_whatsapp) whatsapps,SUM(s.converted_order) orders,ROUND(AVG(s.engaged_ms)/1000.0,1) avg_seconds
       FROM sessions s JOIN target_sessions t ON t.session_id=s.session_id GROUP BY device ORDER BY sessions DESC`
    ).bind(sku, since).all();
    const regions = await env.DB.prepare(
      `SELECT COALESCE(NULLIF(region,''),NULLIF(city,''),'未知') region,COUNT(DISTINCT session_id) sessions,
       COUNT(DISTINCT CASE WHEN type='addcart' THEN session_id END) carts,
       COUNT(DISTINCT CASE WHEN type='whatsapp' THEN session_id END) whatsapps
       FROM events WHERE sku=? AND ts>=? AND is_bot=0 AND session_id<>'' GROUP BY region ORDER BY sessions DESC LIMIT 15`
    ).bind(sku, since).all();
    const quality = await env.DB.prepare(
      `WITH target AS (SELECT session_id,COUNT(DISTINCT vid) vids FROM events
       WHERE sku=? AND ts>=? AND is_bot=0 AND session_id<>'' GROUP BY session_id)
       SELECT COUNT(*) sessions,SUM(vids>1) multi_vid_sessions,COALESCE(SUM(vids-1),0) extra_vids,
       (SELECT COUNT(*) FROM events WHERE sku=? AND type='addcart' AND ts>=? AND is_bot=0 AND cart_total<=0) addcarts_without_total
       FROM target`
    ).bind(sku, since, sku, since).first();

    const dailyOrders = await env.DB.prepare(
      `SELECT date((o.created_at/1000)-14400,'unixepoch') day,
       COUNT(DISTINCT o.order_id) orders,COALESCE(SUM(oi.quantity),0) units,
       COALESCE(SUM(oi.line_total),0) revenue
       FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
       WHERE oi.sku=? AND o.created_at>=? AND o.status<>'cancelled'
       GROUP BY day ORDER BY day ASC`
    ).bind(sku, since).all();

    const recent = await env.DB.prepare(
      `SELECT ts,vid,type,qty,price,cart_total,ip_full,ip_masked,city,region,as_org,
       device_type,utm_source,utm_campaign,code,session_id,source_section,selected_color,offer_qty,
       gallery_index,review_index,calculated_qty,wall_width,wall_height,order_id
       FROM events WHERE sku=? AND ts>=? AND is_bot=0
       AND type NOT IN ('scroll','engagement','section_view')
       ORDER BY ts DESC LIMIT 100`
    ).bind(sku, since).all();

    return json({ ok:true, sku, days, summary:{ ...(summary || {}), ...(orderSummary || {}) },
      channels:channels.results || [], daily:daily.results || [],
      daily_orders:dailyOrders.results || [], order_status:orderStatus.results || [],
      colors:colors.results || [], add_sources:addSources.results || [], offers:offers.results || [],
      devices:devices.results || [], regions:regions.results || [], quality:quality || {},
      unattributed_orders:unattributedOrders, recent:recent.results || [] });
  }

  if (sub === "analytics" && req.method === "GET") {
    const days = Math.max(1, Math.min(365, Number(url.searchParams.get("days")) || 30));
    const since = now() - days * 864e5;
    const funnel = await env.DB.prepare(
      `SELECT
       COUNT(DISTINCT CASE WHEN type='click' THEN vid END) clicks,
       COUNT(DISTINCT CASE WHEN type='view' AND code<>'' THEN COALESCE(NULLIF(session_id,''),vid) END) arrivals,
       COUNT(DISTINCT CASE WHEN type='view' AND sku<>'' AND code<>'' THEN COALESCE(NULLIF(session_id,''),vid) END) product_views,
       COUNT(DISTINCT CASE WHEN type='addcart' AND code<>'' THEN COALESCE(NULLIF(session_id,''),vid) END) addcarts,
       COUNT(DISTINCT CASE WHEN type='checkout' AND code<>'' THEN COALESCE(NULLIF(session_id,''),vid) END) checkouts,
       COUNT(DISTINCT CASE WHEN type='whatsapp' AND code<>'' THEN COALESCE(NULLIF(session_id,''),vid) END) whatsapps,
       COUNT(DISTINCT CASE WHEN type='order' AND code<>'' THEN COALESCE(NULLIF(session_id,''),vid) END) orders
       FROM events WHERE ts>=? AND is_bot=0`
    ).bind(since).first();
    const channels = await env.DB.prepare(
      `SELECT COALESCE(NULLIF(utm_campaign,''),NULLIF(link_code,''),'直接访问') channel,
       COUNT(*) sessions,SUM(page_views=1 AND engaged_ms<10000 AND converted_cart=0 AND converted_whatsapp=0) bounces,
       SUM(converted_cart) carts,SUM(converted_whatsapp) whatsapps,SUM(converted_order) orders,
       ROUND(AVG(engaged_ms)/1000.0,1) avg_seconds
       FROM sessions WHERE started_at>=? AND is_bot=0 GROUP BY channel ORDER BY sessions DESC LIMIT 30`
    ).bind(since).all();
    const devices = await env.DB.prepare(
      `SELECT COALESCE(NULLIF(device_type,''),'未知') device,COUNT(*) sessions,
       SUM(converted_whatsapp) whatsapps,SUM(converted_order) orders,
       ROUND(AVG(engaged_ms)/1000.0,1) avg_seconds
       FROM sessions WHERE started_at>=? AND is_bot=0 GROUP BY device ORDER BY sessions DESC`
    ).bind(since).all();
    const behavior = await env.DB.prepare(
      `SELECT CASE WHEN converted_whatsapp=1 THEN '点击WhatsApp' ELSE '未点击WhatsApp' END segment,
       COUNT(*) sessions,ROUND(AVG(engaged_ms)/1000.0,1) avg_seconds,
       ROUND(AVG(page_views),1) avg_pages,ROUND(AVG(max_scroll),1) avg_scroll
       FROM sessions WHERE started_at>=? AND is_bot=0 GROUP BY converted_whatsapp ORDER BY converted_whatsapp DESC`
    ).bind(since).all();
    const products = await env.DB.prepare(
      `SELECT sku,MAX(product_title) title,MAX(product_img) image,
       COUNT(DISTINCT CASE WHEN type='view' THEN COALESCE(NULLIF(session_id,''),vid) END) viewers,
       COUNT(DISTINCT CASE WHEN type='addcart' THEN COALESCE(NULLIF(session_id,''),vid) END) carts,
       COUNT(DISTINCT CASE WHEN type='whatsapp' THEN COALESCE(NULLIF(session_id,''),vid) END) whatsapps
       FROM events WHERE ts>=? AND is_bot=0 AND sku<>'' GROUP BY sku
       HAVING viewers>0 OR carts>0 OR whatsapps>0 ORDER BY viewers DESC LIMIT 50`
    ).bind(since).all();
    const quality = await env.DB.prepare(
      `SELECT COUNT(*) total_events,SUM(is_bot) bot_events,
       SUM(session_id='') legacy_events FROM events WHERE ts>=?`
    ).bind(since).first();
    const versions = await env.DB.prepare(
      `SELECT COALESCE(NULLIF(site_version,''),'anterior') version,
       COUNT(DISTINCT COALESCE(NULLIF(session_id,''),vid)) sessions,
       COUNT(DISTINCT CASE WHEN type='search' THEN COALESCE(NULLIF(session_id,''),vid) END) searchers,
       COUNT(DISTINCT CASE WHEN type='addcart' THEN COALESCE(NULLIF(session_id,''),vid) END) carts,
       COUNT(DISTINCT CASE WHEN type='checkout' THEN COALESCE(NULLIF(session_id,''),vid) END) checkouts,
       COUNT(DISTINCT CASE WHEN type='order' THEN COALESCE(NULLIF(session_id,''),vid) END) orders,
       ROUND(AVG(CASE WHEN type='search' THEN result_count END),1) avg_search_results
       FROM events WHERE ts>=? AND is_bot=0 GROUP BY version ORDER BY MAX(ts) DESC`
    ).bind(since).all();
    const costs = await env.DB.prepare(
      `SELECT campaign,SUM(spend) spend,SUM(impressions) impressions,SUM(ad_clicks) ad_clicks
       FROM campaign_costs WHERE day>=date(?/1000,'unixepoch') GROUP BY campaign`
    ).bind(since).all();
    const costMap = Object.fromEntries((costs.results||[]).map((x) => [x.campaign,x]));
    for (const row of channels.results||[]) {
      const c = costMap[row.channel] || {};
      row.spend = Number(c.spend)||0; row.impressions = Number(c.impressions)||0;
      row.ad_clicks = Number(c.ad_clicks)||0; row.cost_per_order = row.orders ? row.spend/row.orders : 0;
    }
    return json({ ok:true, days, funnel, channels:channels.results||[], devices:devices.results||[],
      behavior:behavior.results||[], products:products.results||[], versions:versions.results||[], quality });
  }

  if (sub === "campaign-cost" && req.method === "POST") {
    const b = await req.json().catch(() => ({}));
    if (!b.day || !b.campaign) return json({ error:"day_and_campaign_required" },400);
    await env.DB.prepare(
      `INSERT INTO campaign_costs(day,campaign,source,spend,impressions,ad_clicks) VALUES(?,?,?,?,?,?)
       ON CONFLICT(day,campaign,source) DO UPDATE SET spend=excluded.spend,
       impressions=excluded.impressions,ad_clicks=excluded.ad_clicks`
    ).bind(String(b.day).slice(0,10),String(b.campaign).slice(0,180),String(b.source||"").slice(0,120),
      Math.max(0,Number(b.spend)||0),Math.max(0,Number(b.impressions)||0),Math.max(0,Number(b.ad_clicks)||0)).run();
    return json({ok:true});
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
         (SELECT COUNT(*) FROM orders WHERE created_at>?) AS orders30,
         (SELECT COUNT(*) FROM orders WHERE status='pending') AS pending_orders,
         (SELECT COUNT(*) FROM coupons WHERE active=1) AS active_coupons`
    ).bind(since, since, since, since, since, since).first();
    return json({ ok: true, ...totals });
  }

  return json({ error: "unknown_admin_route" }, 404);
}
