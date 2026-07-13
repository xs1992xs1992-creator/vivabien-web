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
SITE_VERSION = "ux2-20260713"

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
                price=r.get("Variant Price", ""), img=r.get("Image Src", ""),
                inventory=r.get("Variant Inventory Qty", ""))

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
    products.sort(key=lambda p: (p["price"] is None, p["group"], p["sub"]))
    return products

def fmt_price(v):
    return "RD$ {:,.0f}".format(v) if v is not None else "Consultar precio"

def esc(s):
    return html.escape(s, quote=True)

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
/* 搜索/分类结果模式 */
.home-promo.hidden{display:none}
.results-head{display:none;align-items:flex-start;justify-content:space-between;gap:12px;margin:18px 0 12px}
.results-head.show{display:flex}
.results-head h2{font-size:19px;line-height:1.25;font-weight:800}
.results-head p{font-size:12px;color:#8a93a2;margin-top:4px}
.results-actions{display:flex;gap:7px;flex:none}
.result-btn,.sort-select{height:38px;border:1.5px solid #DDE5F0;border-radius:10px;background:#fff;color:#344154;font-weight:700;font-size:12px;padding:0 11px;cursor:pointer}
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
.buy-facts{display:grid;gap:8px;margin:-4px 0 18px}
.buy-fact{display:flex;align-items:flex-start;gap:9px;background:#F7F9FD;border:1px solid #E8EDF5;border-radius:12px;padding:10px 12px;font-size:12px;line-height:1.45;color:#435066}
.buy-fact b{display:block;color:#16202E;margin-bottom:1px}
.stock-ok{color:#157A4E}.stock-check{color:#9A6700}
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
.fld.invalid input,.fld.invalid textarea,.fld.invalid select{border-color:#E44D4D;background:#FFF8F8}
.fld .err-msg{display:none;color:#C73535;font-size:10.5px;font-weight:700;margin-top:4px}
.fld.invalid .err-msg{display:block}
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
.ship-quote{background:#EEF7FF;border:1px solid #CFE2F7;border-radius:13px;padding:11px 12px;margin:8px 0 10px;display:grid;grid-template-columns:1fr auto;gap:4px 12px}
.ship-quote span{font-size:11px;color:#5f7186;font-weight:700}.ship-quote b{font-size:14px}.ship-quote small{grid-column:1/-1;color:#68758a;font-size:10.5px}
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
 var a=get('vb_attr',{}),has=false;keys.forEach(function(k){if(q.get(k)){a[k]=q.get(k);has=true}});if(has)put('vb_attr',a);
 var ss=get('vb_session',{});if(!ss.id||now-(ss.last||0)>1800000)ss={id:'s-'+(crypto.randomUUID?crypto.randomUUID():now+'-'+Math.random()),last:now};ss.last=now;put('vb_session',ss);
 var dev=/Mobi|Android|iPhone/i.test(navigator.userAgent)?'mobile':(/iPad|Tablet/i.test(navigator.userAgent)?'tablet':'desktop'),last=Date.now(),sent={};
 function id(){return crypto.randomUUID?crypto.randomUUID():'e-'+Date.now()+'-'+Math.random()}
 function ctx(){var p=window.VB_PAGE||{},b={event_id:id(),session_id:ss.id,path:location.pathname,device_type:dev,screen_width:screen.width,site_version:'__VERSION__',category:p.category||'',product_title:p.title||'',product_img:p.img||''};keys.forEach(function(k){b[k]=a[k]||''});return b}
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
         track_title="", track_img="", wa_float=False):
    page_ctx = json.dumps({"sku": track_sku or "", "category": track_category or "",
                           "title": track_title or "", "img": track_img or ""}, ensure_ascii=False)
    view_js = f"<script>vbTrack('view',{json.dumps(track_sku or '')})</script>"
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc[:150])}">
{FONT}
<style>{CSS}</style>
{pixel(pixel_extra)}
{CART_JS}
<script>window.VB_PAGE={page_ctx};</script>
{TRACK_JS}
</head><body>
{body}
{view_js}
{WA_FLOAT if wa_float else ""}
<footer>© {SITE_NAME} · Envíos en toda República Dominicana · Contra entrega en Gran Santo Domingo
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
<div class="fld" id="fldNom"><label>Nombre completo *</label><input id="fNom" name="name" autocomplete="name" placeholder="Tu nombre"><div class="err-msg">Escribe tu nombre.</div></div>
<div class="fld" id="fldTel"><label>Teléfono / WhatsApp *</label><input id="fTel" name="tel" autocomplete="tel" inputmode="tel" placeholder="809 000 0000"><div class="err-msg">Escribe un teléfono válido.</div>
<div class="hint">📞 Te llamaremos a este número cuando tu pedido esté llegando</div></div>
<div class="fld" id="fldProv"><label>Provincia *</label><select id="fProv" name="address-level1" autocomplete="address-level1" onchange="provUI()"></select><div class="err-msg">Selecciona la provincia.</div></div>
<div class="fld" id="sectorFld"><label>Sector / Zona *</label><select id="fSector" name="address-level2" autocomplete="address-level2" onchange="quoteShipping()"></select></div>
<div class="fld" id="cityFld" style="display:none"><label>Municipio / Ciudad *</label><input id="fCity" name="address-level2" autocomplete="address-level2" placeholder="Ej: Santiago, Moca..." onblur="quoteShipping()"><div class="err-msg">Escribe el municipio o ciudad.</div></div>
<div class="fld" id="fldDir"><label>Dirección (calle y número) *</label><textarea id="fDir" name="street-address" autocomplete="street-address" rows="2" placeholder="Calle, No., referencia"></textarea><div class="err-msg">Escribe la dirección de entrega.</div></div>
<div class="fld"><label>Nota (opcional)</label><input id="fNota" placeholder="Referencia, horario..."></div>
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
<div class="ship-quote" id="shipQuote"><span>Envío estimado</span><b id="tShip">Selecciona tu provincia</b><small id="shipEta">Verás el costo y el tiempo antes de confirmar.</small></div>
<div class="gt"><span id="totalLabel">Total</span> <span id="tTot">RD$ 0</span></div>
<button class="btn-conf" id="btnConf" onclick="confirmar()">🛡️ Confirmar pedido</button>
<div class="sub-note">Al confirmar, tu pedido queda registrado. Después puedes continuar por WhatsApp si lo deseas.</div>
</div>
</div>

<div class="ok" id="okScreen">
<div class="ck">✓</div>
<h2>¡Pedido confirmado!</h2>
<p>Tu pedido <b id="okId"></b> quedó registrado correctamente.<br>Te contactaremos para coordinar la entrega.</p>
<div class="ok-actions"><a class="ok-wa" id="okWa" href="#" target="_blank">Continuar por WhatsApp</a><a class="ok-shop" href="index.html">Seguir comprando</a></div>
</div>

<script>
var WA='__WA__';
var COUPON=null; // {code,kind,value} —— 已应用的优惠券
var SHIPPING={fee:0,fee_min:0,fee_max:0,zone:'',delivery:'',cod_allowed:false,ready:false};
function money(v){return 'RD$ '+Math.round(v).toLocaleString('en-US')}
function subtotal(){return vbCart().reduce(function(a,it){return a+it.price*it.qty},0)}
function calcDiscount(sub){
 if(!COUPON)return 0;
 var d=COUPON.kind==='percent'?sub*COUPON.value/100:COUPON.value;
 return Math.min(d,sub);
}
function paintTotals(){
 var sub=subtotal(),disc=calcDiscount(sub),productTotal=sub-disc;
 var shipMin=SHIPPING.ready?Number(SHIPPING.fee_min||SHIPPING.fee||0):0;
 var shipMax=SHIPPING.ready?Number(SHIPPING.fee_max||SHIPPING.fee||0):0;
 var ranged=SHIPPING.ready&&shipMax>shipMin,totMin=productTotal+shipMin,totMax=productTotal+shipMax;
 document.getElementById('tSub').textContent=money(sub);
 var dl=document.getElementById('discLn');
 if(disc>0){dl.style.display='flex';
  document.getElementById('tDisc').textContent='- '+money(disc);
  document.getElementById('discCode').textContent=COUPON.code;
 }else{dl.style.display='none';}
 document.getElementById('tShip').textContent=SHIPPING.ready?(ranged?money(shipMin)+' – '+money(shipMax):money(shipMin)):'Selecciona tu provincia';
 document.getElementById('shipEta').textContent=SHIPPING.ready?SHIPPING.delivery+' · Costo estimado según la zona.':'Verás el costo y el tiempo antes de confirmar.';
 document.getElementById('totalLabel').textContent=ranged?'Total estimado':'Total';
 document.getElementById('tTot').textContent=ranged?money(totMin)+' – '+money(totMax):money(totMin);
 document.getElementById('btnConf').textContent=ranged?'🛡️ Confirmar pedido · '+money(productTotal)+' + envío':'🛡️ Confirmar pedido · '+money(totMin);
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
function qty(i,d){var c=vbCart();c[i].qty+=d;if(c[i].qty<1)c[i].qty=1;vbSave(c);render();
 if(d>0){var it=c[i];try{vbTrack('addcart',it.sku,{qty:it.qty,price:it.price,
  cart_total:c.reduce(function(a,x){return a+x.price*x.qty},0),product_title:it.title,product_img:it.img})}catch(e){}}}
function rm(i){var c=vbCart();c.splice(i,1);vbSave(c);render()}
function payUI(){
 var t=document.querySelector('input[name=pay]:checked').value;
 document.getElementById('lCod').classList.toggle('on',t==='cod');
 document.getElementById('lTra').classList.toggle('on',t==='transfer');
 document.getElementById('bankPanel').classList.toggle('show',t==='transfer');
}
var PROVS=["","Distrito Nacional (Santo Domingo)","Santo Domingo (provincia)","Santiago","La Altagracia","La Vega","San Cristóbal","Puerto Plata","Duarte","San Pedro de Macorís","La Romana","Espaillat","Azua","Barahona","Monseñor Nouel","Sánchez Ramírez","Peravia","Valverde","Monte Plata","Hato Mayor","El Seibo","Samaná","María Trinidad Sánchez","Hermanas Mirabal","Bahoruco","Independencia","Elías Piña","San Juan","Dajabón","Santiago Rodríguez","Monte Cristi","Pedernales","San José de Ocoa"];
var DN_SECTORES=["Distrito Nacional (centro)","Naco","Piantini","Bella Vista","Gazcue","Los Prados","Arroyo Hondo","Los Ríos","El Millón","Evaristo Morales","Villa Consuelo","Cristo Rey","Otro sector del Distrito Nacional"];
var SD_SECTORES=["Santo Domingo Este","Santo Domingo Norte","Santo Domingo Oeste","Otro municipio de Santo Domingo"];
function fillSel(id,arr){var s=document.getElementById(id);
 s.innerHTML='';arr.forEach(function(x){var o=document.createElement('option');o.value=x;o.textContent=x||(id==='fProv'?'Selecciona una provincia':'Selecciona una zona');if(!x)o.disabled=true;o.selected=!x;s.appendChild(o)});}
function provUI(){
 var prov=document.getElementById('fProv').value,isDN=prov.indexOf('Distrito Nacional')===0,isSDP=prov.indexOf('Santo Domingo (provincia)')===0,isMetro=isDN||isSDP;
 document.getElementById('sectorFld').style.display=isMetro?'block':'none';
 document.getElementById('cityFld').style.display=isMetro?'none':'block';
 if(isDN)fillSel('fSector',DN_SECTORES);else if(isSDP)fillSel('fSector',SD_SECTORES);
 SHIPPING={fee:0,fee_min:0,fee_max:0,zone:'',delivery:'',cod_allowed:false,ready:false};quoteShipping();
}
async function quoteShipping(){
 var prov=document.getElementById('fProv').value;if(!prov){paintTotals();return}
 var metro=document.getElementById('sectorFld').style.display!=='none';
 var zone=metro?document.getElementById('fSector').value:document.getElementById('fCity').value.trim();
 try{var r=await fetch('__API__/api/shipping/quote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({province:prov,zone:zone})});var d=await r.json();if(!r.ok||!d.ok)throw new Error();SHIPPING=d;
  var cod=document.querySelector('input[name=pay][value=cod]'),tra=document.querySelector('input[name=pay][value=transfer]');
  cod.disabled=!d.cod_allowed;document.getElementById('lCod').style.display=d.cod_allowed?'flex':'none';document.getElementById('codNote').classList.toggle('show',!d.cod_allowed);
  if(!d.cod_allowed)tra.checked=true;payUI();paintTotals();
  try{vbTrack('shipping_quote','',{shipping_fee:d.fee,shipping_zone:d.zone,delivery_estimate:d.delivery})}catch(e){}
 }catch(e){SHIPPING={fee:0,fee_min:0,fee_max:0,zone:'',delivery:'No pudimos calcular el envío. Intenta de nuevo.',cod_allowed:false,ready:false};paintTotals()}}
fillSel('fProv',PROVS);fillSel('fSector',[]);paintTotals();
function fieldState(id,bad){var x=document.getElementById(id);if(x)x.classList.toggle('invalid',!!bad)}
async function confirmar(){
 var c=vbCart();if(!c.length)return;
 var nom=document.getElementById('fNom').value.trim(),
     tel=document.getElementById('fTel').value.trim(),
     dir=document.getElementById('fDir').value.trim(),
     nota=document.getElementById('fNota').value.trim();
 var prov=document.getElementById('fProv').value;
 var metro=document.getElementById('sectorFld').style.display!=='none';
 var zona=metro?document.getElementById('fSector').value:document.getElementById('fCity').value.trim();
 fieldState('fldNom',!nom);fieldState('fldTel',tel.replace(/\D/g,'').length<10);fieldState('fldProv',!prov);fieldState('cityFld',!metro&&!zona);fieldState('fldDir',!dir);
 if(!nom||tel.replace(/\D/g,'').length<10||!prov||!zona||!dir){document.querySelector('.fld.invalid').scrollIntoView({behavior:'smooth',block:'center'});return;}
 if(!SHIPPING.ready){await quoteShipping();if(!SHIPPING.ready){alert('No pudimos calcular el envío. Intenta nuevamente.');return;}}
 var loc=prov+' · '+zona;
 var pay=document.querySelector('input[name=pay]:checked').value;
 var oid='VB-'+Math.random().toString(36).slice(2,7).toUpperCase();
 var sub=0,lines=c.map(function(it){sub+=it.price*it.qty;
   return it.qty+'x '+it.title+' ('+it.sku+') — '+money(it.price*it.qty)});
 var disc=calcDiscount(sub),productTotal=sub-disc;
 var shipMin=Number(SHIPPING.fee_min||SHIPPING.fee||0),shipMax=Number(SHIPPING.fee_max||SHIPPING.fee||0);
 var ranged=shipMax>shipMin,totMin=productTotal+shipMin,totMax=productTotal+shipMax;
 var shippingText=ranged?money(shipMin)+' – '+money(shipMax):money(shipMin);
 var totalText=ranged?money(totMin)+' – '+money(totMax):money(totMin);
 var msg='🛒 *Pedido '+oid+'*\\n'+lines.join('\\n')
  +(disc>0?'\\n——\\nSubtotal: '+money(sub)+'\\n🏷️ Cupón '+COUPON.code+': - '+money(disc):'')
  +'\\n🚚 Envío estimado: '+shippingText+' ('+SHIPPING.delivery+')'
  +'\\n*Total estimado: '+totalText+'*\\n——\\n👤 '+nom+'\\n📞 '+tel+'\\n📍 '+loc+'\\n🏠 '+dir
  +(nota?'\\n📝 '+nota:'')
  +'\\n💳 Pago: '+(pay==='cod'?'Contra entrega (efectivo)':'Transferencia bancaria — enviaré el comprobante')
  +(pay==='transfer'?'\\n\\nCuentas:\\n__BANKLINES__':'');
 var btn=document.getElementById('btnConf');
 btn.disabled=true;btn.textContent='Guardando pedido...';
 try{
  var orderRes=await fetch('__API__/api/order',{method:'POST',credentials:'include',
   headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:oid,
    customer_name:nom,phone:tel,province:prov,zone:zona,address:dir,note:nota,
    payment_method:pay,shipping_zone:SHIPPING.zone,shipping_fee:ranged?0:shipMin,
    shipping_fee_min:shipMin,shipping_fee_max:shipMax,delivery_estimate:SHIPPING.delivery,
    subtotal:sub,discount:disc,total:ranged?productTotal:totMin,total_min:totMin,total_max:totMax,
    coupon_code:COUPON?COUPON.code:'',tracking:vbContext(),items:c.map(function(it){return {
     sku:it.sku,title:it.title,image:it.img,unit_price:it.price,quantity:it.qty}})})});
  var orderData=await orderRes.json();
  if(!orderRes.ok||!orderData.ok)throw new Error(orderData.error||'No se pudo guardar el pedido');
 }catch(e){btn.disabled=false;paintTotals();
  alert('No pudimos guardar tu pedido. Revisa tu conexión e intenta de nuevo.');return;}
 try{fbq('track','Purchase',{value:productTotal,currency:'DOP',content_type:'product',num_items:c.reduce(function(a,b){return a+b.qty},0)})}catch(e){}
    vbTrack('checkout','',{coupon:COUPON?COUPON.code:''});
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
render();payUI();
try{var autoCoupon=new URLSearchParams(location.search).get('coupon')||localStorage.getItem('vb_campaign_coupon');
 if(autoCoupon){document.getElementById('cpnCode').value=autoCoupon.toUpperCase();setTimeout(applyCoupon,80)}}catch(e){}
</script>"""
    body = (body.replace("__BANKS__", banks_html).replace("__WA__", WHATSAPP)
                .replace("__BANKLINES__", bank_lines).replace("__API__", API_BASE))
    return page(f"Tu compra — {SITE_NAME}", body,
                pixel_extra="fbq('track','InitiateCheckout');",
                desc="Carrito de compras VivaBien — contra entrega en Gran Santo Domingo o transferencia nacional.")

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

def modern_home_body(feats, tiles, cat_sections, group_options, subs_json, cards, total):
    """轻量首页：首批 24 个商品 + 外部索引搜索、筛选和渐进加载。"""
    body = header() + """
<div class="wrap">
<div class="search"><svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input id="q" type="search" placeholder="¿Qué buscas hoy? Ej: audífonos, espejo…" autocomplete="off"><button class="clr" id="qClr" aria-label="Borrar">✕</button></div>
<div class="recent" id="recentRow"></div>
<div class="home-promo" id="homePromo"><div class="hero"><h1>Compra fácil, paga seguro</h1><div class="sub">🚚 Envíos a todo el país · 🤝 Contra entrega en Gran Santo Domingo</div></div>__FEATS__<div class="cat-hd"><b>Categorías</b><button class="cat-open" id="catOpen">Ver todas →</button></div><div class="cattiles" id="cattiles">__TILES__</div></div>
<div class="results-head" id="resultsHead"><div><h2 id="resultsTitle">Productos</h2><p id="resultsSummary"></p></div><div class="results-actions"><button class="result-btn" id="filterOpen">Filtrar</button><select class="sort-select" id="sort"><option value="default">Relevancia</option><option value="price-asc">Precio: menor</option><option value="price-desc">Precio: mayor</option><option value="name">Nombre A-Z</option></select></div></div>
<div class="filter-panel" id="filterPanel"><div class="filter-grid"><div><label>Categoría</label><select id="filterGroup">__GROUP_OPTIONS__</select></div><div><label>Subcategoría</label><select id="filterSub"><option value="*">Todas</option></select></div><div><label>Precio mínimo RD$</label><input id="priceMin" inputmode="numeric" type="number" min="0" placeholder="0"></div><div><label>Precio máximo RD$</label><input id="priceMax" inputmode="numeric" type="number" min="0" placeholder="Sin límite"></div></div><div class="filter-foot"><button class="filter-reset" id="filterReset">Limpiar</button><button class="filter-apply" id="filterApply">Ver resultados</button></div></div>
<div class="count"><span id="n">__COUNT__</span> productos</div><div class="grid" id="grid">__CARDS__</div><button class="load-more show" id="loadMore">Ver más productos</button></div>
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
function card(p){var price=p.price==null?'<span class="ask">Consultar</span>':'<b>RD$ '+Math.round(p.price).toLocaleString('en-US')+'</b>';var add=p.price==null?'':'<button class="card-add" type="button" aria-label="Agregar al carrito" data-sku="'+h(p.sku)+'" data-handle="'+h(p.handle)+'" data-title="'+h(p.title)+'" data-price="'+p.price+'" data-img="'+h(p.img)+'" onclick="vbCardAdd(event,this)">__BAG__</button>';return '<article class="card"><a class="card-link" href="producto/'+encodeURIComponent(p.handle)+'.html"><div class="imgbox"><img src="images/'+encodeURIComponent(p.img)+'" alt="'+h(p.title)+'" loading="lazy" onerror="this.style.display=\\'none\\'"><span class="badge">'+h(p.sub)+'</span></div><div class="info"><div class="nm">'+h(p.title)+'</div><div class="pr">'+price+'</div></div></a>'+add+'</article>'}
function apply(reset){if(!all.length)return;var words=snorm(cur.q).split(/\s+/).filter(Boolean);filtered=all.filter(function(p){if(cur.g!=='*'&&p.group!==cur.g)return false;if(cur.s!=='*'&&p.sub!==cur.s)return false;if(words.length&&!words.every(function(w){return matchWord(p,w)}))return false;if(cur.min!=null&&(p.price==null||p.price<cur.min))return false;if(cur.max!=null&&(p.price==null||p.price>cur.max))return false;return true});filtered.sort(function(a,b){if(cur.sort==='price-asc')return (a.price==null?1e15:a.price)-(b.price==null?1e15:b.price);if(cur.sort==='price-desc')return (b.price==null?-1:b.price)-(a.price==null?-1:a.price);if(cur.sort==='name')return a.title.localeCompare(b.title,'es');return a.i-b.i});var mode=!!cur.q||cur.g!=='*'||cur.s!=='*'||cur.min!=null||cur.max!=null||cur.sort!=='default';document.getElementById('homePromo').classList.toggle('hidden',mode);document.getElementById('resultsHead').classList.toggle('show',mode);document.getElementById('n').textContent=filtered.length;var label=cur.q?'Resultados para “'+cur.q+'”':(cur.s!=='*'?cur.s:(cur.g!=='*'?cur.g:'Productos'));document.getElementById('resultsTitle').textContent=label;document.getElementById('resultsSummary').textContent=filtered.length+' productos encontrados';if(reset){shown=0;grid.innerHTML='';showNext()}}
function showNext(){if(!all.length)return;if(!filtered.length){grid.innerHTML='<div class="no-results"><b>No encontramos productos</b>Prueba otra palabra o elimina algún filtro.</div>';document.getElementById('loadMore').classList.remove('show');return}var next=filtered.slice(shown,shown+BATCH);grid.insertAdjacentHTML('beforeend',next.map(card).join(''));shown+=next.length;document.getElementById('loadMore').classList.toggle('show',shown<filtered.length)}
function updateSubs(g,selected){var s=document.getElementById('filterSub'),vals=g==='*'?[]:(SUBS[g]||[]);s.innerHTML='<option value="*">Todas</option>'+vals.map(function(x){return '<option value="'+h(x)+'">'+h(x)+'</option>'}).join('');s.value=selected&&vals.indexOf(selected)>=0?selected:'*'}
function selectCategory(g,s){cur.g=g;cur.s=s||'*';document.getElementById('filterGroup').value=g;updateSubs(g,cur.s);closeCategories();apply(true);try{vbTrack('filter','',{filter_group:g,filter_sub:cur.s,result_count:filtered.length})}catch(e){}window.scrollTo({top:0,behavior:'smooth'})}
function openCategories(g){var d=document.getElementById('catDialog');d.classList.add('show');document.body.style.overflow='hidden';if(g){var x=d.querySelector('[data-section="'+CSS.escape(g)+'"]');if(x)setTimeout(function(){x.scrollIntoView({block:'start'})},60)}}
function closeCategories(){document.getElementById('catDialog').classList.remove('show');document.body.style.overflow=''}
async function loadData(){try{var r=await fetch('products-index.json');all=await r.json();apply(true)}catch(e){document.getElementById('loadMore').classList.remove('show')}}
recPaint();qEl.addEventListener('input',function(){var next=qEl.value.trim();if(!cur.q&&next){cur.g='*';cur.s='*';cur.min=null;cur.max=null;document.getElementById('filterGroup').value='*';updateSubs('*','')}cur.q=next;qClr.style.display=cur.q?'block':'none';apply(true);clearTimeout(qT);if(cur.q.length>2)qT=setTimeout(function(){try{fbq('track','Search',{search_string:cur.q});vbTrack('search','',{search_query:cur.q,result_count:filtered.length,sort_mode:cur.sort,filter_group:cur.g,filter_sub:cur.s})}catch(e){}recAdd(cur.q.toLowerCase())},900)});qClr.onclick=function(){qEl.value='';cur.q='';qClr.style.display='none';apply(true);qEl.focus()};var qp=new URLSearchParams(location.search).get('q');if(qp){qEl.value=qp;cur.q=qp;qClr.style.display='block'}if(new URLSearchParams(location.search).has('buscar'))qEl.focus();
document.getElementById('catOpen').onclick=function(){openCategories('')};document.querySelectorAll('.tile').forEach(function(t){t.onclick=function(){openCategories(t.dataset.g)}});document.querySelectorAll('.cat-section-title,.cat-sub').forEach(function(b){b.onclick=function(){selectCategory(b.dataset.g,b.dataset.s)}});document.getElementById('catClose').onclick=closeCategories;document.getElementById('catDialog').onclick=function(e){if(e.target===this)closeCategories()};addEventListener('keydown',function(e){if(e.key==='Escape')closeCategories()});
document.getElementById('filterOpen').onclick=function(){document.getElementById('filterPanel').classList.toggle('show')};document.getElementById('filterGroup').onchange=function(){updateSubs(this.value,'')};document.getElementById('filterApply').onclick=function(){cur.g=document.getElementById('filterGroup').value;cur.s=document.getElementById('filterSub').value;var a=document.getElementById('priceMin').value,b=document.getElementById('priceMax').value;cur.min=a===''?null:Number(a);cur.max=b===''?null:Number(b);document.getElementById('filterPanel').classList.remove('show');apply(true);try{vbTrack('filter','',{filter_group:cur.g,filter_sub:cur.s,result_count:filtered.length,sort_mode:cur.sort})}catch(e){}};document.getElementById('filterReset').onclick=function(){cur.g='*';cur.s='*';cur.min=null;cur.max=null;cur.sort='default';document.getElementById('filterGroup').value='*';updateSubs('*','');document.getElementById('priceMin').value='';document.getElementById('priceMax').value='';document.getElementById('sort').value='default';apply(true)};document.getElementById('sort').onchange=function(){cur.sort=this.value;apply(true)};document.getElementById('loadMore').onclick=showNext;
var io=new IntersectionObserver(function(es){if(es[0].isIntersecting&&all.length&&shown<filtered.length)showNext()},{rootMargin:'300px'});io.observe(document.getElementById('loadMore'));setTimeout(loadData,0);
</script>"""
    return (body.replace("__FEATS__", feats).replace("__TILES__", tiles)
            .replace("__COUNT__", str(total)).replace("__CARDS__", "".join(cards))
            .replace("__CAT_SECTIONS__", "".join(cat_sections)).replace("__GROUP_OPTIONS__", group_options)
            .replace("__SUBS__", subs_json).replace("__BAG__", BAG_SVG))

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

    # ---- 商品索引 + 首批商品卡（首页不再一次渲染 1000+ 个 DOM 节点） ----
    index_products = []
    for i, p in enumerate(products):
        search_text = " ".join((p["title"], p["sub"], p["group"], p["type"], p["body"][:360]))
        index_products.append({
            "i": i, "sku": p["sku"], "handle": p["handle"], "title": p["title"],
            "price": p["price"], "img": p["img"], "group": p["group"], "sub": p["sub"],
            "available": p.get("inventory") is not None and p["inventory"] > 0,
            "q": snorm(search_text),
        })
    with open(f"{OUT_DIR}/products-index.json", "w", encoding="utf-8") as f:
        json.dump(index_products, f, ensure_ascii=False, separators=(",", ":"))
    cards = [product_card(p) for p in products[:24]]

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
                                 cards, len(products))
    with open(f"{OUT_DIR}/index.html", "w", encoding="utf-8") as f:
        f.write(page(f"{SITE_NAME} — Tienda online RD", home_body, wa_float=True,
                     desc="Hogar, belleza, herramientas, electrónica y más. Contra entrega en Gran Santo Domingo."))

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
 var it=c.find(function(x){return x.sku===sku});
 vbTrack('addcart',sku,{qty:it.qty,price:it.price,cart_total:c.reduce(function(a,x){return a+x.price*x.qty},0),product_title:it.title,product_img:it.img});
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
{facts_html}
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
                         desc=p["body"][:150], track_sku=p["sku"], track_category=p["sub"],
                         track_title=p["title"], track_img=p["img"]))

    # ---- 分类统计 ----
    print(f"✅ 构建完成: {len(products)} 个商品 → {OUT_DIR}/")
    for g in groups:
        subs = sorted(subs_of[g].items(), key=lambda kv: -kv[1])
        print(f"   {g}: " + ", ".join(f"{s}({n})" for s, n in subs))

if __name__ == "__main__":
    build()
