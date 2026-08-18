#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VivaBien 静态站构建脚本
读取 data/products.csv → 生成 dist/ 整站（首页 + 商品详情页 + 购物车结算页）
用法: python3 build.py
"""
import csv, os, re, html, json, shutil, unicodedata, hashlib
from datetime import date
from urllib.parse import quote

# ============ 配置区（只需要改这里）============
WHATSAPP   = "18092811992"          # WhatsApp 号码（国家码+号码，不带+号）
PIXEL_ID   = "882086747967886"      # Meta Pixel
SITE_NAME  = "VivaBien"             # 品牌名
SITE_URL   = "https://vivabien.xyz" # 你的域名
API_BASE   = "https://vivabien.xyz" # 边缘后端（Worker）同域：/s/* 短链、/api/* 埋点/优惠券
CSV_PATH   = "data/products.csv"
IMG_DIR    = "images"               # 商品图片文件夹（VBxxxx.jpg 都放这里）
OUT_DIR    = "dist"
SITE_VERSION = "cro1-20260713"
META_DOP_PER_USD = float(os.environ.get("VIVABIEN_META_DOP_PER_USD", "59.20"))
REVIEWS_PATH = "data/reviews.json"
FEATURED_PATH = "data/featured.json"
HOME_PRIORITY_PATH = "data/home_priority.json"   # 首页商品网格优先展示的 SKU（运营可改）
SOCIAL_PATH = "data/social.json"                 # 推广落地页 /enlaces.html 配置
DETAIL_ROLLOUT_PATH = "data/product_detail_rollout.json"
STORES_PATH = "data/stores.json"
PANELS_PATH = "data/panels.json"
ADHESIVE_PANEL_PATH = "data/adhesive_panel.json"
REPORT_DIR = "reports"

# 银行转账收款账户（结算页展示）
BANKS = [
    ("Banco Popular", "820011674",   "Corner Store"),
    ("Banco BHD",     "39058710013", "Wenwen Shi"),
    ("Banreservas",   "9607180504",  "Weixiong Chen"),
]

# ===============================================

# ---------- 多级分类：大组 ----------
GROUPS = {
    "Belleza y Cuidado Personal": "Belleza y Salud",
    "Cocina y Hogar":             "Cocina y Electrohogar",
    "Decoración del Hogar":       "Hogar",
    "Baño y Sanitarios":          "Hogar",
    "Electrónicos y Tecnología":  "Tecnología",
    "Herramientas y Ferretería":  "Ferretería",
    "Bebés y Maternidad":         "Bebés y Niños",
    "Juguetes y Juegos":          "Bebés y Niños",
    "Papelería y Oficina":        "Más categorías",
    "Artículos para Adultos":     "Más categorías",
    "Otros":                      "Más categorías",
}
GROUP_ORDER = ["Belleza y Salud", "Hogar", "Cocina y Electrohogar", "Ferretería",
               "Tecnología", "Bebés y Niños", "Más categorías"]
GROUP_ICONS = {"Belleza y Salud": "✨", "Hogar": "🏠", "Cocina y Electrohogar": "🍳",
               "Ferretería": "🔧", "Tecnología": "📱",
               "Bebés y Niños": "🍼", "Más categorías": "🛍️"}

# ---------- 多级分类：子分类关键词规则（按标题匹配，顺序优先） ----------
SUBRULES = {
    "Belleza y Salud": [
        ("Pestañas y Cejas",      ['pestañ', 'ceja']),
        ("Uñas",                  ['uña', 'manicura', 'esmalte', 'nail', 'acrilic', 'sticker', 'calcomania']),
        ("Cuidado de Pies",       ['pies', 'pomez', 'callo', 'pedicur', 'talon']),
        ("Cuidado del Cabello",   ['cabello', 'pelo', 'peluca', 'rizador', 'trenza', 'peine',
                                   'diadema', 'moño', 'turbante', 'secador', 'lazo', 'scrunchie',
                                   'shampoo', 'champu', 'acondicionador']),
        ("Maquillaje",            ['maquillaje', 'labial', 'brocha', 'sombra', 'delineador', 'paleta',
                                   'rubor', 'corrector', 'cosmetiquera', 'gloss', 'esponja de maquillaje']),
        ("Cuidado Facial",        ['mascarilla facial', 'facial', 'rostro', 'cara', 'serum', 'acne',
                                   'agua micelar', 'desmaquillante', 'protector solar', 'parche de ojos',
                                   'contorno de ojos', 'crema blanqueadora']),
        ("Cuidado Corporal",      ['crema corporal', 'locion', 'body lotion', 'manteca corporal', 'exfoliante',
                                   'hidratante corporal', 'aceite corporal', 'colageno', 'masaje']),
        ("Depilación y Afeitado", ['afeita', 'rasurad', 'rastrillo', 'depila', 'cera depilatoria']),
        ("Perfumes y Fragancias", ['perfume', 'colonia', 'fragancia', 'body mist']),
        ("Higiene Personal",      ['diente', 'dental', 'jabon', 'desodorante', 'hisopo', 'algodon',
                                   'toallitas', 'oido', 'cortauña', 'talco', 'alcohol', 'antibacterial',
                                   'antimicrobiano', 'depresor', 'enjuague bucal']),
        ("Cuidado de la Piel",    ['mascarilla', 'crema', 'hidratante', 'limpiador', 'parche']),
    ],
    "Hogar": [
        ("Muebles",                ['mesa de noche', 'estante', 'aparador', 'escritorio', 'mueble auxiliar',
                                    'mesa de centro', 'juego de mesas', 'mesas nido', 'mesa infantil',
                                    'silla colgante', 'tocador', 'mesa auxiliar', 'banco de']),
        ("Plantas y Flores",      ['planta', 'flor artificial', 'rama decorativa', 'macetero', 'jardinera']),
        ("Espejos, Marcos y Cuadros", ['espejo', 'cuadro', 'marco', 'portarretrato', 'foto']),
        ("Aromas para el Hogar",  ['vela', 'difusor', 'aceite esencial', 'esencia', 'ambientador', 'aromatic']),
        ("Iluminación Decorativa", ['lampara decorativa', 'luz decorativa', 'guirnalda de luz', 'luces decorativas']),
        ("Figuras y Esculturas",  ['figura decorativa', 'estatua', 'escultura', 'oso decorativo', 'osito decorativo',
                                   'elefante decorativo', 'piña decorativa', 'pera decorativa', 'mariposa decorativa']),
        ("Bandejas y Centros de Mesa", ['bandeja', 'charola', 'centro de mesa', 'plato decorativo']),
        ("Letreros y Adhesivos",  ['letrero', 'cartel', 'numero adhesivo', 'numeros adhesivos', 'letra adhesiva',
                                   'letras autoadhesivas', 'pegatina de pared', 'calcomania de pared']),
        ("Libros y Revistas Decorativas", ['libro decorativo', 'libros decorativos', 'revista decorativa']),
        ("Baño",                  ['baño', 'ducha', 'jabonera', 'inodoro', 'toalla', 'banera',
                                   'destapador', 'papel higienico', 'desague', 'trampa', 'lavamanos']),
        ("Organización",          ['organizador', 'estante', 'repisa', 'gancho', 'colgador', 'cesta',
                                   'perchero', 'zapatero', 'armario', 'closet', 'almacenamiento', 'caja']),
        ("Limpieza",              ['trapeador', 'escoba', 'limpieza', 'limpiador', 'guante',
                                   'zafacon', 'basura', 'plumero', 'cepillo', 'abrillantador']),
        ("Cama y Textiles",       ['sabana', 'almohada', 'cobija', 'manta', 'edredon', 'cojin', 'funda',
                                   'mosquitero', 'tul', 'pabellon']),
        ("Cortinas y Alfombras",  ['tapete', 'alfombra', 'cortina']),
        ("Relojes de Pared",      ['reloj de pared']),
        ("Adornos Decorativos",   ['florero', 'adorno', 'decorativ', 'decoracion', 'guirnalda', 'jarron',
                                   'bandeja decorativa', 'charola decorativa', 'numero', 'letra', 'letrero']),
    ],
    "Cocina y Electrohogar": [
        ("Muebles de Cocina",      ['mueble auxiliar de cocina', 'aparador', 'gabinete de cocina']),
        ("Estufas y Hornillas",    ['estufa', 'fogón', 'fogon', 'hornilla']),
        ("Ollas, Sartenes y Calderos", ['olla', 'sarten', 'caldero', 'cazo']),
        ("Utensilios de Cocina",  ['cuchillo', 'tabla de picar', 'rallador', 'colador', 'exprimidor',
                                   'abrelatas', 'molde', 'batidor', 'espatula', 'cucharon', 'pelador',
                                   'picador', 'majador', 'pinza de cocina']),
        ("Vajilla y Cubiertos",   ['plato', 'cubierto', 'cuchara', 'tenedor', 'vajilla']),
        ("Vasos, Tazas y Botellas", ['taza', 'vaso', 'termo', 'botella', 'jarra', 'greca']),
        ("Organización de Cocina", ['recipiente', 'hermetico', 'dispensador', 'especias', 'huevo',
                                    'organizador de cocina', 'porta']),
        ("Dispensadores de Agua",  ['bomba de agua usb', 'bomba manual para agua', 'botellon', 'botellón']),
        ("Básculas de Cocina",     ['bascula', 'báscula', 'pesa alimentos', 'pesa electronica']),
        ("Pequeños Electrodomésticos", ['waflera', 'waffle', 'sanduchera', 'sandwichera', 'freidora',
                                   'hornilla', 'parrilla electrica', 'cafetera', 'licuadora', 'hervidor',
                                   'procesador de alimentos', 'batidora', 'tostadora', 'maquina de',
                                   'maquina para', 'donut', 'dona', 'barquillo']),
        ("Climatización",         ['ventilador', 'abanico', 'humidificador', 'calentador']),
    ],
    "Ferretería": [
        ("Herramientas Eléctricas", ['taladro', 'pulidora', 'amoladora', 'soldador', 'soldadura',
                                     'pistola de calor', 'esmeril', 'rotomartillo', 'sierra electrica',
                                     'bomba de agua', 'motobomba', 'tester', 'probador']),
        ("Plomería y Grifería",     ['grifo', 'manguera', 'llave de agua', 'llave de fregadero',
                                     'llave de cocina', 'valvula', 'tuberia', 'conector', 'rociador',
                                     'regadera', 'filtro de agua', 'fregadero']),
        ("Electricidad",            ['regleta', 'extension', 'enchufe', 'interruptor', 'cable', 'bombillo',
                                     'foco', 'voltaje', 'toma corriente', 'tomacorriente', 'switch', 'socket',
                                     'portalampara', 'conexiones electricas', 'linterna']),
        ("Tornillos y Herrajes",    ['tornillo', 'screw', 'perno', 'varilla roscada', 'arandela', 'clavo',
                                     'abrazadera', 'tirrap', 'zip tie', 'tiras plasticas', 'bisagra', 'gozne',
                                     'charnela', 'gancho', 'separadores']),
        ("Pintura",                 ['pintura', 'spray', 'aerosol', 'terebentina', 'aguarras', 'brocha', 'rolo']),
        ("Pegamentos y Selladores", ['silicon', 'sellador', 'impermeabiliz', 'pega ', 'pegamento',
                                     'teflon', 'cinta adhesiva', 'cinta doble cara', 'tape doble cara', 'adhesiv']),
        ("Cerraduras y Seguridad",  ['candado', 'cerradura', 'cadena de seguridad', 'pestillo', 'cerrojo',
                                     'tranca', 'cono', 'señal']),
        ("Jardinería",              ['jardin', 'rastrillo', 'pala', 'manguera de jardin', 'tijera de podar']),
        ("Protección Personal",     ['guante de trabajo', 'lente de seguridad', 'casco', 'mascarilla de proteccion']),
        ("Cuchillas y Corte",       ['cuchilla', 'exacto', 'cortador', 'raspador']),
        ("Accesorios para Vehículos", ['carro', 'vehiculo', 'vehículo', 'limpiaparabrisas', 'guardalodo',
                                      'matricula', 'matrícula', 'parqueo', 'inflador portátil']),
        ("Herramientas Manuales",   ['destornillador', 'martillo', 'alicate', 'llave inglesa', 'llave de tubo',
                                     'cinta metrica', 'nivel', 'sierra', 'lima', 'juego de herramientas',
                                     'navaja', 'multiherramienta', 'remachadora', 'allen', 'broca', 'tijera',
                                     'espatula', 'rasqueta', 'disco de corte', 'hoja diamantada',
                                     'kit de herramientas']),
    ],
    "Tecnología": [
        ("Audio",                   ['audifono', 'bocina', 'speaker', 'microfono', 'radio', 'karaoke']),
        ("Cables y Cargadores",      ['cargador', 'cable usb', 'tipo c', 'type-c', 'lightning', 'adaptador usb',
                                      'carga rapida']),
        ("Cables de Audio y Video", ['cable de audio', 'cable auxiliar', 'hdmi', 'vga']),
        ("Computación y Periféricos", ['mouse', 'raton', 'ratón', 'teclado', 'mousepad', 'memoria usb']),
        ("Accesorios para Celulares", ['celular', 'forro', 'protector de pantalla', 'manos libres']),
        ("Soportes para Celulares",  ['soporte de celular', 'soporte para celular', 'tripode', 'selfie']),
        ("Energía y Protección",    ['power bank', 'bateria portatil', 'bateria recargable', 'pila', 'ups',
                                     'protector de voltaje', 'regleta', 'tomacorriente', 'toma corriente']),
        ("Adaptadores y Controles", ['adaptador', 'control remoto']),
        ("Relojes y Smartwatch",     ['reloj', 'smartwatch']),
        ("Iluminación",             ['led', 'lampara', 'luz', 'tira de luces', 'proyector']),
    ],
    "Bebés y Niños": [
        ("Juguetes",                ['juguete', 'juego', 'peluche', 'muñec', 'rompecabezas', 'bloques']),
        ("Alimentación del Bebé",   ['biberon', 'tetera', 'chupon', 'comida de bebe', 'procesador', 'babero']),
        ("Pañales y Cambio",        ['pañal', 'cambiador', 'toallitas para bebe']),
        ("Baño y Cuidado del Bebé", ['shampoo para bebe', 'champu para bebe', 'jabon para bebe',
                                      'aceite para bebe', 'talco para bebe', 'crema para bebe', 'baño de bebe',
                                      'bebe', 'bebé', 'infantil']),
        ("Dormitorio y Seguridad",  ['cuna', 'mosquitero para bebe', 'protector', 'luz nocturna', 'lampara infantil']),
    ],
}
SUB_DEFAULT = {"Belleza y Salud": "Accesorios de Belleza", "Hogar": "Otros para el Hogar",
               "Cocina y Electrohogar": "Otros de Cocina", "Ferretería": "Otros de Ferretería",
               "Tecnología": "Otros de Tecnología",
               "Bebés y Niños": "Cuidado del Bebé", "Más categorías": "Otros"}

def norm(s):
    """小写 + 去重音（保留 ñ）——分类规则用"""
    s = s.lower().replace('ñ', '\x01')
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s.replace('\x01', 'ñ')

def snorm(s):
    """小写 + 全部去重音（ñ→n）——搜索匹配用，客人不打重音也能搜到"""
    s = s.lower()
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def classify(p):
    """返回 (大组, 子分类)"""
    t = norm(p["title"])
    group = GROUPS.get(p["type"], "Más categorías")
    # Corrige errores fuertes del tipo fuente usando la intención de compra.
    if any(k in t for k in ("reloj de pared", "cuadro decorativo", "espejo decorativo")):
        group = "Hogar"
    elif any(k in t for k in ("grifo", "llave de agua", "llave de fregadero", "regulador de gas")):
        group = "Ferretería"
    if group == "Más categorías":
        return group, (p["type"] if p["type"] in GROUPS else "Otros")
    # 当上游类型过宽时，按消费者用途修正到更符合本地零售习惯的大类。
    if group == "Tecnología" and any(k in t for k in (
            "ventilador", "abanico", "licuadora", "hervidor", "cafetera", "freidora",
            "sandwichera", "waflera", "batidora", "aspiradora", "plancha electrica")):
        group = "Cocina y Electrohogar"
    for sub, kws in SUBRULES.get(group, []):
        for kw in kws:
            if kw in t:
                return group, sub
    return group, SUB_DEFAULT[group]

def parse_row(r):
    return dict(handle=r.get("Handle", ""), title=r.get("Title", ""),
                body=r.get("Body (HTML)", ""), type=r.get("Type", ""),
                published=r.get("Published", ""), sku=r.get("Variant SKU", ""),
                price=r.get("Variant Price", ""), img=r.get("Image Src", ""),
                inventory=r.get("Variant Inventory Qty", ""),
                old_price=r.get("precio_anterior") or "",
                label=r.get("etiqueta") or "", featured=r.get("destacado") or "")

# ---------- 图片类型体系（方案B，与上游 vivabien.py TIPO_ORDER 一致） ----------
# 展示顺序（用户定）：场景效果图 → 白底图 → 正面 → 背面 → 细节 → 补充 → 尺寸图
TIPO_ORDER = ["scene", "white", "front", "back", "detail", "extra", "dim", "3d"]

def img_tipo(fname, tag=""):
    """图片类型：CSV 附加行 Tags 显式标签优先，否则按文件名后缀猜（老数据兜底）。"""
    if tag in TIPO_ORDER:
        return tag
    s = fname.lower()
    if s.endswith("_scene.jpg"): return "scene"
    if s.endswith("_dim.jpg"):   return "dim"
    if re.search(r"_[2-9]\.jpg$", s): return "extra"
    return "white"

def product_gallery(p):
    """商品完整画廊（有序文件名列表）：
    显式清单（CSV 附加行，Tags=类型）∪ 传统命名兜底（老数据没有附加行），
    去重后按 TIPO_ORDER 排序。卡片图 = 第一张。"""
    sku = p["sku"].strip()
    seen, typed = set(), []
    def add(f, tipo):
        if f and f not in seen and os.path.isfile(os.path.join(IMG_DIR, f)):
            seen.add(f); typed.append((f, tipo))
    if p["img"]:
        add(p["img"], img_tipo(p["img"]))
    for f, tag in p.get("extras", []):
        add(f, img_tipo(f, tag))
    if sku:   # 命名约定兜底
        add(f"{sku}_scene.jpg", "scene")
        add(f"{sku}.jpg", "white")
        for i in range(2, 10):
            add(f"{sku}_{i}.jpg", "extra")
        add(f"{sku}_dim.jpg", "dim")
    typed.sort(key=lambda x: TIPO_ORDER.index(x[1]) if x[1] in TIPO_ORDER else 98)
    return [f for f, _ in typed]

def load_products():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # 多图附加行：无标题、有 Handle+Image Src；Tags 列 = 图片类型（方案B）
    extras = {}
    for r in rows:
        h   = (r.get("Handle") or "").strip()
        img = (r.get("Image Src") or "").strip()
        if h and img and not (r.get("Title") or "").strip():
            extras.setdefault(h, []).append((img, (r.get("Tags") or "").strip()))
    seen, products = set(), []
    for r in rows:
        p = parse_row(r)
        if not p["title"].strip() or not p["handle"].strip():
            continue
        if p["handle"] in seen:
            continue
        if p["published"].strip().upper() != "TRUE":
            continue
        seen.add(p["handle"])
        p["title"] = p["title"].strip()
        p["type"]  = p["type"].strip() or "Otros"
        p["price"] = float(p["price"]) if p["price"].strip() else None
        raw_old = str(p.get("old_price", "")).strip()
        p["old_price"] = float(raw_old) if re.fullmatch(r"\d+(?:\.\d+)?", raw_old) else None
        if p["price"] is None or p["old_price"] is None or p["old_price"] <= p["price"]:
            p["old_price"] = None
        p["label"] = str(p.get("label", "")).strip()[:24]
        p["featured"] = str(p.get("featured", "")).strip().lower() in {"1", "true", "si", "sí", "yes", "x"}
        raw_inventory = str(p.get("inventory", "")).strip()
        p["inventory"] = int(raw_inventory) if re.fullmatch(r"-?\d+", raw_inventory) else None
        p["img"]   = p["img"].strip()
        p["extras"] = extras.get(p["handle"], [])
        # 卡片图 = 画廊第一张（有场景图先场景图，用户规则）
        gal = product_gallery(p)
        if gal:
            p["img"] = gal[0]
        p["group"], p["sub"] = classify(p)
        products.append(p)
    # 首页优先曝光：home_priority.json 里的 SKU 排最前（按文件里的顺序），其余照旧
    prio = load_json(HOME_PRIORITY_PATH, {})
    if isinstance(prio, dict):
        prio = prio.get("skus", [])
    rank = {str(s).strip(): i for i, s in enumerate(prio) if str(s).strip()}
    products.sort(key=lambda p: (rank.get(p["sku"], 10**6),
                                 p["price"] is None, p["group"], p["sub"]))
    return products

def fmt_price(v):
    return "RD$ {:,.0f}".format(v) if v is not None else "Consultar precio"

def discount_info(p):
    old, current = p.get("old_price"), p.get("price")
    if old is None or current is None or old <= current:
        return None
    saving = old - current
    return {"saving": saving, "percent": max(1, round(saving / old * 100))}

def load_json(path, default):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value
    except (OSError, ValueError):
        return default

def esc(s):
    return html.escape(s, quote=True)

def public_url(path=""):
    """Return the canonical URL Cloudflare serves after its HTML redirect."""
    path = str(path or "").lstrip("/")
    if path in {"", "index.html"}:
        return f"{SITE_URL}/"
    if path.endswith(".html"):
        path = path[:-5]
    return f"{SITE_URL}/{quote(path, safe='/')}"

def plain_text(raw):
    text = re.sub(r"<[^>]+>", " ", str(raw or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()

def product_meta_description(p):
    """Use product-specific source copy before the shared purchase context."""
    detail = plain_text(p.get("body", ""))
    text = f'{p["title"]}. '
    if detail and snorm(detail) != snorm(p["title"]):
        text += detail + " "
    if p.get("price") is not None:
        text += f'Precio {fmt_price(p["price"])}. '
    text += "Compra online en República Dominicana."
    return text[:157].rstrip(" ,.;") + "."

def write_merchant_candidates(products, limit=100):
    """Create a private review list; this is intentionally not a publishable feed."""
    rows = []
    excluded = {"adult_category": 0, "missing_price": 0, "unknown_stock": 0,
                "missing_image": 0, "short_description": 0}
    for p in products:
        description = plain_text(p.get("body", ""))
        gallery = product_gallery(p)
        reasons = []
        if p.get("type") == "Artículos para Adultos":
            reasons.append("adult_category")
        if p.get("price") is None:
            reasons.append("missing_price")
        if p.get("inventory") is None or p["inventory"] <= 0:
            reasons.append("unknown_stock")
        if not gallery:
            reasons.append("missing_image")
        if len(description) < 80:
            reasons.append("short_description")
        for reason in reasons:
            excluded[reason] += 1
        score = min(len(description), 500) / 25
        score += 20 if p.get("price") is not None else 0
        score += 20 if p.get("inventory") is not None and p["inventory"] > 0 else 0
        score += 20 if gallery else 0
        score += min(len(gallery), 5) * 4
        rows.append({
            "score": round(score, 1), "eligible": not reasons, "blockers": ",".join(reasons),
            "sku": p["sku"], "handle": p["handle"], "title": p["title"],
            "category": p["group"], "subcategory": p["sub"], "price_dop": p["price"],
            "inventory": p["inventory"], "image_count": len(gallery),
            "description_chars": len(description), "link": public_url(f"producto/{p['handle']}.html"),
            "brand": "", "gtin": "", "mpn": "",
            "identifier_status": "needs_business_confirmation",
        })
    candidates = sorted((r for r in rows if r["eligible"]),
                        key=lambda r: (-r["score"], r["title"]))[:limit]
    os.makedirs(REPORT_DIR, exist_ok=True)
    fields = ["rank", "score", "sku", "handle", "title", "category", "subcategory",
              "price_dop", "inventory", "image_count", "description_chars", "link",
              "brand", "gtin", "mpn", "identifier_status"]
    with open(os.path.join(REPORT_DIR, "merchant_candidates.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for rank, row in enumerate(candidates, 1):
            writer.writerow({key: (rank if key == "rank" else row[key]) for key in fields})
    report = {
        "generated_on": date.today().isoformat(), "catalog_products": len(products),
        "eligible_before_identifier_review": sum(r["eligible"] for r in rows),
        "selected_candidates": len(candidates), "excluded_counts": excluded,
        "publish_blocker": "Confirm brand, GTIN or MPN for each candidate before creating the Merchant Center feed.",
    }
    with open(os.path.join(REPORT_DIR, "merchant_audit.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report

def body_html(raw):
    t = esc(raw.strip())
    return t.replace("\n", "<br>")

def product_measurements(p):
    """从现有标题和特点中提取可确认的尺寸/容量，不猜测缺失信息。"""
    text = re.sub(r"<[^>]+>", " ", f'{p.get("title", "")} {p.get("body", "")}')
    hits = re.findall(
        r"\b\d+(?:[.,]\d+)?\s?(?:mm|cm|kg|ml|oz|fl\.?\s?oz|pulgadas?|unidades?|metros?|litros?|[glm])\b",
        text, flags=re.I)
    out = []
    for hit in hits:
        cleaned = re.sub(r"\s+", " ", hit.strip())
        if cleaned.lower() not in {x.lower() for x in out}:
            out.append(cleaned)
    return " · ".join(out[:4])

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

WA_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.89-.79-1.49-1.77-1.66-2.07-.17-.3-.02-.46.13-.61.14-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.5s1.07 2.9 1.22 3.1c.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.76-.72 2-1.42.25-.7.25-1.3.18-1.42-.08-.13-.28-.2-.58-.35zM12.05 21.8h-.01a9.87 9.87 0 0 1-5.03-1.38l-.36-.21-3.74.98 1-3.65-.24-.37a9.82 9.82 0 0 1-1.51-5.26c0-5.44 4.43-9.87 9.89-9.87a9.8 9.8 0 0 1 6.99 2.9 9.8 9.8 0 0 1 2.89 6.98c0 5.45-4.43 9.88-9.88 9.88zm8.41-18.29A11.8 11.8 0 0 0 12.05 0C5.5 0 .16 5.33.16 11.89c0 2.1.55 4.14 1.59 5.94L.06 24l6.33-1.66a11.9 11.9 0 0 0 5.66 1.44h.01c6.55 0 11.89-5.33 11.89-11.88 0-3.18-1.24-6.16-3.49-8.4z"/></svg>'
BAG_SVG = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>'

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Plus Jakarta Sans',-apple-system,sans-serif;background:#F7F9FD;color:#16202E}
a{text-decoration:none;color:inherit}
img{display:block}
button{font-family:inherit}
.wrap{max-width:1100px;margin:0 auto;padding:0 18px}
/* header */
.hd{background:#fff;border-bottom:1px solid #EEF1F6;position:sticky;top:0;z-index:50}
.hd-in{display:flex;align-items:center;justify-content:space-between;height:62px}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:20px;letter-spacing:-.03em}
.logo .ic{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#2563D9,#3b82f6);display:flex;align-items:center;justify-content:center;color:#fff;font-size:19px}
.hd-r{display:flex;align-items:center;gap:10px}
.hd-wa{display:flex;align-items:center;gap:7px;background:#25D366;color:#fff;font-weight:700;font-size:13px;padding:9px 16px;border-radius:99px}
.hd-cart{position:relative;display:flex;align-items:center;justify-content:center;width:42px;height:42px;border:1.5px solid #E5EAF2;border-radius:13px;color:#2563D9;background:#fff}
.cart-n{position:absolute;top:-6px;right:-6px;background:#FF6B4A;color:#fff;font-size:10px;font-weight:800;min-width:18px;height:18px;border-radius:99px;display:none;align-items:center;justify-content:center;padding:0 4px}
/* hero */
.hero{margin:16px auto 4px;background:linear-gradient(120deg,#2563D9,#1A47A6);border-radius:22px;padding:28px 24px;color:#fff;position:relative;overflow:hidden}
.hero h1{font-weight:800;font-size:26px;line-height:1.15;letter-spacing:-.02em;max-width:340px}
.hero .sub{display:flex;align-items:center;gap:7px;margin-top:12px;font-weight:700;font-size:13px;color:#d3e0fb}
.promise-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#E5EAF2;border:1px solid #E5EAF2;border-radius:14px;overflow:hidden;margin:10px 0 18px}
.promise-strip div{background:#fff;padding:11px 7px;text-align:center;font-size:10.5px;font-weight:800;line-height:1.35;color:#344154}
@media(min-width:640px){.promise-strip div{font-size:12px;padding:13px 10px}}
/* search（强化版：蓝边+阴影，一进页面就能看到） */
.search{display:flex;align-items:center;gap:10px;background:#fff;border:2px solid #2563D9;border-radius:18px;padding:14px 16px;margin-top:16px;box-shadow:0 4px 16px rgba(37,99,217,.10)}
.search svg{flex:none;color:#2563D9}
.search input{flex:1;border:0;outline:none;font-size:15px;font-family:inherit;background:transparent;color:#16202E}
.search .clr{flex:none;border:0;background:#F1F4F9;color:#5a6577;width:24px;height:24px;border-radius:99px;cursor:pointer;font-size:12px;display:none}
/* 最近搜索（用户自己的历史，存 localStorage） */
.recent{display:none;gap:7px;overflow-x:auto;margin-top:10px;scrollbar-width:none;align-items:center}
.recent.show{display:flex}
.recent::-webkit-scrollbar{display:none}
.recent .rlb{flex:none;font-size:11.5px;color:#9aa3b2;font-weight:600}
.recent .rch{flex:none;background:#EEF4FF;color:#2563D9;font-weight:600;font-size:12px;padding:6px 12px;border-radius:99px;cursor:pointer}
.recent .rclr{flex:none;border:0;background:none;color:#c3cad6;font-size:13px;cursor:pointer;padding:4px}
/* 分类图标网格 */
.cat-hd{display:flex;align-items:baseline;justify-content:space-between;margin:22px 0 12px}
.cat-hd b{font-weight:800;font-size:17px}
.cat-clear{color:#2563D9;font-weight:700;font-size:12.5px;cursor:pointer;display:none}
.cattiles{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
@media(min-width:640px){.cattiles{grid-template-columns:repeat(6,1fr)}}
.tile{background:#fff;border:1.5px solid #EDF1F7;border-radius:16px;padding:14px 8px;text-align:center;cursor:pointer;transition:transform .12s}
.tile:hover{transform:translateY(-2px)}
.tile.on{border-color:#2563D9;box-shadow:0 0 0 1px #2563D9}
.tico{width:46px;height:46px;margin:0 auto 8px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px}
.tile .tnm{font-size:12px;font-weight:700;line-height:1.2}
.cat-open{border:0;background:none;color:#2563D9;font-weight:800;font-size:12.5px;cursor:pointer}
.cat-dialog{position:fixed;inset:0;background:rgba(15,24,39,.48);z-index:90;display:none;align-items:flex-end;justify-content:center}
.cat-dialog.show{display:flex}
.cat-sheet{width:100%;max-height:84vh;overflow:auto;background:#fff;border-radius:20px 20px 0 0;padding:18px;box-shadow:0 -16px 40px rgba(15,24,39,.18)}
.cat-sheet-head{position:sticky;top:-18px;background:#fff;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:10px 0 14px;border-bottom:1px solid #EEF1F6}
.cat-sheet-head h2{font-size:20px;font-weight:800}
.cat-close{width:38px;height:38px;border:0;border-radius:50%;background:#F1F4F9;color:#435066;font-size:18px;cursor:pointer}
.cat-section{padding:16px 0;border-bottom:1px solid #EEF1F6}
.cat-section:last-child{border:0}
.cat-section-title{display:flex;align-items:center;justify-content:space-between;width:100%;border:0;background:none;text-align:left;font-weight:800;font-size:15px;color:#16202E;cursor:pointer;margin-bottom:10px}
.cat-section-title span{color:#8a93a2;font-size:11px}
.cat-subgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.cat-sub{border:1px solid #E5EAF2;background:#F8FAFD;color:#344154;border-radius:10px;padding:10px;text-align:left;font-size:12px;font-weight:700;cursor:pointer;line-height:1.35}
.cat-sub small{display:block;color:#8a93a2;margin-top:3px;font-weight:600}
@media(min-width:720px){.cat-dialog{align-items:center}.cat-sheet{max-width:760px;border-radius:16px;max-height:80vh}.cat-subgrid{grid-template-columns:repeat(3,minmax(0,1fr))}}
/* featured collection switcher */
.feat-switcher{margin:16px 0 2px}
.feat-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;background:#EAF0F9;padding:4px;border-radius:8px;margin-bottom:8px}
.feat-tab{min-width:0;height:40px;border:0;border-radius:6px;background:transparent;color:#5D6879;font:800 12px inherit;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.feat-tab.on{background:#fff;color:#2563D9;box-shadow:0 1px 4px rgba(27,46,78,.1)}
.feat-stage{position:relative;aspect-ratio:16/10;border-radius:8px;overflow:hidden;background:#16202E}
.feat-slide{position:absolute;inset:0;display:none;color:#fff;text-decoration:none;overflow:hidden}
.feat-slide.on{display:block}
.feat-slide>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.feat-slide:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(10,17,29,.82) 0%,rgba(10,17,29,.48) 48%,rgba(10,17,29,.12) 100%)}
.feat-copy{position:relative;z-index:1;display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-end;width:min(72%,430px);height:100%;padding:18px}
.feat-kick{font-size:10.5px;font-weight:800;text-transform:uppercase}
.feat-copy h3{font-size:23px;line-height:1.08;margin:5px 0 6px}
.feat-copy p{font-size:12px;line-height:1.45;color:#EEF3FA;margin-bottom:13px}
.feat-go{display:inline-flex;align-items:center;min-height:40px;background:#fff;color:#16202E;font-weight:800;font-size:12.5px;padding:0 15px;border-radius:7px}
@media(min-width:640px){.feat-stage{aspect-ratio:16/7}.feat-copy{padding:25px}.feat-copy h3{font-size:29px}}
/* theme (colección) page */
.tbanner{color:#fff;padding:26px 18px 24px}
.tbanner .bk{font-size:12px;opacity:.9;font-weight:700;margin-bottom:9px;color:#fff;text-decoration:none;display:inline-block}
.tbanner h2{font-size:26px;font-weight:800;letter-spacing:-.02em}
.tbanner p{font-size:12.5px;opacity:.92;font-weight:600;margin-top:6px;max-width:520px;line-height:1.55}
.tcta{display:inline-flex;align-items:center;gap:7px;background:#fff;color:#16202E;font-weight:800;font-size:13.5px;padding:11px 20px;border-radius:99px;margin-top:14px}
.valstrip{display:flex;justify-content:space-between;gap:6px;background:#fff;border:1px solid #EDF1F7;border-radius:16px;padding:13px 8px;margin-top:14px}
.valstrip>div{flex:1;text-align:center;font-size:11px;font-weight:700;color:#3a4250;line-height:1.4}
.valstrip>div+div{border-left:1px solid #EDF1F7}
.cchips{display:flex;gap:8px;overflow-x:auto;padding:16px 0 4px;scrollbar-width:none}
.cchips::-webkit-scrollbar{display:none}
.cchip{flex:none;background:#EAF0FB;color:#2563D9;font-weight:700;font-size:12px;padding:8px 14px;border-radius:99px;cursor:pointer;white-space:nowrap}
.cchip.on{background:#16202E;color:#fff}
.cta-final{text-align:center;background:#fff;border:1px solid #EDF1F7;border-radius:20px;padding:26px 18px;margin:6px 0 30px}
.cta-final b{font-size:16px;font-weight:800}
.cta-final p{font-size:12.5px;color:#8a93a2;font-weight:600;margin:6px 0 14px}
.cta-final a{display:inline-flex;align-items:center;gap:8px;background:#25D366;color:#fff;font-weight:800;font-size:14px;padding:12px 22px;border-radius:99px}
/* category chips */
.cats{display:flex;gap:8px;overflow-x:auto;padding:18px 0 6px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.cats::-webkit-scrollbar{display:none}
.chip{flex:none;display:flex;align-items:center;gap:6px;background:#fff;border:1.5px solid #E5EAF2;color:#5a6577;font-weight:600;font-size:12.5px;padding:9px 15px;border-radius:99px;cursor:pointer;white-space:nowrap}
.chip.on{background:#2563D9;border-color:#2563D9;color:#fff}
.subcats{display:none;gap:7px;overflow-x:auto;padding:2px 0 6px;scrollbar-width:none}
.subcats.show{display:flex}
.subcats::-webkit-scrollbar{display:none}
.schip{flex:none;background:#EAF0FB;border:1.5px solid transparent;color:#2563D9;font-weight:700;font-size:12px;padding:7px 13px;border-radius:99px;cursor:pointer;white-space:nowrap}
.schip.on{background:#16202E;color:#fff}
/* 搜索/分类结果模式 */
.home-promo.hidden{display:none}
.results-head{display:none;align-items:flex-start;justify-content:space-between;gap:12px;margin:18px 0 12px}
.results-head.show{display:flex}
.results-head h2{font-size:19px;line-height:1.25;font-weight:800}
.results-head p{font-size:12px;color:#8a93a2;margin-top:4px}
.results-actions{display:flex;gap:7px;flex:none}
.result-btn,.sort-select{height:38px;border:1.5px solid #DDE5F0;border-radius:10px;background:#fff;color:#344154;font-weight:700;font-size:12px;padding:0 11px;cursor:pointer}
.share-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;color:#2563D9}
.share-btn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.share-toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom));z-index:120;transform:translate(-50%,18px);background:#16202E;color:#fff;border-radius:10px;padding:11px 16px;font-size:12px;font-weight:800;opacity:0;pointer-events:none;transition:.2s;box-shadow:0 8px 24px rgba(22,32,46,.24)}
.share-toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:520px){.results-head{flex-wrap:wrap}.results-head>div:first-child{flex:1 1 100%;min-width:0}.results-actions{width:100%}.results-actions #filterOpen,.results-actions .sort-select{flex:1;min-width:0}.share-btn{width:42px;padding:0}.share-btn span{display:none}}
.filter-panel{display:none;background:#fff;border:1px solid #E5EAF2;border-radius:14px;padding:13px;margin-bottom:12px}
.filter-panel.show{display:block}
.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.filter-grid label{display:block;font-size:10.5px;font-weight:700;color:#68758a;margin-bottom:4px}
.filter-grid select,.filter-grid input{width:100%;height:40px;border:1.5px solid #E5EAF2;border-radius:10px;background:#fff;padding:0 10px;font:12px inherit;color:#16202E}
.filter-foot{display:flex;justify-content:flex-end;gap:8px;margin-top:10px}
.filter-foot button{border:0;border-radius:10px;padding:9px 13px;font-weight:800;cursor:pointer}
.filter-reset{background:#F1F4F9;color:#5a6577}.filter-apply{background:#2563D9;color:#fff}
.no-results{grid-column:1/-1;text-align:center;padding:52px 18px;background:#fff;border:1px solid #EDF1F7;border-radius:14px;color:#68758a}
.no-results b{display:block;color:#16202E;font-size:17px;margin-bottom:7px}
.load-more{display:none;margin:-40px auto 54px;border:1.5px solid #DDE5F0;background:#fff;color:#2563D9;border-radius:12px;padding:11px 20px;font-weight:800;cursor:pointer}
.load-more.show{display:block}
/* grid */
.count{font-size:13px;color:#8a93a2;margin:10px 0 12px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:13px;padding-bottom:60px}
@media(min-width:640px){.grid{grid-template-columns:repeat(3,1fr)}}
@media(min-width:920px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{position:relative;background:#fff;border:1px solid #EDF1F7;border-radius:18px;overflow:hidden;box-shadow:0 4px 14px rgba(20,40,80,.05);transition:transform .15s}
.card:hover{transform:translateY(-3px)}
.card-link{display:block}
.card .imgbox{position:relative;aspect-ratio:1;background:#F0F3F8}
.card img{width:100%;height:100%;object-fit:cover}
.badge{position:absolute;top:9px;left:9px;background:#EAF0FB;color:#2563D9;font-size:10px;font-weight:800;padding:3px 8px;border-radius:99px}
.card .info{padding:11px 54px 13px 12px}
.card .nm{font-weight:700;font-size:12.5px;line-height:1.3;height:33px;overflow:hidden}
.card .pr{display:flex;align-items:center;justify-content:space-between;margin-top:8px}
.card .pr b{font-weight:800;font-size:16px}
.card .pr .ask{font-weight:700;font-size:12px;color:#FF6B4A}
.sale-badge{position:absolute;top:9px;right:9px;background:#FF6B4A;color:#fff;font-size:10px;font-weight:800;padding:4px 8px;border-radius:99px;box-shadow:0 2px 8px rgba(255,107,74,.24)}
.offer-label{display:inline-flex;align-items:center;color:#C94F35;background:#FFF0EC;border-radius:6px;padding:3px 6px;font-size:9.5px;font-weight:800;margin-top:7px}
.price-stack{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin-top:7px}
.price-stack .current{font-size:16px;font-weight:800}.price-stack del{color:#9AA3B2;font-size:11px;font-weight:600}
.saving{display:inline-flex;color:#E4583B;background:#FFF0EC;border-radius:6px;padding:3px 6px;font-size:9.5px;font-weight:800;margin-top:4px}
.card-add{position:absolute;right:11px;bottom:11px;width:38px;height:38px;border:0;border-radius:12px;background:#2563D9;color:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 12px rgba(37,99,217,.28);transition:background .15s,transform .15s}
.card-add:active{transform:scale(.92)}
.card-add.added{background:#157A4E}
.card-add svg{width:19px;height:19px}
/* detail */
.dt{max-width:920px;margin:0 auto;padding:0 0 165px}
@media(min-width:760px){.dt{display:grid;grid-template-columns:1fr 1fr;gap:28px;padding:26px 18px 40px;align-items:start}}
.dt .pic{background:#F0F3F8}
@media(min-width:760px){.dt .pic{border-radius:22px;overflow:hidden;position:sticky;top:80px}}
.dt .pic img.main{width:100%;aspect-ratio:1;object-fit:contain}
/* 大图画廊：整宽滑动 + 圆点指示器 */
.galwrap{position:relative}
.gal{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.gal::-webkit-scrollbar{display:none}
.gal .gs{flex:none;width:100%;scroll-snap-align:center}
.gal .gs img{width:100%;aspect-ratio:1;object-fit:contain;background:#F0F3F8}
.dots{position:absolute;bottom:12px;left:0;right:0;display:flex;justify-content:center;gap:6px;pointer-events:none}
.dots span{width:7px;height:7px;border-radius:50%;background:rgba(255,255,255,.55);box-shadow:0 1px 3px rgba(0,0,0,.25);transition:background .15s}
.dots span.on{background:#fff}
.thumbs{display:flex;gap:9px;padding:12px;background:#fff;overflow-x:auto;scrollbar-width:none}
.thumbs::-webkit-scrollbar{display:none}
.thumbs img{width:52px;height:52px;border-radius:12px;object-fit:cover;border:2px solid transparent;cursor:pointer;background:#F0F3F8;opacity:.6;flex:none}
.thumbs img.on{border-color:#2563D9;opacity:1}
.panel{background:#fff;border-radius:24px 24px 0 0;margin-top:-22px;position:relative;padding:22px 20px 16px}
@media(min-width:760px){.panel{border-radius:22px;margin-top:0;border:1px solid #EDF1F7}}
.panel h1{font-weight:800;font-size:21px;line-height:1.25;margin-bottom:12px;letter-spacing:-.02em}
.price{font-weight:800;font-size:30px;letter-spacing:-.02em;margin-bottom:16px}
.price.ask{font-size:22px;color:#FF6B4A}
.detail-price{margin-bottom:16px}.detail-price .price{display:inline;margin:0}.detail-price del{color:#9AA3B2;font-size:15px;font-weight:600;margin-left:8px}.detail-price .saving{font-size:11px;margin:8px 0 0}.detail-offer{display:inline-flex;background:#FFF0EC;color:#C94F35;border-radius:7px;padding:5px 8px;font-size:10px;font-weight:800;margin-bottom:8px}
.trust{display:flex;justify-content:space-between;background:#F7F9FD;border:1px solid #EDF1F7;border-radius:18px;padding:16px 6px;margin-bottom:20px}
.trust>div{display:flex;flex-direction:column;align-items:center;gap:7px;flex:1;font-size:10.5px;font-weight:700;text-align:center}
.trust>div+div{border-left:1px solid #E5EAF2}
.trust .em{width:38px;height:38px;border-radius:50%;background:#EAF0FB;display:flex;align-items:center;justify-content:center;font-size:18px}
.sec{font-weight:800;font-size:15px;margin-bottom:8px}
.desc{font-size:13px;color:#3a4250;line-height:1.65;margin-bottom:18px}
.buy-facts{display:grid;gap:8px;margin:-4px 0 18px}
.buy-fact{display:flex;align-items:flex-start;gap:9px;background:#F7F9FD;border:1px solid #E8EDF5;border-radius:12px;padding:10px 12px;font-size:12px;line-height:1.45;color:#435066}
.buy-fact b{display:block;color:#16202E;margin-bottom:1px}
.stock-ok{color:#157A4E}.stock-check{color:#9A6700}
.customer-proof{display:flex;align-items:center;justify-content:center;background:#FFF8E8;border:1px solid #F4D88A;color:#765410;border-radius:11px;padding:9px 10px;margin:0 0 10px;font-size:11.5px;font-weight:800;text-align:center}
/* action bar（含加购信任微标） */
.bar{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #EEF1F6;padding:12px 16px calc(8px + env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:8px;z-index:60}
.bar-btns{display:flex;gap:10px}
.microtrust{display:flex;flex-direction:column;gap:3px;font-size:11px;font-weight:600;color:#5a6577;padding:0 2px}
.microtrust span{display:flex;align-items:center;gap:6px}
@media(min-width:760px){.bar{position:static;border:0;padding:0;background:transparent}}
.btn-wa{flex:none;width:54px;height:52px;display:flex;align-items:center;justify-content:center;background:#25D366;color:#fff;border-radius:16px;cursor:pointer}
.btn-wa.wide{flex:1;gap:9px;font-weight:800;font-size:16px}
.btn-back{flex:none;width:54px;height:52px;border:2px solid #2563D9;border-radius:16px;display:flex;align-items:center;justify-content:center;color:#2563D9;font-size:20px}
.btn-add{flex:1;display:flex;align-items:center;justify-content:center;gap:9px;background:#FF6B4A;color:#fff;font-weight:800;font-size:16px;height:52px;border-radius:16px;cursor:pointer;border:0}
.btn-add.added{background:#16a34a}
.crumb{padding:14px 18px 0;font-size:13px;color:#8a93a2}
.crumb a{color:#2563D9;font-weight:700}
/* 新版通用商品详情：沿用墙纸页的购买节奏，按名单分批启用 */
.commerce-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;color:#7B8797;font-size:11px;font-weight:700;margin:-3px 0 10px}
.commerce-meta span{background:#F1F5FB;border-radius:7px;padding:4px 7px}
.commerce-strip{display:flex;align-items:center;justify-content:center;gap:8px;background:#ECF8EF;border:1px solid #CDEBD5;color:#17733E;border-radius:12px;padding:10px 9px;margin:0 0 14px;font-size:11.5px;font-weight:800;text-align:center}
.commerce-strip i{width:1px;height:15px;background:#B8DEC3}
.commerce-choice{display:flex;align-items:center;justify-content:space-between;gap:14px;border-top:1px solid #EEF1F6;border-bottom:1px solid #EEF1F6;padding:13px 0;margin:2px 0 16px}
.commerce-choice-label b{display:block;font-size:13px}.commerce-choice-label span{display:block;color:#8490A1;font-size:10.5px;margin-top:2px}
.commerce-qty{display:grid;grid-template-columns:38px 42px 38px;align-items:center;border:1.5px solid #DDE5F0;border-radius:12px;overflow:hidden;background:#fff;height:40px}
.commerce-qty button{height:100%;border:0;background:#F7F9FD;color:#2563D9;font-size:19px;font-weight:800;cursor:pointer}
.commerce-qty output{text-align:center;font-size:14px;font-weight:800}
.commerce-proof{display:flex;align-items:center;gap:9px;background:#FFF8E8;border:1px solid #F4D88A;color:#765410;border-radius:12px;padding:10px 12px;margin:0 0 15px;font-size:11.5px;font-weight:750;line-height:1.4}
.commerce-proof strong{display:block;color:#4C390B}
.commerce-bar-total{display:flex;align-items:end;justify-content:space-between;gap:12px;padding:0 2px}
.commerce-bar-total span{display:block;color:#7B8797;font-size:10.5px;font-weight:700}.commerce-bar-total strong{font-size:22px;line-height:1;color:#16202E}
.dt.commerce .customer-proof{display:none}
@media(max-width:759px){
 .dt.commerce{padding-bottom:152px}.dt.commerce .panel{padding-top:20px}
 .dt.commerce .panel h1{font-size:19px;margin-bottom:8px}
 .dt.commerce .detail-price{margin-bottom:12px}.dt.commerce .detail-price .price{font-size:29px}
 .dt.commerce .trust{margin-bottom:16px}
 .dt.commerce .bar{gap:9px;max-width:100vw;overflow:hidden}.dt.commerce .microtrust{display:none}
 .dt.commerce .commerce-bar-total{width:100%;min-width:0}
 .dt.commerce .commerce-bar-total strong{min-width:0;max-width:58%;font-size:19px;white-space:nowrap;text-align:right}
 .dt.commerce .bar-btns{min-width:0}.dt.commerce .btn-add{min-width:0;padding:0 9px;font-size:14px;white-space:nowrap}
 .dt.commerce .btn-back{display:none}.dt.commerce .btn-wa{width:50px}
}
@media(min-width:760px){
 .dt.commerce{max-width:1040px;grid-template-columns:minmax(0,1.08fr) minmax(360px,.92fr);gap:32px}
 .dt.commerce .panel{padding:24px}.dt.commerce .commerce-bar-total{margin-top:12px}
}
/* 推荐栏 */
.recs{max-width:920px;margin:0 auto;padding:6px 18px 110px}
@media(min-width:760px){.recs{padding-bottom:40px}}
.recs h2{font-weight:800;font-size:17px;margin-bottom:12px;letter-spacing:-.02em}
.rec-row{display:flex;gap:11px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;padding-bottom:6px}
.rec-row::-webkit-scrollbar{display:none}
.rec{flex:none;width:140px;background:#fff;border:1px solid #EDF1F7;border-radius:15px;overflow:hidden}
.rec img{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}
.rec .rn{font-weight:700;font-size:11.5px;line-height:1.3;height:30px;overflow:hidden;padding:8px 9px 0}
.rec .rp{font-weight:800;font-size:13.5px;padding:5px 9px 10px}
.rec .rp.ask{color:#FF6B4A;font-size:11px;font-weight:700}
/* home conversion sections */
.home-section{margin:24px 0}.home-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:12px}.home-section-head h2{font-size:18px;font-weight:800}.home-section-head p{font-size:11.5px;color:#8A93A2;margin-top:3px}
.best-row{display:flex;gap:12px;overflow-x:auto;padding:2px 1px 10px;scrollbar-width:none;scroll-snap-type:x proximity}.best-row::-webkit-scrollbar{display:none}.best-row .card{flex:none;width:210px;scroll-snap-align:start}.best-row .card .nm{font-size:13.5px;height:36px}.best-row .card .info{padding-bottom:16px}
.reviews-grid{display:grid;gap:10px}.review{background:#fff;border:1px solid #E8EDF5;border-radius:14px;padding:15px}.review-top{display:flex;align-items:center;gap:10px;margin-bottom:9px}.review-avatar{width:38px;height:38px;border-radius:50%;overflow:hidden;background:#EAF0FB;display:grid;place-items:center;color:#2563D9;font-weight:800;flex:none}.review-avatar img{width:100%;height:100%;object-fit:cover;grid-area:1/1}.review-avatar span{grid-area:1/1}.review-name{font-size:12.5px;font-weight:800}.review-city{font-size:10.5px;color:#8A93A2}.review-stars{color:#F5A524;font-size:12px;margin-left:auto}.review-text{font-size:12px;line-height:1.55;color:#435066}
@media(min-width:700px){.reviews-grid{grid-template-columns:repeat(3,1fr)}}
.stores{margin:30px 0 8px}.store-grid{display:grid;gap:12px}.store{display:grid;grid-template-columns:112px minmax(0,1fr);background:#fff;border:1px solid #E8EDF5;border-radius:16px;overflow:hidden}.store-photo{width:112px;height:100%;min-height:142px;object-fit:cover;background:#EEF2F7}.store-photo-missing{display:grid;place-items:center;color:#7C8798;font-size:11px;text-align:center;padding:10px}.store-info{padding:14px}.store-info h3{font-size:14px;font-weight:800}.store-info p{font-size:11.5px;line-height:1.5;color:#68758A;margin-top:5px}.store-info a{display:inline-flex;margin-top:10px;color:#2563D9;font-size:11.5px;font-weight:800}
@media(min-width:720px){.store-grid{grid-template-columns:1fr 1fr}}
.policy{max-width:760px;margin:24px auto 48px;padding:0 18px}.policy h1{font-size:27px;font-weight:800;margin-bottom:8px}.policy .lead{font-size:14px;color:#68758A;line-height:1.6;margin-bottom:20px}.policy section{background:#fff;border:1px solid #E8EDF5;border-radius:14px;padding:17px;margin-bottom:11px}.policy h2{font-size:15px;font-weight:800;margin-bottom:7px}.policy p,.policy li{font-size:12.5px;color:#435066;line-height:1.65}.policy ul{padding-left:18px}.policy .contact{display:inline-flex;background:#25D366;color:#fff;border-radius:12px;padding:12px 16px;font-weight:800;margin-top:6px}
footer{text-align:center;font-size:12px;color:#9aa3b2;padding:26px 18px 34px;line-height:1.9}
footer .rnc{font-size:11px;color:#b3bac6}
footer .footer-links{display:flex;justify-content:center;gap:15px;margin-bottom:4px}footer .footer-links a{color:#2563D9;font-weight:700}
/* 悬浮 WhatsApp（呼吸灯 + 30秒提示气泡） */
.wa-float{position:fixed;right:16px;bottom:calc(18px + env(safe-area-inset-bottom));width:56px;height:56px;border-radius:50%;background:#25D366;color:#fff;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 20px rgba(37,211,102,.45);z-index:70;animation:wapulse 2.4s infinite}
@keyframes wapulse{0%{box-shadow:0 6px 20px rgba(37,211,102,.45),0 0 0 0 rgba(37,211,102,.45)}70%{box-shadow:0 6px 20px rgba(37,211,102,.45),0 0 0 16px rgba(37,211,102,0)}100%{box-shadow:0 6px 20px rgba(37,211,102,.45),0 0 0 0 rgba(37,211,102,0)}}
.wa-tip{position:fixed;right:82px;bottom:calc(30px + env(safe-area-inset-bottom));background:#16202E;color:#fff;font-size:12.5px;font-weight:700;padding:9px 14px;border-radius:13px;z-index:70;display:none;box-shadow:0 6px 18px rgba(0,0,0,.2)}
.wa-tip:after{content:'';position:absolute;right:-6px;top:50%;transform:translateY(-50%);border:6px solid transparent;border-left-color:#16202E;border-right:0}
/* 表单小提示 */
.hint{font-size:11.5px;color:#8a93a2;font-weight:600;margin-top:5px;display:flex;align-items:center;gap:5px}
/* 转账三步图 */
.steps{display:flex;gap:6px;margin-bottom:11px}
.steps>div{flex:1;background:#fff;border:1px solid #E9EDF4;border-radius:12px;padding:10px 7px;text-align:center}
.steps .sn{width:22px;height:22px;border-radius:50%;background:#2563D9;color:#fff;font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center;margin:0 auto 6px}
.steps .st{font-size:10.5px;font-weight:700;line-height:1.35;color:#3a4250}
/* ---- carrito ---- */
.ct{max-width:640px;margin:0 auto;padding:18px 18px 40px}
.ct h1{font-weight:800;font-size:24px;margin:8px 0 16px;letter-spacing:-.02em}
.box{background:#fff;border:1px solid #EDF1F7;border-radius:20px;padding:16px;margin-bottom:14px}
.box .bt{display:flex;align-items:center;gap:7px;font-weight:800;font-size:15px;margin-bottom:12px}
.ci{display:flex;gap:12px;align-items:center;padding:10px 0}
.ci+.ci{border-top:1px solid #F1F4F9}
.ci img{width:64px;height:64px;border-radius:14px;object-fit:cover;background:#F0F3F8}
.ci .t{flex:1;min-width:0}
.ci .nm{font-weight:700;font-size:13px;line-height:1.3;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.ci .pr{font-weight:800;font-size:14px;margin-top:4px}
.ci .tier-note{display:block;margin-top:2px;color:#0F9D58;font-size:10px;font-weight:700}
.qty{display:flex;align-items:center;gap:10px;margin-top:6px}
.qty button{width:26px;height:26px;border-radius:9px;border:1.5px solid #E5EAF2;background:#fff;color:#2563D9;font-weight:800;font-size:15px;cursor:pointer}
.qty span{font-weight:800;font-size:14px;min-width:16px;text-align:center}
.ci .rm{border:0;background:none;color:#c3cad6;font-size:17px;cursor:pointer;padding:4px}
.empty{text-align:center;padding:40px 0;color:#8a93a2;font-weight:600}
.empty a{color:#2563D9;font-weight:800}
/* form */
.fld{margin-bottom:10px}
.fld label{display:block;font-weight:700;font-size:12px;color:#5a6577;margin-bottom:5px}
.fld input,.fld textarea,.fld select{width:100%;border:1.5px solid #E5EAF2;border-radius:13px;padding:12px 14px;font-size:14px;font-family:inherit;background:#fff;color:#16202E}
.fld input:focus,.fld textarea:focus,.fld select:focus{outline:none;border-color:#2563D9}
.fld.invalid input,.fld.invalid textarea,.fld.invalid select{border-color:#E44D4D;background:#FFF8F8}
.fld .err-msg{display:none;color:#C73535;font-size:10.5px;font-weight:700;margin-top:4px}
.fld.invalid .err-msg{display:block}
.fld select{appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%235a6577' stroke-width='3'><path d='M6 9l6 6 6-6'/></svg>");background-repeat:no-repeat;background-position:right 14px center}
/* checkout location + preferred delivery */
.delivery-extra{display:none;border-top:1px solid #E8EDF5;margin-top:14px;padding-top:15px}.delivery-extra.show{display:block}
.extra-head{display:flex;align-items:flex-start;gap:10px;margin-bottom:11px}.extra-icon{width:34px;height:34px;border-radius:9px;background:#EAF0FB;display:grid;place-items:center;flex:none}.extra-head b{display:block;font-size:13px}.extra-head p{font-size:10.5px;color:#68758A;line-height:1.45;margin-top:3px}.optional{color:#7B8797;font-weight:700}
.map-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.map-row input{min-width:0}.map-paste{border:0;border-radius:10px;background:#2563D9;color:#fff;padding:0 13px;font-weight:800;cursor:pointer}.map-paste:disabled{opacity:.45}
.map-status{display:none;align-items:center;justify-content:space-between;gap:9px;color:#167747;font-size:10.5px;font-weight:800;margin-top:8px}.map-status.show{display:flex}.map-status a{color:#2563D9;text-decoration:underline}.map-error{display:none;color:#C73535;font-size:10.5px;font-weight:700;margin-top:6px}.map-error.show{display:block}
.location-later{display:flex;align-items:flex-start;gap:8px;margin-top:11px;color:#566276;font-size:11px;font-weight:700;line-height:1.45;cursor:pointer}.location-later input{width:17px;height:17px;margin:0;accent-color:#2563D9;flex:none}
.map-help{width:100%;display:flex;align-items:center;justify-content:space-between;border:0;background:transparent;color:#2563D9;padding:14px 1px 2px;font-weight:800;cursor:pointer}.map-tutorial{display:none;margin-top:11px}.map-tutorial.show{display:block}.map-steps{display:flex;gap:9px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:7px}.map-step{flex:0 0 76%;scroll-snap-align:start;background:#F7F9FD;border-radius:11px;padding:10px}.map-visual{height:78px;border-radius:9px;background:#E8EEF8;display:grid;place-items:center;font-size:30px;margin-bottom:8px}.map-step b{font-size:11.5px}.map-step p{font-size:10.5px;color:#68758A;line-height:1.4;margin-top:3px}.tutorial-hint{font-size:10.5px;color:#68758A;line-height:1.45;margin:7px 1px 0}
.schedule-box{display:none}.schedule-box.show{display:block}.schedule-copy{font-size:11.5px;line-height:1.5;color:#68758A;margin:-5px 0 12px}.date-shortcuts{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:11px}.date-choice,.time-choice{border:1.5px solid #DDE5F0;background:#fff;border-radius:10px;min-height:50px;padding:7px 5px;text-align:center;font-weight:800;color:#4E596B;cursor:pointer}.date-choice small{display:block;color:#8B95A5;font-size:9px;margin-top:3px}.date-choice.on,.time-choice.on{border-color:#2563D9;background:#EEF4FF;color:#2563D9}.date-choice:disabled,.time-choice:disabled{opacity:.45;cursor:not-allowed;background:#F2F4F7}
.custom-date{display:none;grid-template-columns:.7fr 1.3fr .9fr;gap:7px;margin:-2px 0 11px}.custom-date.show{display:grid}.custom-date select{width:100%;height:43px;border:1.5px solid #DDE5F0;border-radius:10px;background:#fff;padding:0 9px;font:700 12px inherit;color:#344154}
.time-choices{display:grid;grid-template-columns:1fr 1fr;gap:7px}.time-choice{min-height:44px;font-size:11px}.schedule-note{display:flex;gap:7px;background:#FFF8E8;border:1px solid #F2D990;border-radius:10px;padding:9px 10px;margin-top:10px;font-size:10px;line-height:1.45;color:#725314}
button:focus-visible,.date-choice:focus-visible,.time-choice:focus-visible{outline:3px solid rgba(37,99,217,.25);outline-offset:2px}
@media(min-width:640px){.map-steps{display:grid;grid-template-columns:repeat(3,1fr);overflow:visible}.map-step{min-width:0}}
@media(max-width:410px){.map-row{grid-template-columns:1fr}.map-paste{height:42px}.date-shortcuts{grid-template-columns:1fr 1fr}.date-shortcuts .date-choice:last-child{grid-column:1/-1}.time-choices{grid-template-columns:1fr}}
/* pago radios */
.pay{display:flex;flex-direction:column;gap:9px}
.pay label{display:flex;align-items:center;gap:11px;border:1.5px solid #E5EAF2;border-radius:15px;padding:14px;cursor:pointer;font-weight:700;font-size:14px;background:#fff}
.pay label.on{border-color:#2563D9;box-shadow:0 0 0 1px #2563D9}
.pay input{accent-color:#2563D9;width:18px;height:18px}
.bank{display:none;background:#F7F9FD;border:1px solid #EDF1F7;border-radius:15px;padding:13px;margin-top:9px}
.bank.show{display:block}
.bank .bk{display:flex;justify-content:space-between;align-items:center;padding:8px 0}
.bank .bk+.bk{border-top:1px solid #E9EDF4}
.bank .bn{font-weight:800;font-size:13px}
.bank .bo{font-size:11px;color:#8a93a2;font-weight:600}
.bank .ba{font-weight:800;font-size:14px;letter-spacing:.02em}
.bank .note{font-size:11.5px;color:#5a6577;margin-top:9px;line-height:1.5}
.bank .remind{display:block;background:#FFF5E9;border:1px solid #F6DDB4;border-radius:11px;padding:10px 12px;margin-top:10px;font-size:12px;font-weight:700;color:#8a5a12;line-height:1.5}
.bank .remind b{color:#16202E}
/* totals */
.tot .ln{display:flex;justify-content:space-between;font-size:13.5px;color:#5a6577;font-weight:600;padding:4px 0}
.tot .ln b{color:#16202E}
.tot .ln.disc b{color:#0FA958}
.cpn{display:flex;gap:8px;margin:2px 0 10px}
.cpn input{flex:1;border:1.5px solid #E5EAF2;border-radius:12px;padding:11px 13px;font-size:13.5px;font-family:inherit;text-transform:uppercase}
.cpn input:focus{outline:none;border-color:#2563D9}
.cpn button{flex:none;background:#EAF0FB;color:#2563D9;font-weight:800;font-size:13.5px;border:0;border-radius:12px;padding:0 16px;cursor:pointer}
.cpn button:disabled{opacity:.5;cursor:default}
.cpn-msg{font-size:12px;font-weight:700;margin:-4px 0 8px;min-height:15px}
.cpn-msg.ok{color:#0FA958}.cpn-msg.err{color:#FF6B4A}
.tot .gt{display:flex;justify-content:space-between;font-weight:800;font-size:19px;border-top:1px solid #F1F4F9;margin-top:8px;padding-top:12px}
.btn-conf{width:100%;display:flex;align-items:center;justify-content:center;gap:9px;background:#FF6B4A;color:#fff;font-weight:800;font-size:16px;height:54px;border-radius:16px;border:0;cursor:pointer;margin-top:6px}
.btn-conf:disabled{opacity:.5}
.sub-note{text-align:center;font-size:11.5px;color:#9aa3b2;margin-top:10px}
.ship-quote{background:#EEF7FF;border:1px solid #CFE2F7;border-radius:13px;padding:11px 12px;margin:8px 0 10px;display:grid;grid-template-columns:1fr auto;gap:4px 12px}
.ship-quote span{font-size:11px;color:#5f7186;font-weight:700}.ship-quote b{font-size:14px}.ship-quote small{grid-column:1/-1;color:#68758a;font-size:10.5px}
.ship-quote b.free{color:#157A4E;font-weight:800;letter-spacing:.3px}
.pay-note{display:none;background:#FFF5E9;border:1px solid #F6DDB4;color:#8a5a12;border-radius:11px;padding:10px 12px;font-size:11.5px;font-weight:700;line-height:1.45;margin-bottom:9px}
.pay-note.show{display:block}
/* confirmación */
.ok{display:none;min-height:70vh;background:linear-gradient(160deg,#2563D9,#1A47A6);border-radius:24px;margin:18px;padding:60px 24px;text-align:center;color:#fff}
.ok .ck{width:86px;height:86px;border-radius:50%;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;margin:0 auto 22px;font-size:38px}
.ok h2{font-weight:800;font-size:26px;margin-bottom:12px}
.ok p{font-size:14px;color:#d3e0fb;line-height:1.6;max-width:320px;margin:0 auto 26px}
.ok a{display:inline-block;background:#fff;color:#2563D9;font-weight:800;font-size:15px;padding:14px 30px;border-radius:16px}
.ok-actions{display:flex;flex-direction:column;gap:9px;max-width:320px;margin:0 auto}.ok-actions .ok-wa{background:#25D366;color:#fff}.ok-actions .ok-shop{background:#fff;color:#2563D9}
"""

CART_JS = """<script>
function vbCart(){try{return JSON.parse(localStorage.getItem('vb_cart')||'[]')}catch(e){return[]}}
function vbSave(c){localStorage.setItem('vb_cart',JSON.stringify(c));vbBadge()}
function vbBadge(){var n=vbCart().reduce(function(a,b){return a+b.qty},0);
 var el=document.getElementById('cartN');if(el){el.textContent=n>99?'99+':n;el.style.display=n?'flex':'none'}}
function vbAddProduct(b){
 var c=vbCart(),sku=b.dataset.sku,f=c.find(function(x){return x.sku===sku});
 if(f){f.qty++}else{c.push({sku:sku,handle:b.dataset.handle,title:b.dataset.title,
  price:parseFloat(b.dataset.price),img:b.dataset.img,qty:1})}
 vbSave(c);
 var item=c.find(function(x){return x.sku===sku});
 try{fbq('track','AddToCart',{content_ids:[sku],content_type:'product',
  value:parseFloat(b.dataset.price),currency:'DOP'})}catch(e){}
 try{vbTrack('addcart',sku,{qty:item.qty,price:item.price,
  cart_total:c.reduce(function(a,x){return a+x.price*x.qty},0),
  product_title:item.title,product_img:item.img})}catch(e){}
}
function vbCardAdd(e,b){
 if(e){e.preventDefault();e.stopPropagation()}
 vbAddProduct(b);b.classList.add('added');b.setAttribute('aria-label','Agregado al carrito');
 var old=b.innerHTML;b.innerHTML='✓';setTimeout(function(){b.classList.remove('added');b.innerHTML=old;
  b.setAttribute('aria-label','Agregar al carrito')},900);
}
try{var vbCampaignCoupon=new URLSearchParams(location.search).get('coupon');
 if(vbCampaignCoupon)localStorage.setItem('vb_campaign_coupon',vbCampaignCoupon.toUpperCase())}catch(e){}
document.addEventListener('DOMContentLoaded',vbBadge);
</script>"""

# 自有埋点：会话、UTM、WhatsApp、停留、滚动和设备（普通事件 fetch，离页 sendBeacon）
TRACK_JS = """<script>
(function(){
 var API='__API__/api/track',now=Date.now(),q=new URLSearchParams(location.search),keys=['utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid'];
 function get(k,d){try{return JSON.parse(localStorage.getItem(k)||'null')||d}catch(e){return d}}
 function put(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
 function uuid(prefix){return prefix+(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random())}
 var client=get('vb_client_id','');if(!client){client=uuid('c-');put('vb_client_id',client)}
 var a=get('vb_attr',{}),first=get('vb_first_attr',{}),has=false;keys.forEach(function(k){if(q.get(k)){a[k]=q.get(k);has=true}});if(has){put('vb_attr',a);if(!first.captured_at){first={captured_at:now};keys.forEach(function(k){first[k]=a[k]||''});put('vb_first_attr',first)}}
 var ss=get('vb_session',{});if(!ss.id||now-(ss.last||0)>1800000)ss={id:'s-'+(crypto.randomUUID?crypto.randomUUID():now+'-'+Math.random()),last:now};ss.last=now;put('vb_session',ss);
 var dev=/Mobi|Android|iPhone/i.test(navigator.userAgent)?'mobile':(/iPad|Tablet/i.test(navigator.userAgent)?'tablet':'desktop'),last=Date.now(),sent={};
 function id(){return crypto.randomUUID?crypto.randomUUID():'e-'+Date.now()+'-'+Math.random()}
 function ctx(){var p=window.VB_PAGE||{},b={event_id:id(),client_id:client,session_id:ss.id,path:location.pathname,device_type:dev,screen_width:screen.width,site_version:'__VERSION__',category:p.category||'',product_title:p.title||'',product_img:p.img||''};keys.forEach(function(k){b[k]=a[k]||'';b['first_'+k]=first[k]||''});return b}
 function send(t,s,x,beacon){try{var b=ctx();b.type=t;b.sku=s||((window.VB_PAGE||{}).sku||'');if(x)for(var k in x)b[k]=x[k];var raw=JSON.stringify(b);if(beacon&&navigator.sendBeacon)navigator.sendBeacon(API,new Blob([raw],{type:'application/json'}));else fetch(API,{method:'POST',credentials:'include',keepalive:true,headers:{'Content-Type':'application/json'},body:raw}).catch(function(){})}catch(e){}}
 window.vbTrack=send;window.vbContext=ctx;
 document.addEventListener('click',function(e){var x=e.target.closest&&e.target.closest('a[href*="wa.me"]');if(!x)return;var loc=x.classList.contains('wa-float')?'floating':x.classList.contains('hd-wa')?'header':x.classList.contains('btn-wa')?'product':'other';send('whatsapp','',{whatsapp_location:loc})},true);
 document.addEventListener('scroll',function(){var h=document.documentElement,den=h.scrollHeight-innerHeight;if(den<=0)return;var d=Math.min(100,Math.round(scrollY/den*100));[25,50,75,100].forEach(function(n){if(d>=n&&!sent[n]){sent[n]=1;send('scroll','',{scroll_depth:n})}})},{passive:true});
 setInterval(function(){if(document.visibilityState==='visible'){send('engagement','',{duration_ms:30000});last=Date.now();ss.last=last;put('vb_session',ss)}},30000);
 addEventListener('pagehide',function(){var d=Math.max(0,Math.min(30000,Date.now()-last));if(d>1000)send('engagement','',{duration_ms:d},true)});
})();
</script>""".replace("__API__", API_BASE).replace("__VERSION__", SITE_VERSION)

WA_FLOAT = f"""<a class="wa-float" href="https://wa.me/{WHATSAPP}" target="_blank" aria-label="WhatsApp"
 onclick="fbq('track','Contact')">{WA_SVG}</a>
<div class="wa-tip" id="waTip">¿Dudas? Escríbenos 👋</div>
<script>
setTimeout(function(){{
 try{{if(sessionStorage.getItem('vb_watip'))return;sessionStorage.setItem('vb_watip','1');}}catch(e){{}}
 var t=document.getElementById('waTip');if(!t)return;t.style.display='block';
 setTimeout(function(){{t.style.display='none'}},6000);
}},30000);
</script>"""

def page(title, body, pixel_extra="", desc="", track_sku=None, track_category="",
         track_title="", track_img="", wa_float=False, extra_head="", canonical="", rel="",
         robots="index,follow", og_image=""):
    page_ctx = json.dumps({"sku": track_sku or "", "category": track_category or "",
                           "title": track_title or "", "img": track_img or ""}, ensure_ascii=False)
    view_js = f"<script>vbTrack('view',{json.dumps(track_sku or '')})</script>"
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc[:160])}">
<meta name="robots" content="{esc(robots)}">
{f'<link rel="canonical" href="{esc(canonical)}">' if canonical else ''}
<meta property="og:type" content="{'product' if track_sku else 'website'}">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc[:200])}">
{f'<meta property="og:url" content="{esc(canonical)}">' if canonical else ''}
{f'<meta property="og:image" content="{esc(og_image)}">' if og_image else ''}
<meta name="twitter:card" content="{'summary_large_image' if og_image else 'summary'}">
{FONT}
<style>{CSS}</style>
{extra_head}
{pixel(pixel_extra)}
{CART_JS}
<script>window.VB_PAGE={page_ctx};</script>
{TRACK_JS}
</head><body>
{body}
{view_js}
{WA_FLOAT if wa_float else ""}
<footer><div class="footer-links"><a href="{rel}garantia">Garantía y devoluciones</a><a href="https://wa.me/{WHATSAPP}" target="_blank">Contacto</a></div>
© {SITE_NAME} · Envíos en toda República Dominicana · Contra entrega en Gran Santo Domingo
<div class="rnc">RNC: 132888855 · Registrado bajo la Ley 126-02 de Comercio Electrónico · 🔒 Sitio seguro</div></footer>
</body></html>"""

def header(rel=""):
    return f"""<div class="hd"><div class="wrap hd-in">
<a class="logo" href="{rel or './'}"><span class="ic">{SITE_NAME[0]}</span>{esc(SITE_NAME)}</a>
<div class="hd-r">
<a class="hd-wa" href="https://wa.me/{WHATSAPP}" target="_blank" onclick="fbq('track','Contact')">{WA_SVG} WhatsApp</a>
<a class="hd-cart" href="{rel}?buscar=1" aria-label="Buscar"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></a>
<a class="hd-cart" href="{rel}carrito" aria-label="Carrito">{BAG_SVG}<span class="cart-n" id="cartN"></span></a>
</div>
</div></div>"""

# ---------- 购物车/结算页 ----------
def carrito_page():
    banks_html = "".join(
        f'<div class="bk"><div><div class="bn">{esc(b)}</div><div class="bo">{esc(o)}</div></div>'
        f'<div class="ba">{esc(a)}</div></div>' for b, a, o in BANKS)
    bank_lines = "\\n".join(f"{b}: {a} ({o})" for b, a, o in BANKS)
    adhesive_cfg = load_json(ADHESIVE_PANEL_PATH, {})
    tier_prices = {}
    if isinstance(adhesive_cfg, dict) and adhesive_cfg.get("sku") and adhesive_cfg.get("tier_price"):
        tier_prices[str(adhesive_cfg["sku"])] = {
            "min_qty": max(2, int(adhesive_cfg.get("tier_min_qty") or 2)),
            "unit_price": float(adhesive_cfg["tier_price"]),
        }
    tier_prices_json = json.dumps(tier_prices, ensure_ascii=False)

    body = header() + """
<div class="ct" id="main">
<h1>Tu compra</h1>
<div class="box" id="itemsBox"><div class="bt">🛍️ Productos</div><div id="items"></div></div>

<div class="box" id="formBox">
<div class="bt">🚚 Datos de entrega</div>
<div class="fld" id="fldNom"><label>Nombre completo *</label><input id="fNom" name="name" autocomplete="name" placeholder="Tu nombre"><div class="err-msg">Escribe tu nombre.</div></div>
<div class="fld" id="fldTel"><label>Teléfono / WhatsApp *</label><input id="fTel" name="tel" autocomplete="tel" inputmode="tel" placeholder="809 000 0000"><div class="err-msg">Escribe un teléfono válido.</div>
<div class="hint">📞 Te llamaremos a este número cuando tu pedido esté llegando</div></div>
<div class="fld" id="fldProv"><label>Provincia *</label><select id="fProv" name="address-level1" autocomplete="address-level1" onchange="provUI()"></select><div class="err-msg">Selecciona la provincia.</div></div>
<div class="fld" id="sectorFld"><label>Sector / Zona *</label><select id="sector-select" name="address-level2" autocomplete="address-level2" onchange="sectorUI()"></select>
<div class="hint" id="shipNote" style="display:none;color:#8a6d1f"></div></div>
<div class="fld" id="cityFld" style="display:none"><label>Municipio / Ciudad *</label><input id="fCity" name="address-level2" autocomplete="address-level2" placeholder="Ej: Santiago, Moca..." onblur="sectorUI()"><div class="err-msg">Escribe el municipio o ciudad.</div></div>
<div class="fld" id="fldDir"><label>Dirección (calle y número) *</label><textarea id="fDir" name="street-address" autocomplete="street-address" rows="2" placeholder="Calle, No., referencia"></textarea><div class="err-msg">Escribe la dirección de entrega.</div></div>
<div class="delivery-extra" id="locationExtra">
<div class="extra-head"><span class="extra-icon">📍</span><div><b>Ubicación exacta <span class="optional">(recomendada)</span></b><p>Comparte un enlace de Google Maps o Waze para ayudar al mensajero a encontrar la entrada.</p></div></div>
<div class="map-row"><input id="fMap" type="url" inputmode="url" placeholder="Pega un enlace de Google Maps o Waze" oninput="mapUI()"><button type="button" class="map-paste" id="mapPaste" onclick="pasteMap()">Pegar enlace</button></div>
<div class="map-status" id="mapStatus" role="status" aria-live="polite"><span>✓ Enlace de ubicación recibido</span><a id="mapOpen" href="#" target="_blank" rel="noopener">Abrir y verificar</a></div>
<div class="map-error" id="mapError">Usa un enlace válido de Google Maps o Waze.</div>
<label class="location-later"><input type="checkbox" id="fLocationLater" onchange="locationLaterUI()"><span>Enviaré mi ubicación por Waze o WhatsApp después de confirmar el pedido.</span></label>
<button type="button" class="map-help" id="mapHelp" aria-expanded="false" onclick="toggleMapHelp()"><span>¿Cómo compartir mi ubicación?</span><span id="mapHelpIcon">＋</span></button>
<div class="map-tutorial" id="mapTutorial">
<div class="map-steps">
<div class="map-step"><div class="map-visual">📍</div><b>1. Marca la entrada</b><p>Abre Google Maps o Waze y marca el punto exacto de entrega.</p></div>
<div class="map-step"><div class="map-visual">↗️</div><b>2. Pulsa “Compartir”</b><p>Busca la opción Compartir ubicación o Compartir viaje.</p></div>
<div class="map-step"><div class="map-visual">🔗</div><b>3. Copia el enlace</b><p>Regresa a VivaBien y pega el enlace en el campo de arriba.</p></div>
</div><p class="tutorial-hint">Marca la entrada del edificio o residencial, no solamente el nombre del sector.</p>
</div>
</div>
<div class="fld"><label>Nota (opcional)</label><input id="fNota" placeholder="Referencia, horario..."></div>
</div>

<div class="box schedule-box" id="scheduleBox">
<div class="bt">🕒 Fecha y horario de entrega</div>
<p class="schedule-copy">Entregamos de 9:00 AM a 7:00 PM. Los pedidos realizados antes de las 6:00 PM pueden entregarse el mismo día.</p>
<div class="date-shortcuts" id="dateShortcuts">
<button type="button" class="date-choice on" id="dateToday" onclick="chooseDate('today')">Hoy<small id="todayText">Disponible antes de 6 PM</small></button>
<button type="button" class="date-choice" id="dateTomorrow" onclick="chooseDate('tomorrow')">Mañana<small id="tomorrowText"></small></button>
<button type="button" class="date-choice" id="dateOther" onclick="chooseDate('other')">Otra fecha<small>Día / Mes / Año</small></button>
</div>
<div class="custom-date" id="customDate">
<select id="deliveryDay" aria-label="Día" onchange="customDateChanged()"><option value="">Día</option></select>
<select id="deliveryMonth" aria-label="Mes" onchange="customDateChanged()"></select>
<select id="deliveryYear" aria-label="Año" onchange="customDateChanged()"></select>
</div>
<div class="time-choices" id="timeChoices">
<button type="button" class="time-choice" data-value="09:00-12:00" data-end="12" onclick="chooseTime(this)">9:00 AM – 12:00 PM</button>
<button type="button" class="time-choice" data-value="12:00-15:00" data-end="15" onclick="chooseTime(this)">12:00 PM – 3:00 PM</button>
<button type="button" class="time-choice" data-value="15:00-19:00" data-end="19" onclick="chooseTime(this)">3:00 PM – 7:00 PM</button>
<button type="button" class="time-choice on" data-value="09:00-19:00" data-end="19" onclick="chooseTime(this)">Cualquier horario · 9:00 AM – 7:00 PM</button>
</div>
<div class="schedule-note"><span>ℹ️</span><span>Este es tu horario preferido. Te confirmaremos la hora exacta por WhatsApp antes de la entrega.</span></div>
<div class="map-error" id="dateError">Selecciona una fecha válida.</div>
</div>

<div class="box" id="payBox">
<div class="bt">💳 ¿Cómo pagas?</div>
<div class="pay-note" id="codNote">La entrega contra pago solo está disponible en el Gran Santo Domingo. Para otras zonas usamos transferencia bancaria.</div>
<div class="pay">
<label class="on" id="lCod"><input type="radio" name="pay" value="cod" checked onchange="payUI()"> 🤝 Contra entrega (efectivo)</label>
<label id="lTra"><input type="radio" name="pay" value="transfer" onchange="payUI()"> 🏦 Transferencia bancaria</label>
</div>
<div class="bank" id="bankPanel">
<div class="steps">
<div><div class="sn">1</div><div class="st">Confirma<br>tu pedido</div></div>
<div><div class="sn">2</div><div class="st">Transfiere a<br>una cuenta</div></div>
<div><div class="sn">3</div><div class="st">Envía el comprobante<br>por WhatsApp</div></div>
</div>
__BANKS__
<div class="remind">📸 Por favor envía el comprobante de transferencia por WhatsApp al <b>+1 (809) 281-1992</b>. Tu pedido se despacha al confirmar el pago.</div>
</div>
</div>

<div class="box tot" id="totBox">
<div class="ln">Subtotal <b id="tSub">RD$ 0</b></div>
<div class="cpn"><input id="cpnCode" placeholder="Código de descuento" autocapitalize="characters" onkeydown="if(event.key==='Enter'){event.preventDefault();applyCoupon()}"><button id="cpnBtn" type="button" onclick="applyCoupon()">Aplicar</button></div>
<div class="cpn-msg" id="cpnMsg"></div>
<div class="ln disc" id="discLn" style="display:none">Descuento (<span id="discCode"></span>) <b id="tDisc">- RD$ 0</b></div>
<div class="ship-quote" id="shipQuote"><span>Envío</span><b id="tShip">Selecciona tu sector</b><small id="shipEta">Verás el costo y el tiempo antes de confirmar.</small></div>
<div class="gt"><span id="totalLabel">Total</span> <span id="tTot">RD$ 0</span></div>
<button class="btn-conf" id="btnConf" onclick="confirmar()">🛡️ Confirmar pedido</button>
<div class="sub-note">Al confirmar, tu pedido queda registrado. Después puedes continuar por WhatsApp si lo deseas.</div>
</div>
</div>

<div class="ok" id="okScreen">
<div class="ck">✓</div>
<h2>¡Pedido confirmado!</h2>
<p>Tu pedido <b id="okId"></b> quedó registrado correctamente.<br>Te contactaremos para coordinar la entrega.</p>
<div class="ok-actions"><a class="ok-wa" id="okWa" href="#" target="_blank">Continuar por WhatsApp</a><a class="ok-shop" href="./">Seguir comprando</a></div>
</div>

<script>
var WA='__WA__';
var COUPON=null; // {code,kind,value} —— 已应用的优惠券
var TIER_PRICES=__TIER_PRICES__;
var DELIVERY_DATE='',DELIVERY_WINDOW='09:00-19:00',DELIVERY_MODE='today';
var MONTHS_ES=['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
// 运费状态机：完全由 data/shipping_zones.json 驱动，JS 不硬编码任何 sector/价格
// SHIP = null(未选) | {other:true}(Otro sector) | {price,eta,zone,sector}(精确报价)
var ZONES=null, ZFAIL=false, DEF_NOTE='', SHIP=null, FREE=null;
var OTHER_LABEL='Otro sector / No está en la lista';
function money(v){return 'RD$ '+Math.round(v).toLocaleString('en-US')}
function isMetro(){return document.getElementById('sectorFld').style.display!=='none'}
// 大圣多明哥包邮：运费已含在商品标价里，结账不再另收。开关在 data/shipping_zones.json
function freeMetro(){return !!(FREE&&FREE.activo)&&isMetro()}
function shipFee(){if(freeMetro())return 0;return (SHIP&&SHIP.price!=null)?Number(SHIP.price):null}
function santoParts(){var ps=new Intl.DateTimeFormat('en-US',{timeZone:'America/Santo_Domingo',year:'numeric',month:'numeric',day:'numeric',hour:'numeric',hourCycle:'h23'}).formatToParts(new Date()),o={};ps.forEach(function(x){if(x.type!=='literal')o[x.type]=Number(x.value)});return o}
function localDate(p){return new Date(p.year,p.month-1,p.day)}
function isoDate(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
function dateLabel(d){return new Intl.DateTimeFormat('es-DO',{day:'numeric',month:'short'}).format(d)}
function isLocationUrl(v){return /^(https:\/\/)?(maps\.app\.goo\.gl|www\.google\.[^/]+\/maps|goo\.gl\/maps|waze\.com\/ul|www\.waze\.com\/live-map|ul\.waze\.com)/i.test((v||'').trim())}
function mapUI(showError){var inp=document.getElementById('fMap'),v=inp.value.trim(),ok=isLocationUrl(v),later=document.getElementById('fLocationLater').checked,st=document.getElementById('mapStatus'),er=document.getElementById('mapError');st.classList.toggle('show',ok||later);er.classList.toggle('show',!!v&&!ok&&!!showError);if(ok){st.querySelector('span').textContent='✓ Enlace de ubicación recibido';document.getElementById('mapOpen').style.display='inline';document.getElementById('mapOpen').href=/^https:\/\//i.test(v)?v:'https://'+v}else if(later){st.querySelector('span').textContent='✓ Puedes enviar la ubicación después de confirmar';document.getElementById('mapOpen').style.display='none'}else{document.getElementById('mapOpen').style.display='none'}}
async function pasteMap(){try{document.getElementById('fMap').value=await navigator.clipboard.readText();mapUI(true)}catch(e){document.getElementById('fMap').focus()}}
function locationLaterUI(){var on=document.getElementById('fLocationLater').checked;document.getElementById('fMap').disabled=on;document.getElementById('mapPaste').disabled=on;if(on)document.getElementById('mapError').classList.remove('show');mapUI(false)}
function toggleMapHelp(){var t=document.getElementById('mapTutorial'),b=document.getElementById('mapHelp'),open=t.classList.toggle('show');b.setAttribute('aria-expanded',open?'true':'false');document.getElementById('mapHelpIcon').textContent=open?'−':'＋'}
function populateDays(){var ds=document.getElementById('deliveryDay'),m=Number(document.getElementById('deliveryMonth').value),y=Number(document.getElementById('deliveryYear').value),keep=Number(ds.value)||1,max=new Date(y,m,0).getDate();ds.innerHTML='<option value="">Día</option>';for(var d=1;d<=max;d++)ds.innerHTML+='<option value="'+d+'">'+d+'</option>';ds.value=String(Math.min(keep,max))}
function initDeliveryUI(){var p=santoParts(),today=localDate(p),tomorrow=new Date(today);tomorrow.setDate(today.getDate()+1);var ms=document.getElementById('deliveryMonth'),ys=document.getElementById('deliveryYear');ms.innerHTML=MONTHS_ES.map(function(x,i){return '<option value="'+(i+1)+'">'+x+'</option>'}).join('');ys.innerHTML='<option value="'+p.year+'">'+p.year+'</option><option value="'+(p.year+1)+'">'+(p.year+1)+'</option>';ms.value=String(today.getMonth()+1);ys.value=String(today.getFullYear());populateDays();document.getElementById('deliveryDay').value=String(today.getDate());document.getElementById('tomorrowText').textContent=dateLabel(tomorrow);if(p.hour>=18){document.getElementById('dateToday').disabled=true;document.getElementById('dateToday').classList.remove('on');document.getElementById('todayText').textContent='Cerrado después de 6 PM';document.getElementById('dateTomorrow').classList.add('on');DELIVERY_MODE='tomorrow';DELIVERY_DATE=isoDate(tomorrow)}else DELIVERY_DATE=isoDate(today);updateTimeAvailability()}
function chooseDate(mode){var b=document.getElementById(mode==='today'?'dateToday':mode==='tomorrow'?'dateTomorrow':'dateOther');if(b.disabled)return;DELIVERY_MODE=mode;document.querySelectorAll('.date-choice').forEach(function(x){x.classList.toggle('on',x===b)});document.getElementById('customDate').classList.toggle('show',mode==='other');var p=santoParts(),d=localDate(p);if(mode==='tomorrow')d.setDate(d.getDate()+1);if(mode!=='other')DELIVERY_DATE=isoDate(d);else customDateChanged();document.getElementById('dateError').classList.remove('show');updateTimeAvailability()}
function customDateChanged(){populateDays();var d=Number(document.getElementById('deliveryDay').value),m=Number(document.getElementById('deliveryMonth').value),y=Number(document.getElementById('deliveryYear').value);DELIVERY_DATE=d&&m&&y?isoDate(new Date(y,m-1,d)):'';var p=santoParts(),min=localDate(p);if(p.hour>=18)min.setDate(min.getDate()+1);document.getElementById('dateError').classList.toggle('show',!DELIVERY_DATE||DELIVERY_DATE<isoDate(min));updateTimeAvailability()}
function updateTimeAvailability(){var p=santoParts(),today=isoDate(localDate(p)),same=DELIVERY_DATE===today;document.querySelectorAll('.time-choice').forEach(function(b){b.disabled=same&&p.hour>=Number(b.dataset.end);if(b.disabled)b.classList.remove('on')});var on=document.querySelector('.time-choice.on:not(:disabled)');if(!on){var avail=[].slice.call(document.querySelectorAll('.time-choice:not(:disabled)')).pop();if(avail){avail.classList.add('on');DELIVERY_WINDOW=avail.dataset.value}}}
function chooseTime(b){if(b.disabled)return;document.querySelectorAll('.time-choice').forEach(function(x){x.classList.remove('on')});b.classList.add('on');DELIVERY_WINDOW=b.dataset.value}
function loadZones(){
 fetch('data/shipping_zones.json').then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})
 .then(function(d){ZONES=d.zones||[];DEF_NOTE=d.default_note||'';FREE=d.envio_gratis_metro||null;buildSectorSelect();sectorUI()})
 .catch(function(e){ZFAIL=true;console.warn('shipping_zones.json 加载失败，运费按 por confirmar 处理:',e);buildSectorSelect();sectorUI()});
}
function buildSectorSelect(){
 var sel=document.getElementById('sector-select');sel.innerHTML='';
 var ph=document.createElement('option');ph.value='';ph.textContent='Selecciona tu sector';ph.disabled=true;ph.selected=true;sel.appendChild(ph);
 var seen={};
 (ZONES||[]).forEach(function(z){
  var og=document.createElement('optgroup');
  og.label='Zona '+z.id+' · RD$'+Number(z.price).toLocaleString('en-US')+' — '+(z.eta||'');
  z.sectors.slice().sort(function(a,b){return a.localeCompare(b,'es')}).forEach(function(s){
   if(seen[s]){console.warn('sector 跨 zone 重名，按第一个匹配:',s);return}
   seen[s]=z.id;
   var o=document.createElement('option');o.value=s;o.textContent=s;og.appendChild(o);
  });
  sel.appendChild(og);
 });
 var oo=document.createElement('option');oo.value='__other__';oo.textContent=OTHER_LABEL;sel.appendChild(oo);
 // 回访自动预选上次的 sector
 try{var mem=localStorage.getItem('vb_sector');
  if(mem&&[].some.call(sel.options,function(o){return o.value===mem})){sel.value=mem}}catch(e){}
}
function findZone(sector){
 for(var i=0;i<(ZONES||[]).length;i++)
  if(ZONES[i].sectors.indexOf(sector)>=0)return ZONES[i];
 return null;
}
function sectorUI(){
 var sel=document.getElementById('sector-select'),v=sel.value,note=document.getElementById('shipNote');
 note.style.display='none';
 if(!isMetro()){SHIP={other:true};paintTotals();return}
 if(!v){SHIP=null}
 else if(v==='__other__'||ZFAIL){SHIP={other:true};
  if(DEF_NOTE){note.textContent='ℹ️ '+DEF_NOTE;note.style.display='block'}}
 else{var z=findZone(v);
  SHIP=z?{price:z.price,eta:z.eta,zone:z.id,sector:v}:{other:true};
  if(z){try{vbTrack('shipping_quote','',{shipping_fee:z.price,shipping_zone:z.id,delivery_estimate:z.eta})}catch(e){}}}
 try{if(v)localStorage.setItem('vb_sector',v)}catch(e){}
 paintTotals();
}
function tierRule(it){var embedded=Number(it.tier_price)>0?{min_qty:Number(it.tier_min_qty)||2,unit_price:Number(it.tier_price)}:null;return embedded||TIER_PRICES[it.sku]||null}
function effectiveUnit(it){var rule=tierRule(it);return rule&&it.qty>=rule.min_qty?rule.unit_price:Number(it.price)}
function itemTotal(it){return effectiveUnit(it)*it.qty}
function subtotal(){return vbCart().reduce(function(a,it){return a+itemTotal(it)},0)}
function calcDiscount(sub){
 if(!COUPON)return 0;
 var d=COUPON.kind==='percent'?sub*COUPON.value/100:COUPON.value;
 return Math.min(d,sub);
}
function paintTotals(){
 var sub=subtotal(),disc=calcDiscount(sub),productTotal=sub-disc;
 var fee=shipFee(),tot=productTotal+(fee||0);
 document.getElementById('tSub').textContent=money(sub);
 var dl=document.getElementById('discLn');
 if(disc>0){dl.style.display='flex';
  document.getElementById('tDisc').textContent='- '+money(disc);
  document.getElementById('discCode').textContent=COUPON.code;
 }else{dl.style.display='none';}
 var tShip=document.getElementById('tShip'),eta=document.getElementById('shipEta');
 tShip.classList.remove('free');
 if(freeMetro()){
  // 不管有没有选 sector 都直接显示 GRATIS，价格不再"最后一步才揭晓"
  tShip.textContent=(FREE&&FREE.etiqueta)||'GRATIS';tShip.classList.add('free');
  eta.textContent=(SHIP&&SHIP.eta)||(FREE&&FREE.eta_default)||'';
 }
 else if(fee!=null){tShip.textContent=money(fee);eta.textContent=(SHIP&&SHIP.eta)||'';}
 else if(SHIP&&SHIP.other){tShip.textContent='por confirmar';eta.textContent='Te confirmamos el costo del envío por WhatsApp.';}
 else{tShip.textContent='Selecciona tu sector';eta.textContent='Verás el costo y el tiempo antes de confirmar.';}
 document.getElementById('tTot').textContent=money(tot);
 // 包邮时按钮不再因为"没选 sector"而置灰；sector 仍是必填，改由提交时的字段校验提示
 var btn=document.getElementById('btnConf');
 var needSector=isMetro()&&!ZFAIL&&!SHIP&&!freeMetro();
 btn.disabled=needSector;
 btn.textContent=needSector?'Selecciona tu sector para calcular el envío'
  :'🛡️ Confirmar pedido · '+money(tot)+(fee==null?' + envío':'');
}
function applyCoupon(){
 var code=document.getElementById('cpnCode').value.trim().toUpperCase();
 var msg=document.getElementById('cpnMsg'),btn=document.getElementById('cpnBtn');
 if(!code){msg.className='cpn-msg err';msg.textContent='Escribe un código.';return;}
 btn.disabled=true;btn.textContent='...';
 fetch('__API__/api/coupon/validate',{method:'POST',credentials:'include',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({code:code,subtotal:subtotal()})})
 .then(function(r){return r.json()}).then(function(d){
  btn.disabled=false;btn.textContent='Aplicar';
  if(d.valid){COUPON={code:d.code,kind:d.kind,value:d.value};
   msg.className='cpn-msg ok';
   msg.textContent='✓ Cupón aplicado'+(d.kind==='percent'?' ('+d.value+'% OFF)':' (- '+money(d.value)+')');
  }else{COUPON=null;
   var m={min_order:'No alcanza el mínimo para este cupón',expired:'Cupón vencido',
    used_up:'Cupón agotado',invalid:'Código inválido',empty:'Escribe un código'};
   msg.className='cpn-msg err';msg.textContent=m[d.reason]||'Código inválido';}
  paintTotals();
 }).catch(function(){btn.disabled=false;btn.textContent='Aplicar';
  msg.className='cpn-msg err';msg.textContent='Error, intenta de nuevo.';});
}
function render(){
 var c=vbCart(),box=document.getElementById('items');
 if(!c.length){
  document.getElementById('itemsBox').innerHTML='<div class="empty">Tu carrito está vacío.<br><br><a href="./">← Ver productos</a></div>';
  ['formBox','payBox','totBox'].forEach(function(i){document.getElementById(i).style.display='none'});
  return;}
 box.innerHTML=c.map(function(it,i){var unit=effectiveUnit(it),tier=unit<Number(it.price);
  return '<div class="ci"><img src="images/'+it.img+'" onerror="this.style.opacity=0">'
  +'<div class="t"><div class="nm">'+it.title+'</div><div class="pr">'+money(unit)+' por unidad</div>'
  +(tier?'<small class="tier-note">✓ Precio por cantidad aplicado</small>':'')
  +'<div class="qty"><button onclick="qty('+i+',-1)">−</button><span>'+it.qty+'</span><button onclick="qty('+i+',1)">+</button></div></div>'
  +'<button class="rm" onclick="rm('+i+')">✕</button></div>';}).join('');
 try{if(!sessionStorage.getItem('vb_checkout_started')){sessionStorage.setItem('vb_checkout_started','1');c.forEach(function(it){vbTrack('checkout_start',it.sku,{qty:it.qty,price:effectiveUnit(it),cart_total:subtotal(),selected_color:it.color||'',source_section:'cart_page'})})}}catch(e){}
 paintTotals();
}
function qty(i,d){var c=vbCart(),it=c[i];it.qty+=d;if(it.qty<1)it.qty=1;vbSave(c);render();
 try{vbTrack('cart_update',it.sku,{qty:it.qty,price:effectiveUnit(it),cart_total:subtotal(),selected_color:it.color||'',source_section:d>0?'cart_increase':'cart_decrease'})}catch(e){}}
function rm(i){var c=vbCart(),it=c[i];c.splice(i,1);vbSave(c);render();try{vbTrack('cart_remove',it.sku,{qty:it.qty,price:effectiveUnit(it),cart_total:subtotal(),selected_color:it.color||'',source_section:'cart_remove'})}catch(e){}}
function payUI(){
 var t=document.querySelector('input[name=pay]:checked').value;
 document.getElementById('lCod').classList.toggle('on',t==='cod');
 document.getElementById('lTra').classList.toggle('on',t==='transfer');
 document.getElementById('bankPanel').classList.toggle('show',t==='transfer');
}
var PROVS=["","Distrito Nacional (Santo Domingo)","Santo Domingo (provincia)","Santiago","La Altagracia","La Vega","San Cristóbal","Puerto Plata","Duarte","San Pedro de Macorís","La Romana","Espaillat","Azua","Barahona","Monseñor Nouel","Sánchez Ramírez","Peravia","Valverde","Monte Plata","Hato Mayor","El Seibo","Samaná","María Trinidad Sánchez","Hermanas Mirabal","Bahoruco","Independencia","Elías Piña","San Juan","Dajabón","Santiago Rodríguez","Monte Cristi","Pedernales","San José de Ocoa"];
function fillSel(id,arr){var s=document.getElementById(id);
 s.innerHTML='';arr.forEach(function(x){var o=document.createElement('option');o.value=x;o.textContent=x||'Selecciona una provincia';if(!x)o.disabled=true;o.selected=!x;s.appendChild(o)});}
function provUI(){
 var prov=document.getElementById('fProv').value,isDN=prov.indexOf('Distrito Nacional')===0,isSDP=prov.indexOf('Santo Domingo (provincia)')===0,metro=isDN||isSDP;
 document.getElementById('sectorFld').style.display=metro?'block':'none';
 document.getElementById('cityFld').style.display=metro?'none':'block';
 document.getElementById('locationExtra').classList.toggle('show',metro);
 document.getElementById('scheduleBox').classList.toggle('show',metro);
 // 货到付款仅限大圣多明各；外省强制转账（纯前端判断）
 var cod=document.querySelector('input[name=pay][value=cod]'),tra=document.querySelector('input[name=pay][value=transfer]');
 cod.disabled=!metro;document.getElementById('lCod').style.display=metro?'flex':'none';
 document.getElementById('codNote').classList.toggle('show',!!prov&&!metro);
 if(prov&&!metro)tra.checked=true;
 payUI();sectorUI();
}
fillSel('fProv',PROVS);initDeliveryUI();loadZones();paintTotals();
function fieldState(id,bad){var x=document.getElementById(id);if(x)x.classList.toggle('invalid',!!bad)}
async function confirmar(){
 var c=vbCart();if(!c.length)return;
 var nom=document.getElementById('fNom').value.trim(),
     tel=document.getElementById('fTel').value.trim(),
     dir=document.getElementById('fDir').value.trim(),
     nota=document.getElementById('fNota').value.trim();
 var prov=document.getElementById('fProv').value;
 var metro=isMetro();
 var mapUrl=metro?document.getElementById('fMap').value.trim():'',locationLater=metro&&document.getElementById('fLocationLater').checked;
 var selV=document.getElementById('sector-select').value;
 var zona=metro?(selV==='__other__'?OTHER_LABEL:selV):document.getElementById('fCity').value.trim();
 var pNow=santoParts(),minDate=localDate(pNow);if(pNow.hour>=18)minDate.setDate(minDate.getDate()+1);
 var mapBad=!!mapUrl&&!isLocationUrl(mapUrl),dateBad=metro&&(!DELIVERY_DATE||DELIVERY_DATE<isoDate(minDate)||!DELIVERY_WINDOW);
 fieldState('fldNom',!nom);fieldState('fldTel',tel.replace(/\D/g,'').length<10);fieldState('fldProv',!prov);
 fieldState('sectorFld',metro&&!selV&&!ZFAIL);fieldState('cityFld',!metro&&!zona);fieldState('fldDir',!dir);
 document.getElementById('mapError').classList.toggle('show',mapBad);document.getElementById('dateError').classList.toggle('show',dateBad);
 if(!nom||tel.replace(/\D/g,'').length<10||!prov||(metro&&!selV&&!ZFAIL)||(!metro&&!zona)||!dir||mapBad||dateBad){
  try{c.forEach(function(it){vbTrack('checkout_error',it.sku,{qty:it.qty,price:effectiveUnit(it),cart_total:subtotal(),source_section:'delivery_validation'})})}catch(e){}
  var inv=document.querySelector('.fld.invalid')||document.querySelector('.map-error.show');if(inv)inv.scrollIntoView({behavior:'smooth',block:'center'});return;}
 var fee=shipFee();
 var loc=prov+' · '+zona;
 var pay=document.querySelector('input[name=pay]:checked').value;
 var oid='VB-'+Math.random().toString(36).slice(2,7).toUpperCase();
 var sub=0,lines=c.map(function(it){var lineTotal=itemTotal(it);sub+=lineTotal;
   return it.qty+'x '+it.title+' ('+it.sku+') — '+money(lineTotal)});
 var disc=calcDiscount(sub),productTotal=sub-disc,tot=productTotal+(fee||0);
 var shipEtaTxt=(SHIP&&SHIP.eta)||(freeMetro()&&FREE?FREE.eta_default:'')||'';
 var shippingText=freeMetro()?('GRATIS'+(shipEtaTxt?' ('+shipEtaTxt+')':''))
  :(fee!=null?money(fee)+(shipEtaTxt?' ('+shipEtaTxt+')':''):'por confirmar');
 var msg='🛒 *Pedido '+oid+'*\\n'+lines.join('\\n')
  +(disc>0?'\\n——\\nSubtotal: '+money(sub)+'\\n🏷️ Cupón '+COUPON.code+': - '+money(disc):'')
  +'\\nSector: '+zona
  +'\\n🚚 Envío: '+shippingText
  +'\\n*Total: '+money(tot)+(fee==null?' + envío':'')+'*'
  +'\\n——\\n👤 '+nom+'\\n📞 '+tel+'\\n📍 '+loc+'\\n🏠 '+dir
  +(metro?'\\n🗺️ Ubicación: '+(mapUrl||(locationLater?'La enviará por Waze o WhatsApp después':'No proporcionada')):'')
  +(metro?'\\n🕒 Preferencia: '+DELIVERY_DATE+' · '+DELIVERY_WINDOW:'')
  +(nota?'\\n📝 '+nota:'')
  +'\\n💳 Pago: '+(pay==='cod'?'Contra entrega (efectivo)':'Transferencia bancaria — enviaré el comprobante')
  +(pay==='transfer'?'\\n\\nCuentas:\\n__BANKLINES__':'');
 var btn=document.getElementById('btnConf');
 btn.disabled=true;btn.textContent='Guardando pedido...';
 try{
  var orderRes=await fetch('__API__/api/order',{method:'POST',credentials:'include',
   headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:oid,
    customer_name:nom,phone:tel,province:prov,zone:zona,address:dir,note:nota,
    map_url:mapUrl,location_followup:locationLater?1:0,
    preferred_delivery_date:metro?DELIVERY_DATE:'',preferred_delivery_window:metro?DELIVERY_WINDOW:'',
    payment_method:pay,shipping_zone:(SHIP&&SHIP.zone)||(metro?'otro':'interior'),
    shipping_fee:fee||0,shipping_fee_min:fee||0,shipping_fee_max:fee||0,
    delivery_estimate:shipEtaTxt||'por confirmar',
    subtotal:sub,discount:disc,total:tot,total_min:tot,total_max:tot,
    coupon_code:COUPON?COUPON.code:'',tracking:vbContext(),items:c.map(function(it){return {
     sku:it.sku,title:it.title,image:it.img,unit_price:effectiveUnit(it),quantity:it.qty}})})});
  var orderData=await orderRes.json();
  if(!orderRes.ok||!orderData.ok)throw new Error(orderData.error||'No se pudo guardar el pedido');
 }catch(e){btn.disabled=false;paintTotals();try{c.forEach(function(it){vbTrack('checkout_error',it.sku,{qty:it.qty,price:effectiveUnit(it),cart_total:tot,source_section:'order_api'})})}catch(_e){}
  alert('No pudimos guardar tu pedido. Revisa tu conexión e intenta de nuevo.');return;}
 try{fbq('track','Purchase',{content_ids:c.map(function(x){return x.sku}),content_type:'product',
  num_items:c.reduce(function(a,b){return a+b.qty},0),order_id:oid,
  value:Math.round(tot/__META_DOP_PER_USD__*100)/100,currency:'USD',local_value_dop:tot})}catch(e){}
 try{c.forEach(function(it){vbTrack('checkout',it.sku,{order_id:oid,qty:it.qty,price:effectiveUnit(it),cart_total:tot,selected_color:it.color||'',source_section:'order_confirmed',coupon:COUPON?COUPON.code:''})})}catch(e){}
 if(COUPON){try{fetch('__API__/api/coupon/redeem',{method:'POST',credentials:'include',keepalive:true,
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({code:COUPON.code,order_id:oid})}).catch(function(){})}catch(e){}}
 localStorage.removeItem('vb_cart');localStorage.removeItem('vb_campaign_coupon');vbBadge();
 document.getElementById('okId').textContent=oid;
 document.getElementById('okWa').href='https://wa.me/'+WA+'?text='+encodeURIComponent(msg);
 document.getElementById('main').style.display='none';
 document.getElementById('okScreen').style.display='block';
 window.scrollTo(0,0);
}
try{localStorage.removeItem('vb_campaign_coupon')}catch(e){}
render();payUI();
</script>"""
    body = (body.replace("__BANKS__", banks_html).replace("__WA__", WHATSAPP)
                .replace("__BANKLINES__", bank_lines).replace("__API__", API_BASE)
                .replace("__TIER_PRICES__", tier_prices_json)
                .replace("__META_DOP_PER_USD__", f"{META_DOP_PER_USD:.4f}"))
    return page(f"Tu compra — {SITE_NAME}", body,
                pixel_extra="fbq('track','InitiateCheckout');",
                desc="Carrito de compras VivaBien — contra entrega en Gran Santo Domingo o transferencia nacional.",
                canonical=public_url("carrito.html"), robots="noindex,follow")

# ---------- 专题合集 ----------
import json as _json, hashlib as _hashlib
COLLECTIONS_PATH = "data/collections.json"
COLL_GRADIENTS = [("#0F6E56", "#1D9E75"), ("#7a4b12", "#b9791f"), ("#185FA5", "#378ADD"),
                  ("#534AB7", "#7F77DD"), ("#993C1D", "#D85A30"), ("#0C447C", "#2563D9")]

def load_collections():
    if os.path.isfile(COLLECTIONS_PATH):
        try:
            with open(COLLECTIONS_PATH, encoding="utf-8") as f:
                data = _json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"⚠️  collections.json 解析失败: {e}")
    return []

def slugify(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "coleccion"

def coll_grad(slug):
    i = int(_hashlib.md5(slug.encode()).hexdigest(), 16) % len(COLL_GRADIENTS)
    return COLL_GRADIENTS[i]

def product_card(p, rel=""):
    sale = discount_info(p)
    if sale:
        price_html = (f'<div class="price-stack"><span class="current">{fmt_price(p["price"])}</span>'
                      f'<del>{fmt_price(p["old_price"])}</del></div>'
                      f'<span class="saving">Ahorras {fmt_price(sale["saving"])}</span>')
    else:
        price_html = (f'<div class="price-stack"><span class="current">{fmt_price(p["price"])}</span></div>'
                      if p["price"] is not None else '<span class="ask">Consultar</span>')
    sale_badge = f'<span class="sale-badge">-{sale["percent"]}%</span>' if sale else ""
    label = f'<span class="offer-label">{esc(p["label"])}</span>' if p.get("label") else ""
    add_button = (f'<button class="card-add" type="button" aria-label="Agregar al carrito" '
                  f'data-sku="{esc(p["sku"])}" data-handle="{esc(p["handle"])}" '
                  f'data-title="{esc(p["title"])}" data-price="{p["price"]}" data-img="{esc(p["img"])}" '
                  f'onclick="vbCardAdd(event,this)">{BAG_SVG}</button>'
                  if p["price"] is not None else "")
    return (f'<article class="card" data-g="{esc(p["group"])}" data-s="{esc(p["sub"])}" '
            f'data-q="{esc(snorm(p["title"] + " " + p["sub"] + " " + p["group"]))}" '
            f'><a class="card-link" href="{rel}producto/{p["handle"]}">'
            f'<div class="imgbox"><img src="{rel}images/{esc(p["img"])}" alt="{esc(p["title"])}" '
            f'loading="lazy" onerror="this.style.display=\'none\'">'
            f'<span class="badge">{esc(p["sub"])}</span>{sale_badge}</div>'
            f'<div class="info"><div class="nm">{esc(p["title"])}</div>{label}'
            f'<div class="pr">{price_html}</div></div></a>{add_button}</article>')

def coleccion_page(c, prods):
    """专题落地页：Hero(可配图/CTA) + 信任条 + 快速筛选 + 商品网格 + 底部WhatsApp CTA"""
    c0, c1 = coll_grad(c["slug"])
    cards = "".join(product_card(p, rel="../") for p in prods)
    # 专题内子分类快速筛选
    subs = {}
    for p in prods:
        subs[p["sub"]] = subs.get(p["sub"], 0) + 1
    chips_html = ""
    if len(subs) > 1:
        chips = [f'<span class="cchip on" data-s="*">Todos ({len(prods)})</span>'] + [
            f'<span class="cchip" data-s="{esc(s)}">{esc(s)} · {n}</span>'
            for s, n in sorted(subs.items(), key=lambda kv: -kv[1])]
        chips_html = f'<div class="cchips">{"".join(chips)}</div>'
    # Hero：可选背景图（collections.json 的 image 字段=images/里的文件名）
    img = (c.get("image") or "").strip()
    if img:
        hero_style = (f"background:linear-gradient(120deg,{c0}D9,{c1}D9),"
                      f"url('../images/{esc(img)}') center/cover")
    else:
        hero_style = f"background:linear-gradient(120deg,{c0},{c1})"
    cta = esc((c.get("cta") or "").strip() or f"Ver los {len(prods)} productos")
    body = f"""{header("../")}
<div class="tbanner" style="{hero_style}">
<a class="bk" href="../">← Volver a la tienda</a>
<h2>{esc(c["title"])}</h2>
{f'<p>{esc(c.get("subtitle",""))}</p>' if c.get("subtitle") else ""}
<a class="tcta" href="#cgrid">{cta} →</a>
</div>
<div class="wrap">
<div class="valstrip">
<div>🚚 Envíos a<br>todo el país</div>
<div>🤝 Contra entrega<br>en Sto. Dgo.</div>
<div>✅ Producto<br>verificado</div>
</div>
{chips_html}
<div class="count"><span id="cN">{len(prods)}</span> productos</div>
<div class="grid" id="cgrid">{cards}</div>
<div class="cta-final">
<b>¿No encuentras lo que buscas?</b>
<p>Escríbenos y te ayudamos a encontrarlo</p>
<a href="https://wa.me/{WHATSAPP}" target="_blank" onclick="fbq('track','Contact')">{WA_SVG} Escríbenos por WhatsApp</a>
</div>
</div>
<script>
document.querySelectorAll('.cchip').forEach(function(ch){{ch.onclick=function(){{
 document.querySelectorAll('.cchip').forEach(function(x){{x.classList.remove('on')}});
 ch.classList.add('on');var s=ch.dataset.s,n=0;
 document.querySelectorAll('#cgrid .card').forEach(function(cd){{
  var ok=s==='*'||cd.dataset.s===s;cd.style.display=ok?'':'none';if(ok)n++;}});
 document.getElementById('cN').textContent=n;}};}});
</script>"""
    return page(f"{c['title']} — {SITE_NAME}", body, wa_float=True,
                desc=(c.get("subtitle") or c["title"])[:150],
                canonical=public_url(f"coleccion/{c['slug']}.html"), rel="../")

def coming_soon_collection_page(c):
    """尚未上架商品的专题占位页；保留正式路由，后续可直接填充商品。"""
    image = str(c.get("image") or "").strip()
    media = (f'<img src="../images/{esc(image)}" alt="{esc(c["title"])}">' if image else "")
    body = f"""{header("../")}
<main class="soon-page">
 <div class="soon-media">{media}</div>
 <div class="soon-copy">
  <span>Próximamente</span>
  <h1>{esc(c['title'])}</h1>
  <p>{esc(c.get('subtitle') or 'Estamos preparando esta colección para ti.')}</p>
  <a href="../">Volver a la tienda</a>
 </div>
</main>
<style>
.soon-page{{min-height:calc(100vh - 68px);display:grid;background:#F5F7FB}}
.soon-media{{min-height:44vh;background:#E9EDF4;overflow:hidden}}
.soon-media img{{width:100%;height:100%;object-fit:cover}}
.soon-copy{{padding:34px 20px 52px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center}}
.soon-copy span{{color:#2563D9;font-size:11px;font-weight:800;text-transform:uppercase}}
.soon-copy h1{{font-size:36px;line-height:1.05;margin:8px 0 12px}}
.soon-copy p{{max-width:480px;color:#667085;line-height:1.6}}
.soon-copy a{{margin-top:22px;display:inline-flex;align-items:center;min-height:46px;padding:0 18px;border-radius:8px;background:#2563D9;color:#fff;font-weight:800}}
@media(min-width:760px){{.soon-page{{grid-template-columns:1.05fr .95fr}}.soon-media{{min-height:calc(100vh - 68px)}}.soon-copy{{padding:60px}}.soon-copy h1{{font-size:54px}}}}
</style>"""
    return page(f"{c['title']} | Próximamente | {SITE_NAME}", body, wa_float=True,
                desc=(c.get("subtitle") or f"Próximamente: {c['title']} en VivaBien.")[:150],
                canonical=public_url(f"coleccion/{c['slug']}.html"), rel="../")

def featured_html(collections, by_sku):
    """首页顶部专题切换器：普通专题、独立落地页和待上新专题共用。"""
    tabs, slides = [], []
    visible = []
    for c in collections:
        prods = [by_sku[s] for s in c.get("skus", []) if s in by_sku]
        image = str(c.get("image") or (prods[0]["img"] if prods else "")).strip()
        if not image:
            continue
        visible.append((c, image))
    for i, (c, image) in enumerate(visible):
        active = " on" if i == 0 else ""
        href = str(c.get("landing") or f'coleccion/{c["slug"]}.html').strip()
        cta = str(c.get("cta") or "Ver colección").strip()
        kick = "Próximamente" if c.get("coming_soon") else "Colección destacada"
        tabs.append(f'<button class="feat-tab{active}" type="button" role="tab" '
                    f'aria-selected="{str(i == 0).lower()}" data-feat="{i}">{esc(c["title"])}</button>')
        slides.append(f'<a class="feat-slide{active}" data-feat-panel="{i}" href="{esc(href)}">'
                      f'<img src="images/{esc(image)}" alt="{esc(c["title"])}" loading="lazy">'
                      f'<span class="feat-copy"><span class="feat-kick">{esc(kick)}</span>'
                      f'<h3>{esc(c["title"])}</h3><p>{esc(c.get("subtitle", ""))}</p>'
                      f'<span class="feat-go">{esc(cta)} →</span></span></a>')
    if not slides:
        return ""
    return (f'<section class="feat-switcher" aria-label="Colecciones destacadas">'
            f'<div class="feat-tabs" role="tablist">{"".join(tabs)}</div>'
            f'<div class="feat-stage">{"".join(slides)}</div></section>'
            '<script>(function(){var ts=document.querySelectorAll(".feat-tab"),'
            'ps=document.querySelectorAll(".feat-slide");ts.forEach(function(t){t.onclick=function(){'
            'var n=t.dataset.feat;ts.forEach(function(x){var on=x===t;x.classList.toggle("on",on);'
            'x.setAttribute("aria-selected",on)});ps.forEach(function(x){x.classList.toggle("on",'
            'x.dataset.featPanel===n)})}})})();</script>')

PROMISE_HTML = """<div class="promise-strip" aria-label="Compromisos de servicio">
<div>🚚 Entrega 24-72 horas</div><div>💵 Pagas al recibir</div><div>↩️ Garantía de 7 días</div>
</div>"""

def best_sellers_html(products):
    configured = load_json(FEATURED_PATH, [])
    if isinstance(configured, dict):
        configured = configured.get("skus", [])
    configured = [str(x).strip() for x in configured if str(x).strip()]
    order = {sku: i for i, sku in enumerate(configured)}
    picks = [p for p in products if p.get("featured") or p["sku"] in order]
    picks.sort(key=lambda p: (order.get(p["sku"], 9999), not p.get("featured"), p["title"]))
    picks = picks[:10]
    if not picks:
        return ""
    cards = "".join(product_card(p) for p in picks)
    return (f'<section class="home-section"><div class="home-section-head"><div><h2>🔥 Más Vendidos</h2>'
            f'<p>Los favoritos de nuestros clientes</p></div></div><div class="best-row">{cards}</div></section>')

def reviews_html():
    reviews = load_json(REVIEWS_PATH, [])
    if not isinstance(reviews, list):
        return ""
    reviews = [r for r in reviews if isinstance(r, dict) and r.get("activo") is not False]
    seed = date.today().isoformat()
    reviews.sort(key=lambda r: hashlib.sha256(
        f'{seed}|{r.get("nombre", "")}|{r.get("ciudad", "")}'.encode("utf-8")).hexdigest())
    cards = []
    for review in reviews[:6]:
        name, city, text = (str(review.get(k, "")).strip() for k in ("nombre", "ciudad", "texto"))
        if not name or not text:
            continue
        photo = str(review.get("foto", "")).strip()
        avatar = (f'<div class="review-avatar"><span>{esc(name[:1].upper())}</span>'
                  f'<img src="images/{esc(photo)}" alt="" loading="lazy" onerror="this.remove()"></div>'
                  if photo else f'<div class="review-avatar">{esc(name[:1].upper())}</div>')
        cards.append(f'<article class="review"><div class="review-top">{avatar}<div><div class="review-name">{esc(name)}</div>'
                     f'<div class="review-city">{esc(city)}</div></div><div class="review-stars" aria-label="5 estrellas">★★★★★</div></div>'
                     f'<p class="review-text">“{esc(text)}”</p></article>')
    if not cards:
        return ""
    return (f'<section class="home-section"><div class="home-section-head"><div><h2>Lo que dicen nuestros clientes</h2>'
            f'<p>Experiencias de compra en República Dominicana</p></div></div>'
            f'<div class="reviews-grid">{"".join(cards)}</div></section>')

def stores_html():
    stores = load_json(STORES_PATH, [])
    if not isinstance(stores, list):
        stores = []
    cards = []
    for i, store in enumerate(stores[:2], 1):
        if not isinstance(store, dict):
            continue
        name = str(store.get("nombre") or f"Tienda VivaBien {i}").strip()
        address = str(store.get("direccion") or "San Pedro de Macorís · dirección por confirmar").strip()
        hours = str(store.get("horario") or "Horario por confirmar").strip()
        image = str(store.get("foto") or f"tienda{i}.jpg").strip()
        maps = str(store.get("mapa") or "https://maps.google.com/?q=San+Pedro+de+Macoris").strip()
        image_path = os.path.join(IMG_DIR, os.path.basename(image))
        photo = (f'<img class="store-photo" src="images/{esc(os.path.basename(image))}" alt="{esc(name)}" loading="lazy">'
                 if os.path.isfile(image_path) else '<div class="store-photo store-photo-missing">🏪<br>Foto pendiente</div>')
        cards.append(f'<article class="store">{photo}<div class="store-info"><h3>{esc(name)}</h3>'
                     f'<p>{esc(address)}</p><p>{esc(hours)}</p><a href="{esc(maps)}" target="_blank" rel="noopener">📍 Cómo llegar</a></div></article>')
    if not cards:
        return ""
    return (f'<section class="stores"><div class="home-section-head"><div><h2>Nuestras Tiendas</h2>'
            f'<p>Tienda física real en San Pedro de Macorís · compra con confianza</p></div></div>'
            f'<div class="store-grid">{"".join(cards)}</div></section>')

def garantia_page():
    body = f"""{header()}
<main class="policy"><h1>Garantía y devoluciones</h1>
<p class="lead">Queremos que compres con tranquilidad. Si algo no está bien, escríbenos y buscaremos una solución clara y rápida.</p>
<section><h2>Garantía de 7 días</h2><p>Tienes hasta 7 días calendario después de recibir tu pedido para reportar un producto con defecto, daño de transporte o diferencia con lo solicitado.</p>
<p><strong>Algunos productos tienen garantía extendida.</strong> Cuando un producto ofrece más de 7 días, lo indicamos claramente en su página. En esos casos aplica el plazo que aparece en la página del producto. Por ejemplo, el <a href="producto/abanico-de-techo-led">abanico de techo con luz LED</a> tiene <strong>garantía de 1 mes</strong>.</p></section>
<section><h2>¿Qué necesitamos?</h2><ul><li>Número de pedido o teléfono usado en la compra.</li><li>Fotos o video donde se vea el problema.</li><li>El producto, empaque y accesorios en el estado en que fueron recibidos.</li></ul></section>
<section><h2>Cambios y devoluciones</h2><p>Después de revisar el caso, podremos ofrecer cambio, crédito o devolución según corresponda. Por higiene, algunos productos de uso personal abiertos no admiten devolución, salvo defecto comprobado.</p></section>
<section><h2>Entrega</h2><p>La mayoría de los pedidos llega entre 24 y 72 horas. El tiempo final depende de la zona, disponibilidad y transportista; verás la estimación disponible antes de confirmar.</p></section>
<a class="contact" href="https://wa.me/{WHATSAPP}" target="_blank">Hablar con VivaBien por WhatsApp</a></main>"""
    return page(f"Garantía de 7 días | {SITE_NAME}", body, wa_float=True,
                desc="Política de garantía, cambios y devoluciones de VivaBien en República Dominicana.",
                canonical=public_url("garantia.html"))

def category_page(title, products, description, slug):
    cards = "".join(product_card(p, rel="../") for p in products)
    body = (f'{header("../")}<main class="wrap"><div class="cat-hd"><div><h1 style="font-size:24px">{esc(title)}</h1>'
            f'<p class="count">{esc(description)}</p></div></div><div class="count">{len(products)} productos</div>'
            f'<div class="grid">{cards}</div></main>')
    return page(f"{title} | Comprar online RD | {SITE_NAME}", body, wa_float=True,
                desc=description, canonical=public_url(f"categoria/{slug}.html"), rel="../")

def load_panel_products():
    """读取格栅板 SKU，供专题、详情页、搜索和购物车共用。"""
    cfg = load_json(PANELS_PATH, {})
    raw_products = cfg.get("products") if isinstance(cfg, dict) else []
    products = []
    for raw in raw_products if isinstance(raw_products, list) else []:
        if not isinstance(raw, dict):
            continue
        sku = str(raw.get("sku") or "").strip().upper()
        image = str(raw.get("image") or "").strip().lstrip("/")
        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError):
            continue
        if not sku or not image or price <= 0:
            continue
        products.append({"sku": sku, "name": str(raw.get("name") or sku).strip(),
                         "price": price, "image": image,
                         "available": raw.get("available") is not False})
    return cfg if isinstance(cfg, dict) else {}, products

def panels_page():
    """格栅板独立专题页：真实纹理选色、数量计算、加购和 WhatsApp。"""
    cfg, products = load_panel_products()
    if not products:
        return ""

    cards = []
    for i, p in enumerate(products):
        cards.append(f'''<button class="pz-card{' selected' if i == 0 else ''}" type="button"
 data-sku="{esc(p['sku'])}" aria-pressed="{'true' if i == 0 else 'false'}">
<span class="pz-card-img"><img src="images/{esc(p['image'])}" alt="Panel decorativo {esc(p['sku'])} {esc(p['name'])}" loading="lazy"></span>
<span class="pz-card-copy"><b>{esc(p['sku'])}</b><span>{esc(p['name'])}</span><strong>{fmt_price(p['price'])}</strong></span>
</button>''')
    product_json = json.dumps(products, ensure_ascii=False).replace("</", "<\\/")
    hero = products[0]
    hero_image = str(cfg.get("hero_image") or hero["image"]).strip().lstrip("/")
    hero_alt = str(cfg.get("hero_alt") or f"Panel decorativo {hero['sku']}").strip()
    title = str(cfg.get("title") or "Transforma tu pared. Transforma tu espacio.").strip()
    subtitle = str(cfg.get("subtitle") or "Paneles decorativos modernos para renovar tu hogar.").strip()
    shipping = str(cfg.get("shipping_faq") or "El costo y el tiempo de entrega se confirman según tu ubicación.").strip()
    wa_general = f"https://wa.me/{WHATSAPP}?text=" + quote("Hola, quiero información sobre los paneles decorativos ZT.")

    css = r"""
<style>
.pz-page,.pz-page *{box-sizing:border-box}.pz-page{background:#F5F5F5;color:#172033;overflow:hidden}.pz-wrap{width:min(900px,100%);margin:auto;padding:0 14px}
.pz-nav{position:sticky;top:0;z-index:80;background:rgba(255,255,255,.96);border-bottom:1px solid #E8EDF5}.pz-nav-in{height:64px;display:flex;align-items:center;gap:18px}.pz-logo{display:flex;align-items:center;gap:9px;font-size:19px;font-weight:800}.pz-logo-i{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;background:#2563D9;color:#fff}.pz-links{display:none;margin-left:auto;gap:22px;font-size:13px;font-weight:700}.pz-actions{margin-left:auto;display:flex;gap:8px}.pz-icon{width:42px;height:42px;display:grid;place-items:center;border:1px solid #DFE6F1;border-radius:8px;color:#2563D9;background:#fff}.pz-buy{display:none;align-items:center;height:42px;padding:0 16px;background:#FF6B4A;color:#fff;border-radius:8px;font-size:13px;font-weight:800}
.pz-hero{height:min(70vh,650px);min-height:470px;position:relative;background:#2b2a27}.pz-hero-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:70% 16%}.pz-hero-copy{display:none}.pz-hero-buttons{display:flex;flex-wrap:wrap;gap:9px;margin-top:23px}.pz-btn{min-height:48px;padding:0 16px;border:0;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;cursor:pointer}.pz-primary{background:#FF6B00;color:#fff}.pz-secondary{background:#fff;color:#172033}
.pz-trust{background:#F4F7FB;border-bottom:1px solid #E6ECF4}.pz-trust-in{display:grid;grid-template-columns:repeat(3,1fr)}.pz-trust span{padding:14px 4px;text-align:center;font-size:9px;font-weight:800;border-right:1px solid #DDE5F0;overflow-wrap:anywhere}.pz-trust span:last-child{border:0}
.pz-summary{padding:18px 14px;background:#fff;border-bottom:8px solid #F5F5F5}.pz-summary h1{font-size:21px;line-height:1.28}.pz-summary-meta{margin-top:7px;color:#667085;font-size:11px}.pz-summary-price{margin-top:12px;color:#FF6B00;font-size:34px;font-weight:800}.pz-summary-stock{display:inline-block;margin-top:8px;padding:5px 8px;border:1px solid #FFB485;border-radius:4px;color:#C94E00;font-size:10px;font-weight:800}.pz-summary-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}.pz-summary-actions a{min-width:0}
.pz-section{padding:64px 0}.pz-soft{background:#F7F9FD}.pz-head{max-width:650px;margin-bottom:26px}.pz-eyebrow{font-size:11px;font-weight:800;text-transform:uppercase;color:#2563D9}.pz-head h2{font-size:29px;line-height:1.15;margin-top:8px}.pz-head p{font-size:14px;color:#667085;line-height:1.6;margin-top:9px}
.pz-products{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.pz-card{text-align:left;border:1px solid #DADDE2;background:#fff;border-radius:7px;overflow:hidden;padding:3px;cursor:pointer;color:#172033}.pz-card.selected{border:2px solid #2563D9;padding:2px;box-shadow:0 0 0 2px rgba(37,99,217,.1)}.pz-card-img{display:block;aspect-ratio:1;overflow:hidden;border-radius:4px;background:#E8EDF3}.pz-card-img img{width:100%;height:100%;object-fit:cover}.pz-card-copy{display:flex;flex-direction:column;padding:8px 5px;min-height:88px}.pz-card-copy b{font-size:11px}.pz-card-copy span{font-size:9px;color:#6B7280;margin:3px 0 7px;min-height:24px}.pz-card-copy strong{font-size:12px;margin-top:auto;color:#FF6B00}
.pz-preview-grid{display:grid;gap:24px}.pz-preview-media{position:relative;aspect-ratio:4/5;background:#ECEFF3;overflow:hidden}.pz-preview-media img{width:100%;height:100%;object-fit:cover;transition:opacity .2s ease}.pz-preview-badge{position:absolute;left:14px;bottom:14px;background:#fff;color:#172033;padding:10px 12px;border-radius:6px;font-size:12px;font-weight:800;box-shadow:0 6px 20px rgba(0,0,0,.15)}.pz-preview-info{display:flex;flex-direction:column;justify-content:center}.pz-preview-info h3{font-size:28px;margin-top:8px}.pz-preview-price{font-size:27px;font-weight:800;margin:16px 0}.pz-swatches{display:flex;gap:8px;flex-wrap:wrap}.pz-swatch{border:1px solid #DCE3ED;background:#fff;border-radius:6px;padding:10px 12px;font-size:12px;font-weight:800;cursor:pointer}.pz-swatch.selected{background:#2563D9;border-color:#2563D9;color:#fff}.pz-add{margin-top:18px;width:100%;gap:8px}
.pz-spec-grid{display:grid;gap:24px;align-items:center}.pz-spec-art{min-height:330px;background-image:linear-gradient(rgba(255,255,255,.05),rgba(255,255,255,.05)),var(--panel-image);background-size:cover;background-position:center;border-radius:8px}.pz-measures{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:22px 0}.pz-measure{padding:18px;background:#F3F6FA;border-left:4px solid #2563D9}.pz-measure b{display:block;font-size:24px}.pz-measure span{font-size:11px;color:#667085}.pz-points{display:grid;gap:12px}.pz-point{display:flex;gap:12px}.pz-num{flex:none;width:28px;height:28px;display:grid;place-items:center;border-radius:50%;background:#EEF4FF;color:#2563D9;font-size:12px;font-weight:800}.pz-point b{display:block;font-size:14px}.pz-point p{font-size:12px;color:#667085;line-height:1.5;margin-top:3px}
.pz-calc{display:grid;gap:22px;background:#172033;color:#fff;padding:24px;border-radius:8px}.pz-calc-copy h2{font-size:28px;line-height:1.15}.pz-calc-copy p{color:#C5CDDA;font-size:13px;line-height:1.6;margin-top:10px}.pz-form{background:#fff;color:#172033;padding:18px;border-radius:8px}.pz-fields{display:grid;gap:12px}.pz-field label{display:block;font-size:11px;font-weight:800;margin-bottom:6px}.pz-input{display:flex;border:1px solid #D6DFEB;border-radius:7px;overflow:hidden}.pz-input input{width:100%;border:0;padding:13px;font:700 16px inherit;outline:0}.pz-input span{display:grid;place-items:center;padding:0 12px;background:#F4F6F9;color:#667085;font-size:12px}.pz-calc-btn{width:100%;margin-top:14px}.pz-result{display:none;margin-top:14px;padding:13px;background:#EEF4FF;border-radius:7px;color:#172033;font-size:13px;line-height:1.5}.pz-result strong{display:block;font-size:20px;color:#2563D9}.pz-result.error{display:block;background:#FFF0EE;color:#A3362C}.pz-result-actions{display:none;gap:8px;margin-top:10px}.pz-result-actions .pz-btn{flex:1;padding:0 10px}.pz-wa-small{background:#25D366;color:#fff}
.pz-steps{display:grid;gap:12px}.pz-step{padding:22px;border-top:3px solid #2563D9;background:#F7F9FD}.pz-step small{font-weight:800;color:#2563D9}.pz-step h3{font-size:18px;margin:12px 0 7px}.pz-step p{font-size:12px;color:#667085;line-height:1.55}.pz-faq{max-width:820px;margin:auto}.pz-faq details{border-bottom:1px solid #E1E7F0;padding:17px 0}.pz-faq summary{cursor:pointer;font-size:14px;font-weight:800;list-style:none}.pz-faq summary::-webkit-details-marker{display:none}.pz-faq p{font-size:13px;color:#667085;line-height:1.6;padding-top:10px}
.pz-review-grid{display:grid;gap:10px}.pz-review{padding:16px;border:1px solid #E1E7F0;border-radius:7px;background:#fff}.pz-review b{font-size:13px}.pz-review p{margin-top:7px;color:#4B5565;font-size:12px;line-height:1.55}.pz-review-source{margin-top:13px;color:#667085;font-size:10px;line-height:1.5}.pz-detail-row{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}.pz-detail-row::-webkit-scrollbar{display:none}.pz-detail-card{flex:0 0 min(78vw,300px);margin:0;overflow:hidden;border:1px solid #E1E7F0;border-radius:7px;background:#fff;scroll-snap-align:start}.pz-detail-card img{width:100%;aspect-ratio:1;display:block;object-fit:cover}.pz-detail-card figcaption{padding:11px;color:#667085;font-size:10px;line-height:1.45}.pz-detail-card b{display:block;margin-bottom:3px;color:#172033;font-size:12px}
.pz-final{position:relative;min-height:520px;display:flex;align-items:flex-end;color:#fff;background:#202026}.pz-final img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.pz-final:after{content:"";position:absolute;inset:0;background:rgba(8,12,18,.62)}.pz-final-copy{position:relative;z-index:1;padding:55px 18px;width:min(1160px,100%);margin:auto}.pz-final h2{font-size:34px;max-width:520px}.pz-final p{margin:10px 0 20px;color:#E5EAF2}.pz-mobile-bar{position:fixed;left:0;right:0;bottom:0;z-index:90;display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:9px 12px calc(9px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid #DFE6F0}.pz-mobile-bar .pz-btn{min-height:46px}.pz-mobile-wa{background:#25D366;color:#fff}
@media(min-width:720px){.pz-links{display:flex}.pz-actions{margin-left:0}.pz-buy{display:flex}.pz-trust span{font-size:12px}.pz-summary{padding:24px}.pz-products{grid-template-columns:repeat(5,1fr);gap:12px}.pz-preview-grid,.pz-spec-grid{grid-template-columns:1.1fr .9fr;gap:50px}.pz-preview-media{aspect-ratio:5/4}.pz-spec-grid{grid-template-columns:1fr 1fr}.pz-calc{grid-template-columns:.85fr 1.15fr;padding:42px;align-items:center}.pz-fields{grid-template-columns:1fr 1fr}.pz-steps{grid-template-columns:repeat(3,1fr)}.pz-review-grid{grid-template-columns:repeat(2,1fr)}.pz-mobile-bar{display:none}.pz-section{padding:72px 0}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto!important}.pz-preview-media img{transition:none}}
</style>
"""
    body = r"""
<div class="pz-page">
<nav class="pz-nav"><div class="pz-wrap pz-nav-in"><a class="pz-logo" href="./"><span class="pz-logo-i">V</span>VivaBien</a><div class="pz-links"><a href="#colores">Colores</a><a href="#medidas">Medidas</a><a href="#calculadora">Calculadora</a><a href="#preguntas">Preguntas</a></div><div class="pz-actions"><a class="pz-icon" href="carrito" aria-label="Carrito">__BAG__<span class="cart-n" id="cartN"></span></a><a class="pz-buy" href="#colores">COMPRAR</a></div></div></nav>
<header class="pz-hero"><img class="pz-hero-media" src="images/__HERO_IMAGE__" alt="__HERO_ALT__" fetchpriority="high"><div class="pz-hero-copy"><span class="pz-kicker">Panel decorativo · 290 × 17 cm</span><h1>__TITLE__</h1><p>__SUBTITLE__</p><div class="pz-hero-buttons"><a class="pz-btn pz-primary" href="#colores">VER COLORES</a><a class="pz-btn pz-secondary" href="#calculadora">CALCULAR CANTIDAD</a></div></div></header>
<div class="pz-trust"><div class="pz-wrap pz-trust-in"><span>290 cm de largo</span><span>17 cm de ancho</span><span>Asesoría por WhatsApp</span></div></div>
<section class="pz-summary"><h1>__TITLE__</h1><p class="pz-summary-meta">Panel rígido ranurado · 290 × 17 cm · <b id="pzSummarySku">__HERO_SKU__</b></p><div class="pz-summary-price" id="pzSummaryPrice">__HERO_PRICE__</div><span class="pz-summary-stock">PRECIO POR PANEL</span><div class="pz-summary-actions"><a class="pz-btn pz-primary" href="#colores">ELEGIR COLOR</a><a class="pz-btn pz-secondary" href="#calculadora">CALCULAR</a></div></section>
<main>
<section class="pz-section" id="colores"><div class="pz-wrap"><div class="pz-head"><span class="pz-eyebrow">Colección ZT</span><h2>Elige el color</h2><p>Todos los recortes tienen el mismo tamaño para comparar mejor. El SKU aparece debajo de cada muestra.</p></div><div class="pz-products">__PRODUCT_CARDS__</div></div></section>
<section class="pz-section pz-soft"><div class="pz-wrap pz-preview-grid"><div class="pz-preview-media"><img id="pzMainImage" src="images/__INITIAL_PRODUCT_IMAGE__" alt="Panel decorativo __HERO_SKU__"><span class="pz-preview-badge" id="pzBadge">__HERO_SKU__ · __HERO_NAME__</span></div><div class="pz-preview-info"><span class="pz-eyebrow">Vista del acabado real</span><h3 id="pzName">__HERO_NAME__</h3><div class="pz-preview-price" id="pzPrice">__HERO_PRICE__</div><div class="pz-swatches" id="pzSwatches">__SWATCHES__</div><button class="pz-btn pz-primary pz-add" id="pzAddOne">__BAG__ AGREGAR AL CARRITO</button></div></div></section>
<section class="pz-section"><div class="pz-wrap"><div class="pz-head"><span class="pz-eyebrow">Comentarios públicos</span><h2>Lo que más valoran en paneles similares</h2><p>Resumen editorial de opiniones públicas sobre productos comparables; no son reseñas verificadas de pedidos de VivaBien.</p></div><div class="pz-review-grid"><article class="pz-review"><b>El cambio visual se nota rápido</b><p>Compradores destacan que una pared sencilla se ve más terminada y cálida después de instalar paneles ranurados.</p></article><article class="pz-review"><b>Medir y alinear hace la diferencia</b><p>La recomendación más repetida es presentar las piezas primero y mantener la primera perfectamente nivelada.</p></article><article class="pz-review"><b>Conviene revisar el tono con la luz real</b><p>El acabado puede verse más claro u oscuro según la pantalla, la iluminación y el ángulo del espacio.</p></article><article class="pz-review"><b>Hay que revisar bordes al recibir</b><p>Algunas opiniones de paneles comparables mencionan golpes de transporte; revisa las piezas antes de instalar.</p></article></div><p class="pz-review-source">Síntesis basada en opiniones públicas de productos similares de Home Depot, WoodUpp y Naturewall. No atribuimos prestaciones acústicas, impermeabilidad ni material sin ficha técnica confirmada.</p></div></section>
<section class="pz-section pz-soft"><div class="pz-wrap"><div class="pz-head"><span class="pz-eyebrow">Detalles visuales</span><h2>Compara ambiente, textura y acabados</h2></div><div class="pz-detail-row"><figure class="pz-detail-card"><img src="images/__HERO_IMAGE__" alt="Sala con panel decorativo ranurado" loading="lazy"><figcaption><b>Resultado en un ambiente</b>Referencia visual para una pared protagonista.</figcaption></figure><figure class="pz-detail-card"><img src="images/panels/swatches/ZT-101.jpg" alt="Textura ZT-101" loading="lazy"><figcaption><b>Roble dorado · ZT-101</b>Acercamiento uniforme de la textura.</figcaption></figure><figure class="pz-detail-card"><img src="images/panels/swatches/ZT-169.jpg" alt="Textura ZT-169" loading="lazy"><figcaption><b>Terrazo gris · ZT-169</b>Una alternativa fría para espacios modernos.</figcaption></figure><figure class="pz-detail-card"><img src="images/panels/swatches/ZT-135.jpg" alt="Textura ZT-135" loading="lazy"><figcaption><b>Rojo madera · ZT-135</b>Una opción más cálida y marcada.</figcaption></figure></div></div></section>
<section class="pz-section" id="medidas"><div class="pz-wrap pz-spec-grid"><div class="pz-spec-art" id="pzSpecArt"></div><div><div class="pz-head"><span class="pz-eyebrow">Medidas confirmadas</span><h2>Una pieza larga para una pared más limpia</h2><p>La cantidad depende del ancho de tu pared. Si la altura supera el largo del panel, te ayudamos a revisar el proyecto.</p></div><div class="pz-measures"><div class="pz-measure"><b>290 cm</b><span>de largo</span></div><div class="pz-measure"><b>17 cm</b><span>de ancho</span></div></div><div class="pz-points"><div class="pz-point"><span class="pz-num">1</span><div><b>Relieve decorativo</b><p>Frente ranurado con cuatro líneas elevadas visibles.</p></div></div><div class="pz-point"><span class="pz-num">2</span><div><b>Tonos combinables</b><p>Opciones claras, cálidas y blancas para distintos ambientes.</p></div></div><div class="pz-point"><span class="pz-num">3</span><div><b>Medición sencilla</b><p>Usa la calculadora para obtener una cantidad inicial.</p></div></div></div></div></div></section>
<section class="pz-section pz-soft" id="calculadora"><div class="pz-wrap"><div class="pz-calc"><div class="pz-calc-copy"><span class="pz-eyebrow">Calculadora</span><h2>¿Cuántos paneles necesitas?</h2><p>Calculamos una instalación vertical usando paneles de 17 cm de ancho y 290 cm de largo.</p></div><form class="pz-form" id="pzCalc" novalidate><div class="pz-fields"><div class="pz-field"><label for="pzWidth">Ancho de la pared</label><div class="pz-input"><input id="pzWidth" type="number" inputmode="decimal" min="1" placeholder="Ej. 340"><span>cm</span></div></div><div class="pz-field"><label for="pzHeight">Alto de la pared</label><div class="pz-input"><input id="pzHeight" type="number" inputmode="decimal" min="1" placeholder="Ej. 260"><span>cm</span></div></div></div><button class="pz-btn pz-primary pz-calc-btn" type="submit">CALCULAR CANTIDAD</button><div class="pz-result" id="pzResult"></div><div class="pz-result-actions" id="pzResultActions"><button class="pz-btn pz-primary" type="button" id="pzAddQty">Agregar al carrito</button><a class="pz-btn pz-wa-small" id="pzCalcWa" href="__WA_GENERAL__" target="_blank">WhatsApp</a></div></form></div></div></section>
<section class="pz-section"><div class="pz-wrap"><div class="pz-head"><span class="pz-eyebrow">Cómo comenzar</span><h2>Renueva tu espacio en pocos pasos</h2></div><div class="pz-steps"><article class="pz-step"><small>PASO 01</small><h3>Mide tu pared</h3><p>Toma el ancho y el alto en centímetros.</p></article><article class="pz-step"><small>PASO 02</small><h3>Elige tu tono</h3><p>Selecciona el modelo ZT que combine con tu espacio.</p></article><article class="pz-step"><small>PASO 03</small><h3>Confirma tu pedido</h3><p>Agrega la cantidad o escríbenos para revisar tus medidas.</p></article></div></div></section>
<section class="pz-section pz-soft" id="preguntas"><div class="pz-wrap pz-faq"><div class="pz-head"><span class="pz-eyebrow">Información útil</span><h2>Preguntas frecuentes</h2></div><details><summary>¿Cuál es el tamaño de cada panel?</summary><p>Cada panel mide 290 cm de largo y 17 cm de ancho.</p></details><details><summary>¿Cómo sé cuántos paneles necesito?</summary><p>Usa nuestra calculadora con las medidas de tu pared o envíanos las medidas por WhatsApp.</p></details><details><summary>¿Los colores de las fotos son reales?</summary><p>Las imágenes corresponden a los modelos mostrados. El tono puede variar ligeramente según la luz y la pantalla.</p></details><details><summary>¿Cómo puedo comprar?</summary><p>Selecciona el modelo, calcula la cantidad y agrégalo al carrito. También puedes consultarnos por WhatsApp.</p></details><details><summary>¿Hacen envíos?</summary><p>__SHIPPING__</p></details></div></section>
</main>
<section class="pz-final"><img id="pzFinalImage" src="images/__FINAL_IMAGE__" alt="Detalle de panel decorativo ZT"><div class="pz-final-copy"><h2>Tu pared puede tener un acabado diferente.</h2><p>Elige tu tono y calcula la cantidad que necesitas.</p><div class="pz-hero-buttons"><a class="pz-btn pz-primary" href="#colores">VER COLORES</a><a class="pz-btn pz-secondary" href="__WA_GENERAL__" target="_blank">HABLAR POR WHATSAPP</a></div></div></section>
<div class="pz-mobile-bar"><a class="pz-btn pz-primary" href="#colores">VER COLORES</a><a class="pz-btn pz-mobile-wa" href="__WA_GENERAL__" target="_blank">WHATSAPP</a></div>
</div>
<script>
(function(){
 var products=__PRODUCT_JSON__,selected=products[0],estimated=0;
 function money(v){return 'RD$ '+Math.round(v).toLocaleString('en-US')}
 function product(sku){return products.find(function(p){return p.sku===sku})||products[0]}
 function select(sku){selected=product(sku);var im=document.getElementById('pzMainImage');im.style.opacity='.2';setTimeout(function(){im.src='images/'+selected.image;im.alt='Panel decorativo '+selected.sku+' '+selected.name;im.style.opacity='1'},120);document.getElementById('pzBadge').textContent=selected.sku+' · '+selected.name;document.getElementById('pzName').textContent=selected.name;document.getElementById('pzPrice').textContent=money(selected.price);document.getElementById('pzSummarySku').textContent=selected.sku;document.getElementById('pzSummaryPrice').textContent=money(selected.price);document.getElementById('pzSpecArt').style.setProperty('--panel-image','url("images/'+selected.image+'")');document.querySelectorAll('.pz-card,.pz-swatch').forEach(function(x){var on=x.dataset.sku===sku;x.classList.toggle('selected',on);x.setAttribute('aria-pressed',on?'true':'false')});if(estimated)paintResult(estimated);try{vbTrack('filter',sku,{filter_group:'paneles',filter_sub:'color_preview_change'})}catch(e){}}
 function add(qty){var c=vbCart(),f=c.find(function(x){return x.sku===selected.sku});if(f)f.qty+=qty;else c.push({sku:selected.sku,handle:selected.sku.toLowerCase(),title:'Panel decorativo '+selected.sku+' · '+selected.name,price:selected.price,img:selected.image,qty:qty});vbSave(c);try{fbq('track','AddToCart',{content_ids:[selected.sku],content_type:'product',value:selected.price*qty,currency:'DOP'});vbTrack('addcart',selected.sku,{qty:qty,price:selected.price,cart_total:c.reduce(function(a,x){return a+x.price*x.qty},0),product_title:'Panel decorativo '+selected.sku,product_img:selected.image})}catch(e){}location.href='carrito'}
 function paintResult(qty){var r=document.getElementById('pzResult');r.className='pz-result';r.style.display='block';r.innerHTML='<strong>'+qty+' paneles</strong>Estimado para instalación vertical con el modelo '+selected.sku+'. Confirma las medidas antes del pedido.';document.getElementById('pzResultActions').style.display='flex';document.getElementById('pzAddQty').textContent='Agregar '+qty+' al carrito';document.getElementById('pzCalcWa').href='https://wa.me/__WA_NUMBER__?text='+encodeURIComponent('Hola, calculé '+qty+' paneles del modelo '+selected.sku+'. Quiero confirmar las medidas.')}
 document.querySelectorAll('.pz-card,.pz-swatch').forEach(function(x){x.onclick=function(){select(x.dataset.sku);document.querySelector('.pz-preview-media').scrollIntoView({behavior:'smooth',block:'center'})}});
 document.getElementById('pzAddOne').onclick=function(){add(1)};document.getElementById('pzAddQty').onclick=function(){if(estimated)add(estimated)};
 document.getElementById('pzCalc').onsubmit=function(e){e.preventDefault();var w=Number(document.getElementById('pzWidth').value),h=Number(document.getElementById('pzHeight').value),r=document.getElementById('pzResult');document.getElementById('pzResultActions').style.display='none';estimated=0;if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0){r.className='pz-result error';r.textContent='Escribe medidas válidas mayores que cero.';return}if(h>290){r.className='pz-result error';r.innerHTML='La altura supera los 290 cm. Escríbenos para ayudarte a calcular la cantidad correcta.';document.getElementById('pzResultActions').style.display='flex';document.getElementById('pzAddQty').style.display='none';document.getElementById('pzCalcWa').href='https://wa.me/__WA_NUMBER__?text='+encodeURIComponent('Hola, necesito ayuda para calcular paneles. Mi pared mide '+w+' cm de ancho y '+h+' cm de alto.');try{vbTrack('search','',{search_query:'panel_calculator_height_exceeded',result_count:0})}catch(e){}return}document.getElementById('pzAddQty').style.display='inline-flex';estimated=Math.ceil(w/17);paintResult(estimated);try{vbTrack('search',selected.sku,{search_query:'panel_calculator_success',result_count:estimated})}catch(e){}};
 select(selected.sku);
})();
</script>
"""
    swatches = "".join(f'<button class="pz-swatch{" selected" if i == 0 else ""}" type="button" data-sku="{esc(p["sku"])}" aria-pressed="{"true" if i == 0 else "false"}">{esc(p["sku"])}</button>' for i, p in enumerate(products))
    body = (body.replace("__BAG__", BAG_SVG).replace("__TITLE__", esc(title))
            .replace("__SUBTITLE__", esc(subtitle)).replace("__HERO_IMAGE__", esc(hero_image))
            .replace("__HERO_ALT__", esc(hero_alt))
            .replace("__INITIAL_PRODUCT_IMAGE__", esc(hero["image"]))
            .replace("__FINAL_IMAGE__", esc(products[-1]["image"])).replace("__HERO_SKU__", esc(hero["sku"]))
            .replace("__HERO_NAME__", esc(hero["name"])).replace("__HERO_PRICE__", fmt_price(hero["price"]))
            .replace("__PRODUCT_CARDS__", "".join(cards)).replace("__SWATCHES__", swatches)
            .replace("__PRODUCT_JSON__", product_json).replace("__WA_GENERAL__", esc(wa_general))
            .replace("__WA_NUMBER__", WHATSAPP).replace("__SHIPPING__", esc(shipping)))
    item_schema = {"@context": "https://schema.org", "@type": "ItemList",
                   "name": "Paneles decorativos ZT", "itemListElement": [
                       {"@type": "ListItem", "position": i + 1,
                        "item": {"@type": "Product", "name": f"Panel decorativo {p['sku']} {p['name']}",
                                 "sku": p["sku"], "image": f"{SITE_URL}/images/{p['image']}",
                                 "offers": {"@type": "Offer", "priceCurrency": "DOP",
                                            "price": f"{p['price']:.2f}",
                                            "availability": "https://schema.org/InStock"}}}
                       for i, p in enumerate(products)]}
    schema = '<script type="application/ld+json">' + json.dumps(item_schema, ensure_ascii=False).replace("</", "<\\/") + '</script>'
    return page(f"Paneles Decorativos para Pared | {SITE_NAME}", body, wa_float=False,
                desc="Paneles decorativos ZT de 290 × 17 cm. Explora colores y calcula cuántos paneles necesitas.",
                track_category="Paneles decorativos", extra_head=css + schema,
                canonical=public_url("paneles-decorativos.html"),
                og_image=f"{SITE_URL}/images/{quote(hero_image, safe='/')}")

def panel_product_page():
    """格栅板统一商品详情：同一页面切换多个 ZT SKU。"""
    _, products = load_panel_products()
    if not products:
        return ""
    first = products[0]
    options = "".join(
        f'<button class="pv-option{" on" if i == 0 else ""}" type="button" data-sku="{esc(p["sku"])}">'
        f'<img src="../images/{esc(p["image"])}" alt="{esc(p["sku"])}" loading="lazy">'
        f'<span><b>{esc(p["sku"])}</b><small>{esc(p["name"])}</small></span></button>'
        for i, p in enumerate(products))
    product_json = json.dumps(products, ensure_ascii=False).replace("</", "<\\/")
    wa_base = f"https://wa.me/{WHATSAPP}?text="
    css = r"""
<style>
.pv-shell{max-width:1160px;margin:auto;padding:18px 18px 46px}.pv-crumb{font-size:11px;color:#7D8795;margin-bottom:13px}.pv-crumb a{color:#2563D9}
.pv-grid{display:grid;gap:22px}.pv-media{position:relative;aspect-ratio:1;background:#F0F3F7;overflow:hidden;border-radius:8px}.pv-media img{width:100%;height:100%;object-fit:cover;transition:opacity .16s ease}.pv-sku-badge{position:absolute;left:12px;bottom:12px;padding:8px 10px;border-radius:6px;background:#fff;color:#172033;font-size:12px;font-weight:800;box-shadow:0 5px 18px rgba(14,29,54,.16)}
.pv-info h1{font-size:27px;line-height:1.12}.pv-sub{color:#667085;font-size:13px;margin-top:7px}.pv-price{font-size:29px;font-weight:800;margin:18px 0 13px}.pv-label{display:block;font-size:11px;font-weight:800;margin-bottom:8px}.pv-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.pv-option{min-width:0;border:2px solid #E3E8F0;border-radius:8px;background:#fff;padding:6px;text-align:left;cursor:pointer}.pv-option.on{border-color:#2563D9;background:#F2F6FF}.pv-option img{display:block;width:100%;aspect-ratio:1;object-fit:cover;border-radius:5px}.pv-option span{display:block;padding:7px 2px 2px}.pv-option b,.pv-option small{display:block;overflow:hidden;text-overflow:ellipsis}.pv-option b{font-size:12px}.pv-option small{font-size:10px;color:#6B7280;margin-top:2px;white-space:nowrap}
.pv-quantity{display:flex;align-items:center;justify-content:space-between;margin-top:18px;padding:10px 12px;background:#F5F7FA;border-radius:8px}.pv-quantity>span{font-size:12px;font-weight:800}.pv-stepper{display:flex;align-items:center;gap:12px}.pv-stepper button{width:36px;height:36px;border:1px solid #DCE3ED;border-radius:7px;background:#fff;color:#2563D9;font-size:19px;font-weight:800;cursor:pointer}.pv-stepper output{min-width:22px;text-align:center;font-weight:800}
.pv-actions{display:grid;grid-template-columns:48px 1fr;gap:8px;margin-top:10px}.pv-wa{display:grid;place-items:center;border-radius:8px;background:#25D366;color:#fff}.pv-add{min-height:50px;border:0;border-radius:8px;background:#2563D9;color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;gap:8px;cursor:pointer}.pv-add.added{background:#173E8F}.pv-cart-link{display:none;margin-top:8px;text-align:center;color:#2563D9;font-size:12px;font-weight:800}.pv-cart-link.show{display:block}
.pv-trust{display:grid;grid-template-columns:repeat(3,1fr);margin-top:18px;border:1px solid #E5EAF2;border-radius:8px}.pv-trust div{padding:12px 5px;text-align:center;font-size:10px;font-weight:800}.pv-trust div+div{border-left:1px solid #E5EAF2}.pv-detail{margin-top:28px;padding-top:24px;border-top:1px solid #E7ECF3}.pv-detail h2{font-size:19px;margin-bottom:10px}.pv-detail p{color:#5E6979;font-size:13px;line-height:1.65}.pv-facts{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:16px 0}.pv-fact{background:#F5F7FA;padding:13px;border-radius:7px}.pv-fact b{display:block;font-size:14px}.pv-fact span{font-size:11px;color:#697586}.pv-topic{display:inline-flex;align-items:center;min-height:44px;padding:0 15px;border-radius:8px;background:#FFF0EC;color:#C94B31;font-size:12px;font-weight:800}
@media(min-width:760px){.pv-shell{padding-top:28px}.pv-grid{grid-template-columns:1.05fr .95fr;gap:44px;align-items:start}.pv-info{position:sticky;top:86px}.pv-info h1{font-size:38px}.pv-media{aspect-ratio:4/5}.pv-options{gap:10px}}
</style>"""
    body = f"""{header('../')}
<main class="pv-shell">
 <div class="pv-crumb"><a href="../">VivaBien</a> / <a href="../paneles-decorativos.html">Paneles decorativos</a> / <span id="pvCrumb">{esc(first['sku'])}</span></div>
 <div class="pv-grid">
  <div class="pv-media"><img id="pvImage" src="../images/{esc(first['image'])}" alt="Panel decorativo {esc(first['sku'])}"><span class="pv-sku-badge" id="pvBadge">{esc(first['sku'])}</span></div>
  <div class="pv-info">
   <h1>Panel decorativo ranurado</h1><p class="pv-sub" id="pvName">{esc(first['name'])} · {esc(first['sku'])}</p>
   <div class="pv-price" id="pvPrice">{fmt_price(first['price'])}</div>
   <span class="pv-label">Elige el modelo</span><div class="pv-options">{options}</div>
   <div class="pv-quantity"><span>Cantidad</span><div class="pv-stepper"><button id="pvMinus" type="button" aria-label="Reducir cantidad">−</button><output id="pvQty">1</output><button id="pvPlus" type="button" aria-label="Aumentar cantidad">+</button></div></div>
   <div class="pv-actions"><a class="pv-wa" id="pvWa" href="{wa_base}" target="_blank" aria-label="Consultar por WhatsApp">{WA_SVG}</a><button class="pv-add" id="pvAdd" type="button">{BAG_SVG} Agregar al carrito</button></div>
   <a class="pv-cart-link" id="pvCart" href="../carrito">Ver carrito →</a>
   <div class="pv-trust"><div>🚚 Entrega<br>24-72 horas</div><div>💵 Pagas<br>al recibir</div><div>↩️ Garantía<br>de 7 días</div></div>
   <div class="pv-detail"><h2>Un acabado moderno para tus paredes</h2><p>Panel decorativo de formato vertical para salas, dormitorios y oficinas. Selecciona el modelo ZT que combine con tu espacio y confirma la cantidad antes de realizar el pedido.</p><div class="pv-facts"><div class="pv-fact"><b>290 cm</b><span>de largo</span></div><div class="pv-fact"><b>17 cm</b><span>de ancho</span></div></div><a class="pv-topic" href="../paneles-decorativos.html">Ver inspiración y calcular paneles →</a></div>
  </div>
 </div>
</main>
<script>
(function(){{
 var products={product_json},selected=products[0],qty=1;
 function money(n){{return 'RD$ '+Math.round(n).toLocaleString('en-US')}}
 function choose(sku,push){{selected=products.find(function(p){{return p.sku===sku}})||products[0];
  var im=document.getElementById('pvImage');im.style.opacity='.25';setTimeout(function(){{im.src='../images/'+selected.image;im.alt='Panel decorativo '+selected.sku+' '+selected.name;im.style.opacity='1'}},90);
  document.getElementById('pvBadge').textContent=selected.sku;document.getElementById('pvCrumb').textContent=selected.sku;document.getElementById('pvName').textContent=selected.name+' · '+selected.sku;document.getElementById('pvPrice').textContent=money(selected.price);
  document.getElementById('pvWa').href='{wa_base}'+encodeURIComponent('Hola, estoy interesado en el panel decorativo '+selected.sku+'. Quiero más información.');
  document.querySelectorAll('.pv-option').forEach(function(x){{x.classList.toggle('on',x.dataset.sku===selected.sku)}});document.getElementById('pvAdd').classList.remove('added');document.getElementById('pvAdd').innerHTML='{BAG_SVG} Agregar al carrito';document.getElementById('pvCart').classList.remove('show');
  if(push)history.replaceState(null,'','?sku='+encodeURIComponent(selected.sku));document.title='Panel decorativo '+selected.sku+' · '+selected.name+' | VivaBien';try{{vbTrack('view',selected.sku,{{product_title:'Panel decorativo '+selected.sku,product_img:selected.image,category:'Paneles decorativos'}})}}catch(e){{}}
 }}
 function paintQty(){{document.getElementById('pvQty').textContent=qty}}
 document.querySelectorAll('.pv-option').forEach(function(x){{x.onclick=function(){{choose(x.dataset.sku,true)}}}});document.getElementById('pvMinus').onclick=function(){{qty=Math.max(1,qty-1);paintQty()}};document.getElementById('pvPlus').onclick=function(){{qty=Math.min(99,qty+1);paintQty()}};
 document.getElementById('pvAdd').onclick=function(){{var c=vbCart(),f=c.find(function(x){{return x.sku===selected.sku}});if(f)f.qty+=qty;else c.push({{sku:selected.sku,handle:'panel-decorativo?sku='+selected.sku,title:'Panel decorativo '+selected.sku+' · '+selected.name,price:selected.price,img:selected.image,qty:qty}});vbSave(c);var b=this;b.classList.add('added');b.textContent='✓ Agregado al carrito';document.getElementById('pvCart').classList.add('show');try{{fbq('track','AddToCart',{{content_ids:[selected.sku],content_type:'product',value:selected.price*qty,currency:'DOP'}});vbTrack('addcart',selected.sku,{{qty:qty,price:selected.price,cart_total:c.reduce(function(a,x){{return a+x.price*x.qty}},0),product_title:'Panel decorativo '+selected.sku,product_img:selected.image}})}}catch(e){{}}}};
 choose(new URLSearchParams(location.search).get('sku')||products[0].sku,false);
}})();
</script>"""
    schema = {"@context": "https://schema.org", "@type": "ProductGroup",
              "name": "Panel decorativo ranurado ZT", "productGroupID": "PANEL-ZT",
              "variesBy": "https://schema.org/color", "hasVariant": [
                  {"@type": "Product", "name": f"Panel decorativo {p['sku']} {p['name']}",
                   "sku": p["sku"], "image": f"{SITE_URL}/images/{p['image']}",
                   "offers": {"@type": "Offer", "priceCurrency": "DOP", "price": f"{p['price']:.2f}",
                              "availability": "https://schema.org/InStock"}}
                  for p in products]}
    schema_head = '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False).replace("</", "<\\/") + '</script>'
    return page(f"Panel decorativo ranurado 290 × 17 cm | {SITE_NAME}", body, wa_float=False,
                desc="Panel decorativo ranurado ZT de 290 × 17 cm. Elige color, cantidad y compra online en VivaBien.",
                track_category="Paneles decorativos", extra_head=css + schema_head,
                canonical=public_url("producto/panel-decorativo.html"), rel="../",
                og_image=f"{SITE_URL}/images/{quote(first['image'], safe='/')}")

def adhesive_panel_page():
    """Meta 投流落地页：卷装自粘木纹格栅贴面，效果优先、单品直购。"""
    cfg = load_json(ADHESIVE_PANEL_PATH, {})
    if not isinstance(cfg, dict) or not cfg.get("sku"):
        return ""

    sku = str(cfg.get("sku")).strip()
    name = str(cfg.get("name") or "Panel decorativo autoadhesivo efecto madera").strip()
    short_name = str(cfg.get("short_name") or name).strip()
    handle = str(cfg.get("handle") or "panel-autoadhesivo").strip()
    color = str(cfg.get("color") or "Roble natural").strip()
    try:
        price = float(cfg.get("price") or 0)
        width = float(cfg.get("width_cm") or 40)
        length = float(cfg.get("length_cm") or 300)
        coverage = float(cfg.get("coverage_m2") or (width * length / 10000))
    except (TypeError, ValueError):
        return ""
    if price <= 0 or width <= 0 or length <= 0 or coverage <= 0:
        return ""

    hero_image = str(cfg.get("hero_image") or "").lstrip("/")
    product_image = str(cfg.get("product_image") or hero_image).lstrip("/")
    installation_image = str(cfg.get("installation_image") or product_image).lstrip("/")
    flexible_image = str(cfg.get("flexible_image") or product_image).lstrip("/")
    roll_image = str(cfg.get("roll_image") or product_image).lstrip("/")
    shipping_text = str(cfg.get("shipping_text") or
                        "El costo y el tiempo de entrega se calculan según tu zona.").strip()
    wa_url = (f"https://wa.me/{WHATSAPP}?text=" +
              quote(f"Hola, quiero información sobre {short_name} ({sku})."))
    product_json = json.dumps({
        "sku": sku, "handle": handle, "title": name, "price": price,
        "img": product_image, "color": color,
    }, ensure_ascii=False).replace("</", "<\\/")

    css = r"""
<style>
.ar-page,.ar-page *{box-sizing:border-box}.ar-page{--ink:#152033;--blue:#2563D9;--orange:#FF6B4A;--soft:#F4F7FB;--line:#E3E9F2;color:var(--ink);background:#fff;overflow:hidden}.ar-wrap{width:min(1160px,100%);margin:auto;padding:0 18px}
.ar-nav{position:sticky;top:0;z-index:80;background:rgba(255,255,255,.97);border-bottom:1px solid var(--line)}.ar-nav-in{height:62px;display:flex;align-items:center;gap:16px}.ar-logo{display:flex;align-items:center;gap:9px;font-size:19px;font-weight:800}.ar-logo-i{width:34px;height:34px;border-radius:8px;display:grid;place-items:center;background:var(--blue);color:#fff}.ar-nav-links{display:none;margin-left:auto;gap:22px;font-size:12px;font-weight:800}.ar-cart{margin-left:auto;width:42px;height:42px;display:grid;place-items:center;border:1px solid #DCE4EF;border-radius:8px;color:var(--blue);position:relative}.ar-cart .cart-n{right:-4px;top:-6px}.ar-nav-buy{display:none;min-height:42px;padding:0 15px;border-radius:8px;background:var(--orange);color:#fff;align-items:center;font-size:12px;font-weight:800}
.ar-hero{position:relative;min-height:78vh;display:flex;align-items:flex-end;color:#fff;background:#2B2925}.ar-hero>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:58% center}.ar-hero:after{content:"";position:absolute;inset:0;background:rgba(8,13,20,.48)}.ar-hero-copy{position:relative;z-index:1;width:min(1160px,100%);margin:auto;padding:62px 18px 54px}.ar-kicker{display:inline-block;padding:7px 10px;border:1px solid rgba(255,255,255,.65);border-radius:6px;font-size:10px;font-weight:800;text-transform:uppercase}.ar-hero h1{max-width:660px;margin-top:13px;font-size:36px;line-height:1.06;overflow-wrap:anywhere}.ar-hero p{max-width:570px;margin-top:13px;font-size:14px;line-height:1.55;color:#F5F7FA}.ar-price{margin-top:17px;display:flex;align-items:baseline;gap:8px}.ar-price strong{font-size:29px}.ar-price span{font-size:11px;color:#E8ECF2}.ar-buttons{display:flex;flex-wrap:wrap;gap:9px;margin-top:18px}.ar-btn{min-height:48px;padding:0 16px;border:0;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;gap:8px;font-size:12px;font-weight:800;cursor:pointer}.ar-primary{background:var(--orange);color:#fff}.ar-secondary{background:#fff;color:var(--ink)}.ar-whatsapp{background:#25D366;color:#fff}
.ar-trust{border-bottom:1px solid var(--line);background:var(--soft)}.ar-trust-in{display:grid;grid-template-columns:repeat(3,1fr)}.ar-trust-in>div{min-height:64px;padding:12px 5px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border-right:1px solid #DCE4EF}.ar-trust-in>div:last-child{border:0}.ar-trust b{font-size:10px}.ar-trust span{font-size:9px;color:#667085;margin-top:3px}
.ar-section{padding:62px 0}.ar-section.soft{background:var(--soft)}.ar-head{max-width:650px;margin-bottom:25px}.ar-eyebrow{color:var(--blue);font-size:10px;font-weight:800;text-transform:uppercase}.ar-head h2{margin-top:7px;font-size:29px;line-height:1.12}.ar-head p{margin-top:9px;color:#667085;font-size:13px;line-height:1.6}.ar-split{display:grid;gap:24px;align-items:center}.ar-media{position:relative;overflow:hidden;border-radius:8px;background:#E9EDF3}.ar-media.square{aspect-ratio:1}.ar-media.portrait{aspect-ratio:4/5}.ar-media img{width:100%;height:100%;display:block;object-fit:cover}.ar-media-note{position:absolute;left:12px;bottom:12px;padding:8px 10px;border-radius:6px;background:#fff;color:var(--ink);font-size:10px;font-weight:800;box-shadow:0 5px 18px rgba(20,32,50,.16)}
.ar-copy h2{font-size:29px;line-height:1.12}.ar-copy>p{margin-top:12px;color:#667085;font-size:13px;line-height:1.65}.ar-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:20px}.ar-fact{min-width:0;padding:15px 8px;background:#fff;border:1px solid var(--line);border-radius:8px;text-align:center}.ar-fact b{display:block;font-size:16px;overflow-wrap:anywhere}.ar-fact span{display:block;margin-top:4px;font-size:9px;color:#667085}
.ar-install-grid{display:grid;gap:14px}.ar-install-photo{aspect-ratio:1;border-radius:8px;overflow:hidden;background:#E7ECF2}.ar-install-photo img{width:100%;height:100%;object-fit:cover}.ar-steps{display:grid;gap:10px}.ar-step{padding:18px;background:#fff;border-top:3px solid var(--blue)}.ar-step small{color:var(--blue);font-weight:800}.ar-step h3{margin-top:7px;font-size:16px}.ar-step p{margin-top:5px;color:#667085;font-size:12px;line-height:1.55}
.ar-flex{position:relative;min-height:480px;display:flex;align-items:flex-end;color:#fff;background:#292521}.ar-flex img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.ar-flex:after{content:"";position:absolute;inset:0;background:rgba(7,12,18,.56)}.ar-flex-copy{position:relative;z-index:1;padding:44px 18px;width:min(1160px,100%);margin:auto}.ar-flex h2{font-size:31px;max-width:560px}.ar-flex p{max-width:540px;margin-top:10px;font-size:13px;line-height:1.6;color:#EEF2F6}
.ar-calc{display:grid;gap:22px;padding:24px;border-radius:8px;background:var(--ink);color:#fff}.ar-calc-copy h2{font-size:28px;line-height:1.15}.ar-calc-copy p{margin-top:9px;color:#C8D0DC;font-size:12px;line-height:1.6}.ar-form{padding:18px;border-radius:8px;background:#fff;color:var(--ink)}.ar-fields{display:grid;gap:10px}.ar-field label{display:block;margin-bottom:6px;font-size:10px;font-weight:800}.ar-input{display:flex;border:1px solid #D7DFEA;border-radius:7px;overflow:hidden}.ar-input input{width:100%;border:0;outline:0;padding:13px;font:700 16px inherit}.ar-input span{display:grid;place-items:center;padding:0 11px;background:#F2F5F9;color:#667085;font-size:11px}.ar-calc-button{width:100%;margin-top:12px;background:var(--blue);color:#fff}.ar-result{display:none;margin-top:12px;padding:12px;border-radius:7px;background:#EEF4FF;color:var(--ink);font-size:12px;line-height:1.5}.ar-result.show{display:block}.ar-result strong{display:block;color:var(--blue);font-size:20px}.ar-result.error{background:#FFF0ED;color:#A33A2D}
.ar-buybox{display:grid;gap:22px;align-items:center}.ar-buy-photo{aspect-ratio:1;border-radius:8px;overflow:hidden;background:#F1F3F6}.ar-buy-photo img{width:100%;height:100%;object-fit:cover}.ar-buy-info h2{font-size:27px}.ar-buy-info .ar-color{margin-top:7px;color:#667085;font-size:12px}.ar-buy-price{font-size:31px;font-weight:800;margin:16px 0}.ar-qty{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-radius:8px;background:var(--soft)}.ar-qty>span{font-size:11px;font-weight:800}.ar-stepper{display:flex;align-items:center;gap:12px}.ar-stepper button{width:36px;height:36px;border:1px solid #DCE3ED;border-radius:7px;background:#fff;color:var(--blue);font-size:18px;font-weight:800;cursor:pointer}.ar-stepper output{min-width:20px;text-align:center;font-weight:800}.ar-buy-actions{display:grid;grid-template-columns:48px 1fr;gap:8px;margin-top:10px}.ar-buy-actions .ar-btn{width:100%}.ar-added{display:none;margin-top:9px;text-align:center;color:var(--blue);font-size:11px;font-weight:800}.ar-added.show{display:block}.ar-shipping{margin-top:15px;padding-top:15px;border-top:1px solid var(--line);font-size:11px;line-height:1.5;color:#667085}
.ar-faq{max-width:820px;margin:auto}.ar-faq details{border-bottom:1px solid var(--line);padding:17px 0}.ar-faq summary{cursor:pointer;list-style:none;font-size:13px;font-weight:800}.ar-faq summary::-webkit-details-marker{display:none}.ar-faq p{padding-top:9px;color:#667085;font-size:12px;line-height:1.6}
.ar-mobile-buy{position:fixed;left:0;right:0;bottom:0;z-index:90;display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center;padding:9px 12px calc(9px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid var(--line)}.ar-mobile-buy strong{font-size:14px}.ar-mobile-buy .ar-btn{min-height:46px}
@media(min-width:740px){.ar-nav-links{display:flex}.ar-cart{margin-left:0}.ar-nav-buy{display:flex}.ar-hero h1{font-size:62px}.ar-hero-copy{padding-bottom:76px}.ar-trust b{font-size:12px}.ar-trust span{font-size:10px}.ar-section{padding:84px 0}.ar-split,.ar-buybox{grid-template-columns:1.06fr .94fr;gap:50px}.ar-media.portrait{aspect-ratio:5/4}.ar-install-grid{grid-template-columns:1.05fr .95fr;gap:36px;align-items:center}.ar-calc{grid-template-columns:.85fr 1.15fr;padding:40px;align-items:center}.ar-fields{grid-template-columns:1fr 1fr}.ar-mobile-buy{display:none}.ar-flex-copy{padding:64px 18px}.ar-flex h2{font-size:44px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto!important}}
</style>
"""

    body = r"""
<div class="ar-page">
<nav class="ar-nav"><div class="ar-wrap ar-nav-in">
 <a class="ar-logo" href="./"><span class="ar-logo-i">V</span>VivaBien</a>
 <div class="ar-nav-links"><a href="#producto">Producto</a><a href="#instalacion">Instalación</a><a href="#calculadora">Calculadora</a><a href="#preguntas">Preguntas</a></div>
 <a class="ar-cart" href="carrito" aria-label="Carrito">__BAG__<span class="cart-n" id="cartN"></span></a>
 <a class="ar-nav-buy" href="#comprar">COMPRAR</a>
</div></nav>

<header class="ar-hero">
 <img src="images/__HERO_IMAGE__" alt="Sala con pared decorativa de listones y rollo autoadhesivo" fetchpriority="high">
 <div class="ar-hero-copy">
  <span class="ar-kicker">Panel flexible · Autoadhesivo · Efecto madera</span>
  <h1>Renueva tu pared sin una obra grande.</h1>
  <p>Un panel decorativo en rollo que aporta textura y calidez. Corta, despega y aplica sobre una superficie limpia, lisa y seca.</p>
  <div class="ar-price"><strong>__PRICE__</strong><span>por rollo · __WIDTH__ × __LENGTH__ cm</span></div>
  <div class="ar-buttons"><a class="ar-btn ar-primary" href="#comprar">COMPRAR AHORA</a><a class="ar-btn ar-secondary" href="#instalacion">VER CÓMO SE INSTALA</a></div>
 </div>
</header>

<section class="ar-trust"><div class="ar-wrap ar-trust-in">
 <div><b>🚚 Envíos a todo RD</b><span>Costo según tu zona</span></div>
 <div><b>💵 Pago al recibir</b><span>En Gran Santo Domingo</span></div>
 <div><b>↩️ Garantía 7 días</b><span>Compra con tranquilidad</span></div>
</div></section>

<section class="ar-section" id="producto"><div class="ar-wrap ar-split">
 <div class="ar-media portrait"><img src="images/__PRODUCT_IMAGE__" alt="Rollo de panel decorativo autoadhesivo efecto madera" loading="lazy"><span class="ar-media-note">Vista del producto y tonos de referencia</span></div>
 <div class="ar-copy"><span class="ar-eyebrow">El producto real, de cerca</span><h2>Textura visual de madera en formato flexible</h2><p>El formato en rollo permite cubrir paredes y acompañar curvas suaves. Las líneas oscuras crean profundidad sin ocupar el espacio de un panel rígido.</p>
  <div class="ar-facts"><div class="ar-fact"><b>__WIDTH__ cm</b><span>de ancho</span></div><div class="ar-fact"><b>__LENGTH__ cm</b><span>de largo</span></div><div class="ar-fact"><b>__COVERAGE_LABEL__ m²</b><span>por rollo</span></div></div>
 </div>
</div></section>

<section class="ar-section soft" id="instalacion"><div class="ar-wrap">
 <div class="ar-head"><span class="ar-eyebrow">Instalación sencilla</span><h2>De una pared simple a un acabado con textura</h2><p>Prepara bien la superficie y trabaja poco a poco para mantener las líneas derechas.</p></div>
 <div class="ar-install-grid">
  <div class="ar-install-photo"><img src="images/__INSTALLATION_IMAGE__" alt="Aplicación del panel decorativo flexible sobre una pared" loading="lazy"></div>
  <div class="ar-steps"><article class="ar-step"><small>01</small><h3>Limpia y mide</h3><p>La pared debe estar limpia, completamente seca, lisa y libre de polvo o grasa.</p></article><article class="ar-step"><small>02</small><h3>Corta a la medida</h3><p>Marca el tramo que necesitas y comprueba la posición antes de retirar el protector.</p></article><article class="ar-step"><small>03</small><h3>Despega y presiona</h3><p>Avanza por secciones, presionando de forma uniforme para evitar desalineaciones.</p></article></div>
 </div>
</div></section>

<section class="ar-flex"><img src="images/__FLEXIBLE_IMAGE__" alt="Panel decorativo en rollo adaptándose a una superficie curva" loading="lazy"><div class="ar-flex-copy"><span class="ar-kicker">Flexible por diseño</span><h2>También acompaña curvas suaves y detalles del espacio.</h2><p>Antes de cubrir una superficie completa, prueba una pequeña sección para confirmar adherencia, acabado y dirección del patrón.</p></div></section>

<section class="ar-section" id="calculadora"><div class="ar-wrap ar-calc">
 <div class="ar-calc-copy"><span class="ar-kicker">Calculadora rápida</span><h2>¿Cuántos rollos necesitas?</h2><p>Ingresa las medidas de la superficie. Añadimos un 10% estimado para cortes y ajustes.</p></div>
 <div class="ar-form"><div class="ar-fields"><div class="ar-field"><label>Ancho de la pared</label><div class="ar-input"><input id="arWidth" type="number" inputmode="decimal" min="1" placeholder="Ej. 240"><span>cm</span></div></div><div class="ar-field"><label>Alto de la pared</label><div class="ar-input"><input id="arHeight" type="number" inputmode="decimal" min="1" placeholder="Ej. 260"><span>cm</span></div></div></div><button class="ar-btn ar-calc-button" id="arCalculate" type="button">CALCULAR ROLLOS</button><div class="ar-result" id="arResult"></div></div>
</div></section>

<section class="ar-section soft" id="comprar"><div class="ar-wrap ar-buybox">
 <div class="ar-buy-photo"><img src="images/__ROLL_IMAGE__" alt="Rollo de panel autoadhesivo color roble natural" loading="lazy"></div>
 <div class="ar-buy-info"><span class="ar-eyebrow">Listo para transformar tu espacio</span><h2>__SHORT_NAME__</h2><p class="ar-color">Color: __COLOR__ · Rollo de __WIDTH__ × __LENGTH__ cm</p><div class="ar-buy-price">__PRICE__</div>
  <div class="ar-qty"><span>Cantidad de rollos</span><div class="ar-stepper"><button id="arMinus" type="button" aria-label="Reducir cantidad">−</button><output id="arQty">1</output><button id="arPlus" type="button" aria-label="Aumentar cantidad">+</button></div></div>
  <div class="ar-buy-actions"><a class="ar-btn ar-whatsapp" href="__WA_URL__" target="_blank" aria-label="Consultar por WhatsApp">__WA_ICON__</a><button class="ar-btn ar-primary" id="arAdd" type="button">__BAG__ AGREGAR AL CARRITO</button></div>
  <a class="ar-added" id="arAdded" href="carrito">✓ Agregado. Ver carrito →</a><p class="ar-shipping">__SHIPPING__</p>
 </div>
</div></section>

<section class="ar-section" id="preguntas"><div class="ar-wrap ar-faq"><div class="ar-head"><span class="ar-eyebrow">Antes de pedir</span><h2>Preguntas frecuentes</h2></div>
 <details><summary>¿Qué tamaño tiene cada rollo?</summary><p>Cada rollo mide __WIDTH__ cm de ancho por __LENGTH__ cm de largo y cubre aproximadamente __COVERAGE_LABEL__ m² antes de considerar cortes.</p></details>
 <details><summary>¿Necesita pegamento adicional?</summary><p>El producto tiene respaldo autoadhesivo. La fijación final depende de que la superficie esté limpia, seca y lisa; prueba primero una sección pequeña.</p></details>
 <details><summary>¿Sirve para paredes con textura?</summary><p>No recomendamos asumirlo. Las superficies porosas, húmedas, con polvo o textura marcada pueden reducir la adherencia. Envíanos una foto por WhatsApp antes de pedir.</p></details>
 <details><summary>¿Cómo calculo la cantidad?</summary><p>Usa la calculadora de esta página. El resultado incluye un 10% estimado para cortes, pero conviene confirmar medidas y orientación antes de comprar.</p></details>
 <details><summary>¿Hacen envíos?</summary><p>__SHIPPING__</p></details>
</div></section>

<div class="ar-mobile-buy"><strong>__PRICE__</strong><a class="ar-btn ar-primary" href="#comprar">COMPRAR AHORA</a></div>
</div>
<script>
(function(){
 var PRODUCT=__PRODUCT_JSON__,qty=1,coverage=__COVERAGE__;
 function paintQty(){document.getElementById('arQty').textContent=qty}
 document.getElementById('arMinus').onclick=function(){qty=Math.max(1,qty-1);paintQty()};
 document.getElementById('arPlus').onclick=function(){qty=Math.min(99,qty+1);paintQty()};
 document.getElementById('arCalculate').onclick=function(){
  var w=Number(document.getElementById('arWidth').value),h=Number(document.getElementById('arHeight').value),out=document.getElementById('arResult');
  out.className='ar-result show';
  if(!isFinite(w)||!isFinite(h)||w<=0||h<=0){out.className='ar-result show error';out.textContent='Ingresa medidas válidas mayores que cero.';return}
  var area=(w*h)/10000,rolls=Math.ceil((area*1.10)/coverage);
  out.innerHTML='<strong>'+rolls+' rollo'+(rolls===1?'':'s')+'</strong>Estimado para '+area.toFixed(2)+' m², incluyendo 10% para cortes.';
  qty=Math.min(99,Math.max(1,rolls));paintQty();
  try{vbTrack('search',PRODUCT.sku,{search_query:'adhesive_panel_calculator',result_count:rolls})}catch(e){}
 };
 document.getElementById('arAdd').onclick=function(){
  var c=vbCart(),f=c.find(function(x){return x.sku===PRODUCT.sku});
  if(f)f.qty+=qty;else c.push({sku:PRODUCT.sku,handle:PRODUCT.handle,title:PRODUCT.title,price:PRODUCT.price,img:PRODUCT.img,qty:qty});
  vbSave(c);document.getElementById('arAdded').classList.add('show');this.textContent='✓ AGREGADO AL CARRITO';
  try{fbq('track','AddToCart',{content_ids:[PRODUCT.sku],content_type:'product',value:PRODUCT.price*qty,currency:'DOP'});vbTrack('addcart',PRODUCT.sku,{qty:qty,price:PRODUCT.price,cart_total:c.reduce(function(a,x){return a+x.price*x.qty},0),product_title:PRODUCT.title,product_img:PRODUCT.img})}catch(e){}
 };
})();
</script>
"""
    body = (body.replace("__HERO_IMAGE__", esc(hero_image))
            .replace("__PRODUCT_IMAGE__", esc(product_image))
            .replace("__INSTALLATION_IMAGE__", esc(installation_image))
            .replace("__FLEXIBLE_IMAGE__", esc(flexible_image))
            .replace("__ROLL_IMAGE__", esc(roll_image))
            .replace("__SHORT_NAME__", esc(short_name))
            .replace("__COLOR__", esc(color))
            .replace("__PRICE__", fmt_price(price))
            .replace("__WIDTH__", f"{width:g}")
            .replace("__LENGTH__", f"{length:g}")
            .replace("__COVERAGE_LABEL__", f"{coverage:g}")
            .replace("__SHIPPING__", esc(shipping_text))
            .replace("__WA_URL__", esc(wa_url))
            .replace("__WA_ICON__", WA_SVG)
            .replace("__BAG__", BAG_SVG)
            .replace("__PRODUCT_JSON__", product_json)
            .replace("__COVERAGE__", f"{coverage:.3f}"))

    schema = {
        "@context": "https://schema.org", "@type": "Product", "name": name,
        "sku": sku, "image": [f"{SITE_URL}/images/{hero_image}",
                              f"{SITE_URL}/images/{product_image}"],
        "description": ("Panel decorativo flexible autoadhesivo efecto madera en rollo "
                        f"de {width:g} × {length:g} cm."),
        "color": color,
        "offers": {"@type": "Offer", "priceCurrency": "DOP", "price": f"{price:.2f}",
                   "availability": "https://schema.org/InStock",
                   "url": public_url("panel-autoadhesivo.html")},
    }
    schema_head = ('<script type="application/ld+json">' +
                   json.dumps(schema, ensure_ascii=False).replace("</", "<\\/") + '</script>')
    return page(f"{short_name} | Comprar en RD | {SITE_NAME}", body, wa_float=False,
                desc=("Panel decorativo flexible autoadhesivo efecto madera. "
                      "Mide tu pared, calcula rollos y compra online en VivaBien."),
                track_sku=sku, track_category="Decoración del Hogar",
                track_title=name, track_img=product_image,
                extra_head=css + schema_head,
                canonical=public_url("panel-autoadhesivo.html"),
                og_image=f"{SITE_URL}/images/{quote(hero_image, safe='/')}")


def adhesive_panel_variant_page(variant):
    """Preview-only conversion layouts for the adhesive panel landing page."""
    cfg = load_json(ADHESIVE_PANEL_PATH, {})
    if variant not in (1, 2, 3) or not isinstance(cfg, dict) or not cfg.get("sku"):
        return ""

    sku = str(cfg["sku"]).strip()
    name = str(cfg.get("name") or "Panel decorativo autoadhesivo efecto madera").strip()
    short_name = str(cfg.get("short_name") or name).strip()
    handle = str(cfg.get("handle") or "panel-autoadhesivo").strip()
    color = str(cfg.get("color") or "Roble natural").strip()
    price = float(cfg.get("price") or 0)
    width = float(cfg.get("width_cm") or 0)
    length = float(cfg.get("length_cm") or 0)
    coverage = float(cfg.get("coverage_m2") or 0)
    if min(price, width, length, coverage) <= 0:
        return ""

    product_image = str(cfg.get("product_image") or "").lstrip("/")
    installation_image = str(cfg.get("installation_image") or product_image).lstrip("/")
    roll_image = str(cfg.get("roll_image") or product_image).lstrip("/")
    shipping_text = str(cfg.get("shipping_text") or
                        "El costo y el tiempo de entrega se calculan según tu zona.").strip()
    hero_image = "panel-autoadhesivo/hero-natural.jpg"
    wa_url = (f"https://wa.me/{WHATSAPP}?text=" +
              quote(f"Hola, quiero información sobre {short_name} ({sku})."))
    product_json = json.dumps({
        "sku": sku, "handle": handle, "title": name, "price": price,
        "img": product_image, "color": color,
    }, ensure_ascii=False).replace("</", "<\\/")

    css = r"""
<style>
.av,.av *{box-sizing:border-box}.av{--blue:#2563D9;--orange:#FF6B4A;--ink:#152033;--muted:#667085;--line:#E1E7EF;--soft:#F4F7FB;--green:#17845C;color:var(--ink);background:#fff;overflow:hidden}.av a{text-decoration:none}.av-wrap{width:min(1160px,100%);margin:auto;padding:0 18px}
.av-switch{position:relative;z-index:2;width:max-content;max-width:calc(100% - 16px);margin:8px auto;display:flex;padding:4px;overflow:auto;background:var(--ink);border-radius:8px;box-shadow:0 5px 18px rgba(0,0,0,.14)}.av-switch a{min-width:82px;padding:9px 10px;border-radius:6px;text-align:center;color:#fff;font-size:11px;font-weight:800}.av-switch a.on{background:#fff;color:var(--blue)}
.av-nav{height:62px;display:flex;align-items:center;border-bottom:1px solid var(--line);background:#fff}.av-nav-in{display:flex;align-items:center;gap:12px}.av-logo{display:flex;align-items:center;gap:9px;color:var(--ink);font-size:19px;font-weight:800}.av-logo-i{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;background:var(--blue);color:#fff}.av-nav-links{display:none;margin-left:auto;gap:20px;font-size:12px;font-weight:800}.av-cart{margin-left:auto;width:42px;height:42px;display:grid;place-items:center;border:1px solid var(--line);border-radius:8px;color:var(--blue);position:relative}.av-cart .cart-n{right:-4px;top:-6px}
.av-hero{height:74vh;min-height:510px;max-height:820px;background:#D7D2C9}.av-hero img{width:100%;height:100%;display:block;object-fit:cover;object-position:center 54%}
.av-intro{padding:24px 0;border-bottom:1px solid var(--line)}.av-intro-grid{display:grid;gap:17px}.av-eyebrow{display:block;color:var(--blue);font-size:10px;font-weight:800;text-transform:uppercase}.av-intro h1{margin-top:6px;font-size:28px;line-height:1.1;overflow-wrap:anywhere}.av-spec{margin-top:8px;color:var(--muted);font-size:12px;overflow-wrap:anywhere}.av-price{font-size:29px;font-weight:800}.av-actions{display:grid;grid-template-columns:1fr 48px;gap:8px}.av-btn{min-height:48px;padding:0 15px;border:0;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;gap:8px;font-size:12px;font-weight:800;cursor:pointer}.av-primary{background:var(--orange);color:#fff}.av-wa{background:#25D366;color:#fff}.av-outline{border:1px solid var(--line);background:#fff;color:var(--blue)}
.av-trust{display:grid;grid-template-columns:repeat(3,1fr);background:var(--soft);border-bottom:1px solid var(--line)}.av-trust div{min-height:67px;padding:11px 5px;display:flex;flex-direction:column;justify-content:center;text-align:center;border-right:1px solid var(--line)}.av-trust div:last-child{border:0}.av-trust b{font-size:10px}.av-trust span{margin-top:3px;color:var(--muted);font-size:9px}
.av-section{padding:58px 0}.av-section.soft{background:var(--soft)}.av-head{max-width:660px;margin-bottom:24px}.av-head h2{margin-top:6px;font-size:29px;line-height:1.13}.av-head p{margin-top:9px;color:var(--muted);font-size:13px;line-height:1.6}.av-gallery{display:grid;grid-template-columns:1.25fr .75fr;grid-template-rows:repeat(2,1fr);gap:9px}.av-photo{position:relative;min-height:0;overflow:hidden;border-radius:8px;background:#E6EAF0}.av-photo:first-child{grid-row:1/3;aspect-ratio:4/5}.av-photo img{width:100%;height:100%;display:block;object-fit:cover}.av-photo small{position:absolute;left:9px;bottom:9px;padding:7px 8px;border-radius:5px;background:rgba(255,255,255,.94);font-size:9px;font-weight:800}
.av-proof-grid{display:grid;gap:10px}.av-proof{display:grid;grid-template-columns:110px 1fr;gap:14px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:8px;background:#fff}.av-proof img{width:110px;height:110px;border-radius:6px;object-fit:cover}.av-proof h3{font-size:15px}.av-proof p{margin-top:5px;color:var(--muted);font-size:11px;line-height:1.5}.av-disclosure{margin-top:12px;color:var(--muted);font-size:10px;line-height:1.5}
.av-calc{display:grid;gap:20px;padding:24px;border-radius:8px;background:var(--ink);color:#fff}.av-calc h2{font-size:27px}.av-calc p{margin-top:8px;color:#CBD3DF;font-size:12px;line-height:1.55}.av-form{padding:17px;border-radius:8px;background:#fff;color:var(--ink)}.av-fields{display:grid;gap:10px}.av-field label{display:block;margin-bottom:5px;font-size:10px;font-weight:800}.av-input{display:flex;border:1px solid #D7DFE9;border-radius:7px;overflow:hidden}.av-input input{width:100%;padding:13px;border:0;outline:0;font:700 16px inherit}.av-input span{display:grid;place-items:center;padding:0 10px;background:#F0F3F7;color:var(--muted);font-size:10px}.av-calc-go{width:100%;margin-top:11px;background:var(--blue);color:#fff}.av-result{display:none;margin-top:10px;padding:11px;border-radius:7px;background:#EDF3FF;font-size:11px;line-height:1.5}.av-result.show{display:block}.av-result strong{display:block;color:var(--blue);font-size:20px}.av-result.error{background:#FFF0ED;color:#9B3328}
.av-buy{display:grid;gap:22px;align-items:center}.av-buy-img{aspect-ratio:1;overflow:hidden;border-radius:8px;background:#EDF0F4}.av-buy-img img{width:100%;height:100%;object-fit:cover}.av-buy h2{margin-top:6px;font-size:27px;line-height:1.15}.av-buy-price{margin:15px 0;font-size:31px;font-weight:800}.av-qty{display:flex;align-items:center;justify-content:space-between;padding:9px 11px;border-radius:8px;background:var(--soft);font-size:11px;font-weight:800}.av-stepper{display:flex;align-items:center;gap:12px}.av-stepper button{width:36px;height:36px;border:1px solid var(--line);border-radius:7px;background:#fff;color:var(--blue);font-size:18px}.av-buy-actions{display:grid;grid-template-columns:48px 1fr;gap:8px;margin-top:9px}.av-added{display:none;margin-top:8px;color:var(--blue);text-align:center;font-size:11px;font-weight:800}.av-added.show{display:block}
.av-reviews{display:grid;gap:11px}.av-review{padding:18px;border:1px solid var(--line);border-radius:8px;background:#fff}.av-stars{color:#F2A100;letter-spacing:0;font-size:14px}.av-review blockquote{margin:10px 0;color:#303B4B;font-size:12px;line-height:1.58}.av-review footer{font-size:10px;font-weight:800}.av-review footer span{color:var(--green)}.av-review.critical{border-left:4px solid var(--orange)}.av-review-source{margin-top:13px;color:var(--muted);font-size:10px;line-height:1.5}
.av-warning{display:grid;gap:18px;padding:22px;border-radius:8px;background:#FFF4F0;border:1px solid #FFD8CE}.av-warning h2{font-size:23px}.av-warning p,.av-warning li{color:#70443B;font-size:12px;line-height:1.55}.av-warning ul{margin:10px 0 0 18px}.av-faq details{padding:16px 0;border-bottom:1px solid var(--line)}.av-faq summary{cursor:pointer;font-size:13px;font-weight:800}.av-faq p{padding-top:8px;color:var(--muted);font-size:12px;line-height:1.55}
.av-mobile{position:fixed;z-index:100;left:0;right:0;bottom:0;display:grid;grid-template-columns:auto 1fr;align-items:center;gap:10px;padding:9px 12px calc(9px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid var(--line);transform:translateY(120%);transition:transform .2s ease}.av-mobile.show{transform:translateY(0)}.av-mobile strong{font-size:14px}
.av.v2 .av-intro{background:var(--soft)}.av.v2 .av-intro-grid{padding:18px;border-radius:8px;background:#fff;border:1px solid var(--line)}.av.v2 .av-section{padding:48px 0}.av.v2 .av-proof-grid{grid-template-columns:1fr}.av.v3 .av-intro{border:0}.av.v3 .av-social-lead{background:#163B34;color:#fff}.av.v3 .av-social-lead .av-head p{color:#D4E1DD}.av.v3 .av-social-lead .av-eyebrow{color:#79D2AF}.av.v3 .av-review{border:0}.av.v3 .av-gallery{grid-template-columns:1fr 1fr;grid-template-rows:auto}.av.v3 .av-photo:first-child{grid-row:auto;grid-column:1/3;aspect-ratio:16/10}
@media(min-width:760px){.av-nav-links{display:flex}.av-cart{margin-left:0}.av-hero{height:76vh}.av-intro{padding:30px 0}.av-intro-grid{grid-template-columns:1fr auto auto;align-items:center}.av-intro h1{font-size:34px}.av-actions{min-width:255px}.av-section{padding:82px 0}.av-gallery{grid-template-columns:1.35fr .65fr;gap:14px}.av-photo:first-child{aspect-ratio:16/10}.av-proof-grid{grid-template-columns:repeat(3,1fr)}.av-proof{display:block}.av-proof img{width:100%;height:auto;aspect-ratio:1}.av-proof h3{margin-top:12px}.av-calc{grid-template-columns:.8fr 1.2fr;align-items:center;padding:38px}.av-fields{grid-template-columns:1fr 1fr}.av-buy{grid-template-columns:1fr 1fr;gap:50px}.av-reviews{grid-template-columns:repeat(3,1fr)}.av-warning{grid-template-columns:.8fr 1.2fr;align-items:center}.av-mobile{display:none}.av.v2 .av-proof-grid{grid-template-columns:repeat(3,1fr)}}
@media(prefers-reduced-motion:reduce){.av-mobile{transition:none}}
</style>
"""

    switcher = "".join(
        f'<a class="{"on" if item == variant else ""}" href="panel-autoadhesivo-v{item}.html">'
        f'Versión {item}</a>' for item in (1, 2, 3)
    )
    nav = f"""
<div class="av-switch" aria-label="Comparar diseños">{switcher}</div>
<nav class="av-nav"><div class="av-wrap av-nav-in">
 <a class="av-logo" href="./"><span class="av-logo-i">V</span>VivaBien</a>
 <div class="av-nav-links"><a href="#detalles">Detalles</a><a href="#calculadora">Calculadora</a><a href="#opiniones">Opiniones</a></div>
 <a class="av-cart" href="carrito" aria-label="Carrito">{BAG_SVG}<span class="cart-n" id="cartN"></span></a>
</div></nav>
"""
    hero = f"""
<header class="av-hero" id="hero"><img src="images/{esc(hero_image)}" alt="Ambiente moderno con pared decorativa de listones finos efecto madera" fetchpriority="high"></header>
"""
    intro = f"""
<section class="av-intro"><div class="av-wrap av-intro-grid">
 <div><span class="av-eyebrow">Panel flexible autoadhesivo</span><h1>{esc(short_name)}</h1><p class="av-spec">{width:g} × {length:g} cm · {coverage:g} m² · {esc(color)}</p></div>
 <div class="av-price">{fmt_price(price)}</div>
 <div class="av-actions"><a class="av-btn av-primary" href="#comprar">AGREGAR AL CARRITO</a><a class="av-btn av-wa" href="{esc(wa_url)}" target="_blank" aria-label="Consultar por WhatsApp">{WA_SVG}</a></div>
</div></section>
"""
    trust = """
<div class="av-trust"><div><b>🚚 Envíos a todo RD</b><span>Costo según tu zona</span></div><div><b>💵 Pago al recibir</b><span>Gran Santo Domingo</span></div><div><b>↩️ Garantía 7 días</b><span>Compra con tranquilidad</span></div></div>
"""
    gallery = """
<section class="av-section" id="detalles"><div class="av-wrap">
 <div class="av-head"><span class="av-eyebrow">Mira el acabado</span><h2>Textura, respaldo y cambio visual</h2><p>Imágenes de referencia de productos comparables para ayudarte a entender el formato. El color final puede variar según la luz y la pantalla.</p></div>
 <div class="av-gallery">
  <figure class="av-photo"><img src="images/panel-autoadhesivo/reference-before-after.jpg" alt="Comparación de pared antes y después de aplicar panel flexible" loading="lazy"><small>Antes / después de referencia</small></figure>
  <figure class="av-photo"><img src="images/panel-autoadhesivo/reference-texture.jpg" alt="Detalle cercano de textura acanalada efecto madera" loading="lazy"><small>Textura de referencia</small></figure>
  <figure class="av-photo"><img src="images/panel-autoadhesivo/reference-backing.jpg" alt="Respaldo adhesivo de un panel flexible comparable" loading="lazy"><small>Respaldo autoadhesivo</small></figure>
 </div><p class="av-disclosure">Estas imágenes explicativas pertenecen a productos comparables. Antes de publicar la versión final sustituiremos las que no correspondan exactamente al lote de VivaBien.</p>
</div></section>
"""
    proof = """
<section class="av-section soft"><div class="av-wrap">
 <div class="av-head"><span class="av-eyebrow">Antes de instalar</span><h2>Tres cosas que debes comprobar</h2><p>La preparación de la pared es la parte que más influye en el resultado.</p></div>
 <div class="av-proof-grid">
  <article class="av-proof"><img src="images/panel-autoadhesivo/reference-texture.jpg" alt="Textura de panel flexible" loading="lazy"><div><h3>Revisa el tono</h3><p>Comprueba el color con la luz real del espacio antes de cubrir toda la pared.</p></div></article>
  <article class="av-proof"><img src="images/__INSTALLATION_IMAGE__" alt="Instalación de panel decorativo" loading="lazy"><div><h3>Alinea primero</h3><p>Mide y presenta el rollo antes de retirar completamente el protector.</p></div></article>
  <article class="av-proof"><img src="images/panel-autoadhesivo/reference-surfaces.jpg" alt="Superficies aptas y no aptas para panel autoadhesivo" loading="lazy"><div><h3>Pared lisa y seca</h3><p>Polvo, humedad y textura marcada pueden reducir la adherencia.</p></div></article>
 </div>
</div></section>
""".replace("__INSTALLATION_IMAGE__", esc(installation_image))
    calculator = f"""
<section class="av-section" id="calculadora"><div class="av-wrap av-calc">
 <div><span class="av-eyebrow">Calculadora rápida</span><h2>¿Cuántos rollos necesitas?</h2><p>Calculamos el área y añadimos 10% estimado para cortes. Cada rollo cubre {coverage:g} m².</p></div>
 <div class="av-form"><div class="av-fields"><div class="av-field"><label>Ancho de la pared</label><div class="av-input"><input id="avWidth" type="number" inputmode="decimal" min="1" placeholder="Ej. 240"><span>cm</span></div></div><div class="av-field"><label>Alto de la pared</label><div class="av-input"><input id="avHeight" type="number" inputmode="decimal" min="1" placeholder="Ej. 260"><span>cm</span></div></div></div><button class="av-btn av-calc-go" id="avCalculate" type="button">CALCULAR ROLLOS</button><div class="av-result" id="avResult"></div></div>
</div></section>
"""
    reviews = """
<section class="av-section __REVIEW_CLASS__" id="opiniones"><div class="av-wrap">
 <div class="av-head"><span class="av-eyebrow">Lo que dicen compradores</span><h2>Opiniones verificadas de productos comparables</h2><p>No son todavía reseñas de clientes de VivaBien. Las mostramos como referencia transparente de lo que compradores reales valoran y de los problemas que debemos evitar.</p></div>
 <div class="av-reviews">
  <article class="av-review"><div class="av-stars" aria-label="5 de 5 estrellas">★★★★★</div><blockquote>“Finalmente recibí el producto antes de lo previsto. Tiene un aspecto muy bonito y combinará perfectamente con el fondo de mi mueble para TV.”</blockquote><footer>de***27 · Filipinas · <span>Compra verificada</span></footer></article>
  <article class="av-review"><div class="av-stars" aria-label="5 de 5 estrellas">★★★★★</div><blockquote>“El material se siente bien al tacto y es grueso. El adhesivo parece lo suficientemente fuerte. El diseño es excelente.”</blockquote><footer>Ja***on · Australia · <span>Compra verificada</span></footer></article>
  <article class="av-review critical"><div class="av-stars" aria-label="5 de 5 estrellas">★★★★★</div><blockquote>“Se veía hermoso, pero después aparecieron burbujas y comenzó a despegarse.” Esta experiencia refuerza la importancia de limpiar, secar y probar primero una sección.</blockquote><footer>Judith M. · Colombia · <span>Compra verificada</span></footer></article>
 </div><p class="av-review-source">Fuente de referencia: reseñas visibles en Temu para artículos similares. Texto resumido y traducido cuando correspondía.</p>
</div></section>
""".replace("__REVIEW_CLASS__", "av-social-lead" if variant == 3 else "soft")
    warning = """
<section class="av-section"><div class="av-wrap av-warning">
 <div><span class="av-eyebrow">Evita burbujas y desprendimientos</span><h2>La pared importa tanto como el producto.</h2></div>
 <div><p>Antes de instalar todo el rollo:</p><ul><li>Retira polvo, grasa y humedad.</li><li>No lo apliques sobre pintura suelta o textura profunda.</li><li>Haz una prueba pequeña y espera antes de continuar.</li><li>Presiona por secciones, sin retirar todo el protector de una vez.</li></ul></div>
</div></section>
"""
    buy = f"""
<section class="av-section soft" id="comprar"><div class="av-wrap av-buy">
 <div class="av-buy-img"><img src="images/{esc(roll_image)}" alt="Rollo de panel autoadhesivo efecto madera" loading="lazy"></div>
 <div><span class="av-eyebrow">Listo para pedir</span><h2>{esc(short_name)}</h2><p class="av-spec">SKU {esc(sku)} · {width:g} × {length:g} cm · {coverage:g} m² por rollo</p><div class="av-buy-price">{fmt_price(price)}</div>
  <div class="av-qty"><span>Cantidad de rollos</span><div class="av-stepper"><button id="avMinus" type="button" aria-label="Reducir cantidad">−</button><output id="avQty">1</output><button id="avPlus" type="button" aria-label="Aumentar cantidad">+</button></div></div>
  <div class="av-buy-actions"><a class="av-btn av-wa" href="{esc(wa_url)}" target="_blank" aria-label="Consultar por WhatsApp">{WA_SVG}</a><button class="av-btn av-primary" id="avAdd" type="button">{BAG_SVG} AGREGAR AL CARRITO</button></div>
  <a class="av-added" id="avAdded" href="carrito">✓ Agregado. Ver carrito →</a><p class="av-disclosure">{esc(shipping_text)}</p>
 </div>
</div></section>
"""
    faq = f"""
<section class="av-section" id="preguntas"><div class="av-wrap av-faq"><div class="av-head"><span class="av-eyebrow">Información clara</span><h2>Preguntas frecuentes</h2></div>
 <details><summary>¿Qué tamaño tiene?</summary><p>Cada rollo mide {width:g} cm de ancho por {length:g} cm de largo y cubre aproximadamente {coverage:g} m² antes de cortes.</p></details>
 <details><summary>¿En qué pared se puede colocar?</summary><p>Recomendamos una superficie lisa, limpia y completamente seca. Si tu pared tiene humedad o textura marcada, envíanos una foto antes de pedir.</p></details>
 <details><summary>¿Cómo calculo la cantidad?</summary><p>Usa la calculadora. El resultado añade 10% para cortes, aunque conviene confirmar las medidas antes de comprar.</p></details>
</div></section>
"""

    if variant == 1:
        sections = intro + trust + gallery + proof + calculator + reviews + warning + buy + faq
    elif variant == 2:
        sections = intro + trust + buy + calculator + proof + warning + reviews + faq
    else:
        sections = intro + trust + reviews + gallery + warning + proof + buy + calculator + faq

    js = f"""
<div class="av-mobile" id="avMobile"><strong>{fmt_price(price)}</strong><a class="av-btn av-primary" href="#comprar">COMPRAR</a></div>
</div>
<script>
(function(){{
 var PRODUCT={product_json},qty=1,coverage={coverage:.3f};
 function paint(){{document.getElementById('avQty').textContent=qty}}
 document.getElementById('avMinus').onclick=function(){{qty=Math.max(1,qty-1);paint()}};
 document.getElementById('avPlus').onclick=function(){{qty=Math.min(99,qty+1);paint()}};
 document.getElementById('avCalculate').onclick=function(){{
  var w=Number(document.getElementById('avWidth').value),h=Number(document.getElementById('avHeight').value),out=document.getElementById('avResult');
  out.className='av-result show';
  if(!isFinite(w)||!isFinite(h)||w<=0||h<=0){{out.className='av-result show error';out.textContent='Ingresa medidas válidas mayores que cero.';return}}
  var area=w*h/10000,rolls=Math.ceil(area*1.10/coverage);out.innerHTML='<strong>'+rolls+' rollo'+(rolls===1?'':'s')+'</strong>Estimado para '+area.toFixed(2)+' m², incluyendo 10% para cortes.';qty=Math.min(99,Math.max(1,rolls));paint();
 }};
 document.getElementById('avAdd').onclick=function(){{
  var c=vbCart(),f=c.find(function(x){{return x.sku===PRODUCT.sku}});if(f)f.qty+=qty;else c.push({{sku:PRODUCT.sku,handle:PRODUCT.handle,title:PRODUCT.title,price:PRODUCT.price,img:PRODUCT.img,qty:qty}});vbSave(c);this.textContent='✓ AGREGADO';document.getElementById('avAdded').classList.add('show');
  try{{fbq('track','AddToCart',{{content_ids:[PRODUCT.sku],content_type:'product',value:PRODUCT.price*qty,currency:'DOP'}});vbTrack('addcart',PRODUCT.sku,{{qty:qty,price:PRODUCT.price,source_section:'adhesive_variant_{variant}'}})}}catch(e){{}}
 }};
 var mobile=document.getElementById('avMobile'),hero=document.getElementById('hero');new IntersectionObserver(function(entries){{mobile.classList.toggle('show',!entries[0].isIntersecting)}},{{threshold:.05}}).observe(hero);
}})();
</script>
"""
    body = f'<div class="av v{variant}">{nav}{hero}{sections}{js}'
    return page(f"Propuesta {variant} · {short_name} | {SITE_NAME}", body, wa_float=False,
                desc="Vista previa de diseño para panel decorativo autoadhesivo VivaBien.",
                track_sku=sku, track_category="Decoración del Hogar",
                track_title=name, track_img=product_image, extra_head=css,
                canonical=public_url("panel-autoadhesivo.html"),
                og_image=f"{SITE_URL}/images/{quote(hero_image, safe='/')}")


def adhesive_panel_temu_page():
    """Mobile commerce preview following Temu's proven product-detail hierarchy."""
    cfg = load_json(ADHESIVE_PANEL_PATH, {})
    if not isinstance(cfg, dict) or not cfg.get("sku"):
        return ""
    sku = str(cfg["sku"]).strip()
    name = str(cfg.get("name") or "Panel decorativo autoadhesivo efecto madera").strip()
    short_name = str(cfg.get("short_name") or name).strip()
    handle = str(cfg.get("handle") or "panel-autoadhesivo").strip()
    raw_colors = cfg.get("colors") if isinstance(cfg.get("colors"), list) else []
    colors = [
        {
            "id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "image": str(item.get("image") or "").lstrip("/"),
        }
        for item in raw_colors if isinstance(item, dict)
        and item.get("name") and item.get("image")
    ]
    color = colors[0]["name"] if colors else str(cfg.get("color") or "Roble natural").strip()
    price = float(cfg.get("price") or 0)
    old_price = float(cfg.get("old_price") or 0)
    tier_price = float(cfg.get("tier_price") or price)
    tier_min_qty = max(2, int(cfg.get("tier_min_qty") or 2))
    width = float(cfg.get("width_cm") or 0)
    length = float(cfg.get("length_cm") or 0)
    coverage = float(cfg.get("coverage_m2") or 0)
    if min(price, width, length, coverage) <= 0:
        return ""

    shipping_text = str(cfg.get("shipping_text") or
                        "El costo y el tiempo de entrega se calculan según tu zona.").strip()
    product_image = str(cfg.get("product_image") or "").lstrip("/")
    installation_image = str(cfg.get("installation_image") or product_image).lstrip("/")
    hero_image = str(cfg.get("hero_image") or "panel-autoadhesivo/hero-ai-v2.jpg").lstrip("/")
    wa_url = (f"https://wa.me/{WHATSAPP}?text=" +
              quote(f"Hola, quiero información sobre {short_name} ({sku})."))
    selected_image = colors[0]["image"] if colors else product_image
    product_json = json.dumps({
        "sku": sku, "handle": handle, "title": name, "price": price,
        "old_price": old_price, "tier_price": tier_price,
        "tier_min_qty": tier_min_qty, "img": selected_image, "color": color,
    }, ensure_ascii=False).replace("</", "<\\/")
    color_html = "".join(
        f'<button class="tm-color-option{" on" if i == 0 else ""}" type="button" '
        f'data-color="{esc(item["name"])}" data-image="{esc(item["image"])}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">'
        f'<span class="tm-color-photo"><img src="images/{esc(item["image"])}" '
        f'alt="Color {esc(item["name"])}" loading="lazy"></span>'
        f'<b>{esc(item["name"])}</b></button>'
        for i, item in enumerate(colors)
    )
    slides = [
        (hero_image,
         "Ambiente decorado con panel flexible efecto madera"),
        ("panel-autoadhesivo/hero-natural.jpg",
         "Ambiente moderno con panel decorativo efecto madera"),
        (product_image, "Rollo de panel decorativo y colores de referencia"),
        ("panel-autoadhesivo/reference-texture.jpg",
         "Detalle de textura de un producto comparable"),
        ("panel-autoadhesivo/reference-backing.jpg",
         "Respaldo autoadhesivo de un producto comparable"),
        ("panel-autoadhesivo/reference-before-after.jpg",
         "Antes y después de referencia"),
    ]
    slide_html = "".join(
        f'<figure class="tm-slide{" tm-slide-main" if i == 0 else ""}"><img src="images/{esc(src)}" alt="{esc(alt)}" '
        + ('fetchpriority="high"' if i == 0 else 'loading="lazy"')
        + '></figure>'
        for i, (src, alt) in enumerate(slides)
    )
    thumb_html = "".join(
        f'<button class="tm-thumb{" on" if i == 0 else ""}" type="button" data-slide="{i}" '
        f'aria-label="Ver imagen {i + 1}"><img src="images/{esc(src)}" alt=""></button>'
        for i, (src, _) in enumerate(slides)
    )

    css = r"""
<style>
.tm,.tm *{box-sizing:border-box}.tm{--ink:#191919;--muted:#666;--line:#E5E5E5;--orange:#FF6B00;--blue:#2563D9;--green:#169B45;background:#F5F5F5;color:var(--ink);overflow:hidden}.tm button{font:inherit}.tm-wrap{width:min(760px,100%);margin:auto;background:#fff}
.tm-head{height:58px;padding:0 14px;display:flex;align-items:center;gap:10px;background:#fff;border-bottom:1px solid var(--line)}.tm-back,.tm-icon{width:40px;height:40px;display:grid;place-items:center;border:1px solid var(--line);border-radius:50%;background:#fff;color:var(--ink)}.tm-icon{position:relative}.tm-logo{margin-right:auto;display:flex;align-items:center;gap:8px;font-size:18px;font-weight:800}.tm-logo span{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;background:var(--blue);color:#fff}
.tm-gallery{position:relative;background:#F0F0F0}.tm-track{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}.tm-track::-webkit-scrollbar{display:none}.tm-slide{min-width:100%;height:min(72vh,650px);scroll-snap-align:start;overflow:hidden;background:#111}.tm-slide img{width:100%;height:100%;display:block;object-fit:cover}.tm-count{position:absolute;right:13px;bottom:13px;padding:6px 10px;border-radius:16px;background:rgba(0,0,0,.62);color:#fff;font-size:11px}.tm-thumbs{display:flex;gap:7px;padding:10px 12px;overflow:auto;background:#fff}.tm-thumb{flex:0 0 56px;width:56px;height:56px;padding:0;border:2px solid transparent;border-radius:7px;overflow:hidden;background:#EEE}.tm-thumb.on{border-color:var(--orange)}.tm-thumb img{width:100%;height:100%;object-fit:cover}
.tm-strip{display:flex;align-items:center;gap:8px;padding:11px 14px;background:#F0FFF4;color:#117A36;border-top:1px solid #D8F3E1;border-bottom:1px solid #D8F3E1;font-size:12px;font-weight:700}.tm-strip span{color:#D0D0D0}
.tm-info{padding:15px 14px 17px}.tm-info h1{font-size:19px;line-height:1.32;overflow-wrap:anywhere}.tm-meta{margin-top:8px;color:var(--muted);font-size:11px;line-height:1.5}.tm-old-price{margin-top:12px;color:var(--muted);font-size:11px}.tm-old-price del{margin-left:4px;text-decoration-thickness:1.5px}.tm-price{display:flex;align-items:baseline;gap:7px;margin-top:5px}.tm-price strong{color:var(--orange);font-size:34px;line-height:1}.tm-price span{color:var(--muted);font-size:11px}.tm-tier-deals{display:grid;gap:7px;margin-top:13px}.tm-tier-option{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:48px;padding:8px 10px;border:1px solid #FFD0B2;border-radius:7px;background:#FFF8F3;color:var(--ink);text-align:left}.tm-tier-option.on{border:2px solid var(--orange);background:#FFF1E7}.tm-tier-option b{display:block;font-size:12px}.tm-tier-option small{display:block;margin-top:2px;color:var(--muted);font-size:9px}.tm-tier-option strong{color:var(--orange);font-size:14px;white-space:nowrap}.tm-stock{display:inline-block;margin-top:10px;padding:5px 8px;border:1px solid #FFB485;border-radius:4px;color:#C94E00;font-size:10px;font-weight:800}
.tm-choice{padding:16px 14px;border-top:8px solid #F5F5F5}.tm-row-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px;font-size:14px;font-weight:800}.tm-row-title span{color:var(--muted);font-size:11px;font-weight:500}.tm-color-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.tm-color-option{position:relative;min-width:0;padding:4px 4px 8px;border:1px solid #DADDE2;border-radius:7px;background:#fff;color:var(--ink);text-align:left}.tm-color-option.on{border:2px solid var(--blue);padding:3px 3px 7px;box-shadow:0 0 0 2px rgba(37,99,217,.1)}.tm-color-option.on:after{content:"✓";position:absolute;top:8px;right:8px;width:20px;height:20px;display:grid;place-items:center;border-radius:50%;background:var(--blue);color:#fff;font-size:11px;font-weight:900}.tm-color-photo{display:block;width:100%;aspect-ratio:1;overflow:hidden;border-radius:4px;background:#EEE}.tm-color-photo img{width:100%;height:100%;display:block;object-fit:cover}.tm-color-option b{display:block;padding:7px 3px 0;font-size:9px;line-height:1.25;overflow-wrap:anywhere}.tm-qty{display:flex;align-items:center;gap:0}.tm-qty button{width:39px;height:39px;border:1px solid #DDD;background:#F7F7F7;font-size:20px}.tm-qty output{min-width:44px;height:39px;display:grid;place-items:center;border-top:1px solid #DDD;border-bottom:1px solid #DDD;font-weight:800}
.tm-review-showcase{padding:16px 0 18px;border-top:8px solid #F5F5F5;background:#fff}.tm-review-showcase-head{display:flex;align-items:center;justify-content:space-between;padding:0 14px 11px}.tm-review-showcase-head h2{font-size:18px}.tm-review-nav{display:flex;gap:6px}.tm-review-nav button{width:34px;height:34px;border:1px solid var(--line);border-radius:50%;background:#fff;color:var(--ink);font-size:18px}.tm-review-track{display:flex;gap:10px;padding:0 14px;overflow-x:auto;overscroll-behavior-x:contain;scroll-behavior:smooth;scroll-snap-type:x mandatory;scrollbar-width:none;-webkit-overflow-scrolling:touch;touch-action:auto}.tm-review-track::-webkit-scrollbar{display:none}.tm-review-card{flex:0 0 min(86vw,350px);overflow:hidden;border-radius:8px;background:#050505;color:#fff;scroll-snap-align:start;scroll-snap-stop:always}.tm-review-photo{width:100%;height:390px;padding:0;border:0;overflow:hidden;background:#151515;cursor:zoom-in;touch-action:auto}.tm-review-photo img{width:100%;height:100%;display:block;object-fit:cover;object-position:center 36%;pointer-events:none}.tm-review-copy{padding:13px 14px 15px}.tm-review-user{display:flex;justify-content:space-between;gap:8px;color:#E7E7E7;font-size:10px}.tm-review-copy .tm-stars{margin-top:8px;color:#fff;font-size:16px}.tm-review-copy p{min-height:54px;margin-top:8px;font-size:11px;line-height:1.52}.tm-review-buy{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px}.tm-review-buy strong{font-size:16px}.tm-review-add{min-height:38px;padding:0 14px;border:0;border-radius:20px;background:var(--orange);color:#fff;font-size:10px;font-weight:800}
.tm-trust{display:grid;grid-template-columns:repeat(3,1fr);border-top:8px solid #F5F5F5;border-bottom:8px solid #F5F5F5;background:#fff}.tm-trust div{padding:13px 5px;text-align:center;border-right:1px solid var(--line)}.tm-trust div:last-child{border:0}.tm-trust b{display:block;font-size:10px}.tm-trust span{display:block;margin-top:4px;color:var(--muted);font-size:9px}
.tm-section{padding:22px 14px;border-bottom:8px solid #F5F5F5}.tm-section h2{font-size:20px}.tm-section>p{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.55}.tm-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}.tm-fact{padding:13px 5px;text-align:center;border:1px solid var(--line);border-radius:7px}.tm-fact b{display:block;font-size:15px}.tm-fact span{display:block;margin-top:4px;color:var(--muted);font-size:9px}
.tm-compare{margin-top:14px}.tm-compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.tm-compare-panel{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:7px;background:#EEE}.tm-compare-panel img{width:100%;height:100%;display:block;object-fit:cover}.tm-compare-panel span{position:absolute;left:8px;bottom:8px;padding:5px 8px;border-radius:4px;background:rgba(0,0,0,.72);color:#fff;font-size:9px;font-weight:900}.tm-compare-note{margin:7px 1px 0;color:var(--muted);font-size:9px;line-height:1.45}.tm-detail-row{display:flex;gap:10px;margin-top:15px;padding-bottom:4px;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}.tm-detail-row::-webkit-scrollbar{display:none}.tm-detail-card{flex:0 0 min(78vw,310px);margin:0;overflow:hidden;border:1px solid var(--line);border-radius:7px;background:#fff;scroll-snap-align:start}.tm-detail-card img{width:100%;aspect-ratio:1;display:block;object-fit:cover}.tm-detail-card figcaption{padding:10px 11px;color:var(--muted);font-size:10px;line-height:1.45}.tm-detail-card figcaption b{display:block;margin-bottom:3px;color:var(--ink);font-size:11px}
.tm-spanish-details{display:grid;gap:10px;margin-top:16px}.tm-spanish-detail{margin:0;overflow:hidden;border:1px solid var(--line);border-radius:7px;background:#fff}.tm-spanish-detail img{width:100%;display:block}.tm-spanish-detail figcaption{padding:10px 11px;color:var(--muted);font-size:10px;line-height:1.45}
.tm-warning{margin-top:14px;padding:14px;border-radius:7px;background:#FFF5EE;border:1px solid #FFD8BD}.tm-warning b{font-size:13px}.tm-warning ul{margin:8px 0 0 18px;color:#73452C;font-size:11px;line-height:1.65}
.tm-calc{margin-top:14px;padding:16px;border-radius:7px;background:#20252D;color:#fff}.tm-fields{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.tm-field label{display:block;margin-bottom:5px;color:#D5DBE3;font-size:9px}.tm-input{display:flex;overflow:hidden;border-radius:6px;background:#fff}.tm-input input{min-width:0;width:100%;padding:12px 9px;border:0;outline:0;font-weight:800}.tm-input span{display:grid;place-items:center;padding:0 8px;background:#EEE;color:#555;font-size:9px}.tm-calc button{width:100%;margin-top:9px;background:var(--orange);color:#fff}.tm-result{display:none;margin-top:9px;padding:10px;border-radius:6px;background:#fff;color:var(--ink);font-size:11px}.tm-result.show{display:block}.tm-result strong{display:block;color:var(--orange);font-size:19px}
.tm-buyer-photos{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:14px}.tm-buyer-photo{margin:0;overflow:hidden;border-radius:7px;background:#F0F0F0}.tm-buyer-photo img{width:100%;aspect-ratio:1;display:block;object-fit:cover}.tm-buyer-photo figcaption{padding:7px 5px;color:var(--muted);font-size:8px;line-height:1.35;text-align:center}
.tm-reviews{display:grid;gap:10px;margin-top:14px}.tm-review{padding:14px;border:1px solid var(--line);border-radius:7px}.tm-stars{color:#FF9A00;font-size:13px}.tm-review p{margin-top:8px;font-size:12px;line-height:1.5}.tm-review footer{margin-top:10px;color:var(--muted);font-size:9px}.tm-source{margin-top:11px!important;font-size:9px!important}.tm-wa{display:flex;align-items:center;justify-content:center;gap:8px;min-height:48px;margin-top:13px;border-radius:7px;background:#25D366;color:#fff;font-size:12px;font-weight:800}
.tm-bottom{position:fixed;z-index:100;left:0;right:0;bottom:0;padding:9px 10px calc(9px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid #DDD}.tm-bottom-in{width:min(740px,100%);margin:auto;display:grid;grid-template-columns:auto 1fr;gap:11px;align-items:center}.tm-bottom-price span{display:block;color:var(--muted);font-size:9px}.tm-bottom-price strong{font-size:18px}.tm-add{min-height:52px;border:0;border-radius:26px;background:var(--orange);color:#fff;font-size:14px;font-weight:900}.tm-added{display:none;padding:9px 14px;background:#E9FFF1;color:#087D32;text-align:center;font-size:11px;font-weight:800}.tm-added.show{display:block}
.tm-lightbox{position:fixed;z-index:400;inset:0;display:none;grid-template-rows:auto 1fr auto;background:#000;color:#fff}.tm-lightbox.show{display:grid}.tm-lightbox-top{display:flex;align-items:center;justify-content:space-between;padding:12px 14px calc(8px + env(safe-area-inset-top))}.tm-lightbox-close,.tm-lightbox-arrow{width:44px;height:44px;border:0;border-radius:50%;background:rgba(255,255,255,.14);color:#fff;font-size:25px}.tm-lightbox-stage{position:relative;min-height:0;display:grid;place-items:center;overflow:hidden;touch-action:pan-y}.tm-lightbox-stage img{width:100%;height:100%;display:block;object-fit:contain}.tm-lightbox-arrow{position:absolute;top:50%;transform:translateY(-50%)}.tm-lightbox-prev{left:10px}.tm-lightbox-next{right:10px}.tm-lightbox-caption{padding:10px 18px calc(16px + env(safe-area-inset-bottom));text-align:center;color:#D9D9D9;font-size:11px}
.tm-spacer{height:84px}
@media(max-width:779px){.tm-slide-main img{transform:scale(1.6)}}
@media(min-width:780px){.tm-wrap{margin-top:20px;box-shadow:0 8px 30px rgba(0,0,0,.08)}.tm-compare-panel{aspect-ratio:16/10}.tm-detail-card{flex-basis:300px}.tm-spanish-details{grid-template-columns:1fr 1fr}.tm-reviews{grid-template-columns:repeat(3,1fr)}.tm-bottom{left:50%;right:auto;width:760px;transform:translateX(-50%)}}
</style>
"""
    body = f"""
<div class="tm"><main class="tm-wrap">
 <header class="tm-head"><a class="tm-back" href="./" aria-label="Volver">‹</a><a class="tm-logo" href="./"><span>V</span>VivaBien</a><a class="tm-icon" href="buscar" aria-label="Buscar">⌕</a><a class="tm-icon" href="carrito" aria-label="Carrito">{BAG_SVG}<span class="cart-n" id="cartN"></span></a></header>
 <section class="tm-gallery"><div class="tm-track" id="tmTrack">{slide_html}</div><span class="tm-count"><b id="tmCurrent">1</b> / {len(slides)}</span></section>
 <div class="tm-thumbs">{thumb_html}</div>
 <div class="tm-strip">✓ Envíos a todo RD <span>|</span> ✓ Compra protegida</div>
 <section class="tm-info">
  <h1>{esc(name)}</h1><p class="tm-meta">SKU {esc(sku)} · Panel flexible en rollo · {width:g} × {length:g} cm</p>
  <div class="tm-old-price">Antes <del>{fmt_price(old_price)}</del></div>
  <div class="tm-price"><strong>{fmt_price(price)}</strong><span>por rollo · {coverage:g} m²</span></div>
  <div class="tm-tier-deals"><button class="tm-tier-option" type="button" data-tier-qty="2"><span><b>Compra 2 rollos</b><small>Antes {fmt_price(price * 2)} · Ahorras {fmt_price((price - tier_price) * 2)}</small></span><strong>{fmt_price(tier_price * 2)}</strong></button><button class="tm-tier-option" type="button" data-tier-qty="3"><span><b>Compra 3 rollos</b><small>Antes {fmt_price(price * 3)} · Ahorras {fmt_price((price - tier_price) * 3)}</small></span><strong>{fmt_price(tier_price * 3)}</strong></button></div>
  <span class="tm-stock">PRECIO CONFIRMADO</span>
 </section>
 <section class="tm-choice"><div class="tm-row-title">Elige el color <span>Seleccionado: <b id="tmSelectedColor">{esc(color)}</b></span></div><div class="tm-color-grid">{color_html}</div></section>
 <section class="tm-choice"><div class="tm-row-title">Cantidad <span>Rollo de {width:g} × {length:g} cm</span></div><div class="tm-qty"><button id="tmMinus" type="button" aria-label="Reducir cantidad">−</button><output id="tmQty">1</output><button id="tmPlus" type="button" aria-label="Aumentar cantidad">+</button></div></section>
 <section class="tm-review-showcase" id="opiniones"><div class="tm-review-showcase-head"><h2>Fotos de compradores</h2><div class="tm-review-nav"><button id="tmReviewPrev" type="button" aria-label="Foto anterior">‹</button><button id="tmReviewNext" type="button" aria-label="Foto siguiente">›</button></div></div><div class="tm-review-track" id="tmReviewTrack">
  <article class="tm-review-card"><button class="tm-review-photo tm-review-open" data-review="0" type="button" aria-label="Ampliar foto de 08***07"><img src="images/panel-autoadhesivo/customer-review-1.jpg" alt="Instalación compartida por comprador de panel similar" loading="lazy"></button><div class="tm-review-copy"><div class="tm-review-user"><b>08***07</b><span>Compra verificada</span></div><div class="tm-stars">★★★★☆</div><p>Se ve genial, pero al abrirlo noté que algunas partes tenían burbujas y tuve que reemplazarlo.</p><div class="tm-review-buy"><strong>{fmt_price(price)}</strong><button class="tm-review-add" type="button">Añadir al carrito</button></div></div></article>
  <article class="tm-review-card"><button class="tm-review-photo tm-review-open" data-review="1" type="button" aria-label="Ampliar foto de Alexandra Davis"><img src="images/panel-autoadhesivo/customer-review-2.jpg" alt="Pared decorada compartida por compradora de panel similar" loading="lazy"></button><div class="tm-review-copy"><div class="tm-review-user"><b>Alexandra Davis</b><span>Compra verificada</span></div><div class="tm-stars">★★★★★</div><p>Un cambio absolutamente increíble que transforma completamente la dinámica de la habitación.</p><div class="tm-review-buy"><strong>{fmt_price(price)}</strong><button class="tm-review-add" type="button">Añadir al carrito</button></div></div></article>
  <article class="tm-review-card"><button class="tm-review-photo tm-review-open" data-review="2" type="button" aria-label="Ampliar foto de da***20"><img src="images/panel-autoadhesivo/customer-review-3.jpg" alt="Isla de cocina decorada con panel efecto madera" loading="lazy"></button><div class="tm-review-copy"><div class="tm-review-user"><b>da***20</b><span>Foto de comprador</span></div><div class="tm-stars">★★★★☆</div><p>Es fácil de instalar y le da un aspecto muy bonito.</p><div class="tm-review-buy"><strong>{fmt_price(price)}</strong><button class="tm-review-add" type="button">Añadir al carrito</button></div></div></article>
  <article class="tm-review-card"><button class="tm-review-photo tm-review-open" data-review="3" type="button" aria-label="Ampliar foto de Lucy Juniper"><img src="images/panel-autoadhesivo/customer-review-4.jpg" alt="Habitación con panel gris compartida por compradora" loading="lazy"></button><div class="tm-review-copy"><div class="tm-review-user"><b>Lucy Juniper</b><span>Compra verificada</span></div><div class="tm-stars">★★★★★</div><p>Es muy fácil de usar, pero hay que tener cuidado al cortar el rollo porque puede agrietarse.</p><div class="tm-review-buy"><strong>{fmt_price(price)}</strong><button class="tm-review-add" type="button">Añadir al carrito</button></div></div></article>
  <article class="tm-review-card"><button class="tm-review-photo tm-review-open" data-review="4" type="button" aria-label="Ampliar foto de Sarah Ristagno"><img src="images/panel-autoadhesivo/customer-review-5.jpg" alt="Pared de televisión decorada compartida por compradora" loading="lazy"></button><div class="tm-review-copy"><div class="tm-review-user"><b>Sarah Ristagno</b><span>Foto de comprador</span></div><div class="tm-stars">★★★★☆</div><p>Foto compartida después de instalar un panel similar en la pared del televisor.</p><div class="tm-review-buy"><strong>{fmt_price(price)}</strong><button class="tm-review-add" type="button">Añadir al carrito</button></div></div></article>
  <article class="tm-review-card"><button class="tm-review-photo tm-review-open" data-review="5" type="button" aria-label="Ampliar foto de Paula Barbosa"><img src="images/panel-autoadhesivo/customer-review-6.jpg" alt="Pared de baño decorada con panel efecto madera" loading="lazy"></button><div class="tm-review-copy"><div class="tm-review-user"><b>Paula Barbosa</b><span>Foto de comprador</span></div><div class="tm-stars">★★★★★</div><p>Excelente. Justo lo que imaginé. Hay que colocarlo con cuidado para evitar doblarlo.</p><div class="tm-review-buy"><strong>{fmt_price(price)}</strong><button class="tm-review-add" type="button">Añadir al carrito</button></div></div></article>
 </div><p class="tm-source" style="padding:0 14px">Fotos y opiniones de compradores de productos similares; las medidas mostradas en las capturas pueden ser diferentes.</p></section>
 <div class="tm-trust"><div><b>🚚 Envíos</b><span>Todo el país</span></div><div><b>💵 Contra entrega</b><span>Gran Santo Domingo</span></div><div><b>↩️ Garantía</b><span>7 días</span></div></div>
 <section class="tm-section" id="detalles"><h2>Detalles del producto</h2><p>Un revestimiento flexible con efecto de listones finos para renovar paredes sin el volumen de un panel rígido.</p><div class="tm-facts"><div class="tm-fact"><b>{width:g} cm</b><span>Ancho</span></div><div class="tm-fact"><b>{length:g} cm</b><span>Largo</span></div><div class="tm-fact"><b>{coverage:g} m²</b><span>Por rollo</span></div></div>
  <div class="tm-compare"><div class="tm-compare-grid"><div class="tm-compare-panel"><img src="images/panel-autoadhesivo/detail-before-ai.png" alt="Comedor con pared lisa antes de la renovación" loading="lazy"><span>ANTES</span></div><div class="tm-compare-panel"><img src="images/panel-autoadhesivo/detail-after-brown.jpg" alt="Comedor con panel decorativo marrón instalado" loading="lazy"><span>DESPUÉS</span></div></div><p class="tm-compare-note">Visualización del mismo ambiente. La imagen “Antes” fue recreada con IA para mostrar el cambio de pared; confirma el tono real en las fotos del producto.</p></div>
  <div class="tm-detail-row" aria-label="Detalles visuales del panel"><figure class="tm-detail-card"><img src="images/panel-autoadhesivo/detail-brown-room.jpg" alt="Panel flexible marrón aplicado en una pared moderna" loading="lazy"><figcaption><b>Resultado completo</b>Referencia de cómo el listón fino cambia una pared.</figcaption></figure><figure class="tm-detail-card"><img src="images/panel-autoadhesivo/detail-brown-roll.jpg" alt="Rollo de panel flexible marrón junto a una pared" loading="lazy"><figcaption><b>Formato flexible</b>El producto se presenta en rollo para facilitar el manejo.</figcaption></figure><figure class="tm-detail-card"><img src="images/panel-autoadhesivo/detail-adhesive-backing.jpg" alt="Parte trasera adhesiva de un panel flexible comparable" loading="lazy"><figcaption><b>Respaldo autoadhesivo</b>Retira el protector poco a poco durante la aplicación.</figcaption></figure><figure class="tm-detail-card"><img src="images/panel-autoadhesivo/detail-texture-close.jpg" alt="Detalle cercano de textura y líneas del panel" loading="lazy"><figcaption><b>Textura de cerca</b>Las líneas finas crean profundidad sin ocupar mucho espacio.</figcaption></figure></div>
  <div class="tm-spanish-details"><figure class="tm-spanish-detail"><img src="images/panel-autoadhesivo/detail-spanish-before-after.jpg" alt="Antes y después de una pared renovada con panel decorativo" loading="lazy"><figcaption>Una pared deteriorada puede convertirse en un punto focal más cálido.</figcaption></figure><figure class="tm-spanish-detail"><img src="images/panel-autoadhesivo/detail-spanish-spaces-v2.jpg" alt="Panel decorativo usado en comedor, sala y dormitorio" loading="lazy"><figcaption>Referencia de uso en sala, comedor y dormitorio.</figcaption></figure></div>
  <div class="tm-warning"><b>Antes de instalar</b><ul><li>Elimina polvo, grasa y humedad.</li><li>No lo apliques sobre pintura suelta o textura profunda.</li><li>Prueba una sección pequeña antes de cubrir toda la pared.</li><li>Avanza por secciones para reducir burbujas.</li></ul></div>
 </section>
 <section class="tm-section" id="calculadora"><h2>Calcula cuántos rollos necesitas</h2><p>Añadimos 10% estimado para cortes y ajustes.</p><div class="tm-calc"><div class="tm-fields"><div class="tm-field"><label>Ancho de la pared</label><div class="tm-input"><input id="tmWidth" type="number" inputmode="decimal" min="1" placeholder="240"><span>cm</span></div></div><div class="tm-field"><label>Alto de la pared</label><div class="tm-input"><input id="tmHeight" type="number" inputmode="decimal" min="1" placeholder="260"><span>cm</span></div></div></div><button class="tm-add" id="tmCalculate" type="button">CALCULAR</button><div class="tm-result" id="tmResult"></div></div></section>
 <section class="tm-section"><h2>¿Necesitas ayuda antes de pedir?</h2><p>Envíanos una foto de tu pared y sus medidas. Te ayudamos a confirmar la cantidad y si la superficie es adecuada.</p><a class="tm-wa" href="{esc(wa_url)}" target="_blank">{WA_SVG} CONSULTAR POR WHATSAPP</a></section>
 <div class="tm-added" id="tmAdded">✓ Agregado al carrito</div><div class="tm-spacer"></div>
 </main>
 <div class="tm-lightbox" id="tmLightbox" role="dialog" aria-modal="true" aria-label="Fotos de compradores" aria-hidden="true"><div class="tm-lightbox-top"><button class="tm-lightbox-close" id="tmLightboxClose" type="button" aria-label="Cerrar">×</button><b id="tmLightboxCount">1 / 6</b><span style="width:44px"></span></div><div class="tm-lightbox-stage" id="tmLightboxStage"><img id="tmLightboxImage" src="images/panel-autoadhesivo/customer-review-1.jpg" alt="Foto de comprador ampliada"><button class="tm-lightbox-arrow tm-lightbox-prev" id="tmLightboxPrev" type="button" aria-label="Foto anterior">‹</button><button class="tm-lightbox-arrow tm-lightbox-next" id="tmLightboxNext" type="button" aria-label="Foto siguiente">›</button></div><div class="tm-lightbox-caption" id="tmLightboxCaption"></div></div>
 <div class="tm-bottom"><div class="tm-bottom-in"><div class="tm-bottom-price"><span>Total del producto</span><strong id="tmTotal">{fmt_price(price)}</strong></div><button class="tm-add" id="tmAdd" type="button">¡AGRÉGALO AHORA!</button></div></div>
</div>
<script>
(function(){{
 var PRODUCT={product_json},qty=1,coverage={coverage:.3f},slides={len(slides)},track=document.getElementById('tmTrack');
 function money(n){{return 'RD$ '+Math.round(n).toLocaleString('en-US')}}
 function unitPrice(q){{return q>=PRODUCT.tier_min_qty?PRODUCT.tier_price:PRODUCT.price}}
 function totalPrice(q){{return unitPrice(q)*q}}
 function paint(){{document.getElementById('tmQty').textContent=qty;document.getElementById('tmTotal').textContent=money(totalPrice(qty));document.querySelectorAll('.tm-tier-option').forEach(function(b){{b.classList.toggle('on',Number(b.dataset.tierQty)===qty)}})}}
 function changeQty(next,source){{var previous=qty;qty=Math.max(1,Math.min(99,next));paint();if(qty!==previous)try{{vbTrack('quantity_change',PRODUCT.sku,{{qty:qty,price:unitPrice(qty),cart_total:totalPrice(qty),offer_qty:qty,selected_color:PRODUCT.color,source_section:source}})}}catch(e){{}}}}
 document.getElementById('tmMinus').onclick=function(){{changeQty(qty-1,'quantity_stepper')}};
 document.getElementById('tmPlus').onclick=function(){{changeQty(qty+1,'quantity_stepper')}};
 document.querySelectorAll('.tm-tier-option').forEach(function(button){{button.onclick=function(){{changeQty(Number(button.dataset.tierQty),'volume_offer');try{{vbTrack('tier_select',PRODUCT.sku,{{qty:qty,price:unitPrice(qty),cart_total:totalPrice(qty),offer_qty:qty,selected_color:PRODUCT.color,source_section:'price_offer'}})}}catch(e){{}}}}}});
 document.querySelectorAll('.tm-color-option').forEach(function(button){{button.onclick=function(){{document.querySelectorAll('.tm-color-option').forEach(function(item){{var selected=item===button;item.classList.toggle('on',selected);item.setAttribute('aria-pressed',selected?'true':'false')}});PRODUCT.color=button.dataset.color;PRODUCT.img=button.dataset.image;document.getElementById('tmSelectedColor').textContent=PRODUCT.color;try{{vbTrack('color_select',PRODUCT.sku,{{selected_color:PRODUCT.color,source_section:'color_selector'}})}}catch(e){{}}}}}});
 document.querySelectorAll('.tm-thumb').forEach(function(b){{b.onclick=function(){{var i=Number(b.dataset.slide);track.scrollTo({{left:track.clientWidth*i,behavior:'smooth'}})}}}});
 var galleryIndex=-1;track.addEventListener('scroll',function(){{var i=Math.max(0,Math.min(slides-1,Math.round(track.scrollLeft/track.clientWidth)));document.getElementById('tmCurrent').textContent=i+1;document.querySelectorAll('.tm-thumb').forEach(function(b){{b.classList.toggle('on',Number(b.dataset.slide)===i)}});if(i!==galleryIndex){{galleryIndex=i;try{{vbTrack('gallery_view',PRODUCT.sku,{{gallery_index:i,selected_color:PRODUCT.color,source_section:'product_gallery'}})}}catch(e){{}}}}}},{{passive:true}});
 document.getElementById('tmCalculate').onclick=function(){{var w=Number(document.getElementById('tmWidth').value),h=Number(document.getElementById('tmHeight').value),out=document.getElementById('tmResult');out.className='tm-result show';if(!isFinite(w)||!isFinite(h)||w<=0||h<=0){{out.textContent='Ingresa medidas válidas mayores que cero.';return}}var area=w*h/10000,rolls=Math.ceil(area*1.10/coverage);out.innerHTML='<strong>'+rolls+' rollo'+(rolls===1?'':'s')+'</strong>Estimado para '+area.toFixed(2)+' m² con 10% para cortes.';qty=Math.min(99,Math.max(1,rolls));paint();try{{vbTrack('calculator_success',PRODUCT.sku,{{calculated_qty:rolls,wall_width:w,wall_height:h,selected_color:PRODUCT.color,source_section:'coverage_calculator'}})}}catch(e){{}}}};
 function addProduct(button,source){{var c=vbCart(),f=c.find(function(x){{return x.sku===PRODUCT.sku&&x.color===PRODUCT.color}});if(f){{f.qty+=qty;f.img=PRODUCT.img;f.tier_price=PRODUCT.tier_price;f.tier_min_qty=PRODUCT.tier_min_qty;f.old_price=PRODUCT.old_price}}else c.push({{sku:PRODUCT.sku,handle:PRODUCT.handle,title:PRODUCT.title+' · '+PRODUCT.color,color:PRODUCT.color,price:PRODUCT.price,old_price:PRODUCT.old_price,tier_price:PRODUCT.tier_price,tier_min_qty:PRODUCT.tier_min_qty,img:PRODUCT.img,qty:qty}});vbSave(c);button.textContent='✓ AGREGADO';document.getElementById('tmAdded').classList.add('show');try{{fbq('track','AddToCart',{{content_ids:[PRODUCT.sku],content_type:'product',value:totalPrice(qty),currency:'DOP'}});vbTrack('addcart',PRODUCT.sku,{{qty:qty,price:unitPrice(qty),cart_total:totalPrice(qty),offer_qty:qty,selected_color:PRODUCT.color,source_section:source}})}}catch(e){{}}}}
 document.getElementById('tmAdd').onclick=function(){{addProduct(this,'sticky_buy_bar');location.href='carrito.html'}};
 document.querySelectorAll('.tm-review-add').forEach(function(button,index){{button.onclick=function(){{addProduct(button,'buyer_review_'+(index+1))}}}});
 var reviewTrack=document.getElementById('tmReviewTrack');
 function moveReviews(direction){{reviewTrack.scrollBy({{left:direction*Math.max(280,reviewTrack.clientWidth*.9),behavior:'smooth'}})}}
 document.getElementById('tmReviewPrev').onclick=function(){{moveReviews(-1)}};
 document.getElementById('tmReviewNext').onclick=function(){{moveReviews(1)}};
 var reviewButtons=Array.prototype.slice.call(document.querySelectorAll('.tm-review-open')),lightbox=document.getElementById('tmLightbox'),lightboxImage=document.getElementById('tmLightboxImage'),lightboxCount=document.getElementById('tmLightboxCount'),lightboxCaption=document.getElementById('tmLightboxCaption'),reviewIndex=0,touchStartX=0;
 function paintReview(){{var button=reviewButtons[reviewIndex],img=button.querySelector('img'),card=button.closest('.tm-review-card');lightboxImage.src=img.src;lightboxImage.alt=img.alt;lightboxCount.textContent=(reviewIndex+1)+' / '+reviewButtons.length;lightboxCaption.textContent=card.querySelector('.tm-review-user b').textContent}}
 function openReview(index){{reviewIndex=index;paintReview();lightbox.classList.add('show');lightbox.setAttribute('aria-hidden','false');document.body.style.overflow='hidden';try{{vbTrack('review_open',PRODUCT.sku,{{review_index:index,selected_color:PRODUCT.color,source_section:'buyer_reviews'}})}}catch(e){{}}}}
 function closeReview(){{lightbox.classList.remove('show');lightbox.setAttribute('aria-hidden','true');document.body.style.overflow=''}}
 function stepReview(direction){{reviewIndex=(reviewIndex+direction+reviewButtons.length)%reviewButtons.length;paintReview()}}
 reviewButtons.forEach(function(button,index){{button.onclick=function(){{openReview(index)}}}});
 document.getElementById('tmLightboxClose').onclick=closeReview;
 document.getElementById('tmLightboxPrev').onclick=function(){{stepReview(-1)}};
 document.getElementById('tmLightboxNext').onclick=function(){{stepReview(1)}};
 document.getElementById('tmLightboxStage').addEventListener('touchstart',function(e){{touchStartX=e.changedTouches[0].clientX}},{{passive:true}});
 document.getElementById('tmLightboxStage').addEventListener('touchend',function(e){{var delta=e.changedTouches[0].clientX-touchStartX;if(Math.abs(delta)>45)stepReview(delta<0?1:-1)}},{{passive:true}});
 addEventListener('keydown',function(e){{if(!lightbox.classList.contains('show'))return;if(e.key==='Escape')closeReview();if(e.key==='ArrowLeft')stepReview(-1);if(e.key==='ArrowRight')stepReview(1)}});
 var observed={{}};if('IntersectionObserver' in window){{var sectionObserver=new IntersectionObserver(function(entries){{entries.forEach(function(entry){{if(!entry.isIntersecting)return;var key=entry.target.id||entry.target.className.split(' ')[0];if(observed[key])return;observed[key]=1;try{{vbTrack('section_view',PRODUCT.sku,{{source_section:key}})}}catch(e){{}}}})}},{{threshold:.35}});['.tm-buybox','#opiniones','.tm-spanish-details','.tm-calc','.tm-faq'].forEach(function(sel){{var el=document.querySelector(sel);if(el)sectionObserver.observe(el)}})}}
 paint();
}})();
</script>
"""
    return page(f"{short_name} | {SITE_NAME}", body, wa_float=False,
                desc=f"Panel autoadhesivo efecto madera de {width:g} × {length:g} cm.",
                track_sku=sku, track_category="Decoración del Hogar",
                track_title=name, track_img=hero_image, extra_head=css,
                canonical=public_url("panel-autoadhesivo.html"),
                og_image=f"{SITE_URL}/images/{hero_image}")


def modern_home_body(feats, tiles, cat_sections, group_options, subs_json, cards, total,
                     best_sellers="", reviews="", stores=""):
    """轻量首页：首批 24 个商品 + 外部索引搜索、筛选和渐进加载。"""
    body = header() + """
<div class="wrap">
<div class="search"><svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input id="q" type="search" placeholder="¿Qué buscas hoy? Ej: audífonos, espejo…" autocomplete="off"><button class="clr" id="qClr" aria-label="Borrar">✕</button></div>
<div class="recent" id="recentRow"></div>
<div class="home-promo" id="homePromo"><div class="hero"><h1>Compra fácil, paga seguro</h1><div class="sub">🚚 Envíos a todo el país · 🤝 Contra entrega en Gran Santo Domingo</div></div>__PROMISES____FEATS__<div class="cat-hd"><b>Categorías</b><button class="cat-open" id="catOpen">Ver todas →</button></div><div class="cattiles" id="cattiles">__TILES__</div>__BEST____REVIEWS__</div>
<div class="results-head" id="resultsHead"><div><h2 id="resultsTitle">Productos</h2><p id="resultsSummary"></p></div><div class="results-actions"><button class="result-btn share-btn" id="shareResults" type="button" title="Compartir resultados" aria-label="Compartir resultados"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.6 6.8-4.2M8.6 13.4l6.8 4.2"/></svg><span>Compartir</span></button><button class="result-btn" id="filterOpen">Filtrar</button><select class="sort-select" id="sort"><option value="default">Relevancia</option><option value="price-asc">Precio: menor</option><option value="price-desc">Precio: mayor</option><option value="name">Nombre A-Z</option></select></div></div>
<div class="filter-panel" id="filterPanel"><div class="filter-grid"><div><label>Categoría</label><select id="filterGroup">__GROUP_OPTIONS__</select></div><div><label>Subcategoría</label><select id="filterSub"><option value="*">Todas</option></select></div><div><label>Precio mínimo RD$</label><input id="priceMin" inputmode="numeric" type="number" min="0" placeholder="0"></div><div><label>Precio máximo RD$</label><input id="priceMax" inputmode="numeric" type="number" min="0" placeholder="Sin límite"></div></div><div class="filter-foot"><button class="filter-reset" id="filterReset">Limpiar</button><button class="filter-apply" id="filterApply">Ver resultados</button></div></div>
<div class="count"><span id="n">__COUNT__</span> productos</div><div class="grid" id="grid">__CARDS__</div><button class="load-more show" id="loadMore">Ver más productos</button>__STORES__</div>
<div class="cat-dialog" id="catDialog" role="dialog" aria-modal="true" aria-labelledby="catDialogTitle"><div class="cat-sheet"><div class="cat-sheet-head"><h2 id="catDialogTitle">Todas las categorías</h2><button class="cat-close" id="catClose" aria-label="Cerrar">✕</button></div>__CAT_SECTIONS__</div></div>
<script>
var all=[],filtered=[],shown=0,BATCH=24,cur={q:'',g:'*',s:'*',min:null,max:null,sort:'default'},SUBS=__SUBS__;
var ALIASES={auricular:['audifono','audifonos'],auriculares:['audifono','audifonos'],movil:['celular','telefono'],telefono:['celular'],nevera:['refrigerador'],bombilla:['bombillo'],biberon:['tetera'],cochecito:['carrito de bebe']};
var qEl=document.getElementById('q'),qClr=document.getElementById('qClr'),qT=null,grid=document.getElementById('grid');
function snorm(s){return String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')}
function h(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function recGet(){try{return JSON.parse(localStorage.getItem('vb_recent')||'[]')}catch(e){return[]}}
function recAdd(w){var r=recGet().filter(function(x){return x!==w});r.unshift(w);r=r.slice(0,6);try{localStorage.setItem('vb_recent',JSON.stringify(r))}catch(e){}recPaint()}
function recPaint(){var r=recGet(),row=document.getElementById('recentRow');if(!r.length){row.classList.remove('show');return}row.innerHTML='<span class="rlb">Recientes:</span>'+r.map(function(w){return '<span class="rch">'+h(w)+'</span>'}).join('')+'<button class="rclr" title="Borrar historial">✕</button>';row.classList.add('show');row.querySelectorAll('.rch').forEach(function(ch){ch.onclick=function(){qEl.value=ch.textContent;qEl.dispatchEvent(new Event('input'))}});row.querySelector('.rclr').onclick=function(){try{localStorage.removeItem('vb_recent')}catch(e){}recPaint()}}
function matchWord(p,w){if(p.q.indexOf(w)>=0)return true;return (ALIASES[w]||[]).some(function(x){return p.q.indexOf(x)>=0})}
function card(p){var sale=p.old_price!=null&&p.price!=null&&p.old_price>p.price,saving=sale?p.old_price-p.price:0,pct=sale?Math.max(1,Math.round(saving/p.old_price*100)):0;var price=p.price==null?'<span class="ask">Consultar</span>':(sale?'<div class="price-stack"><span class="current">RD$ '+Math.round(p.price).toLocaleString('en-US')+'</span><del>RD$ '+Math.round(p.old_price).toLocaleString('en-US')+'</del></div><span class="saving">Ahorras RD$ '+Math.round(saving).toLocaleString('en-US')+'</span>':'<div class="price-stack"><span class="current">RD$ '+Math.round(p.price).toLocaleString('en-US')+'</span></div>');var label=p.label?'<span class="offer-label">'+h(p.label)+'</span>':'';var badge=sale?'<span class="sale-badge">-'+pct+'%</span>':'';var add=p.price==null?'':'<button class="card-add" type="button" aria-label="Agregar al carrito" data-sku="'+h(p.sku)+'" data-handle="'+h(p.handle)+'" data-title="'+h(p.title)+'" data-price="'+p.price+'" data-img="'+h(p.img)+'" onclick="vbCardAdd(event,this)">__BAG__</button>';var href=p.url||('producto/'+encodeURIComponent(p.handle));return '<article class="card"><a class="card-link" href="'+h(href)+'"><div class="imgbox"><img src="images/'+encodeURIComponent(p.img)+'" alt="'+h(p.title)+'" loading="lazy" onerror="this.style.display=\\'none\\'"><span class="badge">'+h(p.sub)+'</span>'+badge+'</div><div class="info"><div class="nm">'+h(p.title)+'</div>'+label+'<div class="pr">'+price+'</div></div></a>'+add+'</article>'}
function syncUrl(){var u=new URL(location.href),p=u.searchParams;['q','categoria','subcategoria','precio_min','precio_max','orden','buscar'].forEach(function(k){p.delete(k)});if(cur.q)p.set('q',cur.q);if(cur.g!=='*')p.set('categoria',cur.g);if(cur.s!=='*')p.set('subcategoria',cur.s);if(cur.min!=null)p.set('precio_min',cur.min);if(cur.max!=null)p.set('precio_max',cur.max);if(cur.sort!=='default')p.set('orden',cur.sort);u.hash='';history.replaceState(null,'',u.pathname+(p.toString()?'?'+p.toString():''))}
function apply(reset){if(!all.length)return;var words=snorm(cur.q).split(/\s+/).filter(Boolean);filtered=all.filter(function(p){if(cur.g!=='*'&&p.group!==cur.g)return false;if(cur.s!=='*'&&p.sub!==cur.s)return false;if(words.length&&!words.every(function(w){return matchWord(p,w)}))return false;if(cur.min!=null&&(p.price==null||p.price<cur.min))return false;if(cur.max!=null&&(p.price==null||p.price>cur.max))return false;return true});filtered.sort(function(a,b){if(cur.sort==='price-asc')return (a.price==null?1e15:a.price)-(b.price==null?1e15:b.price);if(cur.sort==='price-desc')return (b.price==null?-1:b.price)-(a.price==null?-1:a.price);if(cur.sort==='name')return a.title.localeCompare(b.title,'es');return a.i-b.i});var mode=!!cur.q||cur.g!=='*'||cur.s!=='*'||cur.min!=null||cur.max!=null||cur.sort!=='default';document.getElementById('homePromo').classList.toggle('hidden',mode);document.getElementById('resultsHead').classList.toggle('show',mode);document.getElementById('n').textContent=filtered.length;var label=cur.q?'Resultados para “'+cur.q+'”':(cur.s!=='*'?cur.s:(cur.g!=='*'?cur.g:'Productos'));document.getElementById('resultsTitle').textContent=label;document.getElementById('resultsSummary').textContent=filtered.length+' productos encontrados';syncUrl();if(reset){shown=0;grid.innerHTML='';showNext()}}
function showNext(){if(!all.length)return;if(!filtered.length){grid.innerHTML='<div class="no-results"><b>No encontramos productos</b>Prueba otra palabra o elimina algún filtro.</div>';document.getElementById('loadMore').classList.remove('show');return}var next=filtered.slice(shown,shown+BATCH);grid.insertAdjacentHTML('beforeend',next.map(card).join(''));shown+=next.length;document.getElementById('loadMore').classList.toggle('show',shown<filtered.length)}
function updateSubs(g,selected){var s=document.getElementById('filterSub'),vals=g==='*'?[]:(SUBS[g]||[]);s.innerHTML='<option value="*">Todas</option>'+vals.map(function(x){return '<option value="'+h(x)+'">'+h(x)+'</option>'}).join('');s.value=selected&&vals.indexOf(selected)>=0?selected:'*'}
function readState(){var p=new URLSearchParams(location.search),g=p.get('categoria')||'*',groups=Array.prototype.map.call(document.getElementById('filterGroup').options,function(o){return o.value});if(groups.indexOf(g)<0)g='*';cur.q=(p.get('q')||'').trim();cur.g=g;updateSubs(g,p.get('subcategoria')||'*');cur.s=document.getElementById('filterSub').value;var min=p.get('precio_min'),max=p.get('precio_max');cur.min=min!==null&&min!==''&&isFinite(Number(min))&&Number(min)>=0?Number(min):null;cur.max=max!==null&&max!==''&&isFinite(Number(max))&&Number(max)>=0?Number(max):null;var order=p.get('orden')||'default';cur.sort=['default','price-asc','price-desc','name'].indexOf(order)>=0?order:'default';qEl.value=cur.q;qClr.style.display=cur.q?'block':'none';document.getElementById('filterGroup').value=cur.g;document.getElementById('priceMin').value=cur.min==null?'':cur.min;document.getElementById('priceMax').value=cur.max==null?'':cur.max;document.getElementById('sort').value=cur.sort}
function shareToast(message){var t=document.getElementById('shareToast');if(!t){t=document.createElement('div');t.id='shareToast';t.className='share-toast';document.body.appendChild(t)}t.textContent=message;t.classList.add('show');clearTimeout(t._timer);t._timer=setTimeout(function(){t.classList.remove('show')},1800)}
async function shareResults(){syncUrl();var label=cur.q?'“'+cur.q+'”':(cur.s!=='*'?cur.s:(cur.g!=='*'?cur.g:'VivaBien')),data={title:'VivaBien',text:'Mira estos productos en VivaBien: '+label,url:location.href};try{if(navigator.share){await navigator.share(data);return}if(navigator.clipboard){await navigator.clipboard.writeText(data.url);shareToast('Enlace copiado');return}var x=document.createElement('textarea');x.value=data.url;x.style.position='fixed';x.style.opacity='0';document.body.appendChild(x);x.select();document.execCommand('copy');x.remove();shareToast('Enlace copiado')}catch(e){if(e.name!=='AbortError')shareToast('No se pudo compartir')}}
function selectCategory(g,s){cur.g=g;cur.s=s||'*';document.getElementById('filterGroup').value=g;updateSubs(g,cur.s);closeCategories();apply(true);try{vbTrack('filter','',{filter_group:g,filter_sub:cur.s,result_count:filtered.length})}catch(e){}window.scrollTo({top:0,behavior:'smooth'})}
function openCategories(g){var d=document.getElementById('catDialog');d.classList.add('show');document.body.style.overflow='hidden';if(g){var x=d.querySelector('[data-section="'+CSS.escape(g)+'"]');if(x)setTimeout(function(){x.scrollIntoView({block:'start'})},60)}}
function closeCategories(){document.getElementById('catDialog').classList.remove('show');document.body.style.overflow=''}
async function loadData(){try{var r=await fetch('products-index.json');all=await r.json();apply(true)}catch(e){document.getElementById('loadMore').classList.remove('show')}}
readState();recPaint();qEl.addEventListener('input',function(){var next=qEl.value.trim();if(!cur.q&&next){cur.g='*';cur.s='*';cur.min=null;cur.max=null;document.getElementById('filterGroup').value='*';updateSubs('*','')}cur.q=next;qClr.style.display=cur.q?'block':'none';apply(true);clearTimeout(qT);if(cur.q.length>2)qT=setTimeout(function(){try{fbq('track','Search',{search_string:cur.q});vbTrack('search','',{search_query:cur.q,result_count:filtered.length,sort_mode:cur.sort,filter_group:cur.g,filter_sub:cur.s})}catch(e){}recAdd(cur.q.toLowerCase())},900)});qClr.onclick=function(){qEl.value='';cur.q='';qClr.style.display='none';apply(true);qEl.focus()};if(new URLSearchParams(location.search).has('buscar'))qEl.focus();
document.getElementById('catOpen').onclick=function(){openCategories('')};document.querySelectorAll('.tile').forEach(function(t){t.onclick=function(){openCategories(t.dataset.g)}});document.querySelectorAll('.cat-section-title,.cat-sub').forEach(function(b){b.onclick=function(){selectCategory(b.dataset.g,b.dataset.s)}});document.getElementById('catClose').onclick=closeCategories;document.getElementById('catDialog').onclick=function(e){if(e.target===this)closeCategories()};addEventListener('keydown',function(e){if(e.key==='Escape')closeCategories()});
document.getElementById('shareResults').onclick=shareResults;document.getElementById('filterOpen').onclick=function(){document.getElementById('filterPanel').classList.toggle('show')};document.getElementById('filterGroup').onchange=function(){updateSubs(this.value,'')};document.getElementById('filterApply').onclick=function(){cur.g=document.getElementById('filterGroup').value;cur.s=document.getElementById('filterSub').value;var a=document.getElementById('priceMin').value,b=document.getElementById('priceMax').value;cur.min=a===''?null:Number(a);cur.max=b===''?null:Number(b);document.getElementById('filterPanel').classList.remove('show');apply(true);try{vbTrack('filter','',{filter_group:cur.g,filter_sub:cur.s,result_count:filtered.length,sort_mode:cur.sort})}catch(e){}};document.getElementById('filterReset').onclick=function(){cur.g='*';cur.s='*';cur.min=null;cur.max=null;cur.sort='default';document.getElementById('filterGroup').value='*';updateSubs('*','');document.getElementById('priceMin').value='';document.getElementById('priceMax').value='';document.getElementById('sort').value='default';apply(true)};document.getElementById('sort').onchange=function(){cur.sort=this.value;apply(true)};document.getElementById('loadMore').onclick=showNext;
var io=new IntersectionObserver(function(es){if(es[0].isIntersecting&&all.length&&shown<filtered.length)showNext()},{rootMargin:'300px'});io.observe(document.getElementById('loadMore'));setTimeout(loadData,0);
</script>"""
    return (body.replace("__PROMISES__", PROMISE_HTML).replace("__FEATS__", feats).replace("__TILES__", tiles)
            .replace("__BEST__", best_sellers).replace("__REVIEWS__", reviews).replace("__STORES__", stores)
            .replace("__COUNT__", str(total)).replace("__CARDS__", "".join(cards))
            .replace("__CAT_SECTIONS__", "".join(cat_sections)).replace("__GROUP_OPTIONS__", group_options)
            .replace("__SUBS__", subs_json).replace("__BAG__", BAG_SVG))

ENLACES_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Plus Jakarta Sans',-apple-system,sans-serif;background:linear-gradient(180deg,#2563D9 0%,#1A47A6 42%,#F7F9FD 42%,#F7F9FD 100%);color:#16202E;min-height:100vh}
a{text-decoration:none;color:inherit}img{display:block}
.lk{max-width:520px;margin:0 auto;padding:30px 18px 46px}
.lk-head{text-align:center;color:#fff;margin-bottom:22px}
.lk-logo{width:76px;height:76px;border-radius:24px;background:#fff;color:#2563D9;font-weight:800;font-size:34px;display:flex;align-items:center;justify-content:center;margin:0 auto 13px;box-shadow:0 10px 30px rgba(10,25,60,.25)}
.lk-head h1{font-size:25px;font-weight:800;letter-spacing:-.02em}
.lk-head p{font-size:13.5px;opacity:.92;margin-top:5px;font-weight:600}
.lk-note{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.28);border-radius:99px;padding:7px 15px;font-size:11.5px;font-weight:700;margin-top:13px}
.lk-links{display:flex;flex-direction:column;gap:11px;margin-bottom:26px}
.lk-btn{display:flex;align-items:center;gap:13px;background:#fff;border-radius:17px;padding:15px 17px;box-shadow:0 8px 26px rgba(20,40,80,.13);transition:transform .13s}
.lk-btn:active{transform:scale(.985)}
.lk-ic{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;flex:none;background:#EAF0FB}
.lk-btn.whatsapp .lk-ic{background:#E4F8EC}.lk-btn.instagram .lk-ic{background:#FDECF3}
.lk-tx{min-width:0;flex:1}
.lk-tx b{display:block;font-size:15px;font-weight:800;letter-spacing:-.01em}
.lk-tx span{display:block;font-size:12px;color:#6B7688;font-weight:600;margin-top:2px}
.lk-go{color:#B6C0D0;font-size:19px;font-weight:800;flex:none}
.lk-btn.principal{background:#16202E;color:#fff}
.lk-btn.principal .lk-ic{background:rgba(255,255,255,.14)}
.lk-btn.principal .lk-tx span{color:#B9C4D6}.lk-btn.principal .lk-go{color:#6C7A90}
.lk-sec-head{margin-bottom:12px}
.lk-sec-head h2{font-size:17px;font-weight:800;letter-spacing:-.02em}
.lk-sec-head p{font-size:12.5px;color:#7C8798;font-weight:600;margin-top:3px}
.lk-grid{display:grid;grid-template-columns:1fr 1fr;gap:11px}
@media(min-width:460px){.lk-grid{grid-template-columns:repeat(3,1fr)}}
.lk-card{background:#fff;border:1px solid #EAEFF7;border-radius:15px;overflow:hidden;box-shadow:0 4px 14px rgba(20,40,80,.06)}
.lk-imgw{position:relative}
.lk-card img{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}
.lk-tag{position:absolute;top:7px;left:7px;z-index:2;background:#FF6B4A;color:#fff;font-size:9.5px;font-weight:800;padding:4px 9px;border-radius:99px;letter-spacing:.02em;box-shadow:0 3px 9px rgba(232,72,42,.35)}
.lk-card .lk-nm{font-size:11.5px;font-weight:700;line-height:1.32;height:30px;overflow:hidden;padding:9px 10px 0}
.lk-card .lk-pr{font-size:14px;font-weight:800;padding:4px 10px 11px}
.lk-card .lk-pr small{display:block;font-size:10px;color:#8A93A2;font-weight:700;text-decoration:line-through}
.lk-all{display:block;text-align:center;background:#fff;border:1.5px solid #D8E1F0;border-radius:15px;padding:14px;font-weight:800;font-size:13.5px;color:#2563D9;margin-top:13px}
.lk-cta{text-align:center;background:#fff;border-radius:19px;padding:24px 18px;margin-top:24px;box-shadow:0 6px 20px rgba(20,40,80,.07)}
.lk-cta b{font-size:15px;font-weight:800}
.lk-cta a{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:#25D366;color:#fff;font-weight:800;font-size:14.5px;padding:13px 26px;border-radius:99px;margin-top:13px}
.lk-foot{text-align:center;font-size:11px;color:#98A2B3;margin-top:22px;line-height:1.7}
/* 欢迎券弹窗 */
.cp-mask{position:fixed;inset:0;background:rgba(10,20,40,.62);backdrop-filter:blur(3px);z-index:200;display:none;align-items:center;justify-content:center;padding:22px}
.cp-mask.show{display:flex;animation:cpFade .22s ease}
@keyframes cpFade{from{opacity:0}to{opacity:1}}
.cp-box{position:relative;width:min(340px,92vw);background:linear-gradient(170deg,#FF6B4A,#E8482A 58%,#fff 58%,#fff 100%);border-radius:24px;padding:26px 22px 22px;text-align:center;box-shadow:0 26px 70px rgba(0,0,0,.4);animation:cpPop .34s cubic-bezier(.2,1.3,.4,1)}
@keyframes cpPop{from{transform:scale(.72) translateY(24px);opacity:0}to{transform:none;opacity:1}}
.cp-x{position:absolute;top:11px;right:11px;width:28px;height:28px;border:0;border-radius:50%;background:rgba(255,255,255,.25);color:#fff;font-size:14px;cursor:pointer;line-height:1}
.cp-emo{font-size:40px;line-height:1;animation:cpBounce 1.5s ease-in-out infinite}
@keyframes cpBounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
.cp-box h3{color:#fff;font-size:22px;font-weight:800;margin:8px 0 3px;letter-spacing:-.02em}
.cp-box .cp-sub{color:rgba(255,255,255,.94);font-size:12.5px;font-weight:600;margin-bottom:17px}
.cp-ticket{background:#fff;border-radius:17px;padding:19px 16px 16px;box-shadow:0 10px 26px rgba(180,50,20,.22);position:relative}
.cp-ticket:before,.cp-ticket:after{content:'';position:absolute;top:50%;width:17px;height:17px;background:#fff;border-radius:50%;transform:translateY(-50%)}
.cp-ticket:before{left:-9px;box-shadow:inset -2px 0 3px rgba(0,0,0,.06)}
.cp-ticket:after{right:-9px;box-shadow:inset 2px 0 3px rgba(0,0,0,.06)}
.cp-val{font-size:40px;font-weight:800;color:#E8482A;letter-spacing:-.03em;line-height:1.05}
.cp-cond{font-size:11.5px;color:#7C8798;font-weight:700;margin-top:5px}
.cp-code{display:inline-block;margin-top:12px;background:#FFF3EF;border:1.5px dashed #FFB4A0;border-radius:10px;padding:8px 17px;font-size:15px;font-weight:800;letter-spacing:.09em;color:#E8482A}
.cp-btn{display:block;width:100%;background:#16202E;color:#fff;border:0;border-radius:14px;padding:15px;font-size:15.5px;font-weight:800;cursor:pointer;margin-top:15px;font-family:inherit}
.cp-btn:active{transform:scale(.985)}
.cp-foot{font-size:11px;color:#98A2B3;font-weight:600;margin-top:10px}
.cp-badge{position:fixed;right:15px;bottom:15px;z-index:190;display:none;align-items:center;gap:7px;background:#FF6B4A;color:#fff;font-size:12.5px;font-weight:800;padding:11px 16px;border-radius:99px;box-shadow:0 8px 24px rgba(232,72,42,.42);cursor:pointer;border:0;font-family:inherit}
.cp-badge.show{display:flex}
"""

def enlaces_page(products):
    """推广落地页（link-in-bio）：三个主入口 + 特色商品图片墙，图片直达商品页。"""
    cfg = load_json(SOCIAL_PATH, {})
    if not cfg:
        return None
    by_sku = {p["sku"]: p for p in products}
    site = SITE_URL.rstrip("/")

    links = ""
    for l in cfg.get("enlaces", []):
        url = str(l.get("url", "")).strip()
        if not url:
            continue
        estilo = str(l.get("estilo", "")).strip()
        ext = ' target="_blank" rel="noopener"' if not url.startswith(site) else ""
        links += (f'<a class="lk-btn {esc(estilo)}" href="{esc(url)}"{ext} '
                  f'onclick="lkTrack(\'{esc(estilo or "link")}\',\'\',\'{esc(url[:150])}\')">'
                  f'<span class="lk-ic">{esc(l.get("icono", "🔗"))}</span>'
                  f'<span class="lk-tx"><b>{esc(l.get("titulo", ""))}</b>'
                  f'<span>{esc(l.get("detalle", ""))}</span></span>'
                  f'<span class="lk-go">›</span></a>')

    # 特色商品：先按配置的 SKU，缺的用首页优先位补齐
    picks, seen = [], set()
    for sku in cfg.get("destacados_skus", []):
        p = by_sku.get(str(sku).strip())
        if p and p["sku"] not in seen:
            picks.append(p); seen.add(p["sku"])
    if len(picks) < 6:
        for p in products:
            if len(picks) >= 6:
                break
            if p["sku"] not in seen and p["price"] is not None:
                picks.append(p); seen.add(p["sku"])

    # 可选标签（如 Más vendido / Nuevo），配置在 destacados_labels: {"SKU": "Más vendido"}
    labels = cfg.get("destacados_labels", {}) or {}
    cards = ""
    for p in picks[:6]:
        old = p.get("old_price")
        price = (f'{fmt_price(p["price"])}'
                 + (f'<small>{fmt_price(old)}</small>' if old and p["price"] and old > p["price"] else "")
                 ) if p["price"] is not None else "Consultar"
        href = p.get("url") or f'producto/{quote(p["handle"])}.html'
        tag = str(labels.get(p["sku"], "")).strip()
        tag_html = f'<span class="lk-tag">{esc(tag)}</span>' if tag else ""
        cards += (f'<a class="lk-card" href="{esc(href)}" '
                  f'onclick="lkTrack(\'producto\',\'{esc(p["sku"])}\',\'{esc(p["title"][:80])}\')">'
                  f'<div class="lk-imgw">{tag_html}'
                  f'<img src="images/{esc(p["img"])}" alt="{esc(p["title"])}" loading="lazy" '
                  f'onerror="this.style.opacity=0"></div>'
                  f'<div class="lk-nm">{esc(p["title"])}</div>'
                  f'<div class="lk-pr">{price}</div></a>')

    # 欢迎券弹窗：只有配置了真实券码才渲染（券码来自后台生成，绝不编造）
    cup = cfg.get("cupon", {}) or {}
    cup_html = ""
    if cup.get("activo") and str(cup.get("codigo", "")).strip():
        code = str(cup["codigo"]).strip().upper()
        once = "1" if cup.get("mostrar_una_vez", True) else ""
        cup_html = f"""
<div class="cp-mask" id="cpMask" role="dialog" aria-modal="true" aria-label="Cupón de bienvenida">
<div class="cp-box">
<button class="cp-x" id="cpX" aria-label="Cerrar">✕</button>
<div class="cp-emo">🎉</div>
<h3>{esc(cup.get("titulo", "¡Felicidades!"))}</h3>
<div class="cp-sub">{esc(cup.get("subtitulo", ""))}</div>
<div class="cp-ticket">
<div class="cp-val">{esc(cup.get("valor_texto", ""))}</div>
{f'<div class="cp-cond">{esc(cup.get("condicion", ""))}</div>' if cup.get("condicion") else ""}
<div class="cp-code">{esc(code)}</div>
<button class="cp-btn" id="cpUse">{esc(cup.get("boton", "Usar mi cupón"))}</button>
<div class="cp-foot">{esc(cup.get("nota_pie", ""))}</div>
</div></div></div>
<button class="cp-badge" id="cpBadge">🎁 Tu cupón {esc(cup.get("valor_texto", ""))}</button>
<script>
(function(){{
 var CODE='{esc(code)}',ONCE={"true" if once else "false"},KEY='vb_enlaces_cupon';
 // 营销活动可用 ?coupon=XXX&val=RD$150+OFF&cond=... 覆盖默认券（每个活动一张专属券）
 try{{
  var qs=new URLSearchParams(location.search);
  var qc=(qs.get('coupon')||'').trim().toUpperCase();
  if(qc){{
   CODE=qc;KEY='vb_enlaces_cupon_'+qc;
   var el=document.querySelector('.cp-code');if(el)el.textContent=qc;
   var v=qs.get('val'),c=qs.get('cond');
   if(v){{var ev=document.querySelector('.cp-val');if(ev)ev.textContent=v}}
   if(c){{var ec=document.querySelector('.cp-cond');if(ec){{ec.textContent=c;ec.style.display=''}}}}
   var b=document.getElementById('cpBadge');if(b&&v)b.textContent='🎁 Tu cupón '+v;
  }}
 }}catch(e){{}}
 var mask=document.getElementById('cpMask'),badge=document.getElementById('cpBadge');
 function save(){{try{{localStorage.setItem('vb_campaign_coupon',CODE);
   localStorage.setItem(KEY,'1')}}catch(e){{}}}}
 function open_(){{mask.classList.add('show');document.body.style.overflow='hidden';
   try{{vbTrack('cupon_view','',{{source_section:'enlaces',coupon:CODE}})}}catch(e){{}}}}
 function close_(){{mask.classList.remove('show');document.body.style.overflow='';
   badge.classList.add('show');save()}}
 document.getElementById('cpX').onclick=close_;
 mask.onclick=function(e){{if(e.target===mask)close_()}};
 document.getElementById('cpUse').onclick=function(){{
   save();
   try{{navigator.clipboard&&navigator.clipboard.writeText(CODE)}}catch(e){{}}
   try{{vbTrack('cupon_claim','',{{source_section:'enlaces',coupon:CODE}});
     fbq('track','Lead',{{content_name:CODE}})}}catch(e){{}}
   location.href='index.html?coupon='+encodeURIComponent(CODE);
 }};
 badge.onclick=open_;
 var seen=false;try{{seen=ONCE&&localStorage.getItem(KEY)==='1'}}catch(e){{}}
 if(seen){{badge.classList.add('show')}}else{{setTimeout(open_,900)}}
}})();
</script>"""

    cta = cfg.get("cta_final", {})
    body = f"""<div class="lk">
<div class="lk-head">
<div class="lk-logo">{esc(str(cfg.get("titulo", SITE_NAME))[:1])}</div>
<h1>{esc(cfg.get("titulo", SITE_NAME))}</h1>
<p>{esc(cfg.get("lema", ""))}</p>
{f'<div class="lk-note">{esc(cfg.get("aviso", ""))}</div>' if cfg.get("aviso") else ""}
</div>
<div class="lk-links">{links}</div>
<div class="lk-sec-head"><h2>{esc(cfg.get("destacados_titulo", "Lo más nuevo"))}</h2>
<p>{esc(cfg.get("destacados_subtitulo", ""))}</p></div>
<div class="lk-grid">{cards}</div>
<a class="lk-all" href="index.html" onclick="lkTrack('ver_todo')">Ver todos los productos →</a>
<div class="lk-cta"><b>{esc(cta.get("texto", "¿Buscas algo? Escríbenos"))}</b><br>
<a href="https://wa.me/{WHATSAPP}" target="_blank" rel="noopener" onclick="lkTrack('wa_cta')">
{WA_SVG} {esc(cta.get("boton", "Escribir por WhatsApp"))}</a></div>
<div class="lk-foot">© {esc(SITE_NAME)} · RNC: 132888855<br>Ley 126-02 de Comercio Electrónico · 🔒 Sitio seguro</div>
</div>
{cup_html}
<script>
// 落地页埋点：进页面记一次 + 每个出口记一次（含目标地址、停留时长、活动短链）
(function(){{
 var t0=Date.now();
 function ctx(){{
  var qs=new URLSearchParams(location.search);
  return {{path:'/enlaces.html',
   code:qs.get('c')||qs.get('code')||'',
   duration_ms:Date.now()-t0,
   utm_source:qs.get('utm_source')||'',utm_campaign:qs.get('utm_campaign')||''}};
 }}
 window.lkCtx=ctx;
 try{{vbTrack('enlaces_view','',ctx())}}catch(e){{}}
 // 页面关闭时补一条停留时长
 addEventListener('pagehide',function(){{
  try{{vbTrack('enlaces_view','',Object.assign(ctx(),{{source_section:'salida'}}))}}catch(e){{}}
 }});
}})();
// t=入口类型  s=SKU  extra={{category:目标地址}}
function lkTrack(t,s,dest){{
 var d=Object.assign(window.lkCtx?window.lkCtx():{{}},{{source_section:t}});
 if(dest)d.category=dest;
 try{{vbTrack('enlaces_click',s||'',d)}}catch(e){{}}
 try{{
  if(t==='whatsapp'||t==='wa_cta')fbq('track','Contact',{{content_name:t}});
  else if(t==='instagram')fbq('trackCustom','InstagramClick');
  else if(t==='producto')fbq('track','ViewContent',{{content_ids:[s],content_type:'product'}});
  else fbq('trackCustom','EnlacesClick',{{seccion:t}});
 }}catch(e){{}}
}}
</script>"""
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(cfg.get("titulo", SITE_NAME))} — Enlaces</title>
<meta name="description" content="{esc(cfg.get("lema", ""))[:150]}">
<link rel="canonical" href="{site}/enlaces.html">
<meta property="og:title" content="{esc(cfg.get("titulo", SITE_NAME))}">
<meta property="og:description" content="{esc(cfg.get("lema", ""))[:150]}">
<meta property="og:type" content="website">
{FONT}
<style>{ENLACES_CSS}</style>
{pixel()}
{TRACK_JS}
</head><body>
{body}
</body></html>"""

# ============ 吸顶风扇（E27）站内商品详情页 ============
# 唯一配置源: data/ventilador_techo.json，页面不写死任何文案/价格/图片。
VENTILADOR_PATH = "data/ventilador_techo.json"

VENTILADOR_CSS = """
.vt *,.vt *::before,.vt *::after{box-sizing:border-box}
.vt{--vt-blue-deep:#173a6b;--vt-blue:#2563D9;--vt-blue-lt:#e9f0fd;--vt-blue-glow:#4dabf7;
 --vt-orange:#FF6B4A;--vt-orange-dk:#e2502f;--vt-green:#157A4E;--vt-dark:#16202E;--vt-mid:#5a6577;
 --vt-light:#8a93a2;--vt-gray:#F7F9FD;--vt-bd:#E5EAF2;--vt-sh-sm:0 2px 8px rgba(22,32,46,.07);
 --vt-sh-md:0 4px 20px rgba(22,32,46,.11);--vt-r:14px;--vt-r-sm:9px;--vt-t:.25s cubic-bezier(.4,0,.2,1);
 color:var(--vt-dark);line-height:1.6}
.vt img{display:block;max-width:100%;height:auto}
.vt ul{list-style:none;margin:0;padding:0}
.vt h1,.vt h2,.vt h3,.vt h4{margin:0}
.vt-band{background:linear-gradient(90deg,var(--vt-orange),var(--vt-orange-dk));color:#fff;text-align:center;
 padding:9px 16px;font-size:13px;font-weight:600;letter-spacing:.2px}
.vt-band span{margin:0 10px;display:inline-block}
.vt-hero{background:linear-gradient(135deg,var(--vt-blue-lt) 0%,#f2f7ff 50%,#fff 100%);padding:28px 20px 46px}
.vt-hero-in{max-width:1120px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:44px;align-items:start}
.vt-gal{position:sticky;top:78px}
.vt-gal-main{width:100%;aspect-ratio:1;background:#fff;border-radius:var(--vt-r);overflow:hidden;
 box-shadow:var(--vt-sh-md);position:relative}
.vt-gal-main img{width:100%;height:100%;object-fit:cover}
.vt-tag-off{position:absolute;top:14px;left:14px;background:var(--vt-orange);color:#fff;padding:6px 13px;
 border-radius:20px;font-size:13px;font-weight:800;box-shadow:0 2px 8px rgba(255,107,74,.4)}
.vt-thumbs{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
.vt-thumb{width:68px;height:68px;border-radius:var(--vt-r-sm);overflow:hidden;cursor:pointer;
 border:2px solid transparent;transition:var(--vt-t);flex-shrink:0;padding:0;background:none}
.vt-thumb img{width:100%;height:100%;object-fit:cover}
.vt-thumb.on,.vt-thumb:hover{border-color:var(--vt-blue)}
.vt-crumb{font-size:13px;color:var(--vt-light);margin-bottom:8px}
.vt-crumb a{color:var(--vt-light);text-decoration:none}
.vt-crumb a:hover{color:var(--vt-blue)}
.vt-title{font-size:24px;font-weight:800;line-height:1.3;margin-bottom:10px}
.vt-sub{font-size:14px;color:var(--vt-mid);margin-bottom:14px}
.vt-rate{display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap;font-size:14px;color:var(--vt-mid)}
.vt-stars{color:#ffc107;font-size:16px;letter-spacing:1px}
.vt-rate b{color:var(--vt-blue-deep);font-size:17px}
.vt-sold{color:var(--vt-light)}
.vt-pbox{background:#fff;border-radius:var(--vt-r);padding:18px;margin-bottom:18px;box-shadow:var(--vt-sh-sm);
 border:1px solid var(--vt-bd)}
.vt-prow{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.vt-price{font-size:34px;font-weight:800;color:var(--vt-orange);line-height:1}
.vt-unit{font-size:13px;color:var(--vt-light);font-weight:600}
.vt-free{color:var(--vt-green);font-weight:700}
.vt-sp small{display:block;font-size:11px;color:var(--vt-light);font-weight:600}
.vt-was{font-size:16px;color:var(--vt-light);text-decoration:line-through}
.vt-off{background:var(--vt-orange);color:#fff;padding:3px 9px;border-radius:5px;font-size:12px;font-weight:700}
.vt-pmeta{display:flex;gap:16px;margin-top:10px;flex-wrap:wrap;font-size:12px;color:var(--vt-mid)}
.vt-pmeta b{color:var(--vt-green)}
.vt-blk{margin-bottom:16px}
.vt-lab{font-size:14px;font-weight:700;margin-bottom:8px}
.vt-pills{display:flex;gap:10px;flex-wrap:wrap}
.vt-pill{padding:11px 16px;border:2px solid var(--vt-bd);border-radius:var(--vt-r-sm);cursor:pointer;
 font-size:14px;font-weight:600;transition:var(--vt-t);background:#fff;text-align:center;min-width:112px;position:relative}
.vt-pill:hover{border-color:var(--vt-blue-glow)}
.vt-pill.on{border-color:var(--vt-blue);background:var(--vt-blue-lt);color:var(--vt-blue)}
.vt-pill i{display:block;font-size:17px;font-weight:800;color:var(--vt-orange);margin-top:4px;font-style:normal}
.vt-pill s{display:block;font-size:11px;color:var(--vt-green);margin-top:2px;text-decoration:none}
.vt-pill em{position:absolute;top:-10px;right:-6px;background:var(--vt-orange);color:#fff;font-size:10px;
 font-weight:700;padding:2px 8px;border-radius:10px;white-space:nowrap;font-style:normal}
.vt-color{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--vt-gray);
 border-radius:var(--vt-r-sm);border:1px solid var(--vt-bd);font-size:14px;font-weight:600}
.vt-sw{width:30px;height:30px;border-radius:50%;background:#f7f7f2;border:2px solid var(--vt-bd);flex-shrink:0}
.vt-qty{display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}
.vt-qc{display:flex;align-items:center;border:2px solid var(--vt-bd);border-radius:var(--vt-r-sm);overflow:hidden}
.vt-qb{width:36px;height:36px;border:none;background:var(--vt-gray);font-size:18px;cursor:pointer;
 display:flex;align-items:center;justify-content:center}
.vt-qb:hover{background:var(--vt-blue-lt)}
.vt-qi{width:46px;height:36px;text-align:center;border:none;font-size:15px;font-weight:700;outline:none}
.vt-stock{font-size:13px;color:var(--vt-orange);font-weight:600}
.vt-units{font-size:12px;color:var(--vt-light);margin-bottom:16px}
.vt-cta{display:flex;gap:10px;margin-bottom:18px}
.vt-btn{flex:1;padding:14px 18px;border:none;border-radius:var(--vt-r);font-size:15px;font-weight:800;
 cursor:pointer;transition:var(--vt-t);text-align:center;display:flex;align-items:center;justify-content:center;
 gap:7px;text-decoration:none;font-family:inherit}
.vt-btn-cart{background:var(--vt-blue-lt);color:var(--vt-blue);border:2px solid var(--vt-blue)}
.vt-btn-cart:hover{background:var(--vt-blue);color:#fff}
.vt-btn-buy{background:linear-gradient(135deg,var(--vt-orange),var(--vt-orange-dk));color:#fff;
 box-shadow:0 4px 15px rgba(255,107,74,.35)}
.vt-btn-buy:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(255,107,74,.45)}
.vt-btn-wa{width:52px;flex:none;background:#fff;border:2px solid #25D366;color:#128C4A;font-size:20px}
.vt-btn-wa:hover{background:#25D366;color:#fff}
.vt-trust{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px;background:#fff;
 border-radius:var(--vt-r);box-shadow:var(--vt-sh-sm)}
.vt-tb{display:flex;flex-direction:column;align-items:center;text-align:center;gap:5px}
.vt-tb i{width:38px;height:38px;border-radius:50%;background:var(--vt-blue-lt);display:flex;
 align-items:center;justify-content:center;font-size:18px;font-style:normal}
.vt-tb span{font-size:11px;color:var(--vt-mid);font-weight:600;line-height:1.35}
.vt-tb b{display:block;color:var(--vt-dark)}
.vt-feat{background:var(--vt-blue-deep);padding:36px 20px;color:#fff}
.vt-feat-in{max-width:1120px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:24px}
.vt-fc{text-align:center;padding:6px}
.vt-fc i{width:54px;height:54px;margin:0 auto 11px;background:rgba(255,255,255,.13);border-radius:50%;
 display:flex;align-items:center;justify-content:center;font-size:25px;font-style:normal;transition:var(--vt-t)}
.vt-fc:hover i{background:rgba(255,255,255,.22);transform:scale(1.08)}
.vt-fc b{font-size:16px;font-weight:800;display:block;margin-bottom:5px}
.vt-fc span{font-size:13px;color:rgba(255,255,255,.82);line-height:1.45;max-width:220px;margin:0 auto;display:block}
.vt-sec{padding:48px 20px}
.vt-sec.alt{background:#fff}
.vt-sec-in{max-width:1000px;margin:0 auto}
.vt-sh{text-align:center;margin-bottom:30px}
.vt-sh em{display:inline-block;background:var(--vt-orange);color:#fff;padding:4px 13px;border-radius:20px;
 font-size:12px;font-weight:700;margin-bottom:10px;font-style:normal}
.vt-sh h2{font-size:25px;font-weight:800}
.vt-sh p{font-size:14px;color:var(--vt-light);margin-top:5px}
.vt-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.vt-card{background:#fff;border:1px solid var(--vt-bd);border-radius:var(--vt-r);padding:22px;
 box-shadow:var(--vt-sh-sm);transition:var(--vt-t)}
.vt-card:hover{box-shadow:var(--vt-sh-md);transform:translateY(-3px)}
.vt-card em{display:inline-block;background:var(--vt-blue-lt);color:var(--vt-blue);padding:4px 11px;
 border-radius:20px;font-size:12px;font-weight:700;margin-bottom:10px;font-style:normal}
.vt-card h3{font-size:19px;font-weight:800;margin-bottom:8px;line-height:1.3}
.vt-card>p{font-size:14px;color:var(--vt-mid);margin-bottom:13px;line-height:1.55}
.vt-card li{display:flex;align-items:flex-start;gap:8px;margin-bottom:7px;font-size:13.5px}
.vt-card li b{color:var(--vt-green);flex-shrink:0}
.vt-hl{margin-top:14px;background:linear-gradient(135deg,var(--vt-blue-lt),#f2f7ff);border-radius:var(--vt-r-sm);
 padding:13px 16px;border-left:4px solid var(--vt-blue)}
.vt-hl b{font-size:26px;font-weight:800;color:var(--vt-blue);line-height:1;display:block}
.vt-hl span{font-size:12.5px;color:var(--vt-mid);display:block;margin-top:3px}
.vt-tbl{width:100%;border-collapse:collapse;border-radius:var(--vt-r);overflow:hidden;box-shadow:var(--vt-sh-sm);background:#fff}
.vt-tbl th,.vt-tbl td{padding:13px 16px;text-align:center;border-bottom:1px solid var(--vt-bd);font-size:13.5px}
.vt-tbl th{background:var(--vt-blue-deep);color:#fff;font-weight:700}
.vt-tbl th.hi{background:var(--vt-blue)}
.vt-tbl td{color:var(--vt-mid)}
.vt-tbl td:first-child{text-align:left;font-weight:700;color:var(--vt-dark)}
.vt-tbl td.hi{background:var(--vt-blue-lt);font-weight:700;color:var(--vt-blue-deep)}
.vt-specs{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border-radius:var(--vt-r);overflow:hidden;
 box-shadow:var(--vt-sh-sm);background:#fff}
.vt-spc{padding:24px}
.vt-spc h3{font-size:15px;font-weight:800;color:var(--vt-blue-deep);margin-bottom:14px;padding-bottom:9px;
 border-bottom:2px solid var(--vt-blue-lt)}
.vt-spc div{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--vt-bd);font-size:13px}
.vt-spc div:last-child{border-bottom:none}
.vt-spc span{color:var(--vt-light)}
.vt-spc b{color:var(--vt-dark);font-weight:600;text-align:right}
.vt-rsum{display:flex;align-items:center;gap:36px;margin-bottom:28px;justify-content:center;flex-wrap:wrap}
.vt-rnum{text-align:center}
.vt-rnum b{font-size:52px;font-weight:800;color:var(--vt-orange);line-height:1;display:block}
.vt-rnum i{color:#ffc107;font-size:18px;margin:5px 0;display:block;font-style:normal}
.vt-rnum span{font-size:13px;color:var(--vt-light)}
.vt-rbars{flex:1;min-width:270px;max-width:350px}
.vt-rbar{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.vt-rbar span{font-size:12px;color:var(--vt-mid);width:40px}
.vt-rbar u{flex:1;height:6px;background:#e3e8f0;border-radius:3px;overflow:hidden;text-decoration:none;display:block}
.vt-rbar u i{display:block;height:100%;background:var(--vt-orange);border-radius:3px}
.vt-rbar b{font-size:12px;color:var(--vt-light);width:38px;text-align:right;font-weight:500}
.vt-rgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
.vt-rc{background:#fff;border-radius:var(--vt-r);padding:18px;box-shadow:var(--vt-sh-sm);border:1px solid var(--vt-bd)}
.vt-rc-h{display:flex;align-items:center;gap:10px;margin-bottom:9px}
.vt-av{width:36px;height:36px;border-radius:50%;background:var(--vt-blue-lt);display:flex;align-items:center;
 justify-content:center;font-size:15px;font-weight:800;color:var(--vt-blue);flex-shrink:0}
.vt-rc-h b{font-size:13px;font-weight:700;display:block}
.vt-rc-h span{font-size:11px;color:var(--vt-light)}
.vt-rc i{color:#ffc107;font-size:13px;display:block;margin-bottom:7px;font-style:normal}
.vt-rc p{font-size:13px;color:var(--vt-mid);line-height:1.55}
/* 「一个痛点 + 一个视频」：竖排，每块之间留足空隙，不再挤成三列 */
.vt-qa-in{max-width:860px}
.vt-qas{display:flex;flex-direction:column;gap:40px}
.vt-qa{margin:0}
.vt-qa-q{display:flex;align-items:flex-start;gap:11px;font-size:20px;font-weight:800;
 line-height:1.35;margin-bottom:16px;color:var(--vt-dark)}
.vt-qa-q span{flex-shrink:0;width:28px;height:28px;border-radius:50%;background:var(--vt-blue);
 color:#fff;font-size:14px;display:flex;align-items:center;justify-content:center;margin-top:1px}
.vt-qa-body{display:grid;grid-template-columns:minmax(0,320px) minmax(0,1fr);gap:22px;align-items:center;
 background:#fff;border:1px solid var(--vt-bd);border-radius:var(--vt-r);padding:16px;box-shadow:var(--vt-sh-sm)}
.vt-qa-a b{display:block;font-size:17px;font-weight:800;margin-bottom:7px;color:var(--vt-green)}
.vt-qa-a span{font-size:14.5px;color:var(--vt-mid);line-height:1.6}
@media(max-width:760px){.vt-qa-body{grid-template-columns:1fr;gap:15px}.vt-qa-q{font-size:18px}
 .vt-qas{gap:30px}}
/* 价格下面的「常问三件事」 */
.vt-dudas{margin-top:14px;border:1px solid var(--vt-bd);border-radius:var(--vt-r);overflow:hidden;background:#fff}
.vt-duda+.vt-duda{border-top:1px solid var(--vt-bd)}
.vt-duda summary{display:flex;align-items:center;gap:10px;padding:13px 15px;cursor:pointer;
 font-size:14px;list-style:none}
.vt-duda summary::-webkit-details-marker{display:none}
.vt-duda summary i{font-style:normal;font-size:17px}
.vt-duda summary b{flex:1;font-weight:700}
.vt-duda summary u{text-decoration:none;color:var(--vt-blue);font-size:17px;font-weight:700}
.vt-duda[open] summary u{transform:rotate(45deg)}
.vt-duda summary:focus-visible{outline:3px solid var(--vt-blue);outline-offset:-3px}
.vt-duda p{padding:0 15px 14px 40px;font-size:13.5px;color:var(--vt-mid);line-height:1.6}
.vt-vwrap{position:relative;aspect-ratio:1;background:#eef1f6;border-radius:var(--vt-r-sm);overflow:hidden}
.vt .vt-video,.vt .vt-vfall{width:100%;height:100%;object-fit:cover;display:block}
.vt-vbtn{position:absolute;right:10px;bottom:10px;width:38px;height:38px;border-radius:50%;border:none;
 background:rgba(22,32,46,.62);color:#fff;font-size:12px;line-height:1;cursor:pointer;display:flex;
 align-items:center;justify-content:center;backdrop-filter:blur(3px)}
.vt-vbtn:hover{background:rgba(22,32,46,.82)}
.vt-vbtn:focus-visible{outline:3px solid var(--vt-blue);outline-offset:2px}




/* 详情图：整幅堆叠，手机上占满宽度 */
.vt-det{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.vt-det img{width:100%;border-radius:var(--vt-r);box-shadow:var(--vt-sh-sm);background:#fff}
/* 评价卡里的买家实拍：图文并排 */
.vt-rc-b{display:flex;gap:13px;align-items:flex-start}
.vt-rc-b>div{min-width:0}
/* 选择器要比上面的 .vt img{height:auto} 更具体，否则高度不生效 */
.vt img.vt-rc-img{width:104px;height:104px;object-fit:cover;border-radius:var(--vt-r-sm);
 border:1px solid var(--vt-bd);background:#f2f4f8;flex-shrink:0}
.vt-faq{max-width:700px;margin:0 auto}
.vt-fq{border-bottom:1px solid var(--vt-bd)}
.vt-fq-q{padding:15px 0;display:flex;justify-content:space-between;align-items:center;cursor:pointer;
 font-size:15px;font-weight:700;gap:14px;transition:var(--vt-t);background:none;border:none;width:100%;
 text-align:left;font-family:inherit;color:inherit}
.vt-fq-q:hover{color:var(--vt-blue)}
.vt-fq-q i{font-size:18px;color:var(--vt-blue);transition:var(--vt-t);font-style:normal;flex-shrink:0}
.vt-fq-q.on i{transform:rotate(45deg)}
.vt-fq-a{max-height:0;overflow:hidden;transition:max-height .35s ease}
.vt-fq-a.on{max-height:340px}
.vt-fq-a p{font-size:13.5px;color:var(--vt-mid);line-height:1.65;padding:0 0 15px}
.vt-sticky{position:fixed;bottom:0;left:0;right:0;background:#fff;box-shadow:0 -4px 20px rgba(22,32,46,.12);
 z-index:90;transform:translateY(105%);transition:transform .35s ease;padding:10px 18px;
 padding-bottom:calc(10px + env(safe-area-inset-bottom))}
.vt-sticky.on{transform:translateY(0)}
.vt-sticky-in{max-width:1120px;margin:0 auto;display:flex;align-items:center;gap:14px}
.vt-sp{display:flex;align-items:center;gap:10px;flex:1;min-width:0}
.vt-sp img{width:44px;height:44px;border-radius:8px;object-fit:cover;flex-shrink:0}
.vt-sp b{font-size:13px;font-weight:700;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vt-sp span{font-size:16px;font-weight:800;color:var(--vt-orange)}
.vt-sp del{font-size:12px;color:var(--vt-light);font-weight:400;margin-left:5px}
.vt-sticky .vt-btn{flex:none;padding:12px 20px;font-size:14px}
.vt-rel{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.vt-rel a{background:#fff;border:1px solid var(--vt-bd);border-radius:var(--vt-r);overflow:hidden;
 text-decoration:none;color:inherit;transition:var(--vt-t);display:block}
.vt-rel a:hover{box-shadow:var(--vt-sh-md);transform:translateY(-3px)}
.vt-rel img{width:100%;aspect-ratio:1;object-fit:cover;background:#f2f4f8}
.vt-rel div{padding:10px 12px 13px}
.vt-rel b{font-size:13px;font-weight:600;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;
 -webkit-box-orient:vertical;overflow:hidden}
.vt-rel span{font-size:15px;font-weight:800;color:var(--vt-orange);display:block;margin-top:6px}
.vt-toast{position:fixed;top:76px;left:50%;transform:translateX(-50%);background:rgba(22,32,46,.92);color:#fff;
 padding:12px 26px;border-radius:30px;font-size:14px;font-weight:600;z-index:9999;opacity:0;
 transition:opacity .3s;pointer-events:none;max-width:90vw;text-align:center}
.vt-toast.on{opacity:1}
/* 入场动画：默认可见，滚到视口才播放。JS 失效时内容照样显示，不会白屏 */
.vt-fade.on{animation:vtIn .6s ease both}
@keyframes vtIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){.vt-fade.on{animation:none}}
@media(max-width:900px){
 .vt-hero-in{grid-template-columns:1fr;gap:24px}
 .vt-gal{position:static}
 .vt-cards{grid-template-columns:1fr}
 .vt-feat-in{grid-template-columns:repeat(2,1fr);gap:18px}
 .vt-rgrid{grid-template-columns:1fr}
 .vt-specs{grid-template-columns:1fr}
 .vt-title{font-size:20px}
 .vt-trust{grid-template-columns:repeat(2,1fr)}
 .vt-sp{display:none}
 .vt-rel{grid-template-columns:repeat(2,1fr)}
 .vt-pills{flex-direction:column}
 .vt-pill{min-width:auto;display:flex;align-items:center;justify-content:space-between;gap:10px;text-align:left}
 .vt-pill i{margin-top:0}
 .vt-sticky .vt-btn{flex:1}
}
@media(max-width:500px){
 .vt-feat-in{grid-template-columns:1fr}
 .vt-trust{grid-template-columns:repeat(2,1fr)}
 .vt-cta{flex-wrap:wrap}
 .vt-btn-wa{width:100%;order:3}
}
"""


def ventilador_page(products=None):
    """吸顶风扇 E27 站内商品详情页。内容全部来自 data/ventilador_techo.json。"""
    cfg = load_json(VENTILADOR_PATH, {})
    if not isinstance(cfg, dict) or not cfg.get("activo") or not cfg.get("sku"):
        return ""
    sku = str(cfg["sku"]).strip()
    handle = str(cfg.get("handle") or "abanico-de-techo-led").strip()
    titulo = str(cfg.get("titulo") or "").strip()
    corto = str(cfg.get("titulo_corto") or titulo).strip()
    precio = float(cfg.get("precio") or 0)
    antes = float(cfg.get("precio_antes") or 0)
    if not titulo or precio <= 0:
        return ""

    imgs = [i for i in (cfg.get("imagenes") or []) if isinstance(i, dict) and i.get("archivo")]
    if not imgs:
        return ""
    main_img = str(imgs[0]["archivo"]).lstrip("/")

    paquetes = [p for p in (cfg.get("paquetes") or []) if isinstance(p, dict) and p.get("precio")]
    if not paquetes:
        paquetes = [{"unidades": 1, "precio": precio, "etiqueta": "x1 Unidad", "ahorro": 0}]

    # WhatsApp prefill turns the ad click into a structured sales inquiry.
    price_lines = []
    for pack in paquetes:
        units = int(pack.get("unidades") or 1)
        pack_price = float(pack.get("precio") or 0)
        saving = float(pack.get("ahorro") or 0)
        saving_text = f" (ahorras {fmt_price(saving)})" if saving > 0 else ""
        price_lines.append(f"• {units} {'unidad' if units == 1 else 'unidades'}: {fmt_price(pack_price)}{saving_text}")
    benefit_lines = []
    for benefit in (cfg.get("beneficios") or [])[:4]:
        if isinstance(benefit, dict) and benefit.get("titulo"):
            benefit_lines.append(f"• {benefit['titulo']}")
    wa_message = "\n".join([
        f"Hola, quiero información sobre: {corto} ({sku}).",
        "",
        "💰 Precios:",
        *price_lines,
        "",
        "✨ Ventajas:",
        *benefit_lines,
        "",
        "🚚 Envío gratis a todo el país",
        "💵 Pago contra entrega disponible en Gran Santo Domingo",
        "",
        "Quiero comprar: [indicar cantidad]",
    ])
    wa_url = f"https://wa.me/{WHATSAPP}?text={quote(wa_message)}"

    # ---- 顶部滚动条 ----
    avisos = [str(a) for a in (cfg.get("aviso_superior") or []) if str(a).strip()]
    cd = int(cfg.get("cuenta_regresiva_segundos") or 0)
    band_bits = []
    for i, a in enumerate(avisos):
        txt = esc(a)
        if cd and "quedan" in a.lower():
            txt += ' <b id="vtCd">--:--:--</b>'
        band_bits.append(f"<span>{txt}</span>")
    band = f'<div class="vt-band">{"·".join(band_bits)}</div>' if band_bits else ""

    # ---- 相册 ----
    thumbs = "".join(
        f'<button class="vt-thumb{" on" if i == 0 else ""}" type="button" '
        f'onclick="vtImg(this,\'{esc(str(im["archivo"]).lstrip("/"))}\')">'
        f'<img src="../images/{esc(str(im["archivo"]).lstrip("/"))}" '
        f'alt="{esc(im.get("alt") or corto)}" loading="lazy"></button>'
        for i, im in enumerate(imgs)) if len(imgs) > 1 else ""
    off_tag = (f'<span class="vt-tag-off">{esc(cfg.get("descuento_texto") or "")}</span>'
               if cfg.get("descuento_texto") else "")

    # ---- 价格框下面那排绿色对勾（含"包邮"）----
    pmeta_cfg = [m for m in (cfg.get("precio_meta") or []) if isinstance(m, dict) and m.get("texto")]
    if not pmeta_cfg:
        pmeta_cfg = [{"texto": "Pago contra entrega", "cola": "en el Gran Santo Domingo"},
                     {"texto": "Garantía de 7 días", "cola": ""}]
    pmeta = "".join(
        f'<span>✅ <b>{esc(m["texto"])}</b>{(" " + esc(m["cola"])) if m.get("cola") else ""}</span>'
        for m in pmeta_cfg)

    # ---- 套餐 ----（predeterminado=true 的档位默认选中，没标就选第一个）
    def_i = next((i for i, p in enumerate(paquetes) if p.get("predeterminado")), 0)
    def_u = int(paquetes[def_i].get("unidades") or 1)
    def_p = float(paquetes[def_i]["precio"])
    pills = ""
    for i, p in enumerate(paquetes):
        u = int(p.get("unidades") or 1)
        pr = float(p["precio"])
        ah = float(p.get("ahorro") or 0)
        pills += (f'<button class="vt-pill{" on" if i == def_i else ""}" type="button" data-u="{u}" '
                  f'data-p="{pr:g}" onclick="vtPack(this)">{esc(p.get("etiqueta") or f"x{u}")}'
                  f'<i>{fmt_price(pr)}</i>'
                  + (f'<s>Ahorras {fmt_price(ah)}</s>' if ah > 0 else "")
                  + (f'<em>{esc(p.get("insignia"))}</em>' if p.get("insignia") else "")
                  + '</button>')

    # ---- 评价 ----
    rs = cfg.get("resenas") or {}
    prom = float(rs.get("promedio") or 0)
    stars = "★" * int(round(prom)) + "☆" * (5 - int(round(prom))) if prom else ""
    bars = "".join(
        f'<div class="vt-rbar"><span>{esc(l)}</span><u><i style="width:{float(v)}%"></i></u>'
        f'<b>{float(v):g}%</b></div>'
        for l, v in (rs.get("distribucion") or []))
    def _rcard(r):
        foto = str(r.get("foto") or "").lstrip("/")
        img = (f'<img class="vt-rc-img" src="../images/{esc(foto)}" '
               f'alt="{esc(r.get("foto_alt") or "Foto de cliente")}" loading="lazy">') if foto else ""
        return (f'<article class="vt-rc"><div class="vt-rc-h">'
                f'<div class="vt-av">{esc(r.get("inicial") or "·")}</div>'
                f'<div><b>{esc(r.get("nombre") or "Cliente verificado")}</b>'
                f'<span>{esc(r.get("fecha") or "Compra verificada")}</span></div></div>'
                f'<div class="vt-rc-b">{img}<div><i>{"★" * int(r.get("estrellas") or 5)}</i>'
                f'<p>{esc(r.get("texto") or "")}</p></div></div></article>')

    rcards = "".join(_rcard(r) for r in (rs.get("lista") or []) if isinstance(r, dict))

    # 「Mira cómo funciona」视频区：静音自动循环、带播放/暂停、失败回退封面图
    vids = [v for v in (cfg.get("videos") or []) if isinstance(v, dict) and v.get("archivo")]
    vid_html = ""
    if vids:
        cards = ""
        for i, v in enumerate(vids):
            mp4 = str(v["archivo"]).lstrip("/")
            pos = str(v.get("poster") or "").lstrip("/")
            alt = esc(v.get("alt") or v.get("titulo") or corto)
            poster_attr = f'poster="../images/{esc(pos)}" ' if pos else ""
            # 结构：一个痛点提问 → 对应的视频回答。竖排，每块之间留白，不再挤成三列
            cards += (
                f'<article class="vt-qa">'
                f'<h3 class="vt-qa-q"><span>{i+1}</span>{esc(v.get("pregunta") or "")}</h3>'
                f'<div class="vt-qa-body">'
                f'<div class="vt-vwrap">'
                f'<video id="vtV{i}" class="vt-video" muted loop playsinline autoplay preload="metadata" '
                f'{poster_attr}'
                f'aria-label="{alt}" onerror="vtVFail({i})">'
                f'<source data-src="../images/{esc(mp4)}" type="video/mp4"></video>'
                + (f'<img class="vt-vfall" id="vtF{i}" src="../images/{esc(pos)}" alt="{alt}" hidden>' if pos else "")
                + f'<button class="vt-vbtn" id="vtB{i}" type="button" onclick="vtVToggle({i})" '
                  f'aria-label="Pausar video: {esc(v.get("pregunta") or "")}">❚❚</button>'
                f'</div>'
                f'<div class="vt-qa-a"><b>{esc(v.get("titulo") or "")}</b>'
                f'<span>{esc(v.get("texto") or "")}</span></div>'
                f'</div></article>')
        vid_html = (f'<section class="vt-sec alt"><div class="vt-sec-in vt-qa-in">'
                    f'<div class="vt-sh"><em>Tus dudas, en video</em>'
                    f'<h2>{esc(cfg.get("videos_titulo") or "Lo que todo el mundo pregunta")}</h2></div>'
                    f'<div class="vt-qas">{cards}</div></div></section>')

    # 详情图（整幅堆叠展示）
    det = [d for d in (cfg.get("imagenes_detalle") or []) if isinstance(d, dict) and d.get("archivo")]
    det_html = ""
    if det:
        det_html = (f'<section class="vt-sec alt"><div class="vt-sec-in">'
                    f'<div class="vt-sh"><em>Detalles</em>'
                    f'<h2>{esc(cfg.get("detalle_titulo") or "Detalles del producto")}</h2></div>'
                    '<div class="vt-det">' + "".join(
                        f'<img src="../images/{esc(str(d["archivo"]).lstrip("/"))}" '
                        f'alt="{esc(d.get("alt") or corto)}" loading="lazy">'
                        for d in det) + '</div></div></section>')

    # ---- 卖点 / 说明卡 / 对比 / 参数 / FAQ ----
    feats = "".join(
        f'<div class="vt-fc"><i>{esc(b.get("icono") or "•")}</i><b>{esc(b.get("titulo") or "")}</b>'
        f'<span>{esc(b.get("texto") or "")}</span></div>'
        for b in (cfg.get("beneficios") or []) if isinstance(b, dict))

    cards = ""
    for s in (cfg.get("secciones") or []):
        if not isinstance(s, dict):
            continue
        pts = "".join(f'<li><b>✓</b><span>{esc(x)}</span></li>' for x in (s.get("puntos") or []))
        hl = ""
        if s.get("destaque_titulo"):
            hl = (f'<div class="vt-hl"><b>{esc(s["destaque_titulo"])}</b>'
                  f'<span>{esc(s.get("destaque_texto") or "")}</span></div>')
        cards += (f'<article class="vt-card vt-fade">'
                  + (f'<em>{esc(s.get("etiqueta"))}</em>' if s.get("etiqueta") else "")
                  + f'<h3>{esc(s.get("titulo") or "")}</h3>'
                  + (f'<p>{esc(s.get("texto"))}</p>' if s.get("texto") else "")
                  + (f'<ul>{pts}</ul>' if pts else "") + hl + '</article>')

    cmp_cfg = cfg.get("comparacion") or {}
    cmp_html = ""
    if cmp_cfg.get("filas"):
        rows = "".join(
            f'<tr><td>{esc(a)}</td><td class="hi">{esc(b)}</td><td>{esc(c)}</td></tr>'
            for a, b, c in cmp_cfg["filas"])
        cmp_html = f"""<section class="vt-sec alt"><div class="vt-sec-in">
<div class="vt-sh"><em>Comparación</em><h2>{esc(cmp_cfg.get("titulo") or "")}</h2></div>
<table class="vt-tbl"><thead><tr><th>Característica</th>
<th class="hi">{esc(cmp_cfg.get("columna_nuestro") or "")}</th>
<th>{esc(cmp_cfg.get("columna_otro") or "")}</th></tr></thead><tbody>{rows}</tbody></table>
</div></section>"""

    specs = "".join(
        f'<div class="vt-spc"><h3>{esc(g.get("grupo") or "")}</h3>'
        + "".join(f'<div><span>{esc(k)}</span><b>{esc(v)}</b></div>' for k, v in (g.get("datos") or []))
        + '</div>'
        for g in (cfg.get("ficha_tecnica") or []) if isinstance(g, dict))

    faqs = "".join(
        f'<div class="vt-fq"><button class="vt-fq-q" type="button" onclick="vtFaq(this)">'
        f'<span>{esc(f.get("p") or "")}</span><i>+</i></button>'
        f'<div class="vt-fq-a"><p>{esc(f.get("r") or "")}</p></div></div>'
        for f in (cfg.get("faq") or []) if isinstance(f, dict))

    trust = "".join(
        f'<div class="vt-tb"><i>{esc(g.get("icono") or "✔")}</i>'
        f'<span><b>{esc(g.get("titulo") or "")}</b>{esc(g.get("texto") or "")}</span></div>'
        for g in (cfg.get("garantias") or []) if isinstance(g, dict))

    # ---- 价格下面的「常问的三件事」：付款 / 安装 / 售后 ----
    dudas = [x for x in (cfg.get("dudas_rapidas") or []) if isinstance(x, dict) and x.get("p")]
    dudas_html = ""
    if dudas:
        items = "".join(
            f'<details class="vt-duda"><summary><i>{esc(x.get("icono") or "•")}</i>'
            f'<b>{esc(x["p"])}</b><u>+</u></summary><p>{esc(x.get("r") or "")}</p></details>'
            for x in dudas)
        dudas_html = f'<div class="vt-dudas">{items}</div>'

    # ---- 同类商品（站内真实商品，价格直接取自 CSV）----
    rel_html = ""
    rel = []
    for p in (products or []):
        t = (p.get("title") or "").lower()
        if ("abanico" in t or "ventilador" in t) and p.get("price"):
            rel.append(p)
    # 优先推同类（吊扇/吸顶扇），再按价格接近本商品排序，避免只推几十块的小手持扇
    rel = sorted(rel, key=lambda x: (0 if "techo" in (x.get("title") or "").lower() else 1,
                                     abs(x["price"] - precio)))[:4]
    if rel:
        rel_html = ('<section class="vt-sec"><div class="vt-sec-in">'
                    '<div class="vt-sh"><em>También te puede servir</em><h2>Otros abanicos en la tienda</h2></div>'
                    '<div class="vt-rel">' + "".join(
                        f'<a href="{esc(quote(p["handle"]))}"><img src="../images/{esc(quote(p["img"]))}" '
                        f'alt="{esc(p["title"])}" loading="lazy">'
                        f'<div><b>{esc(p["title"])}</b><span>{fmt_price(p["price"])}</span></div></a>'
                        for p in rel) + '</div></div></section>')

    product_json = json.dumps({
        "sku": sku, "handle": handle, "title": corto, "img": main_img,
        "price": precio,
    }, ensure_ascii=False).replace("</", "<\\/")

    body = f"""{header("../")}
<div class="vt">
{band}
<section class="vt-hero"><div class="vt-hero-in">
 <div class="vt-gal">
  <div class="vt-gal-main"><img id="vtMain" src="../images/{esc(main_img)}"
    alt="{esc(imgs[0].get("alt") or corto)}">{off_tag}</div>
  {f'<div class="vt-thumbs">{thumbs}</div>' if thumbs else ''}
 </div>
 <div>
  <div class="vt-crumb"><a href="../">Inicio</a> / {esc(cfg.get("categoria") or "")}</div>
  <h1 class="vt-title">{esc(titulo)}</h1>
  <p class="vt-sub">{esc(cfg.get("subtitulo") or "")}</p>
  <div class="vt-rate"><span class="vt-stars">{stars}</span>
   <span><b>{prom:g}</b> ({esc(rs.get("total_texto") or "")}+ reseñas)</span>
   <span class="vt-sold">Vendidos: {esc(rs.get("total_texto") or "")}+</span></div>

  <div class="vt-pbox">
   <div class="vt-prow"><span class="vt-price">RD$ {precio:,.0f}</span>
    <span class="vt-unit">por unidad</span>
    {f'<span class="vt-was">{fmt_price(antes)}</span>' if antes > precio else ''}
    {f'<span class="vt-off">{esc(cfg.get("descuento_texto"))}</span>' if cfg.get("descuento_texto") else ''}</div>
   <div class="vt-pmeta">{pmeta}</div>
  </div>

  <div class="vt-blk"><div class="vt-lab">Color: {esc(cfg.get("color") or "")}</div>
   <div class="vt-color"><span class="vt-sw"></span>{esc(cfg.get("color_nota") or cfg.get("color") or "")}</div></div>

  <div class="vt-blk"><div class="vt-lab">Cantidad:</div><div class="vt-pills">{pills}</div></div>

  <div class="vt-qty"><span class="vt-lab" style="margin:0">Llevar:</span>
   <div class="vt-qc"><button class="vt-qb" type="button" onclick="vtQty(-1)" aria-label="Menos">−</button>
    <input class="vt-qi" id="vtQty" type="number" value="1" min="1" max="99" onchange="vtSync()">
    <button class="vt-qb" type="button" onclick="vtQty(1)" aria-label="Más">+</button></div>
   {f'<span class="vt-stock">{esc(cfg.get("existencias_texto"))}</span>' if cfg.get("existencias_texto") else ''}
  </div>
  <div class="vt-units" id="vtUnits"></div>

  <div class="vt-cta">
   <button class="vt-btn vt-btn-cart" type="button" onclick="vtAdd(0)">🛒 Agregar al carrito</button>
   <button class="vt-btn vt-btn-buy" type="button" onclick="vtAdd(1)">⚡ Comprar ahora</button>
   <a class="vt-btn vt-btn-wa" href="{esc(wa_url)}" target="_blank" rel="noopener"
      aria-label="Preguntar por WhatsApp" onclick="try{{vbTrack('whatsapp','{esc(sku)}')}}catch(e){{}}">💬</a>
  </div>

  <div class="vt-trust">{trust}</div>
  {dudas_html}
 </div>
</div></section>

{vid_html}

{det_html}

{f'<section class="vt-feat"><div class="vt-feat-in">{feats}</div></section>' if feats else ''}

{f'''<section class="vt-sec"><div class="vt-sec-in">
<div class="vt-sh"><em>El producto</em><h2>Por dentro y por fuera</h2></div>
<div class="vt-cards">{cards}</div></div></section>''' if cards else ''}

{cmp_html}

{f'''<section class="vt-sec"><div class="vt-sec-in">
<div class="vt-sh"><em>Ficha técnica</em><h2>Especificaciones</h2></div>
<div class="vt-specs">{specs}</div></div></section>''' if specs else ''}

{f'''<section class="vt-sec alt"><div class="vt-sec-in">
<div class="vt-sh"><em>Reseñas</em><h2>{esc(rs.get("subtitulo") or "")}</h2></div>
<div class="vt-rsum"><div class="vt-rnum"><b>{prom:g}</b><i>{stars}</i>
 <span>{esc(rs.get("total_texto") or "")} reseñas</span></div>
 <div class="vt-rbars">{bars}</div></div>
<div class="vt-rgrid">{rcards}</div></div></section>''' if rcards else ''}

{f'''<section class="vt-sec"><div class="vt-sec-in">
<div class="vt-sh"><em>FAQ</em><h2>Preguntas frecuentes</h2></div>
<div class="vt-faq">{faqs}</div></div></section>''' if faqs else ''}

{rel_html}

<div class="vt-sticky" id="vtSticky"><div class="vt-sticky-in">
 <div class="vt-sp"><img src="../images/{esc(main_img)}" alt="{esc(corto)}">
  <div><b>{esc(corto)}</b><span>RD$ <span id="vtPrice2">{def_p:,.0f}</span></span>
   <small id="vtPackLbl">{esc(paquetes[def_i].get("etiqueta") or "")}</small></div></div>
 <div style="display:flex;gap:10px;flex:1;justify-content:flex-end">
  <button class="vt-btn vt-btn-cart" type="button" onclick="vtAdd(0)">Agregar</button>
  <button class="vt-btn vt-btn-buy" type="button" onclick="vtAdd(1)">Comprar ahora</button></div>
</div></div>
</div>
<script>
var VT={product_json},vtU={def_u},vtP={def_p:g};
function vtFmt(n){{return Number(n).toLocaleString('en-US')}}
function vtImg(b,src){{document.querySelectorAll('.vt-thumb').forEach(function(t){{t.classList.remove('on')}});
 b.classList.add('on');document.getElementById('vtMain').src='../images/'+src;
 try{{vbTrack('gallery_view',VT.sku,{{img:src}})}}catch(e){{}}}}
function vtPack(b){{document.querySelectorAll('.vt-pill').forEach(function(p){{p.classList.remove('on')}});
 b.classList.add('on');vtU=parseInt(b.dataset.u);vtP=parseFloat(b.dataset.p);
 // 顶部大价格固定是「单台含运费价」，不随档位变；变的是底部条和总计行
 document.getElementById('vtPrice2').textContent=vtFmt(vtP);
 var lbl=document.getElementById('vtPackLbl');
 if(lbl)lbl.textContent=b.textContent.split('RD$')[0].trim();
 vtSync();try{{vbTrack('tier_select',VT.sku,{{units:vtU,price:vtP}})}}catch(e){{}}}}
function vtQty(d){{var i=document.getElementById('vtQty');var v=parseInt(i.value||1)+d;
 i.value=v<1?1:(v>99?99:v);vtSync();
 try{{vbTrack('quantity_change',VT.sku,{{qty:parseInt(i.value)}})}}catch(e){{}}}}
function vtSync(){{var q=parseInt(document.getElementById('vtQty').value||1),n=vtU*q;
 var el=document.getElementById('vtUnits');
 // 总计一直显示，客人任何时候都知道最终要付多少（含运费，结账不再加价）
 el.innerHTML='Total: '+n+(n>1?' unidades':' unidad')+' · <b>RD$ '+vtFmt(vtP*q)
  +'</b> <span class="vt-free">· envío gratis en Gran Santo Domingo</span>';}}
function vtToast(m){{var t=document.createElement('div');t.className='vt-toast';t.textContent=m;
 document.body.appendChild(t);setTimeout(function(){{t.classList.add('on')}},10);
 setTimeout(function(){{t.classList.remove('on');setTimeout(function(){{t.remove()}},320)}},1900)}}
function vtAdd(buy){{
 var q=parseInt(document.getElementById('vtQty').value||1);
 var sku=vtU>1?(VT.sku+'-P'+vtU):VT.sku;
 var title=vtU>1?(VT.title+' (paquete de '+vtU+')'):VT.title;
 var item={{sku:sku,handle:VT.handle,title:title,price:vtP,img:VT.img,qty:q}};
 var c;
 if(buy){{
  // 「Comprar ahora」只结算当前商品和当前数量，不把历史购物车带进结算页
  c=[item];
 }}else{{
  c=vbCart();var f=c.find(function(x){{return x.sku===sku}});
  if(f){{f.qty+=q}}else{{c.push(item)}}
 }}
 vbSave(c);
 try{{fbq('track','AddToCart',{{content_ids:[sku],content_type:'product',value:vtP*q,currency:'DOP'}})}}catch(e){{}}
 try{{vbTrack('addcart',sku,{{qty:q,price:vtP,units:vtU*q,product_title:title,product_img:VT.img,
  cart_total:c.reduce(function(a,x){{return a+x.price*x.qty}},0)}})}}catch(e){{}}
 if(buy){{try{{fbq('track','InitiateCheckout',{{value:vtP*q,currency:'DOP'}})}}catch(e){{}}
  location.href='../carrito';return}}
 vtToast('✅ Agregado al carrito');
}}
function vtVFail(i){{ // 视频加载失败 → 显示封面图兜底
 var v=document.getElementById('vtV'+i),f=document.getElementById('vtF'+i),b=document.getElementById('vtB'+i);
 if(v)v.style.display='none'; if(b)b.style.display='none'; if(f)f.hidden=false;}}
function vtVToggle(i){{
 var v=document.getElementById('vtV'+i),b=document.getElementById('vtB'+i);
 if(!v)return;
 var s=v.querySelector('source[data-src]');
 if(s&&!s.src){{s.src=s.dataset.src;v.load();v.dataset.loaded='1'}}
 if(v.paused){{delete v.dataset.userPaused;v.play();b.textContent='❚❚';b.setAttribute('aria-label','Pausar video')}}
 else{{v.dataset.userPaused='1';v.pause();b.textContent='▶';b.setAttribute('aria-label','Reproducir video')}}}}
(function(){{
 // 只加载「滚到眼前」的那一个视频：3 段一起预加载要 5MB，手机流量吃不消。
 // 离开视口就暂停，省流量也省电。尊重"减少动态效果"设置：不自动播，等用户点。
 var quiet=matchMedia('(prefers-reduced-motion: reduce)').matches;
 function load(v){{
  if(v.dataset.loaded)return;
  var s=v.querySelector('source[data-src]');
  if(s){{s.src=s.dataset.src;v.load();v.dataset.loaded='1'}}
 }}
 var vs=[].slice.call(document.querySelectorAll('.vt-video'));
 vs.forEach(function(v,i){{
  v.dataset.i=i;
  if(quiet){{v.removeAttribute('autoplay');
   var b=document.getElementById('vtB'+i);
   if(b){{b.textContent='▶';b.setAttribute('aria-label','Reproducir video')}}}}
 }});
 if(!('IntersectionObserver' in window)){{vs.forEach(load);return}}
 var io=new IntersectionObserver(function(es){{
  es.forEach(function(e){{
   var v=e.target;
   if(e.isIntersecting){{
    load(v);
    if(!quiet&&!v.dataset.userPaused){{var p=v.play();if(p&&p.catch)p.catch(function(){{}})}}
   }}else if(!v.paused){{v.pause()}}
  }});
 }},{{threshold:.35}});
 vs.forEach(function(v){{io.observe(v)}});
 // 兜底：某些浏览器/扩展环境下 IntersectionObserver 回调不触发，视频会一直停在封面。
 // 所以另外做一次手动可见性检查（首屏 + 滚动 + 窗口变化），保证该播的一定会播。
 function sweep(){{
  vs.forEach(function(v){{
   var r=v.getBoundingClientRect();
   var vis=r.top<innerHeight*0.9&&r.bottom>innerHeight*0.1;
   if(vis){{load(v);if(!quiet&&!v.dataset.userPaused&&v.paused){{
    var p=v.play();if(p&&p.catch)p.catch(function(){{}})}}}}
   else if(!v.paused){{v.pause()}}
  }});
 }}
 addEventListener('scroll',sweep,{{passive:true}});
 addEventListener('resize',sweep);
 sweep();setTimeout(sweep,800);
}})();
function vtFaq(q){{var a=q.nextElementSibling,open=q.classList.contains('on');
 document.querySelectorAll('.vt-fq-q').forEach(function(x){{x.classList.remove('on');
  x.nextElementSibling.classList.remove('on')}});
 if(!open){{q.classList.add('on');a.classList.add('on');
  try{{vbTrack('review_open',VT.sku,{{pregunta:q.textContent.trim().slice(0,60)}})}}catch(e){{}}}}}}
addEventListener('scroll',function(){{
 var h=document.querySelector('.vt-hero');if(!h)return;
 document.getElementById('vtSticky').classList.toggle('on',scrollY>h.offsetHeight+150)}});
(function(){{var o=new IntersectionObserver(function(es){{es.forEach(function(e){{
 if(e.isIntersecting)e.target.classList.add('on')}})}},{{threshold:.12}});
 document.querySelectorAll('.vt-fade').forEach(function(el){{o.observe(el)}});}})();
{f'''(function(){{var el=document.getElementById('vtCd');if(!el)return;var t={cd};
 setInterval(function(){{t--;if(t<0)t={cd};
  el.textContent=String(Math.floor(t/3600)).padStart(2,'0')+':'+
   String(Math.floor(t%3600/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0')}},1000)}})();''' if cd else ''}
vtSync();
</script>"""

    return page(f"{corto} | {SITE_NAME}", body,
                pixel_extra=(f"fbq('track','ViewContent',{{content_ids:['{sku}'],content_type:'product',"
                             f"value:{precio:g},currency:'DOP'}});"),
                desc=str(cfg.get("subtitulo") or titulo)[:160],
                track_sku=sku, track_category=str(cfg.get("categoria") or ""),
                track_title=corto, track_img=main_img,
                extra_head=f"<style>{VENTILADOR_CSS}</style>",
                canonical=public_url(f"producto/{handle}.html"),
                og_image=public_url(f"images/{main_img}"), rel="../")


def build():
    products = load_products()
    detail_rollout = load_json(DETAIL_ROLLOUT_PATH, {})
    detail_rollout_skus = set(detail_rollout.get("skus", []))
    detail_rollout_all = detail_rollout.get("mode") == "all"
    merchant_report = write_merchant_candidates(products)
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(f"{OUT_DIR}/producto", exist_ok=True)
    if os.path.isdir(IMG_DIR):
        shutil.copytree(IMG_DIR, f"{OUT_DIR}/images",
                        ignore=shutil.ignore_patterns("*_original*", "*_price_crop*", ".*",
                                                      "*.json", "*.tmp"))  # JSON 含内部数据，不上线
    else:
        os.makedirs(f"{OUT_DIR}/images", exist_ok=True)
        print(f"⚠️  未找到 {IMG_DIR}/ 文件夹，图片将显示为占位背景")

    # ---- 分类结构：大组 → 子分类 ----
    subs_of = {}
    for p in products:
        subs_of.setdefault(p["group"], {}).setdefault(p["sub"], 0)
        subs_of[p["group"]][p["sub"]] += 1
    groups = [g for g in GROUP_ORDER if g in subs_of]

    # ---- 商品索引 + 首批商品卡（首页不再一次渲染 1000+ 个 DOM 节点） ----
    index_products = []
    for i, p in enumerate(products):
        search_text = " ".join((p["title"], p["sub"], p["group"], p["type"], p["body"][:360]))
        index_products.append({
            "i": i, "sku": p["sku"], "handle": p["handle"], "title": p["title"],
            "price": p["price"], "img": p["img"], "group": p["group"], "sub": p["sub"],
            "old_price": p.get("old_price"), "label": p.get("label", ""),
            "available": p.get("inventory") is not None and p["inventory"] > 0,
            "q": snorm(search_text),
        })
    _, panel_variants = load_panel_products()
    for i, p in enumerate(panel_variants, start=len(index_products)):
        title = f"Panel decorativo ranurado {p['sku']} · {p['name']}"
        index_products.append({
            "i": i, "sku": p["sku"], "handle": "panel-decorativo",
            "url": f"producto/panel-decorativo.html?sku={quote(p['sku'])}",
            "title": title, "price": p["price"], "img": p["image"],
            "group": "Hogar", "sub": "Paneles decorativos",
            "old_price": None, "label": "290 × 17 cm",
            "available": p["available"],
            "q": snorm(f"{title} panel pared paneles decorativos panel ranurado lambrin liston ZT {p['sku']}"),
        })
    # 吸顶风扇专页也进搜索索引，让站内搜索/分类能找到它（页面本身由 ventilador_page 生成）
    _vt = load_json(VENTILADOR_PATH, {})
    if _vt.get("activo") and _vt.get("sku") and _vt.get("precio"):
        _vt_img = ((_vt.get("imagenes") or [{}])[0].get("archivo") or "").lstrip("/")
        index_products.append({
            "i": len(index_products), "sku": _vt["sku"],
            "handle": _vt.get("handle", "abanico-de-techo-led"),
            "url": f'producto/{quote(_vt.get("handle", "abanico-de-techo-led"))}.html',
            "title": _vt.get("titulo_corto") or _vt.get("titulo", ""),
            "price": float(_vt["precio"]), "img": _vt_img,
            "group": "Cocina y Electrohogar", "sub": "Climatización",
            "old_price": (float(_vt["precio_antes"]) if _vt.get("precio_antes") else None),
            "label": _vt.get("descuento_texto", ""), "available": True,
            "q": snorm(f'{_vt.get("titulo","")} {_vt.get("subtitulo","")} abanico ventilador de techo '
                       f'luz led lampara control remoto E27 climatizacion {_vt["sku"]}'),
        })

    with open(f"{OUT_DIR}/products-index.json", "w", encoding="utf-8") as f:
        json.dump(index_products, f, ensure_ascii=False, separators=(",", ":"))
    cards = [product_card(p) for p in products[:24]]

    # ---- 推广落地页 /enlaces.html（link-in-bio）----
    _enl_products = list(products)
    _adh = load_json(ADHESIVE_PANEL_PATH, {})
    if _adh.get("sku") and not any(p["sku"] == _adh["sku"] for p in _enl_products):
        _c0 = (_adh.get("colors") or [{}])[0]
        _enl_products.append({
            "sku": _adh["sku"], "handle": _adh.get("handle", "panel-autoadhesivo"),
            "title": _adh.get("short_name") or _adh.get("name", ""),
            "price": _adh.get("price"), "old_price": _adh.get("old_price"),
            "img": _c0.get("image") or _adh.get("image", ""),
            "url": "panel-autoadhesivo.html", "group": "Hogar", "sub": "Paneles",
        })
    enlaces = enlaces_page(_enl_products)
    if enlaces:
        with open(f"{OUT_DIR}/enlaces.html", "w", encoding="utf-8") as f:
            f.write(enlaces)
        print(f"✅ 推广落地页: {OUT_DIR}/enlaces.html")

    # ---- 专题合集 ----
    by_sku = {p["sku"]: p for p in products}
    collections = [c for c in load_collections() if c.get("active")]
    collections.sort(key=lambda c: c.get("order", 0))
    for c in collections:
        c["slug"] = slugify(c.get("slug") or c.get("title", ""))
    feats = featured_html(collections, by_sku)

    TILE_BG = {"Belleza y Salud": "#FCEFF4", "Hogar": "#EAF6EF",
               "Cocina y Electrohogar": "#FFF3E5", "Ferretería": "#EEF2F7",
               "Tecnología": "#EAF0FB", "Bebés y Niños": "#FFF0E8",
               "Más categorías": "#F4F0FA"}
    tiles = "".join(
        f'<div class="tile" data-g="{esc(g)}"><div class="tico" style="background:{TILE_BG.get(g, "#F1F3F6")}">'
        f'{GROUP_ICONS.get(g, "🛍️")}</div><div class="tnm">{esc(g)}</div></div>' for g in groups)
    cat_sections = []
    for g in groups:
        total = sum(subs_of[g].values())
        sub_buttons = [
            f'<button class="cat-sub" data-g="{esc(g)}" data-s="{esc(s)}">{esc(s)}<small>{n} productos</small></button>'
            for s, n in sorted(subs_of[g].items(), key=lambda kv: -kv[1])]
        cat_sections.append(
            f'<section class="cat-section" data-section="{esc(g)}"><button class="cat-section-title" data-g="{esc(g)}" data-s="*">'
            f'{GROUP_ICONS.get(g, "🛍️")} {esc(g)} <span>Ver los {total}</span></button>'
            f'<div class="cat-subgrid">{"".join(sub_buttons)}</div></section>')
    group_options = '<option value="*">Todas las categorías</option>' + "".join(
        f'<option value="{esc(g)}">{esc(g)}</option>' for g in groups)
    subs_json = json.dumps({g: sorted(subs_of[g]) for g in groups}, ensure_ascii=False)
    home_body = modern_home_body(feats, tiles, cat_sections, group_options, subs_json,
                                 cards, len(index_products), best_sellers_html(products),
                                 reviews_html(), stores_html())
    with open(f"{OUT_DIR}/index.html", "w", encoding="utf-8") as f:
        f.write(page(f"{SITE_NAME} — Tienda online RD", home_body, wa_float=True,
                     desc="Hogar, belleza, herramientas, electrónica y más. Contra entrega en Gran Santo Domingo.",
                     canonical=public_url()))

    # ---- 购物车页 ----
    with open(f"{OUT_DIR}/carrito.html", "w", encoding="utf-8") as f:
        f.write(carrito_page())

    # ---- Garantía ----
    with open(f"{OUT_DIR}/garantia.html", "w", encoding="utf-8") as f:
        f.write(garantia_page())

    # ---- 格栅板独立专题页（数据来自 data/panels.json）----
    panels_html = panels_page()
    if panels_html:
        with open(f"{OUT_DIR}/paneles-decorativos.html", "w", encoding="utf-8") as f:
            f.write(panels_html)
        print(f"✅ 格栅板专题: {OUT_DIR}/paneles-decorativos.html")
    panel_detail_html = panel_product_page()
    if panel_detail_html:
        with open(f"{OUT_DIR}/producto/panel-decorativo.html", "w", encoding="utf-8") as f:
            f.write(panel_detail_html)
        print(f"✅ 格栅板多 SKU 详情: {OUT_DIR}/producto/panel-decorativo.html")

    # ---- 吸顶风扇 E27 商品详情页 ----
    ventilador_html = ventilador_page(products)
    if ventilador_html:
        _vt_handle = str(load_json(VENTILADOR_PATH, {}).get("handle") or "abanico-de-techo-led")
        os.makedirs(f"{OUT_DIR}/producto", exist_ok=True)
        with open(f"{OUT_DIR}/producto/{_vt_handle}.html", "w", encoding="utf-8") as f:
            f.write(ventilador_html)
        print(f"✅ 吸顶风扇详情页: {OUT_DIR}/producto/{_vt_handle}.html")

    # ---- 卷装自粘格栅贴面投流落地页 ----
    adhesive_panel_html = adhesive_panel_page()
    if adhesive_panel_html:
        with open(f"{OUT_DIR}/panel-autoadhesivo.html", "w", encoding="utf-8") as f:
            f.write(adhesive_panel_html)
        print(f"✅ 自粘墙面卷材落地页: {OUT_DIR}/panel-autoadhesivo.html")
        for variant in (1, 2, 3):
            variant_html = adhesive_panel_variant_page(variant)
            with open(f"{OUT_DIR}/panel-autoadhesivo-v{variant}.html", "w", encoding="utf-8") as f:
                f.write(variant_html)
        print(f"✅ 自粘墙面卷材设计提案: 3 个预览版本")
        temu_html = adhesive_panel_temu_page()
        with open(f"{OUT_DIR}/panel-autoadhesivo-temu.html", "w", encoding="utf-8") as f:
            f.write(temu_html)
        print(f"✅ 自粘墙面卷材 Temu 排版预览")

    # ---- 配送分区数据（前端 fetch，改价只改 JSON 不动 JS）----
    if os.path.isfile("data/shipping_zones.json"):
        os.makedirs(f"{OUT_DIR}/data", exist_ok=True)
        shutil.copy2("data/shipping_zones.json", f"{OUT_DIR}/data/shipping_zones.json")
    else:
        print("⚠️  缺少 data/shipping_zones.json，结算页运费将显示 por confirmar")

    # ---- 专题合集页 ----
    n_coll = 0
    if collections:
        os.makedirs(f"{OUT_DIR}/coleccion", exist_ok=True)
        for c in collections:
            if c.get("landing"):
                continue
            prods = [by_sku[s] for s in c.get("skus", []) if s in by_sku]
            if not prods and not c.get("coming_soon"):
                continue
            with open(f"{OUT_DIR}/coleccion/{c['slug']}.html", "w", encoding="utf-8") as f:
                f.write(coming_soon_collection_page(c) if c.get("coming_soon") else coleccion_page(c, prods))
            n_coll += 1
        if n_coll:
            print(f"✅ 专题合集: {n_coll} 个 → {OUT_DIR}/coleccion/")

    # ---- 独立分类页（SEO + 可分享链接）----
    os.makedirs(f"{OUT_DIR}/categoria", exist_ok=True)
    category_urls = []
    for g in groups:
        group_products = [p for p in products if p["group"] == g]
        group_slug = slugify(g)
        description = f"Compra {g.lower()} online en República Dominicana. Precios claros, entrega y atención por WhatsApp."
        with open(f"{OUT_DIR}/categoria/{group_slug}.html", "w", encoding="utf-8") as f:
            f.write(category_page(g, group_products, description, group_slug))
        category_urls.append(public_url(f"categoria/{group_slug}.html"))
        for sub in sorted(subs_of[g]):
            sub_products = [p for p in group_products if p["sub"] == sub]
            sub_slug = slugify(f"{g}-{sub}")
            sub_desc = f"Encuentra {sub.lower()} en VivaBien RD. Compra online con entrega y soporte por WhatsApp."
            with open(f"{OUT_DIR}/categoria/{sub_slug}.html", "w", encoding="utf-8") as f:
                f.write(category_page(sub, sub_products, sub_desc, sub_slug))
            category_urls.append(public_url(f"categoria/{sub_slug}.html"))

    # ---- 推荐栏索引 ----
    by_sub, by_group = {}, {}
    for p in products:
        by_sub.setdefault((p["group"], p["sub"]), []).append(p)
        by_group.setdefault(p["group"], []).append(p)

    def recommendations(p, n=8):
        """同子分类优先，不够用同大组补齐；有价格优先；顺序按 handle 哈希稳定打散"""
        def rank(c):
            h = hashlib.md5((p["handle"] + c["handle"]).encode()).hexdigest()
            return (c["price"] is None, h)
        same_sub = [c for c in by_sub.get((p["group"], p["sub"]), []) if c["handle"] != p["handle"]]
        picks = sorted(same_sub, key=rank)[:n]
        if len(picks) < n:
            seen = {c["handle"] for c in picks} | {p["handle"]}
            rest = [c for c in by_group.get(p["group"], []) if c["handle"] not in seen]
            picks += sorted(rest, key=rank)[:n - len(picks)]
        return picks

    # ---- 详情页 ----
    for p in products:
        commerce_detail = detail_rollout_all or p["sku"] in detail_rollout_skus
        # 多图画廊：整宽滑动 + 圆点指示器 + 缩略图（单图退化为普通大图）
        gal = product_gallery(p)
        if len(gal) > 1:
            lazy = "loading='lazy' "
            slides = "".join(
                f'<div class="gs"><img src="../images/{esc(g)}" alt="{esc(p["title"])}" '
                f'{lazy if i else ""}onerror="this.style.opacity=0"></div>'
                for i, g in enumerate(gal))
            dots = "".join(f'<span class="{"on" if i == 0 else ""}"></span>' for i in range(len(gal)))
            gallery_html = (f'<div class="galwrap"><div class="gal" id="gal">{slides}</div>'
                            f'<div class="dots" id="dots">{dots}</div></div>')
            thumbs = '<div class="thumbs" id="galThumbs">' + "".join(
                f'<img src="../images/{esc(g)}" class="{"on" if i==0 else ""}" data-i="{i}">'
                for i, g in enumerate(gal)) + '</div>'
            gal_js = """<script>
(function(){
 var gal=document.getElementById('gal'),dots=document.getElementById('dots').children,
     ths=document.getElementById('galThumbs').children,n=gal.children.length,cur=0;
 function setOn(i){if(i===cur)return;cur=i;
  for(var k=0;k<n;k++){dots[k].classList.toggle('on',k===i);ths[k].classList.toggle('on',k===i)}}
 gal.addEventListener('scroll',function(){setOn(Math.round(gal.scrollLeft/gal.clientWidth))},{passive:true});
 for(var k=0;k<n;k++)(function(i){ths[i].onclick=function(){gal.scrollTo({left:i*gal.clientWidth,behavior:'smooth'})}})(k);
})();
</script>"""
        else:
            gallery_html = (f'<img class="main" src="../images/{esc(gal[0] if gal else "")}" '
                            f'alt="{esc(p["title"])}" onerror="this.style.opacity=0">')
            thumbs = ""
            gal_js = ""
        sale = discount_info(p)
        detail_label = f'<span class="detail-offer">{esc(p["label"])}</span><br>' if p.get("label") else ""
        if sale:
            price_html = (f'<div class="detail-price">'
                          f'{detail_label}'
                          f'<div class="price">{fmt_price(p["price"])}</div><del>{fmt_price(p["old_price"])}</del><br>'
                          f'<span class="saving">Ahorras {fmt_price(sale["saving"])} · -{sale["percent"]}%</span></div>')
        elif p["price"] is not None:
            price_html = (f'<div class="detail-price">'
                          f'{detail_label}'
                          f'<div class="price">{fmt_price(p["price"])}</div></div>')
        else:
            price_html = '<div class="price ask">Consultar precio por WhatsApp</div>'
        desc_html = body_html(p["body"]) if len(p["body"].strip()) > 10 else esc(p["title"])
        safe_name = esc(p["title"])
        ve = (f"""fbq('track','ViewContent',{{content_ids:['{p["sku"]}'],content_name:'{safe_name}',content_type:'product',value:{p["price"] or 0},currency:'DOP'}});""")
        if p["price"] is not None:
            actions = f"""<a class="btn-back" href="../">←</a>
<a class="btn-wa" href="{wa_link(p['title'])}" target="_blank" aria-label="WhatsApp"
 onclick="fbq('track','Contact',{{content_ids:['{p["sku"]}']}})">{WA_SVG}</a>
<button class="btn-add" id="btnAdd" data-sku="{esc(p['sku'])}" data-handle="{esc(p['handle'])}"
 data-title="{esc(p['title'])}" data-price="{p['price']}" data-img="{esc(p['img'])}"
 onclick="addCart(this)">{BAG_SVG} Agregar al carrito</button>"""
            add_js = """<script>
function addCart(b){
 var c=vbCart(),sku=b.dataset.sku,f=c.find(function(x){return x.sku===sku});
 if(f){f.qty++}else{c.push({sku:sku,handle:b.dataset.handle,title:b.dataset.title,
  price:parseFloat(b.dataset.price),img:b.dataset.img,qty:1})}
 vbSave(c);
 fbq('track','AddToCart',{content_ids:[sku],content_type:'product',
  value:parseFloat(b.dataset.price),currency:'DOP'});
 var it=c.find(function(x){return x.sku===sku});
 vbTrack('addcart',sku,{qty:it.qty,price:it.price,cart_total:c.reduce(function(a,x){return a+x.price*x.qty},0),product_title:it.title,product_img:it.img});
 b.classList.add('added');b.innerHTML='✓ Agregado — Ver carrito';
 b.onclick=function(){location.href='../carrito'};
}
</script>"""
            if commerce_detail:
                add_js = add_js.replace(
                    "var c=vbCart(),sku=b.dataset.sku,f=c.find(function(x){return x.sku===sku});",
                    "var q=Math.max(1,parseInt((document.getElementById('detailQty')||{}).value||1,10));"
                    "var c=vbCart(),sku=b.dataset.sku,f=c.find(function(x){return x.sku===sku});")
                add_js = add_js.replace(
                    "if(f){f.qty++}else{c.push({sku:sku,handle:b.dataset.handle,title:b.dataset.title,\n  price:parseFloat(b.dataset.price),img:b.dataset.img,qty:1})}",
                    "if(f){f.qty+=q}else{c.push({sku:sku,handle:b.dataset.handle,title:b.dataset.title,\n  price:parseFloat(b.dataset.price),img:b.dataset.img,qty:q})}")
                add_js = add_js.replace(
                    "value:parseFloat(b.dataset.price),currency:'DOP'",
                    "value:parseFloat(b.dataset.price)*q,currency:'DOP'")
                add_js = f"""<script>
function detailQty(delta){{
 var q=document.getElementById('detailQty'),total=document.getElementById('detailTotal');
 if(!q)return;var n=Math.max(1,Math.min(99,parseInt(q.value||1,10)+delta));q.value=n;q.textContent=n;
 if(total)total.textContent='RD$ '+({p['price']:.2f}*n).toLocaleString('en-US',{{maximumFractionDigits:2}});
}}
</script>""" + add_js
        else:
            actions = f"""<a class="btn-back" href="../">←</a>
<a class="btn-wa wide" href="{wa_link(p['title'])}" target="_blank"
 onclick="fbq('track','Contact',{{content_ids:['{p["sku"]}']}})">{WA_SVG} Pedir por WhatsApp</a>"""
            add_js = ""
        recs = recommendations(p)
        recs_html = ""
        if recs:
            cards_r = "".join(
                f'<a class="rec" href="{c["handle"]}">'
                f'<img src="../images/{esc(c["img"])}" loading="lazy" onerror="this.style.opacity=0">'
                f'<div class="rn">{esc(c["title"])}</div>'
                + (f'<div class="rp">{fmt_price(c["price"])}</div>' if c["price"] is not None
                   else '<div class="rp ask">Consultar</div>')
                + '</a>' for c in recs)
            recs_html = f'<div class="recs"><h2>También te puede gustar</h2><div class="rec-row">{cards_r}</div></div>'
        measurements = product_measurements(p)
        if p.get("inventory") is not None and p["inventory"] > 0:
            stock_html = '<b class="stock-ok">Disponible</b><span>Existencia registrada; confirmaremos antes del despacho.</span>'
        else:
            stock_html = '<b class="stock-check">Disponibilidad por confirmar</b><span>Te confirmaremos la existencia antes del despacho.</span>'
        measure_html = (f'<div class="buy-fact"><span>📏</span><div><b>Tamaño / presentación</b>{esc(measurements)}</div></div>'
                        if measurements else
                        f'<div class="buy-fact"><span>📏</span><div><b>¿Necesitas una medida exacta?</b><a href="{wa_link(p["title"])}" target="_blank">Pregúntanos por WhatsApp</a></div></div>')
        facts_html = (f'<div class="buy-facts"><div class="buy-fact"><span>✅</span><div>{stock_html}</div></div>'
                      f'{measure_html}<div class="buy-fact"><span>🚚</span><div><b>Tiempo estimado</b>'
                      '1-2 días laborables en Gran Santo Domingo; 1-7 días en el resto del país, según la zona.</div></div></div>')
        detail_class = "dt commerce" if commerce_detail else "dt"
        if commerce_detail:
            commerce_meta = (f'<div class="commerce-meta"><span>SKU {esc(p["sku"])}</span>'
                               f'<span>{esc(p["sub"])}</span></div>')
            commerce_strip = ('<div class="commerce-strip"><span>✓ Envíos a todo RD</span>'
                              '<i></i><span>✓ Compra protegida</span></div>')
            commerce_proof = ('<div class="commerce-proof"><span>💬</span><div>'
                              '<strong>¿Tienes dudas antes de comprar?</strong>'
                              'Confirma existencia, tamaño o entrega por WhatsApp.</div></div>')
            if p["price"] is not None:
                quantity_html = ('<div class="commerce-choice"><div class="commerce-choice-label">'
                                 '<b>Cantidad</b><span>Selecciona cuántas unidades necesitas</span></div>'
                                 '<div class="commerce-qty"><button type="button" onclick="detailQty(-1)" '
                                 'aria-label="Reducir cantidad">−</button><output id="detailQty" value="1">1</output>'
                                 '<button type="button" onclick="detailQty(1)" aria-label="Aumentar cantidad">+</button></div></div>')
                commerce_total = (f'<div class="commerce-bar-total"><span>Total del producto</span>'
                                  f'<strong id="detailTotal">{fmt_price(p["price"])}</strong></div>')
            else:
                quantity_html = ""
                commerce_total = ""
        else:
            commerce_meta = commerce_strip = commerce_proof = quantity_html = commerce_total = ""
        detail = f"""{header("../")}
<div class="crumb"><a href="../">{esc(SITE_NAME)}</a> / <a href="../categoria/{slugify(p['group'])}">{esc(p['group'])}</a> / {esc(p['sub'])}</div>
<div class="{detail_class}">
<div class="pic">{gallery_html}{thumbs}</div>
<div>
<div class="panel">
<h1>{esc(p['title'])}</h1>
{commerce_meta}
{price_html}
{commerce_strip}
{quantity_html}
{commerce_proof}
<div class="trust">
<div><span class="em">🚚</span>Entrega<br>24-72 horas</div>
<div><span class="em">💵</span>Pagas<br>al recibir</div>
<div><span class="em">↩️</span>Garantía<br>de 7 días</div>
</div>
{facts_html}
<div class="sec">Descripción</div>
<div class="desc">{desc_html}</div>
<div class="bar">
{commerce_total}
<div class="customer-proof">⭐ +120 clientes satisfechos en toda RD</div>
<div class="bar-btns">
{actions}
</div>
<div class="microtrust">
<span>🛡️ Pago 100% seguro</span>
<span>👀 Puedes verificar tu producto antes de pagar</span>
</div>
</div>
</div>
</div>
</div>
{recs_html}
{gal_js}
{add_js}"""
        availability = None
        if p.get("inventory") is not None:
            availability = ("https://schema.org/InStock" if p["inventory"] > 0
                            else "https://schema.org/OutOfStock")
        product_url = public_url(f"producto/{p['handle']}.html")
        category_url = public_url(f"categoria/{slugify(p['group'])}.html")
        product_schema = {
            "@type": "Product", "name": p["title"],
            "image": [f"{SITE_URL}/images/{g}" for g in (gal or [p["img"]])],
            "description": plain_text(p["body"])[:500] or p["title"],
            "sku": p["sku"],
        }
        if p["price"] is not None:
            product_schema["offers"] = {
                "@type": "Offer", "url": product_url,
                "priceCurrency": "DOP", "price": f'{p["price"]:.2f}',
                "itemCondition": "https://schema.org/NewCondition"
            }
            if availability:
                product_schema["offers"]["availability"] = availability
        breadcrumb_schema = {
            "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": public_url()},
                {"@type": "ListItem", "position": 2, "name": p["group"], "item": category_url},
                {"@type": "ListItem", "position": 3, "name": p["title"], "item": product_url},
            ]
        }
        schema_graph = {"@context": "https://schema.org", "@graph": [product_schema, breadcrumb_schema]}
        schema_head = '<script type="application/ld+json">' + json.dumps(schema_graph, ensure_ascii=False).replace("</", "<\\/") + '</script>'
        product_title = f'{p["title"]} | {fmt_price(p["price"])} en RD | {SITE_NAME}'
        product_desc = product_meta_description(p)
        with open(f"{OUT_DIR}/producto/{p['handle']}.html", "w", encoding="utf-8") as f:
            f.write(page(product_title, detail, pixel_extra=ve,
                         desc=product_desc, track_sku=p["sku"], track_category=p["sub"],
                         track_title=p["title"], track_img=p["img"], extra_head=schema_head,
                         canonical=product_url, rel="../",
                         og_image=f"{SITE_URL}/images/{quote((gal or [p['img']])[0])}"))

    # ---- SEO 索引 ----
    sitemap_urls = [public_url(), public_url("garantia.html")]
    if panels_html:
        sitemap_urls.append(public_url("paneles-decorativos.html"))
    if panel_detail_html:
        sitemap_urls.append(public_url("producto/panel-decorativo.html"))
    if adhesive_panel_html:
        sitemap_urls.append(public_url("panel-autoadhesivo.html"))
    if ventilador_html:
        sitemap_urls.append(public_url(f"producto/{_vt_handle}.html"))
    sitemap_urls += category_urls
    sitemap_urls += [public_url(f"coleccion/{c['slug']}.html") for c in collections
                     if not c.get("landing") and
                     (c.get("coming_soon") or any(s in by_sku for s in c.get("skus", [])))]
    sitemap_urls += [public_url(f"producto/{p['handle']}.html") for p in products]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f'<url><loc>{esc(url)}</loc></url>' for url in sitemap_urls]
    sitemap.append('</urlset>')
    with open(f"{OUT_DIR}/sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap))
    with open(f"{OUT_DIR}/robots.txt", "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")

    # ---- 分类统计 ----
    print(f"✅ 构建完成: {len(products)} 个商品 → {OUT_DIR}/")
    print(f"✅ Merchant 候选: {merchant_report['selected_candidates']} 个 → {REPORT_DIR}/merchant_candidates.csv")
    for g in groups:
        subs = sorted(subs_of[g].items(), key=lambda kv: -kv[1])
        print(f"   {g}: " + ", ".join(f"{s}({n})" for s, n in subs))

if __name__ == "__main__":
    build()
