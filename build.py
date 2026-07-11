#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VivaBien 静态站构建脚本
读取 data/products.csv → 生成 dist/ 整站（首页 + 商品详情页 + 购物车结算页）
用法: python3 build.py
"""
import csv, os, re, html, json, shutil, unicodedata

# ============ 配置区（只需要改这里）============
WHATSAPP   = "18092811992"          # WhatsApp 号码（国家码+号码，不带+号）
PIXEL_ID   = "882086747967886"      # Meta Pixel
SITE_NAME  = "VivaBien"             # 品牌名
SITE_URL   = "https://vivabien.xyz" # 你的域名
API_BASE   = "https://vivabien.xyz" # 边缘后端（Worker）同域：/s/* 短链、/api/* 埋点/优惠券
CSV_PATH   = "data/products.csv"
IMG_DIR    = "images"               # 商品图片文件夹（VBxxxx.jpg 都放这里）
OUT_DIR    = "dist"

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
                price=r.get("Variant Price", ""), img=r.get("Image Src", ""))

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
        p["img"]   = p["img"].strip()
        p["extras"] = extras.get(p["handle"], [])
        # 卡片图 = 画廊第一张（有场景图先场景图，用户规则）
        gal = product_gallery(p)
        if gal:
            p["img"] = gal[0]
        p["group"], p["sub"] = classify(p)
        products.append(p)
    products.sort(key=lambda p: (p["price"] is None, p["group"], p["sub"]))
    return products

def fmt_price(v):
    return "RD$ {:,.0f}".format(v) if v is not None else "Consultar precio"

def esc(s):
    return html.escape(s, quote=True)

def body_html(raw):
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
/* featured collections */
.feats{display:flex;flex-direction:column;gap:11px;margin:16px 0 2px}
@media(min-width:640px){.feats{flex-direction:row;flex-wrap:wrap}.feats .feat{flex:1;min-width:280px}}
.feat{border-radius:18px;padding:16px;color:#fff;text-decoration:none;display:block;position:relative;overflow:hidden}
.feat .kick{font-size:10.5px;font-weight:800;letter-spacing:.06em;opacity:.85;text-transform:uppercase}
.feat h3{font-size:19px;font-weight:800;margin:4px 0 2px;letter-spacing:-.01em}
.feat p{font-size:12px;opacity:.92;font-weight:600}
.feat .thumbs{display:flex;gap:7px;margin:12px 0 13px}
.feat .thumbs img{flex:1;width:0;aspect-ratio:1;object-fit:cover;border-radius:10px;background:rgba(255,255,255,.18)}
.feat .go{display:inline-flex;align-items:center;gap:6px;background:#fff;color:#16202E;font-weight:800;font-size:13px;padding:8px 15px;border-radius:99px}
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
.card-add{position:absolute;right:11px;bottom:11px;width:38px;height:38px;border:0;border-radius:12px;background:#2563D9;color:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 12px rgba(37,99,217,.28);transition:background .15s,transform .15s}
.card-add:active{transform:scale(.92)}
.card-add.added{background:#157A4E}
.card-add svg{width:19px;height:19px}
/* detail */
.dt{max-width:920px;margin:0 auto;padding:0 0 100px}
@media(min-width:760px){.dt{display:grid;grid-template-columns:1fr 1fr;gap:28px;padding:26px 18px 40px;align-items:start}}
.dt .pic{background:#F0F3F8}
@media(min-width:760px){.dt .pic{border-radius:22px;overflow:hidden;position:sticky;top:80px}}
.dt .pic img.main{width:100%;aspect-ratio:1;object-fit:cover}
/* 大图画廊：整宽滑动 + 圆点指示器 */
.galwrap{position:relative}
.gal{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.gal::-webkit-scrollbar{display:none}
.gal .gs{flex:none;width:100%;scroll-snap-align:center}
.gal .gs img{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}
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
.trust{display:flex;justify-content:space-between;background:#F7F9FD;border:1px solid #EDF1F7;border-radius:18px;padding:16px 6px;margin-bottom:20px}
.trust>div{display:flex;flex-direction:column;align-items:center;gap:7px;flex:1;font-size:10.5px;font-weight:700;text-align:center}
.trust>div+div{border-left:1px solid #E5EAF2}
.trust .em{width:38px;height:38px;border-radius:50%;background:#EAF0FB;display:flex;align-items:center;justify-content:center;font-size:18px}
.sec{font-weight:800;font-size:15px;margin-bottom:8px}
.desc{font-size:13px;color:#3a4250;line-height:1.65;margin-bottom:18px}
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
footer{text-align:center;font-size:12px;color:#9aa3b2;padding:26px 18px 34px;line-height:1.9}
footer .rnc{font-size:11px;color:#b3bac6}
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
.fld select{appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%235a6577' stroke-width='3'><path d='M6 9l6 6 6-6'/></svg>");background-repeat:no-repeat;background-position:right 14px center}
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
/* confirmación */
.ok{display:none;min-height:70vh;background:linear-gradient(160deg,#2563D9,#1A47A6);border-radius:24px;margin:18px;padding:60px 24px;text-align:center;color:#fff}
.ok .ck{width:86px;height:86px;border-radius:50%;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;margin:0 auto 22px;font-size:38px}
.ok h2{font-weight:800;font-size:26px;margin-bottom:12px}
.ok p{font-size:14px;color:#d3e0fb;line-height:1.6;max-width:320px;margin:0 auto 26px}
.ok a{display:inline-block;background:#fff;color:#2563D9;font-weight:800;font-size:15px;padding:14px 30px;border-radius:16px}
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
 try{fbq('track','AddToCart',{content_ids:[sku],content_type:'product',
  value:parseFloat(b.dataset.price),currency:'DOP'})}catch(e){}
 try{vbTrack('addcart',sku)}catch(e){}
}
function vbCardAdd(e,b){
 if(e){e.preventDefault();e.stopPropagation()}
 vbAddProduct(b);b.classList.add('added');b.setAttribute('aria-label','Agregado al carrito');
 var old=b.innerHTML;b.innerHTML='✓';setTimeout(function(){b.classList.remove('added');b.innerHTML=old;
  b.setAttribute('aria-label','Agregar al carrito')},900);
}
document.addEventListener('DOMContentLoaded',vbBadge);
</script>"""

