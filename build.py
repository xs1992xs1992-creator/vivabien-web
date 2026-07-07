#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Caoba / VivaBien 静态站构建脚本
读取 data/products.csv → 生成 dist/ 整站（首页 + 每个商品详情页）
用法: python3 build.py
"""
import csv, os, re, html, shutil, unicodedata

# ============ 配置区（只需要改这里）============
WHATSAPP   = "18092811992"          # ← 改成你的 WhatsApp 号码（国家码+号码，不带+号）
PIXEL_ID   = "882086747967886"      # Meta Pixel
SITE_NAME  = "VivaBien"             # 品牌名
SITE_URL   = "https://vivabien.xyz" # 你的域名
CSV_PATH   = "data/products.csv"
IMG_DIR    = "images"               # 商品图片文件夹（VBxxxx.jpg 都放这里）
OUT_DIR    = "dist"
# ===============================================

# 分类 → 图标(emoji) 映射，新分类会自动用默认图标
CAT_ICONS = {
    "Electrónicos y Tecnología": "📱",
    "Cocina y Hogar": "🍳",
    "Belleza y Cuidado Personal": "✨",
    "Bebés y Maternidad": "🍼",
    "Decoración del Hogar": "🛋️",
    "Herramientas y Ferretería": "🔧",
    "Baño y Sanitarios": "🚿",
    "Papelería y Oficina": "✏️",
}
DEFAULT_ICON = "🛍️"

def parse_row(r):
    """按列名读取（DictReader 行），不再依赖列的位置和数量"""
    return dict(handle=r.get("Handle", ""), title=r.get("Title", ""),
                body=r.get("Body (HTML)", ""), type=r.get("Type", ""),
                published=r.get("Published", ""), sku=r.get("Variant SKU", ""),
                price=r.get("Variant Price", ""), img=r.get("Image Src", ""))

def load_products():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    seen, products = set(), []
    for r in rows:
        p = parse_row(r)
        if not p["title"].strip() or not p["handle"].strip():
            continue
        if p["handle"] in seen:              # 去重
            continue
        if p["published"].strip().upper() != "TRUE":
            continue
        seen.add(p["handle"])
        p["title"] = p["title"].strip()
        p["type"]  = p["type"].strip() or "Otros"
        p["price"] = float(p["price"]) if p["price"].strip() else None
        p["img"]   = p["img"].strip()
        products.append(p)
    # 有价格的排前面
    products.sort(key=lambda p: (p["price"] is None, p["type"]))
    return products

def fmt_price(v):
    return "RD$ {:,.0f}".format(v) if v is not None else "Consultar precio"

def esc(s):
    return html.escape(s, quote=True)

def body_html(raw):
    """商品描述：转义 + 换行转 <br>"""
    t = esc(raw.strip())
    return t.replace("\n", "<br>")

def wa_link(title):
    from urllib.parse import quote
    msg = quote(f"Hola! Me interesa: {title}")
    return f"https://wa.me/{WHATSAPP}?text={msg}"

# ---------- 通用 HTML 片段 ----------
FONT = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">"""

def pixel(extra=""):
    return f"""<script>
!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,
document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init','{PIXEL_ID}');fbq('track','PageView');{extra}
</script><noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id={PIXEL_ID}&ev=PageView&noscript=1"/></noscript>"""

