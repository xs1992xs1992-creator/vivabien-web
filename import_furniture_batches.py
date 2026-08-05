#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性脚本：把 design-previews 里两批已审核的家具/灯具图上架到 data/products.csv
- 批次A: previous-30-products-review.html (producto_330–359) → 合并重复组 → 26 个商品
- 批次B: latest-15-products-review.html  (producto_360–374) → 合并重复组 → 10 个商品
规则：
- 价格只搬运审核页人工确认值，绝不估算
- 重复图合并成同一商品的多图（主图 + _2.._N 补充图）
- 图片统一转成 1000×1000 白底居中（不裁切商品）
- 描述留空 → build.py 自动用标题，不编造参数
- 已存在同名商品则跳过，不覆盖
用法: cd ~/vivabien-web && python3 import_furniture_batches.py [--dry-run]
"""
import csv, os, re, sys, json, uuid, unicodedata, subprocess
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(ROOT, "data/products.csv")
IMG_DIR = os.path.join(ROOT, "images")
PREV = os.path.join(ROOT, "design-previews")
DRY = "--dry-run" in sys.argv

# 审核页 cat → 网站 Type（沿用现有 12 个类目，不新建）
CAT_MAP = {
    "tables": "Decoración del Hogar",
    "kids": "Juguetes y Juegos",
    "lighting": "Electrónicos y Tecnología",
    "Iluminación": "Electrónicos y Tecnología",
    "Dormitorio": "Decoración del Hogar",
    "Organización": "Decoración del Hogar",
    "Cocina": "Cocina y Hogar",
    "Oficina": "Papelería y Oficina",
}
# 儿童桌椅归玩具类不合适 → 单独指定
TITLE_OVERRIDE = [
    (r"escritorio infantil|mesa infantil", "Decoración del Hogar"),
    (r"ventilador de techo", "Electrónicos y Tecnología"),
]

def extract(fname):
    """从审核页 HTML 里取 items 数组（JS 对象字面量 → 用 node 转 JSON）"""
    path = os.path.join(PREV, fname)
    js = f"const fs=require('fs');const t=fs.readFileSync({json.dumps(path)},'utf8');" \
         "const d=eval(t.match(/items\\s*=\\s*(\\[[\\s\\S]*?\\]);/)[1]);console.log(JSON.stringify(d));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)

def slugify(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60] or "producto"

def dup_key(x):
    """同一商品的判定：审核页写明的重复组，或标题去掉 '· 视角' 后缀相同"""
    g = (x.get("group") or "").strip()
    if "重复" in g or "同款" in g:
        return "G:" + g
    base = re.split(r"\s*·\s*", x["title"])[0].strip().lower()
    # 批次B：同名不同视角（壁架4张、橱柜2张）合并；颜色/角色不同则算不同商品
    if re.search(r"vista|foto real|ambiente|frontal|lateral", x["title"], re.I):
        return "T:" + base
    if base in ("mueble auxiliar de cocina con puertas y estantes", "aparador blanco de cocina con puertas y cajones"):
        return "T:cocina-aparador"
    return "N:%s" % x["n"]

def pick_type(title, cat):
    t = title.lower()
    for pat, typ in TITLE_OVERRIDE:
        if re.search(pat, t):
            return typ
    return CAT_MAP.get(cat, "Decoración del Hogar")

def square(src, dst, size=1000):
    """转 1000×1000 白底居中，完整保留商品（不裁切）"""
    im = Image.open(src).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    canvas.save(dst, "JPEG", quality=88, optimize=True)

def main():
    # 批次B(360–374) 之前已由另一会话以变体方式上架（LC050-* 系列），
    # 核对后只有 producto_360 六边形LED灯漏掉 → ONLY_N 精确补这一个
    batches = [("previous-30-products-review.html", "latest30", "批次A 家具/灯具", None),
               ("latest-15-products-review.html", "latest15", "批次B 补漏", {360})]
    rows = list(csv.reader(open(CSV_PATH, encoding="utf-8-sig")))
    header, ncol = rows[0], len(rows[0])
    idx = {n.strip(): i for i, n in enumerate(header)}
    existing_titles = {r[idx["Title"]].strip().lower() for r in rows[1:] if len(r) == ncol}

    new_rows, log, n_img = [], [], 0
    for fname, assets, label, only_n in batches:
        items = extract(fname)
        if only_n:
            items = [x for x in items if x["n"] in only_n]
        groups = {}
        for x in items:
            groups.setdefault(dup_key(x), []).append(x)
        log.append(f"\n=== {label}: {len(items)} 张图 → {len(groups)} 个商品 ===")
        for key, members in groups.items():
            head = members[0]
            title = re.split(r"\s*·\s*(Vista|Foto real|Ambiente)", head["title"])[0].strip()
            if title.lower() in existing_titles:
                log.append(f"  ⏭ 已存在，跳过: {title[:44]}")
                continue
            existing_titles.add(title.lower())
            sku = "VB" + uuid.uuid4().hex[:8].upper()
            handle = slugify(title)
            typ = pick_type(title, head.get("cat", ""))
            main_img = f"{sku}.jpg"
            # 主图 + 补充图
            for i, m in enumerate(members):
                src = os.path.join(PREV, "assets", assets, f"producto_{m['n']}.jpg")
                if not os.path.isfile(src):
                    log.append(f"  ⚠️ 缺图 producto_{m['n']}.jpg"); continue
                dst = os.path.join(IMG_DIR, main_img if i == 0 else f"{sku}_{i+1}.jpg")
                if not DRY:
                    square(src, dst)
                n_img += 1
            r = [""] * ncol
            r[idx["Handle"]] = handle
            r[idx["Title"]] = title
            r[idx["Body (HTML)"]] = ""            # 留空 → 前端自动用标题，不编造参数
            r[idx["Vendor"]] = "VivaBien"
            r[idx["Type"]] = typ
            r[idx["Published"]] = "TRUE"
            r[idx["Variant SKU"]] = sku
            r[idx["Variant Price"]] = f"{head['price']:.2f}"
            r[idx["Image Src"]] = main_img
            if "categoria_es" in idx: r[idx["categoria_es"]] = typ
            if "Canal" in idx: r[idx["Canal"]] = "Shopify"
            if "notas" in idx:
                r[idx["notas"]] = f"审核页上架 {fname} #{'+#'.join(str(m['n']) for m in members)}"
            new_rows.append(r)
            tag = f" [{len(members)}图]" if len(members) > 1 else ""
            log.append(f"  + RD${head['price']:>6,} | {title[:46]:<46} | {typ}{tag}")

    print("\n".join(log))
    print(f"\n合计新增 {len(new_rows)} 个商品，处理图片 {n_img} 张")
    if DRY:
        print("（dry-run，未写入）"); return
    rows.extend(new_rows)
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    chk = list(csv.reader(open(CSV_PATH, encoding="utf-8-sig")))
    assert all(len(r) == ncol for r in chk), "列数校验失败"
    print(f"✅ 已写入 data/products.csv：{len(rows)-len(new_rows)} → {len(chk)} 行，{ncol} 列结构完整")

if __name__ == "__main__":
    main()