# 自有埋点：把访客行为回传边缘后端 D1（vb_vid cookie 由 /s/:code 或本请求种下）
# vbTrack(type, sku)  type: view | addcart | checkout
TRACK_JS = ("<script>window.vbTrack=function(t,s,x){try{var b={type:t,sku:s||''};"
            "if(x)for(var k in x)b[k]=x[k];"
            "fetch('__API__/api/track',{method:'POST',credentials:'include',keepalive:true,"
            "headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify(b)}).catch(function(){})}catch(e){}};</script>"
            ).replace("__API__", API_BASE)

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

def page(title, body, pixel_extra="", desc="", track_sku=None, wa_float=False):
    view_js = f"<script>vbTrack('view',{json.dumps(track_sku)})</script>" if track_sku else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc[:150])}">
{FONT}
<style>{CSS}</style>
{pixel(pixel_extra)}
{CART_JS}
{TRACK_JS}
</head><body>
{body}
{view_js}
{WA_FLOAT if wa_float else ""}
<footer>© {SITE_NAME} · Envíos en toda República Dominicana · Pago contra entrega
<div class="rnc">RNC: 132888855 · Registrado bajo la Ley 126-02 de Comercio Electrónico · 🔒 Sitio seguro</div></footer>
</body></html>"""

def header(rel=""):
    return f"""<div class="hd"><div class="wrap hd-in">
<a class="logo" href="{rel}index.html"><span class="ic">{SITE_NAME[0]}</span>{esc(SITE_NAME)}</a>
<div class="hd-r">
<a class="hd-wa" href="https://wa.me/{WHATSAPP}" target="_blank" onclick="fbq('track','Contact')">{WA_SVG} WhatsApp</a>
<a class="hd-cart" href="{rel}index.html?buscar=1" aria-label="Buscar"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></a>
<a class="hd-cart" href="{rel}carrito.html" aria-label="Carrito">{BAG_SVG}<span class="cart-n" id="cartN"></span></a>
</div>
</div></div>"""

# ---------- 购物车/结算页 ----------
def carrito_page():
    banks_html = "".join(
        f'<div class="bk"><div><div class="bn">{esc(b)}</div><div class="bo">{esc(o)}</div></div>'
        f'<div class="ba">{esc(a)}</div></div>' for b, a, o in BANKS)
    bank_lines = "\\n".join(f"{b}: {a} ({o})" for b, a, o in BANKS)

    body = header() + """