# WhatsApp 图标 SVG（内联，无外部依赖）
WA_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.89-.79-1.49-1.77-1.66-2.07-.17-.3-.02-.46.13-.61.14-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.5s1.07 2.9 1.22 3.1c.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.76-.72 2-1.42.25-.7.25-1.3.18-1.42-.08-.13-.28-.2-.58-.35zM12.05 21.8h-.01a9.87 9.87 0 0 1-5.03-1.38l-.36-.21-3.74.98 1-3.65-.24-.37a9.82 9.82 0 0 1-1.51-5.26c0-5.44 4.43-9.87 9.89-9.87a9.8 9.8 0 0 1 6.99 2.9 9.8 9.8 0 0 1 2.89 6.98c0 5.45-4.43 9.88-9.88 9.88zm8.41-18.29A11.8 11.8 0 0 0 12.05 0C5.5 0 .16 5.33.16 11.89c0 2.1.55 4.14 1.59 5.94L.06 24l6.33-1.66a11.9 11.9 0 0 0 5.66 1.44h.01c6.55 0 11.89-5.33 11.89-11.88 0-3.18-1.24-6.16-3.49-8.4z"/></svg>'

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Plus Jakarta Sans',-apple-system,sans-serif;background:#F7F9FD;color:#16202E}
a{text-decoration:none;color:inherit}
img{display:block}
.wrap{max-width:1100px;margin:0 auto;padding:0 18px}
/* header */
.hd{background:#fff;border-bottom:1px solid #EEF1F6;position:sticky;top:0;z-index:50}
.hd-in{display:flex;align-items:center;justify-content:space-between;height:62px}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:20px;letter-spacing:-.03em}
.logo .ic{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#2563D9,#3b82f6);display:flex;align-items:center;justify-content:center;color:#fff;font-size:19px}
.hd-wa{display:flex;align-items:center;gap:7px;background:#25D366;color:#fff;font-weight:700;font-size:13px;padding:9px 16px;border-radius:99px}
/* hero */
.hero{margin:16px auto 4px;background:linear-gradient(120deg,#2563D9,#1A47A6);border-radius:22px;padding:28px 24px;color:#fff;position:relative;overflow:hidden}
.hero h1{font-weight:800;font-size:26px;line-height:1.15;letter-spacing:-.02em;max-width:340px}
.hero .sub{display:flex;align-items:center;gap:7px;margin-top:12px;font-weight:700;font-size:13px;color:#d3e0fb}
/* category chips */
.cats{display:flex;gap:8px;overflow-x:auto;padding:18px 0 6px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.cats::-webkit-scrollbar{display:none}
.chip{flex:none;display:flex;align-items:center;gap:6px;background:#fff;border:1.5px solid #E5EAF2;color:#5a6577;font-weight:600;font-size:12.5px;padding:9px 15px;border-radius:99px;cursor:pointer;white-space:nowrap}
.chip.on{background:#2563D9;border-color:#2563D9;color:#fff}
/* grid */
.count{font-size:13px;color:#8a93a2;margin:10px 0 12px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:13px;padding-bottom:60px}
@media(min-width:640px){.grid{grid-template-columns:repeat(3,1fr)}}
@media(min-width:920px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{background:#fff;border:1px solid #EDF1F7;border-radius:18px;overflow:hidden;box-shadow:0 4px 14px rgba(20,40,80,.05);transition:transform .15s}
.card:hover{transform:translateY(-3px)}
.card .imgbox{position:relative;aspect-ratio:1;background:#F0F3F8}
.card img{width:100%;height:100%;object-fit:cover}
.badge{position:absolute;top:9px;left:9px;background:#EAF0FB;color:#2563D9;font-size:10px;font-weight:800;padding:3px 8px;border-radius:99px}
.card .info{padding:11px 12px 13px}
.card .nm{font-weight:700;font-size:12.5px;line-height:1.3;height:33px;overflow:hidden}
.card .pr{display:flex;align-items:center;justify-content:space-between;margin-top:8px}
.card .pr b{font-weight:800;font-size:16px}
.card .pr .ask{font-weight:700;font-size:12px;color:#FF6B4A}
/* detail */
.dt{max-width:920px;margin:0 auto;padding:0 0 90px}
@media(min-width:760px){.dt{display:grid;grid-template-columns:1fr 1fr;gap:28px;padding:26px 18px 40px;align-items:start}}
.dt .pic{background:#F0F3F8}
@media(min-width:760px){.dt .pic{border-radius:22px;overflow:hidden;position:sticky;top:80px}}
.dt .pic img{width:100%;aspect-ratio:1;object-fit:cover}
.panel{background:#fff;border-radius:24px 24px 0 0;margin-top:-22px;position:relative;padding:22px 20px 16px}
@media(min-width:760px){.panel{border-radius:22px;margin-top:0;border:1px solid #EDF1F7}}
.panel h1{font-weight:800;font-size:21px;line-height:1.25;margin-bottom:12px;letter-spacing:-.02em}
.price{font-weight:800;font-size:30px;letter-spacing:-.02em;margin-bottom:16px}
.price.ask{font-size:22px;color:#FF6B4A}
.trust{display:flex;justify-content:space-between;background:#F7F9FD;border:1px solid #EDF1F7;border-radius:18px;padding:16px 8px;margin-bottom:20px}
.trust>div{display:flex;flex-direction:column;align-items:center;gap:6px;flex:1;font-size:11px;font-weight:700;text-align:center}
.trust>div+div{border-left:1px solid #E5EAF2}
.trust .em{font-size:20px}
.sec{font-weight:800;font-size:15px;margin-bottom:8px}
.desc{font-size:13px;color:#3a4250;line-height:1.65;margin-bottom:18px}
/* action bar */
.bar{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #EEF1F6;padding:12px 16px calc(14px + env(safe-area-inset-bottom));display:flex;gap:12px;z-index:60}
@media(min-width:760px){.bar{position:static;border:0;padding:0;background:transparent}}
.btn-wa{flex:1;display:flex;align-items:center;justify-content:center;gap:9px;background:#25D366;color:#fff;font-weight:800;font-size:16px;height:52px;border-radius:16px;cursor:pointer}
.btn-back{flex:none;width:54px;height:52px;border:2px solid #2563D9;border-radius:16px;display:flex;align-items:center;justify-content:center;color:#2563D9;font-size:20px}
.crumb{padding:14px 18px 0;font-size:13px;color:#8a93a2}
.crumb a{color:#2563D9;font-weight:700}
footer{text-align:center;font-size:12px;color:#9aa3b2;padding:26px 0 34px}
"""

def page(title, body, pixel_extra="", desc=""):
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc[:150])}">
{FONT}
<style>{CSS}</style>
{pixel(pixel_extra)}
</head><body>
{body}
<footer>© {SITE_NAME} · Envíos en toda República Dominicana · Pago contra entrega</footer>
</body></html>"""

def header(rel=""):
    return f"""<div class="hd"><div class="wrap hd-in">
<a class="logo" href="{rel}index.html"><span class="ic">{SITE_NAME[0]}</span>{esc(SITE_NAME)}</a>
<a class="hd-wa" href="https://wa.me/{WHATSAPP}" target="_blank" onclick="fbq('track','Contact')">{WA_SVG} WhatsApp</a>
</div></div>"""

def build():
    products = load_products()
    cats = sorted({p["type"] for p in products})
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(f"{OUT_DIR}/producto", exist_ok=True)
    if os.path.isdir(IMG_DIR):
        # 跳过原图和价格截图：网站用不到，且不应公开
        shutil.copytree(IMG_DIR, f"{OUT_DIR}/images",
                        ignore=shutil.ignore_patterns("*_original*", "*_price_crop*", ".*"))
    else:
        os.makedirs(f"{OUT_DIR}/images", exist_ok=True)
        print(f"⚠️  未找到 {IMG_DIR}/ 文件夹，图片将显示为占位背景")

    # ---- 商品卡 ----
    cards = []
    for p in products:
        price_html = (f'<b>{fmt_price(p["price"])}</b>' if p["price"] is not None
                      else '<span class="ask">Consultar</span>')
        cards.append(f"""<a class="card" data-cat="{esc(p['type'])}" href="producto/{p['handle']}.html">
<div class="imgbox"><img src="images/{esc(p['img'])}" alt="{esc(p['title'])}" loading="lazy"
 onerror="this.style.display='none'"><span class="badge">{esc(p['type'])}</span></div>
<div class="info"><div class="nm">{esc(p['title'])}</div>
<div class="pr">{price_html}</div></div></a>""")

    chips = ['<div class="chip on" data-cat="*">Todos</div>'] + [
        f'<div class="chip" data-cat="{esc(c)}">{CAT_ICONS.get(c, DEFAULT_ICON)} {esc(c)}</div>' for c in cats]

    home_body = f"""{header()}
<div class="wrap">
<div class="hero"><h1>Compra fácil, paga seguro</h1>
<div class="sub">🛡️ Pago contra entrega · Envíos a todo el país</div></div>
<div class="cats">{''.join(chips)}</div>
<div class="count"><span id="n">{len(products)}</span> productos</div>
<div class="grid" id="grid">{''.join(cards)}</div>
</div>
<script>
document.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{{
 document.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));
 ch.classList.add('on');const cat=ch.dataset.cat;let n=0;
 document.querySelectorAll('.card').forEach(cd=>{{
  const show=cat==='*'||cd.dataset.cat===cat;cd.style.display=show?'':'none';if(show)n++;}});
 document.getElementById('n').textContent=n;}});
</script>"""
    with open(f"{OUT_DIR}/index.html", "w", encoding="utf-8") as f:
        f.write(page(f"{SITE_NAME} — Tienda online RD", home_body,
                     desc="Hogar, electrónica y más. Pago contra entrega en República Dominicana."))

    # ---- 详情页 ----
    for p in products:
        price_html = (f'<div class="price">{fmt_price(p["price"])}</div>' if p["price"] is not None
                      else '<div class="price ask">Consultar precio por WhatsApp</div>')
        desc_html = body_html(p["body"]) if len(p["body"].strip()) > 10 else esc(p["title"])
        safe_name = esc(p["title"])  # esc已把引号转义,JS字符串安全
        ve = (f"""fbq('track','ViewContent',{{content_ids:['{p["sku"]}'],content_name:'{safe_name}',content_type:'product',value:{p["price"] or 0},currency:'DOP'}});""")
        detail = f"""{header("../")}
<div class="crumb"><a href="../index.html">← {esc(SITE_NAME)}</a> / {esc(p['type'])}</div>
<div class="dt">
<div class="pic"><img src="../images/{esc(p['img'])}" alt="{esc(p['title'])}" onerror="this.style.opacity=0"></div>
<div>
<div class="panel">
<h1>{esc(p['title'])}</h1>
{price_html}
<div class="trust">
<div><span class="em">🚚</span>Envío a<br>todo el país</div>
<div><span class="em">🤝</span>Pago contra<br>entrega</div>
<div><span class="em">✅</span>Producto<br>verificado</div>
</div>
<div class="sec">Descripción</div>
<div class="desc">{desc_html}</div>
<div class="bar">
<a class="btn-back" href="../index.html">←</a>
<a class="btn-wa" href="{wa_link(p['title'])}" target="_blank"
 onclick="fbq('track','Contact',{{content_ids:['{p["sku"]}']}})">{WA_SVG} Pedir por WhatsApp</a>
</div>
</div>
</div>
</div>"""
        with open(f"{OUT_DIR}/producto/{p['handle']}.html", "w", encoding="utf-8") as f:
            f.write(page(f"{p['title']} — {SITE_NAME}", detail, pixel_extra=ve, desc=p["body"][:150]))

    print(f"✅ 构建完成: {len(products)} 个商品, {len(cats)} 个分类 → {OUT_DIR}/")
    print(f"   首页: {OUT_DIR}/index.html")
    print(f"   详情页: {OUT_DIR}/producto/ ({len(products)} 页)")

if __name__ == "__main__":
    build()