<div class="ct" id="main">
<h1>Tu compra</h1>
<div class="box" id="itemsBox"><div class="bt">🛍️ Productos</div><div id="items"></div></div>

<div class="box" id="formBox">
<div class="bt">🚚 Datos de entrega</div>
<div class="fld"><label>Nombre completo *</label><input id="fNom" placeholder="Tu nombre"></div>
<div class="fld"><label>Teléfono / WhatsApp *</label><input id="fTel" inputmode="tel" placeholder="809 000 0000">
<div class="hint">📞 Te llamaremos a este número cuando tu pedido esté llegando</div></div>
<div class="fld"><label>Provincia *</label><select id="fProv" onchange="provUI()"></select></div>
<div class="fld" id="sectorFld"><label>Sector / Zona *</label><select id="fSector"></select></div>
<div class="fld" id="cityFld" style="display:none"><label>Municipio / Ciudad *</label><input id="fCity" placeholder="Ej: Santiago, Moca..."></div>
<div class="fld"><label>Dirección (calle y número) *</label><textarea id="fDir" rows="2" placeholder="Calle, No., referencia"></textarea></div>
<div class="fld"><label>Nota (opcional)</label><input id="fNota" placeholder="Referencia, horario..."></div>
</div>

<div class="box" id="payBox">
<div class="bt">💳 ¿Cómo pagas?</div>
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
<div class="ln">Envío <b>Se confirma por WhatsApp</b></div>
<div class="gt">Total <span id="tTot">RD$ 0</span></div>
<button class="btn-conf" id="btnConf" onclick="confirmar()">🛡️ Confirmar pedido</button>
<div class="sub-note">Al confirmar se abre WhatsApp con tu pedido listo para enviar.</div>
</div>
</div>

<div class="ok" id="okScreen">
<div class="ck">✓</div>
<h2>¡Pedido enviado!</h2>
<p>Tu pedido <b id="okId"></b> fue enviado por WhatsApp.<br>Te confirmaremos la entrega en breve.</p>
<a href="index.html">Seguir comprando</a>
</div>

<script>
var WA='__WA__';
var COUPON=null; // {code,kind,value} —— 已应用的优惠券
function money(v){return 'RD$ '+Math.round(v).toLocaleString('en-US')}
function subtotal(){return vbCart().reduce(function(a,it){return a+it.price*it.qty},0)}
function calcDiscount(sub){
 if(!COUPON)return 0;
 var d=COUPON.kind==='percent'?sub*COUPON.value/100:COUPON.value;
 return Math.min(d,sub);
}
function paintTotals(){
 var sub=subtotal(),disc=calcDiscount(sub),tot=sub-disc;
 document.getElementById('tSub').textContent=money(sub);
 var dl=document.getElementById('discLn');
 if(disc>0){dl.style.display='flex';
  document.getElementById('tDisc').textContent='- '+money(disc);
  document.getElementById('discCode').textContent=COUPON.code;
 }else{dl.style.display='none';}
 document.getElementById('tTot').textContent=money(tot);
 document.getElementById('btnConf').textContent='🛡️ Confirmar pedido · '+money(tot);
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
  document.getElementById('itemsBox').innerHTML='<div class="empty">Tu carrito está vacío.<br><br><a href="index.html">← Ver productos</a></div>';
  ['formBox','payBox','totBox'].forEach(function(i){document.getElementById(i).style.display='none'});
  return;}
 box.innerHTML=c.map(function(it,i){
  return '<div class="ci"><img src="images/'+it.img+'" onerror="this.style.opacity=0">'
  +'<div class="t"><div class="nm">'+it.title+'</div><div class="pr">'+money(it.price)+'</div>'
  +'<div class="qty"><button onclick="qty('+i+',-1)">−</button><span>'+it.qty+'</span><button onclick="qty('+i+',1)">+</button></div></div>'
  +'<button class="rm" onclick="rm('+i+')">✕</button></div>';}).join('');
 paintTotals();
}
function qty(i,d){var c=vbCart();c[i].qty+=d;if(c[i].qty<1)c[i].qty=1;vbSave(c);render()}
function rm(i){var c=vbCart();c.splice(i,1);vbSave(c);render()}
function payUI(){
 var t=document.querySelector('input[name=pay]:checked').value;
 document.getElementById('lCod').classList.toggle('on',t==='cod');
 document.getElementById('lTra').classList.toggle('on',t==='transfer');
 document.getElementById('bankPanel').classList.toggle('show',t==='transfer');
}
var PROVS=["Distrito Nacional (Santo Domingo)","Santo Domingo (provincia)","Santiago","La Altagracia","La Vega","San Cristóbal","Puerto Plata","Duarte","San Pedro de Macorís","La Romana","Espaillat","Azua","Barahona","Monseñor Nouel","Sánchez Ramírez","Peravia","Valverde","Monte Plata","Hato Mayor","El Seibo","Samaná","María Trinidad Sánchez","Hermanas Mirabal","Bahoruco","Independencia","Elías Piña","San Juan","Dajabón","Santiago Rodríguez","Monte Cristi","Pedernales","San José de Ocoa"];
var SECTORES=["Santo Domingo Este","Santo Domingo Norte","Santo Domingo Oeste","Distrito Nacional (centro)","Naco","Piantini","Bella Vista","Gazcue","Los Prados","Arroyo Hondo","Los Ríos","El Millón","Evaristo Morales","Villa Mella","Herrera","Los Alcarrizos","Boca Chica","Villa Consuelo","Cristo Rey","Otro sector..."];
function fillSel(id,arr){var s=document.getElementById(id);
 arr.forEach(function(x){var o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o)});}
function provUI(){
 var isSD=document.getElementById('fProv').value.indexOf('Distrito Nacional')===0;
 document.getElementById('sectorFld').style.display=isSD?'block':'none';
 document.getElementById('cityFld').style.display=isSD?'none':'block';
}
fillSel('fProv',PROVS);fillSel('fSector',SECTORES);provUI();
function confirmar(){
 var c=vbCart();if(!c.length)return;
 var nom=document.getElementById('fNom').value.trim(),
     tel=document.getElementById('fTel').value.trim(),
     dir=document.getElementById('fDir').value.trim(),
     nota=document.getElementById('fNota').value.trim();
 var prov=document.getElementById('fProv').value;
 var isSD=prov.indexOf('Distrito Nacional')===0;
 var zona=isSD?document.getElementById('fSector').value
              :document.getElementById('fCity').value.trim();
 if(!nom||!tel||!prov||!zona||!dir){
  alert('Por favor completa nombre, teléfono, provincia, sector/ciudad y dirección.');return;}
 var loc=prov+' · '+zona;
 var pay=document.querySelector('input[name=pay]:checked').value;
 var oid='VB-'+Math.random().toString(36).slice(2,7).toUpperCase();
 var sub=0,lines=c.map(function(it){sub+=it.price*it.qty;
   return it.qty+'x '+it.title+' ('+it.sku+') — '+money(it.price*it.qty)});
 var disc=calcDiscount(sub),tot=sub-disc;
 var msg='🛒 *Pedido '+oid+'*\\n'+lines.join('\\n')
  +(disc>0?'\\n——\\nSubtotal: '+money(sub)+'\\n🏷️ Cupón '+COUPON.code+': - '+money(disc):'')
  +'\\n*Total: '+money(tot)+'*\\n——\\n👤 '+nom+'\\n📞 '+tel+'\\n📍 '+loc+'\\n🏠 '+dir
  +(nota?'\\n📝 '+nota:'')
  +'\\n💳 Pago: '+(pay==='cod'?'Contra entrega (efectivo)':'Transferencia bancaria — enviaré el comprobante')
  +(pay==='transfer'?'\\n\\nCuentas:\\n__BANKLINES__':'');
 fbq('track','Contact');
 try{fbq('track','InitiateCheckout',{value:tot,currency:'DOP',num_items:c.reduce(function(a,b){return a+b.qty},0)})}catch(e){}
 vbTrack('checkout','',{code:COUPON?COUPON.code:''});
 if(COUPON){try{fetch('__API__/api/coupon/redeem',{method:'POST',credentials:'include',keepalive:true,
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({code:COUPON.code,order_id:oid})}).catch(function(){})}catch(e){}}
 window.open('https://wa.me/'+WA+'?text='+encodeURIComponent(msg),'_blank');
 localStorage.removeItem('vb_cart');vbBadge();
 document.getElementById('okId').textContent=oid;
 document.getElementById('main').style.display='none';
 document.getElementById('okScreen').style.display='block';
 window.scrollTo(0,0);
}
render();payUI();
</script>"""
    body = (body.replace("__BANKS__", banks_html).replace("__WA__", WHATSAPP)
                .replace("__BANKLINES__", bank_lines).replace("__API__", API_BASE))
    return page(f"Tu compra — {SITE_NAME}", body,
                pixel_extra="fbq('track','InitiateCheckout');",
                desc="Carrito de compras VivaBien — pago contra entrega o transferencia.")

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
    price_html = (f'<b>{fmt_price(p["price"])}</b>' if p["price"] is not None
                  else '<span class="ask">Consultar</span>')
    add_button = (f'<button class="card-add" type="button" aria-label="Agregar al carrito" '
                  f'data-sku="{esc(p["sku"])}" data-handle="{esc(p["handle"])}" '
                  f'data-title="{esc(p["title"])}" data-price="{p["price"]}" data-img="{esc(p["img"])}" '
                  f'onclick="vbCardAdd(event,this)">{BAG_SVG}</button>'
                  if p["price"] is not None else "")
    return (f'<article class="card" data-g="{esc(p["group"])}" data-s="{esc(p["sub"])}" '
            f'data-q="{esc(snorm(p["title"] + " " + p["sub"] + " " + p["group"]))}" '
            f'><a class="card-link" href="{rel}producto/{p["handle"]}.html">'
            f'<div class="imgbox"><img src="{rel}images/{esc(p["img"])}" alt="{esc(p["title"])}" '
            f'loading="lazy" onerror="this.style.display=\'none\'">'
            f'<span class="badge">{esc(p["sub"])}</span></div>'
            f'<div class="info"><div class="nm">{esc(p["title"])}</div>'
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
<a class="bk" href="../index.html">← Volver a la tienda</a>
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
                desc=(c.get("subtitle") or c["title"])[:150])

def featured_html(collections, by_sku):
    """首页顶部专题入口卡片"""
    cards = ""
    for c in collections:
        prods = [by_sku[s] for s in c.get("skus", []) if s in by_sku]
        if not prods:
            continue
        c0, c1 = coll_grad(c["slug"])
        thumbs = "".join(
            f'<img src="images/{esc(pp["img"])}" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">'
            for pp in prods[:4])
        sub = f'<p>{esc(c.get("subtitle",""))}</p>' if c.get("subtitle") else ""
        cards += (f'<a class="feat" style="background:linear-gradient(120deg,{c0},{c1})" '
                  f'href="coleccion/{esc(c["slug"])}.html">'
                  f'<div class="kick">★ Destacado</div><h3>{esc(c["title"])}</h3>{sub}'
                  f'<div class="thumbs">{thumbs}</div>'
                  f'<span class="go">Ver colección →</span></a>')
    return f'<div class="feats">{cards}</div>' if cards else ""

def build():
    products = load_products()
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

    # ---- 商品卡 ----
    cards = [product_card(p) for p in products]

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
    subrows = []
    for g in groups:
        schips = ['<div class="schip on" data-s="*">Todo</div>'] + [
            f'<div class="schip" data-s="{esc(s)}">{esc(s)} · {n}</div>'
            for s, n in sorted(subs_of[g].items(), key=lambda kv: -kv[1])]
        subrows.append(f'<div class="subcats" data-g="{esc(g)}">{"".join(schips)}</div>')

    home_body = f"""{header()}
<div class="wrap">
<div class="search">
<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
<input id="q" type="search" placeholder="¿Qué buscas hoy? Ej: audífonos, espejo…" autocomplete="off">
<button class="clr" id="qClr" aria-label="Borrar">✕</button>
</div>
<div class="recent" id="recentRow"></div>
<div class="hero"><h1>Compra fácil, paga seguro</h1>
<div class="sub">🚚 Envíos a todo el país · 🤝 Contra entrega en Sto. Dgo.</div></div>
{feats}
<div class="cat-hd"><b id="catHdT">Categorías</b><span class="cat-clear" id="catClear">Quitar filtro ✕</span></div>
<div class="cattiles" id="cattiles">{tiles}</div>
{''.join(subrows)}
<div class="count"><span id="n">{len(products)}</span> productos</div>
<div class="grid" id="grid">{''.join(cards)}</div>
</div>
<script>
var curG='*',curS='*',curQ='';
function snorm(s){{return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')}}
function apply(){{let n=0;
 const words=snorm(curQ).split(/\\s+/).filter(Boolean);
 document.querySelectorAll('.card').forEach(cd=>{{
  const ok=(curG==='*'||cd.dataset.g===curG)&&(curS==='*'||cd.dataset.s===curS)
   &&words.every(w=>cd.dataset.q.includes(w));
  cd.style.display=ok?'':'none';if(ok)n++;}});
 document.getElementById('n').textContent=n;}}
var qEl=document.getElementById('q'),qClr=document.getElementById('qClr'),qT=null;
// 最近搜索（只存用户自己的搜索词，最多6个）
function recGet(){{try{{return JSON.parse(localStorage.getItem('vb_recent')||'[]')}}catch(e){{return[]}}}}
function recAdd(w){{var r=recGet().filter(x=>x!==w);r.unshift(w);r=r.slice(0,6);
 try{{localStorage.setItem('vb_recent',JSON.stringify(r))}}catch(e){{}}recPaint();}}
function recPaint(){{
 var r=recGet(),row=document.getElementById('recentRow');
 if(!r.length){{row.classList.remove('show');return}}
 row.innerHTML='<span class="rlb">Recientes:</span>'+r.map(w=>'<span class="rch">'+w.replace(/[<>&"]/g,'')+'</span>').join('')
  +'<button class="rclr" title="Borrar historial">✕</button>';
 row.classList.add('show');
 row.querySelectorAll('.rch').forEach(ch=>ch.onclick=()=>{{qEl.value=ch.textContent;qEl.dispatchEvent(new Event('input'))}});
 row.querySelector('.rclr').onclick=()=>{{try{{localStorage.removeItem('vb_recent')}}catch(e){{}}recPaint()}};
}}
recPaint();
qEl.addEventListener('input',()=>{{
 curQ=qEl.value;qClr.style.display=curQ?'block':'none';apply();
 clearTimeout(qT);
 if(curQ.trim().length>2)qT=setTimeout(()=>{{
  try{{fbq('track','Search',{{search_string:curQ.trim()}})}}catch(e){{}}
  recAdd(curQ.trim().toLowerCase());
 }},1200);
}});
qClr.onclick=()=>{{qEl.value='';curQ='';qClr.style.display='none';apply();qEl.focus()}};
var qp=new URLSearchParams(location.search).get('q');
if(qp){{qEl.value=qp;curQ=qp;qClr.style.display='block';apply()}}
if(new URLSearchParams(location.search).has('buscar'))qEl.focus();
// 分类图标网格：点瓦片=选中该大类并展开子分类；再点或“Quitar filtro”=清除
var catHdT=document.getElementById('catHdT'),catClear=document.getElementById('catClear');
function setGroup(g,icon){{
 curG=g;curS='*';
 document.querySelectorAll('.tile').forEach(t=>t.classList.toggle('on',t.dataset.g===g));
 document.querySelectorAll('.subcats').forEach(r=>{{
  r.classList.toggle('show',r.dataset.g===g);
  r.querySelectorAll('.schip').forEach((s,i)=>s.classList.toggle('on',i===0));}});
 catHdT.textContent=g==='*'?'Categorías':icon+' '+g;
 catClear.style.display=g==='*'?'none':'inline';
 apply();
}}
document.querySelectorAll('.tile').forEach(t=>t.onclick=()=>{{
 var icon=t.querySelector('.tico').textContent;
 setGroup(t.classList.contains('on')?'*':t.dataset.g,icon);
 if(curG!=='*')t.scrollIntoView({{block:'nearest'}});
}});
catClear.onclick=()=>setGroup('*','');
document.querySelectorAll('.schip').forEach(sc=>sc.onclick=()=>{{
 sc.parentElement.querySelectorAll('.schip').forEach(s=>s.classList.remove('on'));
 sc.classList.add('on');curS=sc.dataset.s;apply();}});
</script>"""
    with open(f"{OUT_DIR}/index.html", "w", encoding="utf-8") as f:
        f.write(page(f"{SITE_NAME} — Tienda online RD", home_body, wa_float=True,
                     desc="Hogar, belleza, herramientas, electrónica y más. Pago contra entrega en República Dominicana."))

    # ---- 购物车页 ----
    with open(f"{OUT_DIR}/carrito.html", "w", encoding="utf-8") as f:
        f.write(carrito_page())

    # ---- 专题合集页 ----
    n_coll = 0
    if collections:
        os.makedirs(f"{OUT_DIR}/coleccion", exist_ok=True)
        for c in collections:
            prods = [by_sku[s] for s in c.get("skus", []) if s in by_sku]
            if not prods:
                continue
            with open(f"{OUT_DIR}/coleccion/{c['slug']}.html", "w", encoding="utf-8") as f:
                f.write(coleccion_page(c, prods))
            n_coll += 1
        if n_coll:
            print(f"✅ 专题合集: {n_coll} 个 → {OUT_DIR}/coleccion/")

    # ---- 推荐栏索引 ----
    import hashlib
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
        price_html = (f'<div class="price">{fmt_price(p["price"])}</div>' if p["price"] is not None
                      else '<div class="price ask">Consultar precio por WhatsApp</div>')
        desc_html = body_html(p["body"]) if len(p["body"].strip()) > 10 else esc(p["title"])
        safe_name = esc(p["title"])
        ve = (f"""fbq('track','ViewContent',{{content_ids:['{p["sku"]}'],content_name:'{safe_name}',content_type:'product',value:{p["price"] or 0},currency:'DOP'}});""")
        if p["price"] is not None:
            actions = f"""<a class="btn-back" href="../index.html">←</a>
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
 vbTrack('addcart',sku);
 b.classList.add('added');b.innerHTML='✓ Agregado — Ver carrito';
 b.onclick=function(){location.href='../carrito.html'};
}
</script>"""
        else:
            actions = f"""<a class="btn-back" href="../index.html">←</a>
<a class="btn-wa wide" href="{wa_link(p['title'])}" target="_blank"
 onclick="fbq('track','Contact',{{content_ids:['{p["sku"]}']}})">{WA_SVG} Pedir por WhatsApp</a>"""
            add_js = ""
        recs = recommendations(p)
        recs_html = ""
        if recs:
            cards_r = "".join(
                f'<a class="rec" href="{c["handle"]}.html">'
                f'<img src="../images/{esc(c["img"])}" loading="lazy" onerror="this.style.opacity=0">'
                f'<div class="rn">{esc(c["title"])}</div>'
                + (f'<div class="rp">{fmt_price(c["price"])}</div>' if c["price"] is not None
                   else '<div class="rp ask">Consultar</div>')
                + '</a>' for c in recs)
            recs_html = f'<div class="recs"><h2>También te puede gustar</h2><div class="rec-row">{cards_r}</div></div>'
        detail = f"""{header("../")}
<div class="crumb"><a href="../index.html">← {esc(SITE_NAME)}</a> / {esc(p['group'])} / {esc(p['sub'])}</div>
<div class="dt">
<div class="pic">{gallery_html}{thumbs}</div>
<div>
<div class="panel">
<h1>{esc(p['title'])}</h1>
{price_html}
<div class="trust">
<div><span class="em">🚚</span>Envío a<br>todo el país</div>
<div><span class="em">🤝</span>Contra entrega<br>en Sto. Dgo.</div>
<div><span class="em">✅</span>Producto<br>verificado</div>
</div>
<div class="sec">Descripción</div>
<div class="desc">{desc_html}</div>
<div class="bar">
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
        with open(f"{OUT_DIR}/producto/{p['handle']}.html", "w", encoding="utf-8") as f:
            f.write(page(f"{p['title']} — {SITE_NAME}", detail, pixel_extra=ve,
                         desc=p["body"][:150], track_sku=p["sku"]))

    # ---- 分类统计 ----
    print(f"✅ 构建完成: {len(products)} 个商品 → {OUT_DIR}/")
    for g in groups:
        subs = sorted(subs_of[g].items(), key=lambda kv: -kv[1])
        print(f"   {g}: " + ", ".join(f"{s}({n})" for s, n in subs))

if __name__ == "__main__":
    build()
