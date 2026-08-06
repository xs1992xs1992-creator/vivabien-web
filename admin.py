#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VivaBien 本地商品管理后台
用法: cd ~/vivabien-web && python3 admin.py
浏览器自动打开 http://localhost:8766（公网走 Cloudflare Tunnel + Access）
功能: 改价格/标题/分类/详情描述、商品多图管理（补充图/尺寸图/替换/删除）、
     上传新商品、删商品、一键重新构建、一键发布上线（构建+git push）
数据直接读写 data/products.csv，与 build.py 共用同一数据源
"""
import csv, os, io, re, sys, json, html, uuid, shutil, subprocess, threading, webbrowser
import hmac, hashlib, secrets, time, unicodedata
import urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, unquote, quote

PORT     = int(os.environ.get("VIVABIEN_ADMIN_PORT", "8766"))
CSV_PATH = "data/products.csv"
IMG_DIR  = "images"

# 上游流水线（只读！绝不写入该目录）
UPSTREAM_DIR = os.environ.get("VIVABIEN_UPSTREAM",
                              os.path.expanduser("~/Downloads/VivaBien/output"))
UPSTREAM_CSV = os.path.join(UPSTREAM_DIR, "products.csv")
REVIEW_URL   = "https://review.vivabien.xyz"

# ---------- 边缘后端（Worker + D1）：短链 / 埋点 / 优惠券 ----------
# 后台通过共享密钥调 Worker 的 /api/admin/*。密钥要和 Worker 的 secret ADMIN_KEY 一致。
# 密钥存 worker_admin_key.txt（已加 .gitignore，不上传）。改密钥=编辑该文件+重启。
WORKER_API   = os.environ.get("VIVABIEN_WORKER", "https://vivabien.xyz")
SITE_URL     = "https://vivabien.xyz"
WKEY_FILE    = "worker_admin_key.txt"
def _load_worker_key():
    if os.path.isfile(WKEY_FILE):
        k = open(WKEY_FILE, encoding="utf-8").read().strip()
        if k: return k
    return ""
WORKER_KEY = _load_worker_key()

def worker_call(path, method="GET", payload=None):
    """调 Worker /api/admin/<path>。返回 (dict, error_str)。"""
    if not WORKER_KEY:
        return None, "未配置 Worker 密钥（worker_admin_key.txt 为空，且未部署 Worker）"
    url = WORKER_API + "/api/admin/" + path.lstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Admin-Key": WORKER_KEY, "Content-Type": "application/json",
        # 伪装成浏览器，避开 Cloudflare 机器人防护（否则 Python 请求会被 403 拦下）
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "es,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}"), None
    except urllib.error.HTTPError as e:
        try:    return json.loads(e.read().decode()), f"HTTP {e.code}"
        except Exception: return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"连接后端失败：{e}"

def admin_image_src(raw):
    """Map a catalog-relative image path to the local admin image route."""
    path = str(raw or "").replace("\\", "/").lstrip("/")
    if path.startswith("images/"):
        path = path[7:]
    if not path or any(part in {"", ".", ".."} for part in path.split("/")):
        return ""
    return "/images/" + quote(path, safe="/")

# ---------- 登录密码 ----------
# 密码存在 admin_password.txt（已加入 .gitignore，不会上传）。
# 想换密码：直接编辑那个文件，重启 admin.py，所有已登录设备都要重新登录。
PW_FILE = "admin_password.txt"
def _load_password():
    if os.path.isfile(PW_FILE):
        pw = open(PW_FILE, encoding="utf-8").read().strip()
        if pw: return pw
    pw = secrets.token_urlsafe(9)
    with open(PW_FILE, "w", encoding="utf-8") as f:
        f.write(pw + "\n")
    return pw
PASSWORD = _load_password()
_TOKEN = hmac.new(PASSWORD.encode(), b"vivabien-admin-session-v1", hashlib.sha256).hexdigest()
_fails = []  # 失败时间戳，防爆破

def check_cookie(headers):
    c = headers.get("Cookie", "")
    m = re.search(r"vbadmin=([0-9a-f]{64})", c)
    return bool(m and hmac.compare_digest(m.group(1), _TOKEN))

def try_login(pw):
    now = time.time()
    recent = [t for t in _fails if now - t < 300]
    _fails[:] = recent
    if len(recent) >= 10:
        return None  # 5分钟内错10次，锁定
    if hmac.compare_digest(pw.strip(), PASSWORD):
        return _TOKEN
    _fails.append(now)
    time.sleep(1)
    return False

LOGIN_HTML = """<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VivaBien 后台登录</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:linear-gradient(150deg,#2563D9,#1A47A6 55%,#12336F);display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border-radius:22px;padding:34px 28px;width:min(360px,92vw);text-align:center;box-shadow:0 24px 70px rgba(10,25,60,.45)}
.badge{width:58px;height:58px;border-radius:18px;background:linear-gradient(135deg,#2563D9,#3b82f6);color:#fff;font-size:28px;font-weight:800;display:flex;align-items:center;justify-content:center;margin:0 auto 14px}
.box h2{font-size:19px;margin-bottom:6px}.box p{font-size:13px;color:#8a93a2;margin-bottom:18px}
input{width:100%;border:1.5px solid #E5EAF2;border-radius:12px;padding:13px;font-size:15px;margin-bottom:12px;text-align:center}
button{width:100%;background:#2563D9;color:#fff;border:0;border-radius:12px;padding:13px;font-weight:700;font-size:15px;cursor:pointer}
.err{color:#c0392b;font-size:13px;margin-bottom:10px;font-weight:600}</style></head><body>
<form class="box" method="POST" action="/login">
<div class="badge">V</div>
<h2>VivaBien 商品管理</h2><p>请输入后台密码</p>
__ERR__
<input type="password" name="pw" id="pw" autofocus autocomplete="current-password">
<label style="display:flex;align-items:center;gap:6px;font-size:13px;color:#5a6577;margin-bottom:12px;justify-content:center;cursor:pointer">
<input type="checkbox" style="width:auto;margin:0" onchange="document.getElementById('pw').type=this.checked?'text':'password'"> 显示密码
</label>
<button>登录</button>
</form></body></html>"""

# ---------- CSV 读写（兼容 14/16/17 字段行） ----------
IDX = {17: dict(handle=0, title=1, body=2, type=4, published=6, sku=7, price=8, img=10),
       16: dict(handle=0, title=1, body=2, type=4, published=6, sku=7, price=8, img=10),
       14: dict(handle=0, title=1, body=2, type=4, published=5, sku=6, price=7, img=9)}

def load_rows():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.reader(f))

def save_rows(rows):
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)

def row_get(r, key):
    m = IDX.get(len(r))
    return r[m[key]] if m else None

def row_set(r, key, val):
    m = IDX.get(len(r))
    if m: r[m[key]] = val

def products():
    seen, out = set(), []
    for r in load_rows()[1:]:
        m = IDX.get(len(r))
        if not m: continue
        h = r[m["handle"]].strip()
        t = r[m["title"]].strip()
        if not h or not t or h in seen: continue
        seen.add(h)
        out.append(dict(handle=h, title=t, type=r[m["type"]], body=r[m["body"]],
                        price=r[m["price"]], img=r[m["img"]], sku=r[m["sku"]]))
    return out

def update_product(handle, fields):
    """fields: dict 可含 title/price/type/body"""
    rows = load_rows()
    n = 0
    for r in rows[1:]:
        if row_get(r, "handle") == handle:
            for k, v in fields.items():
                row_set(r, k, v)
            n += 1
    if n: save_rows(rows)
    return n

def delete_product(handle):
    rows = load_rows()
    # 删图片文件
    for r in rows[1:]:
        if row_get(r, "handle") == handle:
            img = (row_get(r, "img") or "").strip()
            if img:
                for f in sku_photos_by_img(img):
                    try: os.remove(os.path.join(IMG_DIR, f))
                    except OSError: pass
            break
    kept = [rows[0]] + [r for r in rows[1:] if row_get(r, "handle") != handle]
    n = len(rows) - len(kept)
    if n: save_rows(kept)
    return n

def add_product(title, price, ptype, img_bytes, img_ext, body="", zh=""):
    sku = "VB" + uuid.uuid4().hex[:8].upper()
    handle = sku.lower()
    fname = f"{sku}{img_ext}"
    os.makedirs(IMG_DIR, exist_ok=True)
    with open(os.path.join(IMG_DIR, fname), "wb") as f:
        f.write(img_bytes)
    rows = load_rows()
    ncol = len(rows[0]) if rows and len(rows[0]) in IDX else 17
    r = [""] * ncol
    for k, v in dict(handle=handle, title=title, body=(body.strip() or title), type=ptype,
                     published="TRUE", sku=sku, price=price, img=fname).items():
        r[IDX[ncol][k]] = v
    if ncol == 17 and zh.strip():
        r[11] = zh.strip()          # nombre_zh 列
    rows.append(r)
    save_rows(rows)
    return handle

# ---------- 商品图片管理 ----------
SLOT_SUFFIX = {"dim": "_dim", "scene": "_scene"}
SLOT_LABEL  = {"main": "主图", "dim": "尺寸图", "scene": "场景图"}
PHOTO_LIMIT = 10

def sku_photos_by_img(img):
    """按主图文件名列出该商品全部图片文件"""
    stem = img[:-4] if img.lower().endswith(".jpg") else img
    out = []
    if os.path.isfile(os.path.join(IMG_DIR, img)):
        out.append(img)
    for suf in ("_scene.jpg", "_dim.jpg"):
        f = stem + suf
        if os.path.isfile(os.path.join(IMG_DIR, f)): out.append(f)
    # 兼容旧的 _2..._9 命名，也允许后台以后使用到第 10 张。
    for f in sorted(os.listdir(IMG_DIR) if os.path.isdir(IMG_DIR) else []):
        if re.fullmatch(re.escape(stem) + r"_\d+\.jpg", f, re.I):
            if f not in out: out.append(f)
    return out

def photo_label(img, fname):
    stem = img[:-4] if img.lower().endswith(".jpg") else img
    if fname == img: return "主图"
    if fname == stem + "_dim.jpg": return "尺寸图"
    if fname == stem + "_scene.jpg": return "场景图"
    return "补充图"

def safe_photo_name(img, fname):
    """校验 fname 属于该商品，防路径穿越"""
    return fname in sku_photos_by_img(img) and "/" not in fname and ".." not in fname

def photo_add(img, slot, data):
    stem = img[:-4] if img.lower().endswith(".jpg") else img
    if slot == "main":
        fname = img
    elif slot in SLOT_SUFFIX:
        fname = stem + SLOT_SUFFIX[slot] + ".jpg"
    else:  # extra: 找空槽位
        fname = None
        if len(sku_photos_by_img(img)) >= PHOTO_LIMIT:
            raise ValueError(f"每个商品最多 {PHOTO_LIMIT} 张图片")
        for i in range(2, PHOTO_LIMIT + 1):
            c = f"{stem}_{i}.jpg"
            if not os.path.isfile(os.path.join(IMG_DIR, c)):
                fname = c; break
        if not fname: raise ValueError(f"每个商品最多 {PHOTO_LIMIT} 张图片")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("图片文件太大，请压缩后再上传（最大 15 MB）")
    with open(os.path.join(IMG_DIR, fname), "wb") as f:
        f.write(data)
    return fname

def photo_replace(img, fname, data):
    """用新图片覆盖商品当前画廊中的指定图片。"""
    if not safe_photo_name(img, fname):
        raise ValueError("无效图片")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("图片文件太大，请压缩后再上传（最大 15 MB）")
    with open(os.path.join(IMG_DIR, fname), "wb") as f:
        f.write(data)
    return fname

# ---------- 流水线导入（上游只读） ----------
def upstream_read():
    """读上游 CSV，返回 (主行列表, 按Handle分组的多图附加行)；上游不存在返回 None"""
    if not os.path.isfile(UPSTREAM_CSV):
        return None
    with open(UPSTREAM_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    mains, extra = [], {}
    for r in rows:
        sku = (r.get("Variant SKU") or "").strip()
        h = (r.get("Handle") or "").strip()
        if sku and (r.get("Title") or "").strip():
            mains.append(r)
        elif h and (r.get("Image Src") or "").strip():
            extra.setdefault(h, []).append(r)   # 家具多图附加行
    return mains, extra

def upstream_estado(sku):
    p = os.path.join(UPSTREAM_DIR, f"{sku}.json")
    if not os.path.isfile(p):
        p = os.path.join(UPSTREAM_DIR, f"{sku.upper()}.json")
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("estado") or "").strip()
    except Exception:
        return ""

def website_skus():
    out = set()
    for r in load_rows()[1:]:
        if IDX.get(len(r)):
            s = (row_get(r, "sku") or "").strip().upper()
            if s: out.add(s)
    return out

def import_candidates():
    """上游已完成(finalizado/confirmado)且本库没有的商品"""
    up = upstream_read()
    if up is None:
        return None
    mains, extra = up
    have = website_skus()
    out = []
    for r in mains:
        sku_raw = r["Variant SKU"].strip()
        sku = sku_raw.upper()
        if sku in have:
            continue                      # 已存在一律跳过，绝不覆盖
        est = upstream_estado(sku_raw)
        if est not in ("finalizado", "confirmado"):
            continue                      # 只要生产完成的
        img = (r.get("Image Src") or "").strip() or f"{sku}.jpg"
        warns = []
        if not (r.get("Variant Price") or "").strip(): warns.append("缺价格")
        if not (r.get("Type") or "").strip(): warns.append("缺类目")
        if re.search(r"[一-鿿]", r.get("Body (HTML)") or ""): warns.append("描述含中文")
        if not os.path.isfile(os.path.join(UPSTREAM_DIR, img)): warns.append("缺主图")
        out.append(dict(row=r, sku=sku, img=img, estado=est, warns=warns,
                        extra=extra.get((r.get("Handle") or "").strip(), [])))
    return out

def do_import(skus):
    """把选中的上游商品追加进本库。只增不改不删；写入前后双重校验。"""
    cands = import_candidates() or []
    bysku = {c["sku"]: c for c in cands}
    rows = load_rows()
    header, ncol = rows[0], len(rows[0])
    if ncol not in IDX:
        raise ValueError(f"本库表头 {ncol} 列，不在支持范围，中止")
    name_idx = {n.strip(): i for i, n in enumerate(header)}
    before = len(rows)

    def mk(rdict):
        r = [""] * ncol
        for n, i in name_idx.items():
            r[i] = (rdict.get(n) or "")
        return r

    added, extra_rows, copied, skipped = [], 0, 0, []
    for s in skus:
        c = bysku.get(s.strip().upper())
        if not c:
            skipped.append(s); continue   # 不在候选（已存在/未完成）→ 跳过
        main = dict(c["row"])
        if not (main.get("Image Src") or "").strip():
            main["Image Src"] = c["img"]
        rows.append(mk(main))
        for e in c["extra"]:
            rows.append(mk(e)); extra_rows += 1
        # 拷图：按 SKU 组全套图 + 附加行引用的图（上游只读，只复制出来）。
        # 旧版用主图文件名当词干：主图是 _scene.jpg 时词干错误，白底图/尺寸图漏拷。
        sku_f = c["sku"]   # 上游文件名用大写 SKU
        names = {c["img"], f"{sku_f}.jpg", f"{sku_f}_scene.jpg", f"{sku_f}_dim.jpg"} \
                | {f"{sku_f}_{i}.jpg" for i in range(2, 10)} \
                | {(e.get("Image Src") or "").strip() for e in c["extra"]}
        for f in names:
            if not f or "/" in f or ".." in f: continue
            srcp, dstp = os.path.join(UPSTREAM_DIR, f), os.path.join(IMG_DIR, f)
            if os.path.isfile(srcp) and not os.path.exists(dstp):
                shutil.copy2(srcp, dstp); copied += 1
        added.append(c["sku"])

    # 写入前校验：所有行列数一致
    for i, r in enumerate(rows[1:], 2):
        if len(r) != ncol:
            raise ValueError(f"校验失败：第{i}行 {len(r)} 列 ≠ 表头 {ncol} 列，已放弃写入")
    save_rows(rows)
    # 写入后校验：重读，行数与结构
    chk = load_rows()
    assert len(chk) == before + len(added) + extra_rows, "写入后行数不符"
    assert all(len(r) == ncol for r in chk), "写入后列数不符"
    dup = len(website_skus())  # 重读一遍确保 SKU 集合无异常
    return (f"✅ 导入 {len(added)} 个商品（另含 {extra_rows} 行多图附加行），拷贝图片 {copied} 张\n"
            + (f"⏭️ 跳过 {len(skipped)} 个（已存在或不在候选）\n" if skipped else "")
            + f"校验通过：{before} → {len(chk)} 行，17列结构完整，本库现有 {dup} 个SKU\n"
            + "商品已入库但还没上线：回主页点「🔄 构建预览」检查 →「🚀 发布上线」")

# ---------- 简易 multipart 解析 ----------
def parse_multipart(body, boundary):
    parts, fields, files = body.split(b"--" + boundary), {}, {}
    for part in parts:
        if b"\r\n\r\n" not in part: continue
        head, _, data = part.partition(b"\r\n\r\n")
        data = data.rstrip(b"\r\n-")
        head = head.decode("utf-8", "ignore")
        m = re.search(r'name="([^"]+)"', head)
        if not m: continue
        name = m.group(1)
        fn = re.search(r'filename="([^"]*)"', head)
        if fn and fn.group(1):
            files[name] = (fn.group(1), data)
        else:
            fields[name] = data.decode("utf-8", "ignore")
    return fields, files

# ---------- 页面 ----------
def esc(s): return html.escape(str(s), quote=True)

# ===== 短链 / 优惠券 / 数据 三页（共用外壳）=====
SUB_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:#F7F9FD;color:#16202E}
.nav{position:sticky;top:0;background:#fff;border-bottom:1px solid #EEF1F6;padding:12px 18px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;z-index:10}
.nav b{font-size:16px;margin-right:10px}
.nav a{color:#5a6577;text-decoration:none;font-weight:700;font-size:13.5px;padding:8px 14px;border-radius:99px}
.nav a.on{background:#2563D9;color:#fff}
.pg{max-width:920px;margin:0 auto;padding:20px 18px 60px}
.pg h1{font-size:22px;margin-bottom:16px;letter-spacing:-.02em}
.pg h1 .sub{font-size:13px;color:#8a93a2;font-weight:600}
.cardp{background:#fff;border:1px solid #EDF1F7;border-radius:18px;padding:18px;margin-bottom:20px}
.frm label{display:block;font-weight:700;font-size:12.5px;color:#5a6577;margin:12px 0 6px 2px}
.frm label:first-child{margin-top:0}
.frm input,.frm select{width:100%;border:1.5px solid #E5EAF2;border-radius:12px;padding:11px 13px;font-size:14px;font-family:inherit;background:#fff}
.frm input:focus,.frm select:focus{outline:none;border-color:#2563D9}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.seg,.seg2{display:flex;gap:10px;align-items:center}
.seg label{display:flex;align-items:center;gap:6px;font-weight:700;font-size:13.5px;margin:0}
.seg2 input{flex:1}.seg2 select{width:auto}
.pri{width:100%;background:#2563D9;color:#fff;border:0;border-radius:13px;padding:13px;font-weight:800;font-size:15px;cursor:pointer;margin-top:16px}
#mkOut{margin-top:12px;font-size:13.5px;font-weight:700;word-break:break-all}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #EDF1F7;border-radius:14px;overflow:hidden;font-size:13px}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #F1F4F9}
th{background:#F7F9FD;font-size:12px;color:#5a6577}
td.n{text-align:right;font-weight:800}
td code{background:#EAF0FB;color:#2563D9;font-weight:800;padding:2px 8px;border-radius:6px}
td.u a{color:#2563D9;text-decoration:none}
.cp{background:#F1F5FB;color:#2563D9;border:0;border-radius:8px;padding:5px 10px;font-weight:700;font-size:12px;cursor:pointer;margin-left:6px}
.empty{text-align:center;color:#9aa3b2;padding:26px}
.tag{font-size:11px;font-weight:800;padding:3px 9px;border-radius:99px}
.tag.on{background:#E4F6EC;color:#157A4E}.tag.off{background:#F1F4F9;color:#8a93a2}
.warn{background:#FFF6E5;color:#8a6d1f;border:1px solid #F3E2B5;border-radius:12px;padding:11px 14px;font-size:13px;font-weight:600;margin-bottom:16px}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:#fff;border:1px solid #EDF1F7;border-radius:16px;padding:18px}
.stat .v{font-size:28px;font-weight:800;color:#2563D9}
.stat .l{font-size:12.5px;color:#5a6577;font-weight:600;margin-top:4px}
.tls{margin-top:14px;display:flex;flex-direction:column;gap:2px}
.tle{display:flex;align-items:center;gap:8px;font-size:13px;padding:8px 0;border-bottom:1px solid #F1F4F9}
.tle time{margin-left:auto;color:#9aa3b2;font-size:11.5px}
.tle code{background:#EAF0FB;color:#2563D9;padding:1px 6px;border-radius:5px;font-size:11.5px}
.tle i{color:#8a93a2;font-style:normal;font-size:11.5px}
"""

def nav(active=""):
    def c(k): return "on" if k == active else ""
    return (f'<div class="nav"><b>🛠️ VivaBien</b>'
            f'<a class="{c("prod")}" href="/">商品</a>'
            f'<a class="{c("orders")}" href="/orders">订单</a>'
            f'<a class="{c("carts")}" href="/cart-visitors">加购访客</a>'
            f'<a class="{c("marketing")}" href="/marketing">📣 营销留存</a>'
            f'<a class="{c("stats")}" href="/stats">📊 数据</a>'
            f'<a class="{c("wallpaper")}" href="/wallpaper-stats">墙纸广告</a>'
            f'<a class="{c("coll")}" href="/colecciones">🪴 专题</a></div>')

def sub_shell(title, active, inner):
    return (f'<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} — VivaBien</title><style>{SUB_CSS}</style></head><body>'
            f'{nav(active)}<div class="pg">{inner}</div></body></html>')

_LINKS_JS = """<script>
function cp(t){navigator.clipboard.writeText(t);}
function mk(){
 var tgt=document.getElementById('tgtCustom').value.trim()||document.getElementById('tgt').value;
 var note=document.getElementById('note').value.trim();
 var out=document.getElementById('mkOut');out.textContent='生成中…';
 fetch('/link_create',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({target:tgt||'/',note:note})}).then(function(r){return r.json()}).then(function(d){
  if(d.url){out.innerHTML='✅ '+d.url+' <button class="cp" onclick="cp(\\''+d.url+'\\')">复制</button>';
   setTimeout(function(){location.reload()},1000);}
  else{out.textContent='❌ '+(d.error||'失败');}
 }).catch(function(){out.textContent='❌ 网络错误';});
}
</script>"""

_COUPONS_JS = """<script>
function kUI(){var k=document.querySelector('input[name=kind]:checked').value;
 document.getElementById('valLbl').textContent=k==='percent'?'折扣百分比（1–100）':'折扣金额 RD$';}
function mk(){
 var kind=document.querySelector('input[name=kind]:checked').value;
 var val=parseFloat(document.getElementById('val').value);
 if(!(val>0)){document.getElementById('mkOut').textContent='❌ 请输入有效面值';return;}
 var days=parseInt(document.getElementById('days').value)||0;
 var body={kind:kind,value:val,
  min_order:parseFloat(document.getElementById('minv').value)||0,
  max_uses:parseInt(document.getElementById('maxu').value)||0,
  expires_at:days>0?Date.now()+days*86400000:0};
 var out=document.getElementById('mkOut');out.textContent='生成中…';
 fetch('/coupon_create',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(body)}).then(function(r){return r.json()}).then(function(d){
  if(d.code){out.innerHTML='✅ 券码 <b>'+d.code+'</b> <button class="cp" onclick="cp(\\''+d.code+'\\')">复制</button>';
   setTimeout(function(){location.reload()},1200);}
  else{out.textContent='❌ '+(d.error||'失败');}
 }).catch(function(){out.textContent='❌ 网络错误';});
}
function cp(t){navigator.clipboard.writeText(t);}
function tog(code){fetch('/coupon_toggle',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({code:code})}).then(function(){location.reload()});}
</script>"""

_STATS_JS = """<script>
function look(){
 var v=document.getElementById('q').value.trim(),t=document.getElementById('qt').value;
 if(!v)return;var tl=document.getElementById('tl');tl.textContent='查询中…';
 fetch('/api_timeline?'+t+'='+encodeURIComponent(v)).then(function(r){return r.json()}).then(function(d){
  if(!d.events||!d.events.length){tl.textContent='无记录';return;}
  var m={click:'🔗 点击短链',view:'👁️ 浏览',addcart:'🛒 加购',checkout:'✅ 进入结算',order:'📦 提交订单',whatsapp:'WhatsApp 点击',engagement:'有效停留',scroll:'滚动深度'};
  tl.innerHTML='<div class="tls">'+d.events.map(function(e){
   return '<div class="tle"><span>'+(m[e.type]||e.type)+'</span>'
    +(e.sku?' <code>'+e.sku+'</code>':'')+(e.code?' <i>'+e.code+'</i>':'')
    +(e.country?' <i>🌎 '+e.country+'</i>':'')+(e.ip_masked?' <i>IP '+e.ip_masked+'</i>':'')
    +'<time>'+new Date(e.ts).toLocaleString()+'</time></div>';}).join('')+'</div>';
 }).catch(function(){tl.textContent='查询失败';});
}
</script>"""

def _warn(err):
    return f'<div class="warn">⚠️ {esc(err)}（部署 Worker 后即可用）</div>' if err else ""

def links_page():
    data, err = worker_call("links")
    prods = products()
    opts = "".join(f'<option value="producto/{esc(p["handle"])}.html">{esc(p["title"][:44])}</option>'
                   for p in prods)
    rows = ""
    for l in (data or {}).get("links", []):
        url = f'{SITE_URL}/s/{l["code"]}'
        rows += (f'<tr><td><code>{esc(l["code"])}</code></td>'
                 f'<td class="u"><a href="{esc(url)}" target="_blank">{esc(url)}</a>'
                 f'<button class="cp" onclick="cp(\'{esc(url)}\')">复制</button></td>'
                 f'<td>{esc(l.get("note",""))}</td>'
                 f'<td class="n">{l.get("clicks",0)}</td>'
                 f'<td class="n">{l.get("visitors",0)}</td>'
                 f'<td class="n">{l.get("addcarts",0)}</td></tr>')
    inner = (f'{_warn(err)}<h1>🔗 短链接</h1>'
             '<div class="cardp"><div class="frm">'
             '<label>目标商品</label>'
             f'<select id="tgt"><option value="/">— 首页 —</option>{opts}</select>'
             '<label>或自定义目标（相对路径 / 完整 URL）</label>'
             '<input id="tgtCustom" placeholder="producto/xxx.html 或 https://...">'
             '<label>备注（发给谁）</label>'
             '<input id="note" placeholder="例：客户A 微信">'
             '<button class="pri" onclick="mk()">生成短链</button>'
             '<div id="mkOut"></div></div></div>'
             '<input placeholder="搜索短码 / 备注…" style="width:100%;border:1.5px solid #E5EAF2;border-radius:99px;'
             'padding:10px 16px;font-size:13px;font-family:inherit;outline:none;margin-bottom:10px" '
             'oninput="var q=this.value.toLowerCase();document.querySelectorAll(\'tbody tr\').forEach('
             'function(r){r.style.display=r.textContent.toLowerCase().includes(q)?\'\':\'none\'})">'
             '<table><thead><tr><th>短码</th><th>链接</th><th>备注</th>'
             '<th>点击</th><th>访客</th><th>加购</th></tr></thead><tbody>'
             + (rows or '<tr><td colspan="6" class="empty">还没有短链</td></tr>')
             + '</tbody></table>' + _LINKS_JS)
    return sub_shell("短链接", "links", inner)

def coupons_page():
    data, err = worker_call("coupons")
    social = {}
    if os.path.isfile("data/social.json"):
        try:
            with open("data/social.json", encoding="utf-8") as f:
                social = json.load(f).get("cupon", {}) or {}
        except Exception:
            social = {}
    wel = (social.get("codigo") or "").strip().upper() if social.get("activo") else ""
    rows = ""
    for c in (data or {}).get("coupons", []):
        val = f'{c["value"]:g}%' if c["kind"] == "percent" else f'RD$ {c["value"]:,.0f}'
        act = bool(c.get("active"))
        code = esc(c["code"])
        is_wel = c["code"].strip().upper() == wel
        cond = (f'En compras desde RD${c.get("min_order"):,.0f}'
                if c.get("min_order") else "Sin monto mínimo")
        vtxt = (f'{c["value"]:g}% OFF' if c["kind"] == "percent" else f'RD${c["value"]:,.0f} OFF')
        wel_btn = ('<span class="tag on" style="margin-left:6px">📣 落地页券</span>'
                   '<button class="cp" onclick="welOff()">取消</button>' if is_wel else
                   f'<button class="cp" onclick="welOn(\'{code}\',\'{esc(vtxt)}\',\'{esc(cond)}\')">设为落地页券</button>')
        rows += (f'<tr><td><code>{code}</code>{" 📣" if is_wel else ""}</td><td>{val}</td>'
                 f'<td>{"百分比" if c["kind"]=="percent" else "固定金额"}</td>'
                 f'<td class="n">{c.get("used_count",0)}</td>'
                 f'<td><span class="tag {"on" if act else "off"}">{"启用" if act else "停用"}</span></td>'
                 f'<td><button class="cp" onclick="tog(\'{code}\')">{"停用" if act else "启用"}</button>'
                 f'{wel_btn}</td></tr>')
    inner = (f'{_warn(err)}<h1>🎟️ 优惠券</h1>'
             '<div class="cardp"><div class="frm">'
             '<label>折扣方式</label>'
             '<div class="seg"><label><input type="radio" name="kind" value="percent" checked onchange="kUI()"> 百分比 %</label>'
             '<label><input type="radio" name="kind" value="amount" onchange="kUI()"> 固定金额 RD$</label></div>'
             '<label id="valLbl">折扣百分比（1–100）</label>'
             '<input id="val" type="number" step="any" placeholder="例：10">'
             '<div class="row2">'
             '<div><label>最低订单额（可选）</label><input id="minv" type="number" step="any" placeholder="0=无门槛"></div>'
             '<div><label>使用次数上限（可选）</label><input id="maxu" type="number" step="1" placeholder="0=不限"></div></div>'
             '<label>有效天数（可选，留空=永久）</label>'
             '<input id="days" type="number" step="1" placeholder="例：30">'
             '<button class="pri" onclick="mk()">随机生成券码</button>'
             '<div id="mkOut"></div></div></div>'
             '<input placeholder="搜索券码，或输入 启用 / 停用 筛选…" style="width:100%;border:1.5px solid #E5EAF2;border-radius:99px;'
             'padding:10px 16px;font-size:13px;font-family:inherit;outline:none;margin-bottom:10px" '
             'oninput="var q=this.value.toLowerCase();document.querySelectorAll(\'tbody tr\').forEach('
             'function(r){r.style.display=r.textContent.toLowerCase().includes(q)?\'\':\'none\'})">'
             '<table><thead><tr><th>券码</th><th>面值</th><th>方式</th><th>已用</th><th>状态</th><th></th></tr></thead><tbody>'
             + (rows or '<tr><td colspan="6" class="empty">还没有优惠券</td></tr>')
             + '</tbody></table>' + _COUPONS_JS)
    return sub_shell("优惠券", "coupons", inner)

_MARKETING_JS = """<script>
// ---- 落地页 /enlaces 欢迎券 ----
(function(){
 var sel=document.getElementById('welCode');
 if(!sel)return;
 function autofill(){
  var o=sel.selectedOptions[0];if(!o||!o.value)return;
  var v=Number(o.dataset.v||0),k=o.dataset.k,min=Number(o.dataset.min||0);
  var t=document.getElementById('welText'),c=document.getElementById('welCond');
  t.value=k==='percent'?(v+'% OFF'):('RD$'+v.toLocaleString('en-US')+' OFF');
  c.value=min>0?('En compras desde RD$'+min.toLocaleString('en-US')):'Sin monto mínimo';
 }
 sel.addEventListener('change',autofill);
})();
function welSave(btn){
 var code=(document.getElementById('welCode')||{}).value||'';
 if(!code){alert('先选一张优惠券');return}
 var txt=document.getElementById('welText').value.trim();
 if(!confirm('把 '+code+' 设为落地页欢迎券？\\n\\n客人打开推广页会弹出「'+(txt||code)+'」。\\n改完要回商品页点「🚀 发布」才生效。'))return;
 btn.disabled=true;
 fetch('/coupon_welcome',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({code:code,valor_texto:txt,
   condicion:document.getElementById('welCond').value.trim(),
   nota_pie:document.getElementById('welFoot').value.trim()})})
 .then(function(r){return r.json()}).then(function(d){
  btn.disabled=false;
  if(d.ok){alert('✅ 已启用\\n\\n下一步：回商品页点「🚀 发布」');location.reload()}
  else alert('失败：'+(d.error||''))}).catch(function(){btn.disabled=false;alert('网络错误')});
}
function welOff(){
 if(!confirm('关闭落地页的优惠券弹窗？'))return;
 fetch('/coupon_welcome_off',{method:'POST'}).then(function(){location.reload()});
}
// 用当前选中的券，一键生成可追踪的落地页推广链接 + 西语文案
async function welLink(btn){
 var code=(document.getElementById('welCode')||{}).value||'';
 if(!code){alert('先选一张优惠券');return}
 var val=document.getElementById('welText').value.trim();
 var cond=document.getElementById('welCond').value.trim();
 btn.disabled=true;btn.textContent='生成中…';
 try{
  var r=await fetch('/enlaces_link',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({code:code,valor_texto:val,condicion:cond,
    audience:document.getElementById('welAudience').value.trim()})});
  var d=await r.json();
  if(!r.ok||!d.url)throw new Error(d.error||'生成失败');
  document.getElementById('welResult').style.display='block';
  document.getElementById('welCodes').innerHTML='<b>券码 '+d.coupon+'</b>'
   +'<a href="'+d.url+'" target="_blank">'+d.url+'</a>'
   +'<button class="cp" onclick="navigator.clipboard.writeText(\\''+d.url+'\\')">复制链接</button>';
  document.getElementById('welCopy').value=
   '¡Hola! 🎁 Tenemos un regalo para ti en VivaBien\\n\\n'
   +'Cupón '+d.coupon+(val?' — '+val:'')+(cond?'\\n'+cond:'')
   +'\\n\\nÁbrelo aquí 👇\\n'+d.url
   +'\\n\\n🛍️ Tienda online · 📢 Canal de WhatsApp · 📸 Instagram — todo en un solo enlace.'
   +'\\n🚚 Envíos a todo el país · 🤝 Contra entrega en Gran Santo Domingo';
  btn.textContent='✓ 已生成';
  document.getElementById('welResult').scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){alert(e.message);btn.textContent='🔗 生成推广链接'}
 finally{btn.disabled=false}
}
function welCopyText(){var t=document.getElementById('welCopy');t.select();navigator.clipboard.writeText(t.value)}
function welShareWA(){var t=document.getElementById('welCopy').value;if(t)window.open('https://wa.me/?text='+encodeURIComponent(t),'_blank')}
var LAST_CAMPAIGN=null;
function money(v){return 'RD$ '+Number(v||0).toLocaleString('es-DO',{maximumFractionDigits:0})}
function discountLabel(d){return d.kind==='percent'?Number(d.value)+'% de descuento':money(d.value)+' de descuento'}
function copyFor(d){
 var offer=discountLabel(d),limit=d.max_uses>0?(' Disponible para '+d.max_uses+(d.max_uses===1?' uso.':' usos.')):'',
     expiry=d.days>0?(' Válido por '+d.days+' días.'):'',min=d.min_order>0?(' Compra mínima: '+money(d.min_order)+'.'):'',
     how='Abre tu enlace exclusivo, agrega tus productos al carrito y el código '+d.coupon+' se aplicará al finalizar.';
 if(d.template==='welcome')return '¡Bienvenido/a a VivaBien! 🎉 Tenemos un regalo para tu primera compra: '+offer+'. '+how+' '+d.url+'.'+expiry+min+limit;
 if(d.template==='winback')return '¡Te extrañamos! 💙 Vuelve a VivaBien y disfruta '+offer+' con tu código exclusivo '+d.coupon+'. Compra aquí: '+d.url+'.'+expiry+min+limit;
 if(d.template==='vip')return '✨ Oferta privada para ti: disfruta '+offer+' en VivaBien. Tu código exclusivo es '+d.coupon+'. Entra aquí: '+d.url+'.'+expiry+min+limit;
 return '¡Gracias por comprar en VivaBien! 🎁 Como agradecimiento, recibe '+offer+' en tu próxima compra. '+how+' '+d.url+'.'+expiry+min+limit;
}
function payloadPreview(){
 return {template:document.getElementById('tpl').value,kind:document.querySelector('input[name=mkKind]:checked').value,
  value:parseFloat(document.getElementById('mkValue').value)||0,min_order:parseFloat(document.getElementById('mkMin').value)||0,
  max_uses:parseInt(document.getElementById('mkUses').value)||0,days:parseInt(document.getElementById('mkDays').value)||0,
  coupon:'TU-CÓDIGO',url:'TU-ENLACE-EXCLUSIVO'};
}
function previewCopy(){document.getElementById('copyOut').value=copyFor(LAST_CAMPAIGN||payloadPreview())}
function kindUI(){document.getElementById('mkValueLabel').textContent=document.querySelector('input[name=mkKind]:checked').value==='percent'?'折扣百分比（%）':'折扣金额（RD$）';previewCopy()}
async function createCampaign(btn){
 var value=parseFloat(document.getElementById('mkValue').value);
 if(!(value>0)){alert('请填写有效优惠金额');return}
 var target=document.getElementById('mkTargetCustom').value.trim()||document.getElementById('mkTarget').value;
 var body={template:document.getElementById('tpl').value,audience:document.getElementById('mkAudience').value.trim(),
  target:target||'/',kind:document.querySelector('input[name=mkKind]:checked').value,value:value,
  min_order:parseFloat(document.getElementById('mkMin').value)||0,max_uses:parseInt(document.getElementById('mkUses').value)||0,
  days:parseInt(document.getElementById('mkDays').value)||0};
 btn.disabled=true;btn.textContent='生成中…';
 try{var r=await fetch('/campaign_create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();
  if(!r.ok||!d.url){throw new Error(d.error||'创建失败')}
  LAST_CAMPAIGN=Object.assign(body,{coupon:d.coupon,url:d.url});
  document.getElementById('campaignResult').style.display='block';
  document.getElementById('resultCodes').innerHTML='<b>优惠码 '+d.coupon+'</b><a href=\"'+d.url+'\" target=\"_blank\">'+d.url+'</a>';
  previewCopy();btn.textContent='✓ 已生成';
 }catch(e){alert(e.message);btn.textContent='一键生成营销活动'}finally{btn.disabled=false}
}
function copyText(){var t=document.getElementById('copyOut');t.select();navigator.clipboard.writeText(t.value)}
function shareWA(){var t=document.getElementById('copyOut').value;if(t)window.open('https://wa.me/?text='+encodeURIComponent(t),'_blank')}
function rowCopy(b){LAST_CAMPAIGN={template:b.dataset.template,kind:b.dataset.kind,value:Number(b.dataset.value),min_order:Number(b.dataset.min),max_uses:Number(b.dataset.uses),days:Number(b.dataset.days),coupon:b.dataset.coupon,url:b.dataset.url};previewCopy();copyText();document.getElementById('campaignResult').style.display='block';document.getElementById('campaignResult').scrollIntoView({behavior:'smooth',block:'center'})}
document.querySelectorAll('#campaignForm input,#campaignForm select').forEach(function(x){x.addEventListener('input',previewCopy)});previewCopy();
</script>"""

def _campaign_note(note):
    vals = {}
    for k, v in re.findall(r"(coupon|template|days|audience)=([^|]*)", note or ""):
        vals[k] = v
    return vals

def marketing_page():
    links_data, links_err = worker_call("links")
    coupons_data, coupons_err = worker_call("coupons")
    overview_data, overview_err = worker_call("overview")
    enl_data, _enl_err = worker_call("enlaces?days=30")
    prods = products()
    opts = "".join(f'<option value="producto/{esc(p["handle"])}.html">{esc(p["title"][:52])}</option>'
                   for p in prods)
    coupons = {c.get("code"): c for c in (coupons_data or {}).get("coupons", [])}
    rows = ""
    for l in (links_data or {}).get("links", []):
        meta = _campaign_note(l.get("note", ""))
        coupon_code = meta.get("coupon", "")
        c = coupons.get(coupon_code, {})
        url = f'{SITE_URL}/s/{l.get("code", "")}'
        clicks = int(l.get("clicks", 0) or 0)
        visitors = int(l.get("visitors", 0) or 0)
        addcarts = int(l.get("addcarts", 0) or 0)
        checkouts = int(l.get("checkouts", 0) or 0)
        uses = int(c.get("used_count", 0) or 0)
        rate = f"{(addcarts / clicks * 100):.1f}%" if clicks else "—"
        value = c.get("value", 0) or 0
        kind = c.get("kind", "percent")
        days = meta.get("days", "0")
        template = meta.get("template", "postpurchase")
        is_enl = template == "enlaces" or "enlaces" in str(l.get("target", ""))
        badge = ' <span class="tag on" style="font-size:10px">📣 落地页</span>' if is_enl else ""
        rows += (f'<tr><td><b>{esc(meta.get("audience") or l.get("note", ""))}</b>{badge}'
                 f'<br><code>{esc(l.get("code",""))}</code></td>'
                 f'<td><code>{esc(coupon_code or "—")}</code></td><td class="n">{clicks}</td><td class="n">{visitors}</td>'
                 f'<td class="n">{addcarts}</td><td class="n">{checkouts}</td><td class="n">{uses}</td><td class="n">{rate}</td>'
                 f'<td><button class="cp row-copy" data-template="{esc(template)}" data-kind="{esc(kind)}" '
                 f'data-value="{value}" data-min="{c.get("min_order",0) or 0}" data-uses="{c.get("max_uses",0) or 0}" '
                 f'data-days="{esc(days)}" data-coupon="{esc(coupon_code)}" data-url="{esc(url)}" onclick="rowCopy(this)">复制文案</button></td></tr>')
    ov = overview_data or {}
    def stat(v, label):
        return f'<div class="stat"><div class="v">{v}</div><div class="l">{label}</div></div>'
    warn = _warn(links_err or coupons_err or overview_err)

    # ---- 落地页 /enlaces 欢迎券配置卡 ----
    social_cup = {}
    if os.path.isfile("data/social.json"):
        try:
            with open("data/social.json", encoding="utf-8") as f:
                social_cup = json.load(f).get("cupon", {}) or {}
        except Exception:
            social_cup = {}
    wel_code = (social_cup.get("codigo") or "").strip().upper()
    wel_on = bool(social_cup.get("activo") and wel_code)
    def _cup_option(c):
        code = c.get("code", "")
        val = c.get("value", 0) or 0
        mino = c.get("min_order", 0) or 0
        label = f"{val:g}%" if c.get("kind") == "percent" else f"RD${val:,.0f}"
        if mino:
            label += f" · mín RD${mino:,.0f}"
        sel = " selected" if code.strip().upper() == wel_code else ""
        return (f'<option value="{esc(code)}" data-v="{esc(str(val))}" '
                f'data-k="{esc(c.get("kind", "percent"))}" data-min="{esc(str(mino))}"{sel}>'
                f'{esc(code)} — {esc(label)}</option>')
    cup_opts = "".join(_cup_option(c) for c in (coupons_data or {}).get("coupons", []))
    _no_cup = "<option value=''>（还没有优惠券，先在上面生成）</option>"
    _off_btn = ('<button class="wa-btn" style="background:#8a93a2" onclick="welOff()">关闭弹窗</button>'
                if wel_on else "")
    welcome_card = (
        '<div class="cardp" style="margin-top:18px"><div class="frm">'
        '<b style="font-size:15px">🎁 推广落地页欢迎券</b>'
        f'<div class="funnel-note" style="margin:6px 0 12px">客人打开 <a href="{SITE_URL}/enlaces.html" target="_blank">'
        f'{SITE_URL}/enlaces.html</a> 时弹出「恭喜获得优惠券」，点击后券码自动带进购物车。'
        '券必须是下面列表里真实存在且启用的，否则客人结算会提示无效。</div>'
        + (f'<div class="tag on" style="display:inline-block;margin-bottom:10px">当前启用：{esc(wel_code)}</div>'
           if wel_on else '<div class="tag off" style="display:inline-block;margin-bottom:10px">当前未启用弹窗</div>')
        + '<label>选择优惠券</label>'
        f'<select id="welCode">{cup_opts or _no_cup}</select>'
        '<div class="row2"><div><label>弹窗大字（客人看到的）</label>'
        f'<input id="welText" placeholder="RD$100 OFF" value="{esc(social_cup.get("valor_texto",""))}"></div>'
        '<div><label>使用条件（西语）</label>'
        f'<input id="welCond" placeholder="En compras desde RD$1,000" value="{esc(social_cup.get("condicion",""))}"></div></div>'
        '<label>底部小字</label>'
        f'<input id="welFoot" placeholder="Válido por 15 días" value="{esc(social_cup.get("nota_pie",""))}">'
        '<label>发给谁（备注，可选）</label>'
        '<input id="welAudience" placeholder="例：WhatsApp 群发 8月 / 客户 María">'
        '<div class="copy-actions" style="margin-top:12px">'
        '<button class="copy-btn" style="background:#FF6B4A" onclick="welLink(this)">🔗 生成推广链接</button>'
        '<button class="wa-btn" style="background:#2563D9" onclick="welSave(this)">设为默认弹窗券</button>'
        + _off_btn
        + '</div>'
        '<div class="mk-result" id="welResult"><div id="welCodes" class="result-codes"></div>'
        '<textarea id="welCopy" style="width:100%;min-height:150px;border:1px solid #D7E7DE;border-radius:10px;'
        'padding:12px;font:13px/1.6 inherit;margin:10px 0;resize:vertical"></textarea>'
        '<div class="copy-actions"><button class="copy-btn" onclick="welCopyText()">复制文案</button>'
        '<button class="wa-btn" onclick="welShareWA()">WhatsApp 发送</button></div></div>'
        '<div class="funnel-note"><b>🔗 生成推广链接</b>：用这张券生成一条可追踪的落地页短链，'
        '客人打开就弹这张券，点击行为会显示在下面的「推广落地页行为」里。发给不同人可各生成一条，分别看数据。<br>'
        '<b>设为默认弹窗券</b>：直接访问 /enlaces（比如从 Instagram 主页点进来、没带链接参数）的人看到的券，改完需「🚀 发布」。</div>'
        '</div></div>')

    # ---- 落地页行为轨迹（近30天）----
    enl = enl_data or {}
    SEC_NAME = {"principal": "🛍️ 进网站", "whatsapp": "📢 进 WhatsApp 频道",
                "instagram": "📸 进 Instagram", "producto": "🖼️ 点了商品图",
                "ver_todo": "📋 看全部商品", "wa_cta": "💬 底部 WhatsApp 咨询",
                "otro": "其他"}
    prod_titles = {p["sku"]: p["title"] for p in prods if p.get("sku")}
    sec_rows = "".join(
        f'<tr><td>{esc(SEC_NAME.get(s.get("seccion",""), s.get("seccion","")))}</td>'
        f'<td class="n">{s.get("clicks",0)}</td><td class="n">{s.get("sessions",0)}</td></tr>'
        for s in enl.get("sections", []))
    prod_rows = "".join(
        f'<tr><td>{esc(prod_titles.get(p.get("sku",""), p.get("sku","")))[:44]}</td>'
        f'<td class="n">{p.get("clicks",0)}</td><td class="n">{p.get("sessions",0)}</td></tr>'
        for p in enl.get("productos", []))
    cup_st = enl.get("cupon", {}) or {}
    vistos, reclam = cup_st.get("vistos", 0) or 0, cup_st.get("reclamados", 0) or 0
    tasa = f"{(reclam / vistos * 100):.0f}%" if vistos else "—"
    avg_s = enl.get("avg_seconds", 0) or 0
    dev_rows = "".join(
        f'<tr><td>{esc(d.get("device","") or "—")}</td><td class="n">{d.get("sessions",0)}</td></tr>'
        for d in enl.get("devices", []))
    reg_rows = "".join(
        f'<tr><td>{esc(r.get("city","") or "—")}'
        + (f' <span style="color:#8a93a2">{esc(r.get("region",""))}</span>' if r.get("region") else "")
        + f'</td><td class="n">{r.get("sessions",0)}</td></tr>'
        for r in enl.get("regions", []))
    link_rows = "".join(
        f'<tr><td><code>{esc(l.get("link",""))}</code></td><td class="n">{l.get("visitas",0)}</td>'
        f'<td class="n">{l.get("clicks",0)}</td><td class="n">{l.get("cupones",0)}</td></tr>'
        for l in enl.get("por_link", []))
    TYPE_NAME = {"enlaces_view": "打开页面", "enlaces_click": "点击",
                 "cupon_view": "看到券", "cupon_claim": "领了券"}
    rec_rows = ""
    for e in enl.get("recent", [])[:40]:
        ts = e.get("ts", 0)
        when = time.strftime("%m-%d %H:%M", time.localtime(ts / 1000)) if ts else "—"
        sec = SEC_NAME.get(e.get("source_section", ""), e.get("source_section", "") or "")
        dest = (e.get("destino") or "")[:40]
        who = (e.get("sid", "") or "")[-6:]
        loc = e.get("city", "") or ""
        rec_rows += (f'<tr><td style="white-space:nowrap">{when}</td>'
                     f'<td><code>{esc(who)}</code></td>'
                     f'<td>{esc(TYPE_NAME.get(e.get("type",""), e.get("type","")))}'
                     + (f' · {esc(sec)}' if sec else "") + '</td>'
                     f'<td style="font-size:11px;color:#68758a">{esc(dest)}</td>'
                     f'<td style="font-size:11px">{esc(loc)}</td>'
                     f'<td style="font-size:11px">{esc(e.get("device_type","") or "")}</td></tr>')
    enlaces_card = (
        '<h1 style="margin-top:26px">📣 推广落地页行为 <span class="sub">近30天 · /enlaces</span></h1>'
        '<div class="stats">'
        + stat(enl.get("visitas", 0), "打开落地页")
        + stat(vistos, "看到优惠券")
        + stat(reclam, "领取优惠券")
        + stat(tasa, "领取率")
        + stat(f"{avg_s:g}s" if avg_s else "—", "平均停留")
        + '</div>'
        '<div class="mk-grid"><div class="cardp"><b>客户点了哪里</b>'
        '<table style="margin-top:10px"><thead><tr><th>入口</th><th>点击</th><th>人数</th></tr></thead><tbody>'
        + (sec_rows or '<tr><td colspan="3" class="empty">还没有数据（发出链接后就会有）</td></tr>')
        + '</tbody></table></div>'
        '<div class="cardp"><b>点了哪些商品</b>'
        '<table style="margin-top:10px"><thead><tr><th>商品</th><th>点击</th><th>人数</th></tr></thead><tbody>'
        + (prod_rows or '<tr><td colspan="3" class="empty">还没有数据</td></tr>')
        + '</tbody></table></div></div>'
        '<div class="mk-grid" style="margin-top:14px"><div class="cardp"><b>每条推广链接的表现</b>'
        '<table style="margin-top:10px"><thead><tr><th>短码</th><th>打开</th><th>点击</th><th>领券</th></tr></thead><tbody>'
        + (link_rows or '<tr><td colspan="4" class="empty">还没有数据</td></tr>')
        + '</tbody></table></div>'
        '<div class="cardp"><b>设备 / 城市</b>'
        '<table style="margin-top:10px"><thead><tr><th>设备</th><th>人数</th></tr></thead><tbody>'
        + (dev_rows or '<tr><td colspan="2" class="empty">—</td></tr>')
        + '</tbody></table>'
        '<table style="margin-top:10px"><thead><tr><th>城市</th><th>人数</th></tr></thead><tbody>'
        + (reg_rows or '<tr><td colspan="2" class="empty">—</td></tr>')
        + '</tbody></table></div></div>'
        '<div class="cardp" style="margin-top:14px"><b>最近的客户轨迹</b>'
        '<div class="funnel-note">同一个访客用后 6 位编号区分，可以看出一个人先点了什么、再点了什么。</div>'
        '<div class="campaign-table"><table style="margin-top:10px"><thead><tr>'
        '<th>时间</th><th>访客</th><th>动作</th><th>去了哪里</th><th>城市</th><th>设备</th>'
        '</tr></thead><tbody>'
        + (rec_rows or '<tr><td colspan="6" class="empty">还没有数据</td></tr>')
        + '</tbody></table></div></div>')
    inner = (f'{warn}<style>'
             '.mk-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr);gap:16px;align-items:start}'
             '.mk-result{display:none;background:#F4FBF7;border:1px solid #CFE9DA;border-radius:14px;padding:14px;margin-top:14px}'
             '.mk-result textarea{width:100%;min-height:180px;border:1px solid #D7E7DE;border-radius:10px;padding:12px;font:13px/1.6 inherit;margin:10px 0;resize:vertical}'
             '.result-codes{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.result-codes a{color:#2563D9;font-size:12px;font-weight:700;word-break:break-all}'
             '.copy-actions{display:flex;gap:8px}.copy-actions button{flex:1;border:0;border-radius:10px;padding:10px;font-weight:800;cursor:pointer}.copy-btn{background:#2563D9;color:#fff}.wa-btn{background:#25D366;color:#fff}'
             '.funnel-note{font-size:12px;color:#68758a;line-height:1.55;margin-top:8px}.campaign-table{overflow-x:auto}.campaign-table table{min-width:940px}'
             '@media(max-width:760px){.mk-grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}'
             '</style><h1>📣 营销留存 <span class="sub">优惠券 + 专属链接 + 西语文案</span></h1>'
             '<div class="stats">'
             + stat(ov.get("clicks30", 0), "近30天专属链接点击")
             + stat(ov.get("visitors30", 0), "独立访客")
             + stat(ov.get("addcarts30", 0), "加购")
             + stat(ov.get("checkouts30", 0), "开始结账")
             + stat(ov.get("coupon_uses30", 0), "优惠券核销")
             + '</div><div class="mk-grid"><div class="cardp"><div class="frm" id="campaignForm">'
             '<label>客户留存模板</label><select id="tpl"><option value="postpurchase">购买后感谢 + 下次优惠</option>'
             '<option value="welcome">新客户欢迎 + 首单优惠</option><option value="winback">沉睡客户召回</option>'
             '<option value="vip">VIP 专属优惠</option></select>'
             '<label>客户 / 分组备注</label><input id="mkAudience" placeholder="例：客户 María / 7月已购客户">'
             '<label>专属链接目标</label><select id="mkTarget">'
             '<option value="enlaces.html">📣 推广落地页（券弹窗+三入口+商品，推荐）</option>'
             '<option value="/">网站首页</option><option value="carrito.html">购物车</option>'
             + opts + '</select><input id="mkTargetCustom" style="margin-top:8px" placeholder="或粘贴自定义链接">'
             '<label>优惠方式</label><div class="seg"><label><input type="radio" name="mkKind" value="percent" checked onchange="kindUI()"> 百分比</label>'
             '<label><input type="radio" name="mkKind" value="amount" onchange="kindUI()"> 固定金额</label></div>'
             '<label id="mkValueLabel">折扣百分比（%）</label><input id="mkValue" type="number" value="10" min="1" step="any">'
             '<div class="row2"><div><label>最低订单额 RD$</label><input id="mkMin" type="number" value="0"></div>'
             '<div><label>可使用次数</label><input id="mkUses" type="number" value="1" min="0"></div></div>'
             '<label>有效天数</label><input id="mkDays" type="number" value="30" min="0">'
             '<button class="pri" onclick="createCampaign(this)">一键生成营销活动</button>'
             '<div class="funnel-note">一次生成：优惠码、带优惠券的专属短链接、西班牙语营销文案。链接会跟踪点击、访客、浏览、加购和结账。</div>'
             '</div></div><div><div class="cardp"><b>西班牙语文案预览</b>'
             '<div class="mk-result" id="campaignResult"><div id="resultCodes" class="result-codes"></div></div>'
             '<textarea id="copyOut" style="width:100%;min-height:240px;border:1.5px solid #E5EAF2;border-radius:12px;padding:13px;font:13px/1.65 inherit;margin-top:12px"></textarea>'
             '<div class="copy-actions"><button class="copy-btn" onclick="copyText()">复制文案</button>'
             '<button class="wa-btn" onclick="shareWA()">WhatsApp 发送</button></div></div>'
             + welcome_card + '</div></div>'
             '<h1 style="margin-top:26px">营销活动表现</h1><div class="campaign-table"><table><thead><tr>'
             '<th>客户/活动</th><th>优惠码</th><th>点击</th><th>访客</th><th>加购</th><th>结账</th><th>核销</th><th>点击→加购</th><th></th>'
             '</tr></thead><tbody>' + (rows or '<tr><td colspan="9" class="empty">还没有营销活动</td></tr>')
             + '</tbody></table></div>' + enlaces_card + _MARKETING_JS)
    return sub_shell("营销留存", "marketing", inner)

_ANALYTICS_JS = """<script>
async function saveCost(){var b={day:document.getElementById('costDay').value,campaign:document.getElementById('costCampaign').value.trim(),source:document.getElementById('costSource').value.trim(),spend:Number(document.getElementById('costSpend').value)||0,impressions:Number(document.getElementById('costImp').value)||0,ad_clicks:Number(document.getElementById('costClicks').value)||0};
 if(!b.day||!b.campaign){alert('请填写日期和活动名称');return}var r=await fetch('/campaign_cost',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});if(r.ok)location.reload();else alert('保存失败：'+await r.text())}
</script>"""

def stats_page():
    data, err = worker_call("analytics?days=30")
    d = data or {}
    funnel = d.get("funnel") or {}
    def pct(a, b): return f"{a / b * 100:.1f}%" if b else "—"
    steps = [("短链点击", int(funnel.get("clicks",0) or 0)),
             ("页面到达", int(funnel.get("arrivals",0) or 0)),
             ("商品浏览", int(funnel.get("product_views",0) or 0)),
             ("加购", int(funnel.get("addcarts",0) or 0)),
             ("打开购物车", int(funnel.get("checkouts",0) or 0)),
             ("WhatsApp", int(funnel.get("whatsapps",0) or 0)),
             ("提交订单", int(funnel.get("orders",0) or 0))]
    drops = [((steps[i-1][1]-v)/steps[i-1][1] if steps[i-1][1] else 0) for i,(_,v) in enumerate(steps) if i]
    worst = (drops.index(max(drops))+1) if drops and max(drops)>0 else -1
    funnel_html = ""
    for i,(label,value) in enumerate(steps):
        rate = pct(value, steps[i-1][1]) if i else "起点"
        drop = pct(max(0,steps[i-1][1]-value),steps[i-1][1]) if i else ""
        funnel_html += (f'<div class="fstep {"worst" if i==worst else ""}"><span>{label}</span><b>{value}</b>'
                        f'<small>{rate}{(" · 流失 "+drop) if i else ""}</small></div>')
    channel_rows = ""
    for x in d.get("channels",[]):
        n=int(x.get("sessions",0) or 0); wa=int(x.get("whatsapps",0) or 0); orders=int(x.get("orders",0) or 0)
        sample = '<span class="sample">样本少</span>' if n < 20 else ""
        channel_rows += (f'<tr><td><b>{esc(x.get("channel",""))}</b>{sample}</td><td class="n">{n}</td>'
                         f'<td class="n">{pct(int(x.get("bounces",0) or 0),n)}</td><td class="n">{pct(wa,n)}</td>'
                         f'<td class="n">{orders}</td><td class="n">{float(x.get("avg_seconds",0) or 0):.0f}s</td>'
                         f'<td class="n">RD$ {float(x.get("spend",0) or 0):,.0f}</td>'
                         f'<td class="n">{("RD$ "+format(float(x.get("cost_per_order",0)),",.0f")) if orders and x.get("spend") else "—"}</td></tr>')
    device_rows = "".join(f'<tr><td><b>{esc(x.get("device",""))}</b></td><td class="n">{int(x.get("sessions",0) or 0)}</td>'
                          f'<td class="n">{pct(int(x.get("whatsapps",0) or 0),int(x.get("sessions",0) or 0))}</td>'
                          f'<td class="n">{int(x.get("orders",0) or 0)}</td><td class="n">{float(x.get("avg_seconds",0) or 0):.0f}s</td></tr>'
                          for x in d.get("devices",[]))
    behavior_rows = "".join(f'<tr><td><b>{esc(x.get("segment",""))}</b></td><td class="n">{int(x.get("sessions",0) or 0)}</td>'
                            f'<td class="n">{float(x.get("avg_seconds",0) or 0):.0f}s</td><td class="n">{float(x.get("avg_pages",0) or 0):.1f}</td>'
                            f'<td class="n">{float(x.get("avg_scroll",0) or 0):.0f}%</td></tr>' for x in d.get("behavior",[]))
    version_rows = ""
    for x in d.get("versions", []):
        sessions=int(x.get("sessions",0) or 0); carts=int(x.get("carts",0) or 0); orders=int(x.get("orders",0) or 0)
        sample = '<span class="sample">样本少</span>' if sessions < 50 else ''
        version_rows += (f'<tr><td><b>{esc("新版 UX2" if x.get("version") == "ux2-20260713" else "改版前/旧数据")}</b>'
                         f'{sample}</td><td class="n">{sessions}</td>'
                         f'<td class="n">{int(x.get("searchers",0) or 0)}</td><td class="n">{pct(carts,sessions)}</td>'
                         f'<td class="n">{int(x.get("checkouts",0) or 0)}</td><td class="n">{orders}</td>'
                         f'<td class="n">{float(x.get("avg_search_results",0) or 0):.1f}</td></tr>')
    product_map={p.get("sku"):p for p in products()}
    product_rows=""
    for x in d.get("products",[]):
        p=product_map.get(x.get("sku"),{}); views=int(x.get("viewers",0) or 0); wa=int(x.get("whatsapps",0) or 0)
        rate=wa/views*100 if views else 0; title=x.get("title") or p.get("title") or x.get("sku",""); img=x.get("image") or p.get("img","")
        signal = "高浏览低咨询" if views>=10 and rate<5 else ("高转化可加曝光" if views>=10 and rate>=20 else "观察")
        product_img = f'<img src="/images/{quote(os.path.basename(img))}">' if img else ""
        product_rows += (f'<tr><td><div class="pmini">{product_img}<div><b>{esc(title)}</b><small>{esc(x.get("sku",""))}</small></div></div></td>'
                         f'<td class="n">{views}</td><td class="n">{int(x.get("carts",0) or 0)}</td><td class="n">{wa}</td><td class="n">{rate:.1f}%</td><td>{signal}{" · 样本少" if views<10 else ""}</td></tr>')
    quality=d.get("quality") or {}; total=int(quality.get("total_events",0) or 0); bots=int(quality.get("bot_events",0) or 0); legacy=int(quality.get("legacy_events",0) or 0)
    table_empty='<tr><td colspan="8" class="empty">等待新版追踪数据积累</td></tr>'
    inner=(f'{_warn(err)}<style>.funnel{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:22px}}.fstep{{background:#fff;border:1px solid #E5EAF2;padding:14px 10px;border-radius:8px;display:flex;flex-direction:column;gap:5px}}.fstep span{{font-size:11px;color:#66758a;font-weight:700}}.fstep b{{font-size:23px}}.fstep small{{font-size:10px;color:#8b96a6}}.fstep.worst{{border:2px solid #E44D4D;background:#FFF5F5}}.section-title{{font-size:17px;margin:24px 0 10px}}.table-wrap{{overflow:auto}}.table-wrap table{{min-width:720px}}.sample{{font-size:9px;background:#FFF1CC;color:#8A6815;padding:2px 5px;border-radius:4px;margin-left:5px}}.pmini{{display:flex;align-items:center;gap:8px;min-width:280px}}.pmini img{{width:44px;height:44px;object-fit:cover;border-radius:6px}}.pmini div{{display:flex;flex-direction:column;gap:3px}}.quality{{font-size:12px;color:#68758a;margin:10px 0 20px}}.cost-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}@media(max-width:760px){{.funnel{{grid-template-columns:repeat(2,1fr)}}.cost-grid{{grid-template-columns:1fr}}}}'
           f'</style><h1>📊 数据分析 <span class="sub">近30天 · 默认排除机器人</span></h1><div class="quality">数据质量：共 {total} 个事件，排除机器人 {bots} 个，历史旧格式 {legacy} 个。小样本指标仅供观察。</div>'
           f'<h2 class="section-title">推广漏斗</h2><div class="funnel">{funnel_html}</div>'
           f'<h2 class="section-title">渠道对比</h2><div class="table-wrap"><table><thead><tr><th>渠道/活动</th><th>会话</th><th>未互动跳出</th><th>WhatsApp率</th><th>订单</th><th>平均停留</th><th>花费</th><th>每单成本</th></tr></thead><tbody>{channel_rows or table_empty}</tbody></table></div>'
           f'<h2 class="section-title">设备分段</h2><div class="table-wrap"><table><thead><tr><th>设备</th><th>会话</th><th>WhatsApp率</th><th>订单</th><th>平均停留</th></tr></thead><tbody>{device_rows or table_empty}</tbody></table></div>'
           f'<h2 class="section-title">行为对比</h2><div class="table-wrap"><table><thead><tr><th>访客分组</th><th>会话</th><th>平均停留</th><th>浏览页数</th><th>滚动深度</th></tr></thead><tbody>{behavior_rows or table_empty}</tbody></table></div>'
           f'<h2 class="section-title">改版前后对比</h2><div class="table-wrap"><table><thead><tr><th>页面版本</th><th>会话</th><th>使用搜索</th><th>加购率</th><th>完成结算</th><th>订单</th><th>平均搜索结果</th></tr></thead><tbody>{version_rows or table_empty}</tbody></table></div>'
           f'<h2 class="section-title">商品机会榜</h2><div class="table-wrap"><table><thead><tr><th>商品</th><th>浏览访客</th><th>加购</th><th>WhatsApp</th><th>咨询率</th><th>判断</th></tr></thead><tbody>{product_rows or table_empty}</tbody></table></div>'
           '<h2 class="section-title">录入广告成本</h2><div class="cardp frm"><div class="cost-grid"><div><label>日期</label><input id="costDay" type="date"></div><div><label>活动名称（必须和UTM campaign一致）</label><input id="costCampaign"></div><div><label>来源</label><input id="costSource" placeholder="facebook"></div><div><label>花费 RD$</label><input id="costSpend" type="number"></div><div><label>展示量</label><input id="costImp" type="number"></div><div><label>广告点击</label><input id="costClicks" type="number"></div></div><button class="pri" onclick="saveCost()">保存广告成本</button></div>'
           '<div class="cardp"><div class="frm"><label>查访客足迹</label><div class="seg2"><input id="q" placeholder="短码 或 访客ID"><select id="qt"><option value="code">按短码</option><option value="vid">按访客ID</option></select><button class="pri" style="width:auto;margin:0" onclick="look()">查询</button></div><div id="tl"></div></div></div>' + _STATS_JS + _ANALYTICS_JS)
    return sub_shell("数据分析", "stats", inner)

def wallpaper_stats_page(days=30):
    days = days if days in (7, 30, 90) else 30
    sku = "VB-ROLL-001"
    data, err = worker_call(f"product-analytics?sku={quote(sku)}&days={days}")
    d = data or {}
    s = d.get("summary") or {}
    visitors = int(s.get("visitors", 0) or 0)
    addcarts = int(s.get("addcart_visitors", 0) or 0)
    whatsapps = int(s.get("whatsapp_sessions", 0) or 0)
    orders = int(s.get("orders", 0) or 0)
    revenue = float(s.get("revenue", 0) or 0)

    def pct(a, b):
        return f"{a / b * 100:.1f}%" if b else "—"

    kpis = [
        ("墙纸访客", visitors, "访问过墙纸商品页"),
        ("加购访客", addcarts, f"访客→加购 {pct(addcarts, visitors)}"),
        ("加购卷数", int(s.get("addcart_units", 0) or 0), "所有加购事件合计"),
        ("WhatsApp", whatsapps, f"访客→咨询 {pct(whatsapps, visitors)}"),
        ("有效订单", orders, f"访客→下单 {pct(orders, visitors)}"),
        ("订单卷数", int(s.get("units", 0) or 0), f"销售额 RD$ {revenue:,.0f}"),
    ]
    kpi_html = "".join(
        f'<div class="w-kpi"><span>{esc(label)}</span><b>{value}</b><small>{esc(note)}</small></div>'
        for label, value, note in kpis
    )

    channel_rows = ""
    for x in d.get("channels", []):
        sessions = int(x.get("sessions", 0) or 0)
        carts = int(x.get("carts", 0) or 0)
        channel_rows += (
            f'<tr><td><b>{esc(x.get("channel", ""))}</b></td>'
            f'<td class="n">{sessions}</td><td class="n">{carts}</td>'
            f'<td class="n">{pct(carts, sessions)}</td>'
            f'<td class="n">{int(x.get("whatsapps", 0) or 0)}</td>'
            f'<td class="n">{int(x.get("actual_orders", 0) or 0)}</td>'
            f'<td class="n">{float(x.get("avg_seconds", 0) or 0):.0f}s</td>'
            f'<td class="n">RD$ {float(x.get("spend", 0) or 0):,.0f}</td>'
            f'<td class="n">{("RD$ "+format(float(x.get("cost_per_cart",0)),",.0f")) if carts and x.get("spend") else "—"}</td></tr>'
        )

    order_by_day = {x.get("day"): x for x in d.get("daily_orders", [])}
    daily_rows = ""
    max_visitors = max([int(x.get("visitors", 0) or 0) for x in d.get("daily", [])] or [1])
    for x in d.get("daily", []):
        day = x.get("day", "")
        od = order_by_day.get(day, {})
        count = int(x.get("visitors", 0) or 0)
        width = max(3, round(count / max_visitors * 100)) if count else 0
        daily_rows += (
            f'<tr><td>{esc(day)}</td><td><div class="daybar"><i style="width:{width}%"></i><b>{count}</b></div></td>'
            f'<td class="n">{int(x.get("addcarts", 0) or 0)}</td>'
            f'<td class="n">{int(od.get("orders", 0) or 0)}</td>'
            f'<td class="n">RD$ {float(od.get("revenue", 0) or 0):,.0f}</td></tr>'
        )
    for day, od in order_by_day.items():
        if not any(x.get("day") == day for x in d.get("daily", [])):
            daily_rows += (
                f'<tr><td>{esc(day)}</td><td><div class="daybar"><b>0</b></div></td><td class="n">0</td>'
                f'<td class="n">{int(od.get("orders", 0) or 0)}</td>'
                f'<td class="n">RD$ {float(od.get("revenue", 0) or 0):,.0f}</td></tr>'
            )

    recent_rows = ""
    type_names = {"view":"浏览", "addcart":"加购", "whatsapp":"WhatsApp", "checkout":"订单确认",
                  "checkout_start":"到达结账", "checkout_error":"结账受阻", "color_select":"选颜色",
                  "tier_select":"选优惠", "gallery_view":"查看主图", "review_open":"查看评论图",
                  "calculator_success":"使用计算器", "cart_update":"修改数量", "cart_remove":"移除商品",
                  "order":"正式下单", "scroll":"滚动", "engagement":"停留"}
    for x in d.get("recent", [])[:50]:
        ts = time.strftime("%m-%d %H:%M", time.localtime((x.get("ts", 0) or 0) / 1000))
        geo = " · ".join(v for v in (x.get("city", ""), x.get("region", "")) if v)
        source = x.get("utm_campaign") or x.get("code") or x.get("utm_source") or "直接访问"
        detail = ""
        if x.get("type") == "addcart":
            detail = f'×{int(x.get("qty", 0) or 0)} · RD$ {float(x.get("cart_total", 0) or 0):,.0f}'
        elif x.get("selected_color"):
            detail = str(x.get("selected_color"))
        elif x.get("type") == "calculator_success":
            detail = f'{float(x.get("wall_width",0) or 0):g}×{float(x.get("wall_height",0) or 0):g} cm → {int(x.get("calculated_qty",0) or 0)} 卷'
        elif x.get("source_section"):
            detail = str(x.get("source_section"))
        recent_rows += (
            f'<tr><td>{ts}</td><td><span class="etype">{esc(type_names.get(x.get("type"), x.get("type", "")))}</span></td>'
            f'<td><b>{esc(x.get("ip_full") or x.get("ip_masked", ""))}</b><small>{esc(geo)}</small></td>'
            f'<td>{esc(x.get("device_type") or "未知")}</td><td><code>{esc(source)}</code></td>'
            f'<td>{esc(detail)}</td></tr>'
        )

    funnel_steps = [
        ("访问墙纸页", visitors),
        ("有效互动", int(s.get("engaged_sessions", 0) or 0)),
        ("选择颜色", int(s.get("color_sessions", 0) or 0)),
        ("查看多件优惠", int(s.get("offer_sessions", 0) or 0)),
        ("使用计算器", int(s.get("calculator_sessions", 0) or 0)),
        ("加入购物车", addcarts),
        ("到达结账页", int(s.get("checkout_sessions", 0) or 0)),
        ("正式下单", orders),
    ]
    funnel_html = ""
    for i, (label, value) in enumerate(funnel_steps):
        prev = funnel_steps[i - 1][1] if i else visitors
        funnel_html += (f'<div class="wf-step"><span>{esc(label)}</span><b>{value}</b>'
                        f'<small>{("起点" if i == 0 else pct(value, prev))}</small></div>')

    status_names = {"pending":"待确认", "confirmed":"已确认", "shipping":"配送中",
                    "completed":"已完成", "cancelled":"已取消"}
    status_html = "".join(
        f'<div class="status-chip"><span>{esc(status_names.get(x.get("status"), x.get("status", "")))}</span>'
        f'<b>{int(x.get("orders",0) or 0)}</b><small>{int(x.get("units",0) or 0)} 卷 · RD$ {float(x.get("revenue",0) or 0):,.0f}</small></div>'
        for x in d.get("order_status", [])
    ) or '<div class="empty">暂无订单状态数据</div>'

    color_rows = "".join(
        f'<tr><td><b>{esc(x.get("color") or "未标记")}</b></td><td class="n">{int(x.get("selectors",0) or 0)}</td>'
        f'<td class="n">{int(x.get("carts",0) or 0)}</td><td class="n">{int(x.get("units",0) or 0)}</td></tr>'
        for x in d.get("colors", [])
    )
    source_rows = "".join(
        f'<tr><td><b>{esc(x.get("source") or "未标记")}</b></td><td class="n">{int(x.get("sessions",0) or 0)}</td>'
        f'<td class="n">{int(x.get("actions",0) or 0)}</td><td class="n">{int(x.get("units",0) or 0)}</td></tr>'
        for x in d.get("add_sources", [])
    )
    device_rows = "".join(
        f'<tr><td><b>{esc(x.get("device") or "未知")}</b></td><td class="n">{int(x.get("sessions",0) or 0)}</td>'
        f'<td class="n">{int(x.get("carts",0) or 0)} ({pct(int(x.get("carts",0) or 0),int(x.get("sessions",0) or 0))})</td>'
        f'<td class="n">{int(x.get("whatsapps",0) or 0)}</td><td class="n">{float(x.get("avg_seconds",0) or 0):.0f}s</td></tr>'
        for x in d.get("devices", [])
    )
    region_rows = "".join(
        f'<tr><td><b>{esc(x.get("region") or "未知")}</b></td><td class="n">{int(x.get("sessions",0) or 0)}</td>'
        f'<td class="n">{int(x.get("carts",0) or 0)}</td><td class="n">{int(x.get("whatsapps",0) or 0)}</td></tr>'
        for x in d.get("regions", [])
    )
    q = d.get("quality") or {}
    unattributed = d.get("unattributed_orders") or {}
    quality_note = (f'统计以会话为主口径。历史数据中有 {int(q.get("multi_vid_sessions",0) or 0)} 个会话曾对应多个访客 ID，'
                    f'有 {int(q.get("addcarts_without_total",0) or 0)} 条旧加购缺少购物车金额；'
                    f'{int(unattributed.get("actual_orders",0) or 0)} 个旧订单因当时未保存 UTM 被列为未归因，不会错误计入直接访问。新版本上线后会逐步消除这些误差。')

    empty = '<tr><td colspan="9" class="empty">还没有墙纸广告数据</td></tr>'
    tabs = "".join(
        f'<a class="{"on" if days == n else ""}" href="/wallpaper-stats?days={n}">近 {n} 天</a>'
        for n in (7, 30, 90)
    )
    inner = (
        f'{_warn(err)}<style>'
        '.w-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:16px}'
        '.w-head h1{margin:0}.periods{display:flex;gap:6px}.periods a{padding:8px 11px;border:1px solid #DCE4EF;border-radius:7px;color:#536176;text-decoration:none;font-size:12px;font-weight:800;background:#fff}.periods a.on{background:#2563D9;color:#fff;border-color:#2563D9}'
        '.w-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.w-kpi{background:#fff;border:1px solid #E5EAF2;border-radius:8px;padding:14px}.w-kpi span,.w-kpi small{display:block;color:#6D7A8D;font-size:11px}.w-kpi b{display:block;font-size:24px;margin:5px 0;color:#172033}.w-kpi small{line-height:1.35}'
        '.w-title{font-size:17px;margin:24px 0 10px}.table-scroll{overflow:auto}.table-scroll table{min-width:780px}.daybar{display:flex;align-items:center;gap:8px;min-width:180px}.daybar i{display:block;height:8px;background:#2563D9;border-radius:4px;max-width:140px}.daybar b{font-size:12px}.etype{display:inline-block;padding:3px 7px;border-radius:5px;background:#EDF3FF;color:#2563D9;font-size:11px;font-weight:800}td small{display:block;color:#8A96A7;margin-top:3px}'
        '.w-note{margin-top:12px;color:#6D7A8D;font-size:12px;line-height:1.55}'
        '.wf{display:grid;grid-template-columns:repeat(8,1fr);gap:8px}.wf-step,.status-chip{padding:12px;border:1px solid #E5EAF2;border-radius:8px;background:#fff}.wf-step span,.wf-step small,.status-chip span,.status-chip small{display:block;color:#6D7A8D;font-size:10px}.wf-step b,.status-chip b{display:block;margin:4px 0;font-size:21px}.statuses{display:flex;gap:8px;flex-wrap:wrap}.status-chip{min-width:150px}.split-tables{display:grid;grid-template-columns:1fr 1fr;gap:14px}.data-alert{margin:12px 0;padding:11px 13px;border:1px solid #F2D38A;border-radius:8px;background:#FFF9E8;color:#76520B;font-size:12px;line-height:1.5}.cost-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.cost-grid input{width:100%;padding:9px;border:1px solid #DCE4EF;border-radius:7px}.cost-grid label{display:block;margin-bottom:4px;color:#68758a;font-size:10px}'
        '@media(max-width:900px){.w-kpis{grid-template-columns:repeat(2,1fr)}.w-head{align-items:flex-start;flex-direction:column}.wf{grid-template-columns:repeat(2,1fr)}.split-tables{grid-template-columns:1fr}.cost-grid{grid-template-columns:1fr}}'
        '</style><div class="w-head"><div><h1>墙纸广告数据</h1>'
        f'<div class="sub">固定商品 {sku} · Panel decorativo autoadhesivo</div></div>'
        f'<div class="periods">{tabs}</div></div><div class="w-kpis">{kpi_html}</div>'
        f'<div class="w-note">平均停留 {float(s.get("avg_seconds",0) or 0):.0f} 秒 · 平均滚动 {float(s.get("avg_scroll",0) or 0):.0f}%。'
        f' 其中 {int(s.get("meta_network_visitors",0) or 0)} 个访客来自 Meta/Facebook 网络，可能包含广告预览或代理流量，先保留但不要直接当成真实客户。'
        '订单和销售额按订单商品明细精确计算；渠道转化按访问过墙纸页的同一会话归因。</div>'
        f'<div class="data-alert">{esc(quality_note)}</div>'
        f'<h2 class="w-title">墙纸转化漏斗</h2><div class="wf">{funnel_html}</div>'
        f'<h2 class="w-title">订单质量</h2><div class="statuses">{status_html}</div>'
        f'<h2 class="w-title">广告渠道表现</h2><div class="table-scroll"><table><thead><tr>'
        '<th>渠道/活动</th><th>会话</th><th>加购</th><th>加购率</th><th>WhatsApp</th><th>实际订单</th><th>停留</th><th>花费</th><th>每次加购成本</th>'
        f'</tr></thead><tbody>{channel_rows or empty}</tbody></table></div>'
        f'<div class="split-tables"><div><h2 class="w-title">颜色选择与加购</h2><div class="table-scroll"><table><thead><tr><th>颜色</th><th>选择会话</th><th>加购会话</th><th>加购卷数</th></tr></thead><tbody>{color_rows or empty}</tbody></table></div></div>'
        f'<div><h2 class="w-title">加购入口</h2><div class="table-scroll"><table><thead><tr><th>入口</th><th>会话</th><th>动作</th><th>卷数</th></tr></thead><tbody>{source_rows or empty}</tbody></table></div></div></div>'
        f'<div class="split-tables"><div><h2 class="w-title">设备表现</h2><div class="table-scroll"><table><thead><tr><th>设备</th><th>会话</th><th>加购率</th><th>WhatsApp</th><th>停留</th></tr></thead><tbody>{device_rows or empty}</tbody></table></div></div>'
        f'<div><h2 class="w-title">地区表现</h2><div class="table-scroll"><table><thead><tr><th>地区</th><th>会话</th><th>加购</th><th>WhatsApp</th></tr></thead><tbody>{region_rows or empty}</tbody></table></div></div></div>'
        f'<h2 class="w-title">每日趋势</h2><div class="table-scroll"><table><thead><tr>'
        f'<th>日期</th><th>访客</th><th>加购访客</th><th>订单</th><th>销售额</th></tr></thead><tbody>{daily_rows or empty}</tbody></table></div>'
        f'<h2 class="w-title">最近墙纸行为</h2><div class="table-scroll"><table><thead><tr>'
        f'<th>时间</th><th>行为</th><th>IP / 地区</th><th>设备</th><th>渠道</th><th>详情</th></tr></thead><tbody>{recent_rows or empty}</tbody></table></div>'
        '<h2 class="w-title">录入墙纸广告成本</h2><div class="cardp frm"><div class="cost-grid"><div><label>日期</label><input id="costDay" type="date"></div><div><label>Meta 活动 ID / UTM campaign</label><input id="costCampaign"></div><div><label>来源</label><input id="costSource" value="facebook"></div><div><label>花费 RD$</label><input id="costSpend" type="number"></div><div><label>展示量</label><input id="costImp" type="number"></div><div><label>广告点击</label><input id="costClicks" type="number"></div></div><button class="pri" onclick="saveCost()">保存广告成本</button></div>'
        + _ANALYTICS_JS
    )
    return sub_shell("墙纸广告数据", "wallpaper", inner)

_ORDER_JS = """<script>
var STATUS={pending:'待确认',confirmed:'已确认',shipping:'配送中',completed:'已完成',cancelled:'已取消'};
async function orderStatus(sel){var id=sel.dataset.id,old=sel.dataset.old;sel.disabled=true;
 try{var r=await fetch('/order_status',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({order_id:id,status:sel.value})});if(!r.ok)throw new Error(await r.text());
  sel.dataset.old=sel.value;sel.closest('.order-card').dataset.status=sel.value;
 }catch(e){sel.value=old;alert('状态更新失败：'+e.message)}finally{sel.disabled=false}}
function orderFilter(){var q=document.getElementById('orderQ').value.toLowerCase(),s=document.getElementById('orderS').value;
 document.querySelectorAll('.order-card').forEach(function(x){x.style.display=(!s||x.dataset.status===s)&&(!q||x.textContent.toLowerCase().includes(q))?'':'none'})}
</script>"""

def orders_page():
    data, err = worker_call("orders")
    orders = (data or {}).get("orders", [])
    status_names = {"pending":"待确认", "confirmed":"已确认", "shipping":"配送中",
                    "completed":"已完成", "cancelled":"已取消"}
    cards = ""
    counts = {k: 0 for k in status_names}
    for o in orders:
        status = o.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
        items = ""
        for it in o.get("items", []):
            src = admin_image_src(it.get("image", ""))
            img_html = f'<img src="{src}" alt="">' if src else '<div class="item-noimg">无图</div>'
            items += (f'<div class="order-item">'
                      f'{img_html}'
                      f'<div class="item-main"><b>{esc(it.get("title",""))}</b><small>{esc(it.get("sku",""))}</small></div>'
                      f'<div class="item-qty">× {int(it.get("quantity",1) or 1)}</div>'
                      f'<div class="item-money">RD$ {float(it.get("line_total",0) or 0):,.0f}</div></div>')
        opts = "".join(f'<option value="{k}" {"selected" if k == status else ""}>{v}</option>'
                       for k, v in status_names.items())
        phone = re.sub(r"\D", "", str(o.get("phone", "")))
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime((o.get("created_at",0) or 0) / 1000))
        location = " · ".join(x for x in (o.get("province",""), o.get("zone","")) if x)
        geo = " · ".join(x for x in (o.get("city",""), o.get("region",""), o.get("postal_code","")) if x)
        note_html = f'<div class="order-note">备注：{esc(o.get("note",""))}</div>' if o.get("note") else ""
        map_url = str(o.get("map_url") or "").strip()
        if map_url:
            map_html = f'<a class="order-map" href="{esc(map_url)}" target="_blank" rel="noopener">📍 打开 Google Maps / Waze</a>'
        elif o.get("location_followup"):
            map_html = '<small class="location-pending">📍 客户稍后通过 Waze / WhatsApp 补发定位</small>'
        else:
            map_html = ""
        preferred_date = str(o.get("preferred_delivery_date") or "").strip()
        preferred_window = str(o.get("preferred_delivery_window") or "").strip()
        delivery_pref_html = (f'<div class="delivery-pref">🕒 客户希望：{esc(preferred_date)} · {esc(preferred_window)}</div>'
                              if preferred_date or preferred_window else "")
        ship_min = float(o.get("shipping_fee_min", o.get("shipping_fee", 0)) or 0)
        ship_max = float(o.get("shipping_fee_max", o.get("shipping_fee", 0)) or 0)
        total_min = float(o.get("total_min", o.get("total", 0)) or 0)
        total_max = float(o.get("total_max", o.get("total", 0)) or 0)
        shipping_text = (f'RD$ {ship_min:,.0f}–{ship_max:,.0f}' if ship_max > ship_min
                         else f'RD$ {ship_min:,.0f}')
        total_text = (f'预计总计 RD$ {total_min:,.0f}–{total_max:,.0f}' if total_max > total_min
                      else f'总计 RD$ {total_min:,.0f}')
        cards += (f'<article class="order-card" data-status="{esc(status)}">'
                  f'<header><div><b class="order-id">{esc(o.get("order_id",""))}</b><time>{created}</time></div>'
                  f'<select data-id="{esc(o.get("order_id",""))}" data-old="{esc(status)}" onchange="orderStatus(this)">{opts}</select></header>'
                  f'<div class="order-customer"><div><strong>{esc(o.get("customer_name",""))}</strong>'
                  f'<a href="https://wa.me/{phone}" target="_blank">WhatsApp {esc(o.get("phone",""))}</a></div>'
                  f'<div><span>{esc(location)}</span><small>{esc(o.get("address",""))}</small>{map_html}</div>'
                  f'<div><span>IP {esc(o.get("ip_full") or o.get("ip_masked",""))}</span><small>{esc(geo)}</small></div></div>'
                  f'<div class="order-items">{items}</div><footer>'
                  f'<span>{"转账" if o.get("payment_method") == "transfer" else "货到付款"}'
                  f' · 预计运费 {shipping_text}'
                  f'{(" · "+esc(o.get("delivery_estimate",""))) if o.get("delivery_estimate") else ""}'
                  f'{(" · 优惠码 "+esc(o.get("coupon_code"))) if o.get("coupon_code") else ""}</span>'
                  f'<div>小计 RD$ {float(o.get("subtotal",0) or 0):,.0f}'
                  f'{(" · 优惠 -RD$ "+format(float(o.get("discount",0) or 0), ",.0f")) if o.get("discount") else ""}'
                  f' · 预计运费 {shipping_text}'
                  f' <b>{total_text}</b></div></footer>'
                  f'{delivery_pref_html}'
                  f'{note_html}</article>')
    stat_html = "".join(f'<div class="stat"><div class="v">{counts.get(k,0)}</div><div class="l">{v}</div></div>'
                        for k, v in status_names.items())
    order_cards_html = cards or '<div class="empty-orders">还没有客户提交订单</div>'
    inner = (f'{_warn(err)}<style>'
             '.order-tools{display:flex;gap:10px;margin-bottom:16px}.order-tools input,.order-tools select{border:1.5px solid #E5EAF2;border-radius:10px;padding:10px 12px;background:#fff}.order-tools input{flex:1}'
             '.order-list{display:flex;flex-direction:column;gap:14px}.order-card{background:#fff;border:1px solid #E3E9F2;border-radius:14px;overflow:hidden}.order-card>header{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:#F8FAFD}.order-id{font-size:16px}.order-card time{font-size:11px;color:#8792a4;margin-left:10px}.order-card select{border:1px solid #DCE4EF;border-radius:9px;padding:8px;background:#fff;font-weight:700}'
             '.order-customer{display:grid;grid-template-columns:1fr 1.4fr 1fr;gap:14px;padding:13px 16px;border-bottom:1px solid #EEF2F7}.order-customer div{display:flex;flex-direction:column;gap:4px}.order-customer a{color:#138a4b;font-size:12px;font-weight:700;text-decoration:none}.order-customer span{font-size:13px;font-weight:700}.order-customer small{color:#7d8999;line-height:1.35}'
             '.order-customer .order-map{color:#2563D9;margin-top:3px}.location-pending{color:#986A12!important;font-weight:700}.delivery-pref{margin:0 16px 11px;padding:9px 11px;border-radius:9px;background:#EEF4FF;color:#2455A8;font-size:12px;font-weight:800}'
             '.order-items{padding:4px 16px}.order-item{display:grid;grid-template-columns:54px minmax(0,1fr) 52px 90px;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid #F0F3F7}.order-item img,.item-noimg{width:54px;height:54px;border-radius:7px;object-fit:cover;background:#F1F4F8}.item-noimg{display:grid;place-items:center;font-size:10px;color:#9aa3b2}.item-main{display:flex;flex-direction:column;gap:4px}.item-main b{font-size:13px}.item-main small{color:#8b96a6}.item-qty{font-weight:800}.item-money{text-align:right;font-weight:800}'
             '.order-card>footer{display:flex;justify-content:space-between;gap:12px;padding:13px 16px}.order-card>footer span{font-size:12px;color:#68758a}.order-card>footer b{margin-left:12px;font-size:16px}.order-note{padding:0 16px 13px;color:#68758a;font-size:12px}.empty-orders{padding:50px;text-align:center;color:#8d98a8}'
             '@media(max-width:720px){.order-customer{grid-template-columns:1fr}.order-card>footer{flex-direction:column}.order-item{grid-template-columns:48px minmax(0,1fr) 34px 76px}.order-item img,.item-noimg{width:48px;height:48px}}'
             '</style><h1>订单 <span class="sub">客户确认购物车后自动进入这里</span></h1>'
             f'<div class="stats">{stat_html}</div><div class="order-tools"><input id="orderQ" placeholder="搜索订单、客户、电话、IP、商品" oninput="orderFilter()">'
             '<select id="orderS" onchange="orderFilter()"><option value="">全部状态</option>'
             + "".join(f'<option value="{k}">{v}</option>' for k,v in status_names.items()) + '</select></div>'
             f'<div class="order-list">{order_cards_html}</div>' + _ORDER_JS)
    return sub_shell("订单", "orders", inner)

def cart_visitors_page():
    data, err = worker_call("cart-visitors")
    product_by_sku = {p.get("sku"): p for p in products()}
    rows = ""
    for e in (data or {}).get("events", []):
        p = product_by_sku.get(e.get("sku"), {})
        img = e.get("product_img") or p.get("img", "")
        title = e.get("product_title") or p.get("title") or e.get("sku", "")
        src = admin_image_src(img)
        img_html = f'<img src="{src}">' if src else ""
        ts = time.strftime("%m-%d %H:%M", time.localtime((e.get("ts",0) or 0) / 1000))
        geo = " · ".join(x for x in (e.get("city",""), e.get("region",""), e.get("postal_code","")) if x)
        rows += (f'<tr><td>{ts}</td><td><b>{esc(e.get("ip_full") or e.get("ip_masked",""))}</b><br><small>{esc(geo)}</small></td>'
                 f'<td><div class="cart-product">{img_html}<div><b>{esc(title)}</b><small>{esc(e.get("sku",""))}</small></div></div></td>'
                 f'<td class="n">{int(e.get("qty",0) or 0)}</td><td class="n">RD$ {float(e.get("cart_total",0) or 0):,.0f}</td>'
                 f'<td><code>{esc(e.get("code") or "直接访问")}</code></td></tr>')
    empty_row = '<tr><td colspan="6" class="empty">暂无新格式的加购记录</td></tr>'
    filtered = int((data or {}).get("filtered_invalid", 0) or 0)
    quality_note = (f'<div class="data-note">已隐藏 {filtered} 条旧格式无效记录（数量或金额为 0）。</div>'
                    if filtered else "")
    inner = (f'{_warn(err)}<style>.cart-table{{overflow:auto}}.cart-table table{{min-width:850px}}.cart-product{{display:flex;align-items:center;gap:9px;min-width:260px}}.cart-product img{{width:48px;height:48px;border-radius:7px;object-fit:cover}}.cart-product div{{display:flex;flex-direction:column;gap:4px}}small{{color:#8994a4}}.data-note{{margin:0 0 12px;padding:10px 12px;border-radius:8px;background:#FFF7E6;color:#765614;font-size:12px}}'
             f'</style><h1>加购访客 <span class="sub">最近30天，查看哪个IP加购了什么</span></h1>'
             f'{quality_note}'
             f'<div class="cart-table"><table><thead><tr><th>时间</th><th>IP / 位置</th><th>商品</th><th>数量</th><th>购物车金额</th><th>来源短链</th></tr></thead><tbody>{rows if rows else empty_row}</tbody></table></div>')
    return sub_shell("加购访客", "carts", inner)

# ===== 专题合集管理 =====
COLLECTIONS_PATH = "data/collections.json"

def _snorm(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def load_collections():
    if os.path.isfile(COLLECTIONS_PATH):
        try:
            with open(COLLECTIONS_PATH, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, list) else []
        except Exception:
            return []
    return []

def save_collections(data):
    os.makedirs(os.path.dirname(COLLECTIONS_PATH), exist_ok=True)
    with open(COLLECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def coll_slugify(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "coleccion"

_COLL_JS = """<script>
var COLLS=__COLLS__, PRODS=__PRODS__, TYPES=__TYPES__, picked={}, order=[], editSlug='';
var INITIAL_EDIT='__EDIT__', INITIAL_FOCUS='__FOCUS__', currentProduct='', pendingPhoto=null, photoTargetFile='';
function esc(s){return (s==null?'':String(s)).replace(/[&<>\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]})}
function product(s){return PRODS.find(function(p){return p.sku===s})}
function count(){document.getElementById('pcnt').textContent=order.filter(function(s){return picked[s]}).length}
function renderBoard(){
 var box=document.getElementById('collectionBoard'),html='',n=0;
 order.forEach(function(s){
  if(!picked[s])return;var p=product(s);if(!p)return;n++;
  var opts=TYPES.map(function(t){return '<option '+(t===p.c?'selected':'')+' value=\"'+esc(t)+'\">'+esc(t)+'</option>'}).join('');
  html+='<article class=\"collection-product\" data-sku=\"'+esc(p.sku)+'\" data-h=\"'+esc(p.h)+'\" data-img=\"'+esc(p.img)+'\">'
   +'<div class=\"cp-num\">'+String(n).padStart(2,'0')+'</div><button class=\"cp-photo-button\" onclick=\"openProductPhotos(\\''+p.sku+'\\')\"><img class=\"cp-img\" src=\"/images/'+esc(p.img)+'\" onerror=\"this.style.opacity=.2\"><span>编辑图片</span></button>'
   +'<div class=\"cp-fields\"><input class=\"cp-title\" value=\"'+esc(p.t)+'\"><div class=\"cp-line\"><span>RD$</span><input class=\"cp-price\" type=\"number\" step=\"any\" value=\"'+esc(p.p)+'\" placeholder=\"价格\"><select class=\"cp-type\">'+opts+'</select></div>'
   +'<div class=\"cp-actions\"><button class=\"save-prod\" onclick=\"saveProduct(this)\">保存商品</button><button class=\"edit-prod\" onclick=\"openProductEdit(\\''+p.sku+'\\')\">编辑详情</button><button class=\"photo-prod\" onclick=\"openProductPhotos(\\''+p.sku+'\\')\">图片</button><button class=\"remove-prod\" onclick=\"removeSku(\\''+p.sku+'\\')\">移出专题</button><button class=\"move-prod\" onclick=\"moveSku(\\''+p.sku+'\\',-1)\">↑</button><button class=\"move-prod\" onclick=\"moveSku(\\''+p.sku+'\\',1)\">↓</button><a class=\"preview-prod\" href=\"/preview-product?handle='+encodeURIComponent(p.h)+'\" target=\"_blank\">预览</a></div></div></article>';
 });
 box.innerHTML=html||'<div class=\"board-empty\">这个专题还没有商品。点击“添加商品”开始。</div>';count();
 if(INITIAL_FOCUS){var el=document.querySelector('.collection-product[data-sku=\"'+INITIAL_FOCUS+'\"],.collection-product[data-h=\"'+INITIAL_FOCUS+'\"]');if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.add('focus-prod')}}
}
function renderPicker(){
 var q=(document.getElementById('pq').value||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
 var box=document.getElementById('picker'),html='';
 PRODS.forEach(function(p){if(q&&p.q.indexOf(q)<0)return;
  html+='<label class=\"add-row\"><input type=\"checkbox\" '+(picked[p.sku]?'checked':'')+' onchange=\"toggleSku(\\''+p.sku+'\\',this.checked)\"><img src=\"/images/'+esc(p.img)+'\"><span>'+esc(p.t)+'</span></label>';});
 box.innerHTML=html||'<div class=\"board-empty\">没有匹配商品</div>';
}
function toggleSku(s,on){picked[s]=on;if(on&&!order.includes(s))order.push(s);if(!on)order=order.filter(function(x){return x!==s});renderBoard();renderPicker()}
function removeSku(s){if(!confirm('只从这个专题中移出商品？'))return;toggleSku(s,false)}
function moveSku(s,d){var i=order.indexOf(s),j=i+d;if(i<0||j<0||j>=order.length)return;var x=order[i];order[i]=order[j];order[j]=x;renderBoard()}
async function saveProduct(btn){
 var row=btn.closest('.collection-product'),p=product(row.dataset.sku);
 var fd=new URLSearchParams({handle:row.dataset.h,title:row.querySelector('.cp-title').value,price:row.querySelector('.cp-price').value,type:row.querySelector('.cp-type').value});
 btn.disabled=true;var r=await fetch('/update',{method:'POST',body:fd});btn.disabled=false;
 if(r.ok){p.t=row.querySelector('.cp-title').value;p.p=row.querySelector('.cp-price').value;p.c=row.querySelector('.cp-type').value;btn.textContent='已保存';setTimeout(function(){btn.textContent='保存商品'},1300)}
 else alert('商品保存失败：'+await r.text());
}
async function openProductEdit(s){
 var p=product(s);if(!p)return;window.currentProduct=s;
 document.getElementById('editTitle').value=p.t||'';document.getElementById('editPrice').value=p.p||'';
 document.getElementById('editType').innerHTML=TYPES.map(function(t){return '<option '+(t===p.c?'selected':'')+' value=\"'+esc(t)+'\">'+esc(t)+'</option>'}).join('');
 var r=await fetch('/body?handle='+encodeURIComponent(p.h));document.getElementById('editBody').value=await r.text();productEditDlg.showModal();
}
async function saveProductEdit(btn){
 var p=product(window.currentProduct);if(!p)return;
 var fd=new URLSearchParams({handle:p.h,title:document.getElementById('editTitle').value,price:document.getElementById('editPrice').value,type:document.getElementById('editType').value,body:document.getElementById('editBody').value});
 btn.disabled=true;var r=await fetch('/update',{method:'POST',body:fd});btn.disabled=false;
 if(!r.ok){alert('详情保存失败：'+await r.text());return}
 p.t=fd.get('title');p.p=fd.get('price');p.c=fd.get('type');p.b=fd.get('body');productEditDlg.close();renderBoard();
}
async function openProductPhotos(s){
 var p=product(s);if(!p)return;window.currentProduct=s;pendingPhoto=null;photoTargetFile='';clearPhotoPreview();setPhotoMode('');
 var r=await fetch('/photos?handle='+encodeURIComponent(p.h));var ps=await r.json();
 document.getElementById('photoGrid').innerHTML=ps.map(function(x){return '<div class=\"photo-cell\"><img src=\"/images/'+esc(x.file)+'?v='+Date.now()+'\"><span>'+esc(x.label)+'</span><div><button class=\"replace-photo\" onclick=\"selectPhotoTarget(\\''+x.file+'\\',\\''+esc(x.label)+'\\')\">替换</button><button class=\"delete-photo\" onclick=\"deleteProductPhoto(\\''+x.file+'\\')\">删除</button></div></div>'}).join('');
 photoDlg.showModal();
}
function setPhotoMode(label){
 var m=document.getElementById('photoMode'),slot=document.getElementById('photoSlot');
 if(label){m.textContent='正在替换：'+label;slot.disabled=true}else{m.textContent='新增图片';slot.disabled=false}
}
function selectPhotoTarget(file,label){photoTargetFile=file;pendingPhoto=null;clearPhotoPreview();setPhotoMode(label);document.getElementById('photoPaste').focus()}
function addPhotoMode(){photoTargetFile='';pendingPhoto=null;clearPhotoPreview();setPhotoMode('')}
async function deleteProductPhoto(f){
 if(!confirm('确认删除这张图片？'))return;var p=product(window.currentProduct);
 var r=await fetch('/photo_del',{method:'POST',body:new URLSearchParams({handle:p.h,file:f})});
 if(r.ok)openProductPhotos(window.currentProduct);else alert('删除失败：'+await r.text());
}
function showPhotoError(m){var d=document.getElementById('photoError');d.textContent=m;d.style.display='block'}
function clearPhotoPreview(){var im=document.getElementById('photoPrev');im.removeAttribute('src');im.style.display='none';document.getElementById('photoHint').style.display='block'}
function stagePhoto(file){
 if(!file||!file.type.startsWith('image/'))return showPhotoError('请选择有效图片');
 if(file.size>20*1024*1024)return showPhotoError('图片超过 20 MB，请先压缩');
 var im=new Image(),rd=new FileReader();rd.onload=function(e){im.onload=function(){
  var max=2400,scale=Math.min(1,max/Math.max(im.naturalWidth,im.naturalHeight)),cv=document.createElement('canvas');cv.width=Math.round(im.naturalWidth*scale);cv.height=Math.round(im.naturalHeight*scale);cv.getContext('2d').drawImage(im,0,0,cv.width,cv.height);
  cv.toBlob(function(blob){if(!blob)return showPhotoError('图片无法处理');pendingPhoto=blob;document.getElementById('photoPrev').src=URL.createObjectURL(blob);document.getElementById('photoPrev').style.display='block';document.getElementById('photoHint').style.display='none';document.getElementById('photoError').style.display='none'},'image/jpeg',.88)
 };im.onerror=function(){showPhotoError('图片无法读取')};im.src=e.target.result};rd.readAsDataURL(file)
}
function previewPhotoFile(){var f=document.getElementById('photoFile').files[0];if(f)stagePhoto(f);else showPhotoError('请先选择图片')}
async function uploadProductPhoto(btn){
 if(!pendingPhoto)return showPhotoError('请先选择或粘贴图片并预览');
 var p=product(window.currentProduct),fd=new FormData();fd.append('handle',p.h);fd.append('slot',document.getElementById('photoSlot').value);fd.append('image',pendingPhoto,'pasted-photo.jpg');
 if(photoTargetFile)fd.append('file',photoTargetFile);
 btn.disabled=true;var r=await fetch(photoTargetFile?'/photo_replace':'/photo_add',{method:'POST',body:fd});btn.disabled=false;
 if(r.ok){pendingPhoto=null;clearPhotoPreview();openProductPhotos(window.currentProduct)}else showPhotoError('上传失败：'+await r.text())
}
function newColl(){editSlug='';picked={};order=[];document.getElementById('cTitle').value='';document.getElementById('cSub').value='';document.getElementById('cCta').value='';document.getElementById('cImg').value='';document.getElementById('cActive').checked=true;document.getElementById('cOrder').value=0;document.getElementById('edTitle').textContent='＋ 新建专题';renderBoard()}
function edit(slug){var c=COLLS.find(function(x){return x.slug===slug});if(!c)return;editSlug=slug;picked={};order=(c.skus||[]).slice();order.forEach(function(s){picked[s]=true});document.getElementById('cTitle').value=c.title||'';document.getElementById('cSub').value=c.subtitle||'';document.getElementById('cCta').value=c.cta||'';document.getElementById('cImg').value=c.image||'';document.getElementById('cActive').checked=c.active!==false;document.getElementById('cOrder').value=c.order||0;document.getElementById('edTitle').textContent='✏️ 编辑：'+(c.title||'');renderBoard();document.getElementById('cTitle').scrollIntoView({behavior:'smooth',block:'center'})}
function save(){var skus=order.filter(function(s){return picked[s]}),title=document.getElementById('cTitle').value.trim();if(!title){alert('请填写专题名称');return}if(!skus.length){alert('专题至少需要一个商品');return}var body={slug:editSlug,title:title,subtitle:document.getElementById('cSub').value.trim(),cta:document.getElementById('cCta').value.trim(),image:document.getElementById('cImg').value.trim(),active:document.getElementById('cActive').checked,order:parseInt(document.getElementById('cOrder').value)||0,skus:skus};fetch('/coleccion_save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json()}).then(function(d){if(d.ok)location.reload();else alert(d.error||'保存失败')})}
function toggle(slug){fetch('/coleccion_save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slug:slug,toggle:true})}).then(function(){location.reload()})}
function del_(slug){if(!confirm('删除专题？（不会删除商品）'))return;fetch('/coleccion_del',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slug:slug})}).then(function(){location.reload()})}
var photoPaste=document.getElementById('photoPaste');
photoPaste.onclick=function(){photoPaste.focus()};
photoPaste.addEventListener('paste',function(ev){var items=[...(ev.clipboardData||{}).items||[]],it=items.find(function(x){return x.type.startsWith('image/')});if(!it)return showPhotoError('剪贴板中没有图片');ev.preventDefault();stagePhoto(it.getAsFile())});
renderPicker();if(INITIAL_EDIT)edit(INITIAL_EDIT);else renderBoard();
</script>"""

def colecciones_page(edit_slug="", focus_sku=""):
    colls = load_collections()
    prods = products()
    rows = ""
    for c in colls:
        nskus = len(c.get("skus", []))
        act = c.get("active") is not False
        slug = esc(c.get("slug", ""))
        rows += (f'<div class="ccard" data-t="{esc((c.get("title") or "").lower())}">'
                 f'<div class="cc-top"><b>{esc(c.get("title",""))}</b>'
                 f'<span class="tag {"on" if act else "off"}">{"上架" if act else "下架"}</span></div>'
                 f'<div class="slug">/coleccion/{slug} · {nskus} 个商品 · 排序 {c.get("order",0)}</div>'
                 f'<div class="cc-acts"><button class="cp" onclick="edit(\'{slug}\')">✏️ 编辑</button>'
                 f'<button class="cp" onclick="toggle(\'{slug}\')">{"下架" if act else "上架"}</button>'
                 f'<a class="cp" href="{SITE_URL}/coleccion/{slug}.html" target="_blank">👁 线上</a>'
                 f'<button class="cp del" onclick="del_(\'{slug}\')">删除</button></div></div>')
    prods_json = json.dumps([
        {"sku": p["sku"], "h": p["handle"], "t": p["title"], "img": p["img"],
         "p": p["price"], "c": p["type"], "b": p.get("body", ""),
         "q": _snorm(p["title"] + " " + p.get("type", ""))} for p in prods if p["sku"]],
        ensure_ascii=False)
    types_json = json.dumps(sorted({p.get("type", "") for p in prods if p.get("type", "")}), ensure_ascii=False)
    colls_json = json.dumps(colls, ensure_ascii=False)
    inner = (
        '<h1>🪴 专题合集 <span class="sub">首页突出入口 + 专属专题页</span></h1>'
        '<div style="display:flex;gap:10px;margin-bottom:14px;align-items:center">'
        '<button class="pri" style="width:auto;margin:0" onclick="newColl()">＋ 新建专题</button>'
        '<input id="cq" placeholder="搜索专题…" style="flex:1;border:1.5px solid #E5EAF2;border-radius:99px;padding:10px 16px;font-size:13px;font-family:inherit;outline:none" '
        'oninput="var q=this.value.toLowerCase();document.querySelectorAll(\'.ccard\').forEach(function(c){c.style.display=c.dataset.t.includes(q)?\'\':\'none\'})"></div>'
        '<div class="ccards">'
        + (rows or '<div class="empty">还没有专题，点「新建专题」开始</div>')
        + '</div>'
        '<div class="cardp" style="margin-top:20px"><div class="frm">'
        '<div id="edTitle" style="font-weight:800;font-size:15px;margin-bottom:12px">＋ Nuevo tema</div>'
        '<label>专题名字（客户可见，西语）</label>'
        '<input id="cTitle" placeholder="Ej: 🪴 Plantas para tu hogar">'
        '<label>副标题（可选）</label>'
        '<input id="cSub" placeholder="Ej: Nuestra selección de esta semana">'
        '<label>按钮文字 CTA（可选，默认"Ver los N productos"）</label>'
        '<input id="cCta" placeholder="Ej: Ver toda la colección">'
        '<label>Hero 背景图（可选，填 images/ 里的文件名，如 VB123ABC.jpg 或某商品的 _scene 图）</label>'
        '<input id="cImg" placeholder="Ej: VB6F3904C8_scene.jpg">'
        '<div class="row2"><div><label>排序（小的在前）</label><input id="cOrder" type="number" value="0"></div>'
        '<div><label>状态</label><label style="display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;margin-top:8px">'
        '<input id="cActive" type="checkbox" checked style="width:18px;height:18px"> 上架显示</label></div></div>'
        '<div class="board-head"><div><b>专题商品</b><span class="pcnt" id="pcnt">0</span><span class="board-hint">可直接修改商品信息，鼠标滚轮浏览</span></div>'
        '<button class="pri add-btn" onclick="addDlg.showModal();renderPicker()">＋ 添加商品</button></div>'
        '<div id="collectionBoard" class="collection-board"></div>'
        '<button class="pri" onclick="save()">保存专题</button>'
        '</div></div>'
        '<dialog id="addDlg"><h3>添加商品到专题</h3><input id="pq" placeholder="搜索商品名…" oninput="renderPicker()"><div id="picker" class="picker"></div><div class="row" style="margin-top:12px"><button class="btn" onclick="addDlg.close()">完成</button></div></dialog>'
        '<dialog id="productEditDlg"><h3>编辑商品</h3><label>商品标题</label><input id="editTitle"><label>价格 RD$</label><input id="editPrice" type="number" step="any"><label>分类</label><select id="editType"></select><label>详情描述</label><textarea id="editBody" rows="10"></textarea><div class="row"><button class="btn b-add" style="flex:1" onclick="saveProductEdit(this)">保存商品</button><button class="btn" onclick="productEditDlg.close()">取消</button></div></dialog>'
        '<dialog id="photoDlg"><h3>编辑商品图片</h3><div class="photo-help">点击某张图片下方的“替换”，然后粘贴或选择新图片；“新增图片”会保留原图。</div><div id="photoGrid" class="photo-grid"></div><div class="photo-mode"><b id="photoMode">新增图片</b><button class="btn" onclick="addPhotoMode()">＋ 新增图片</button></div><div class="paste-box" id="photoPaste" tabindex="0"><span id="photoHint">点击这里后按 ⌘V 粘贴图片</span><img id="photoPrev"></div><div class="ferr" id="photoError"></div><div class="photo-upload"><select id="photoSlot"><option value="extra">＋ 补充图</option><option value="dim">＋ 尺寸图</option><option value="scene">＋ 场景图</option></select><input id="photoFile" type="file" accept="image/*" onchange="previewPhotoFile()"><button class="btn b-add" onclick="previewPhotoFile()">预览</button><button class="btn b-add" onclick="uploadProductPhoto(this)">确认保存</button></div><button class="btn" onclick="photoDlg.close()">关闭</button></dialog>'
        + _COLL_JS.replace("__COLLS__", colls_json).replace("__PRODS__", prods_json).replace("__TYPES__", types_json)
                    .replace("__EDIT__", esc(edit_slug)).replace("__FOCUS__", esc(focus_sku)))
    extra_css = (
        '<style>.slug{font-size:11px;color:#8a93a2;font-weight:600;margin-top:2px}'
        '.ccards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-bottom:6px}'
        '.ccard{background:#fff;border:1px solid #EDF1F7;border-radius:15px;padding:14px}'
        '.cc-top{display:flex;align-items:center;justify-content:space-between;gap:8px}'
        '.cc-top b{font-size:14.5px}'
        '.cc-acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:11px}'
        '.cc-acts .cp{margin-left:0;text-decoration:none}'
        '.acts{white-space:nowrap}.cp.del{color:#c0392b}'
        '.board-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:4px 0 12px}'
        '.board-head b{font-size:16px}.board-hint{font-size:12px;color:#8a93a2;margin-left:9px}'
        '.pcnt{display:inline-block;background:#2563D9;color:#fff;border-radius:99px;padding:2px 8px;font-weight:800;margin-left:7px;font-size:12px}'
        '.add-btn{width:auto;margin:0;padding:9px 13px;font-size:13px}'
        '.collection-board{display:flex;flex-direction:column;gap:9px;margin-bottom:16px}'
        '.collection-product{display:grid;grid-template-columns:34px 86px minmax(0,1fr);gap:12px;align-items:center;background:#fff;border:1px solid #E7ECF4;border-radius:13px;padding:9px 11px}'
        '.collection-product.focus-prod{border-color:#2563D9;box-shadow:0 0 0 3px rgba(37,99,217,.13)}'
        '.cp-num{font-weight:800;color:#9aa3b2;text-align:center}.cp-photo-button{position:relative;padding:0;border:0;border-radius:10px;background:#F0F3F8;cursor:pointer;overflow:hidden}.cp-photo-button span{position:absolute;left:0;right:0;bottom:0;background:rgba(22,32,46,.78);color:#fff;font-size:11px;font-weight:800;padding:5px}.cp-img{display:block;width:86px;height:86px;object-fit:cover;background:#F0F3F8}'
        '.cp-fields{min-width:0}.cp-title{width:100%;border:1px solid #E5EAF2;border-radius:8px;padding:8px 9px;font:600 14px inherit}.cp-line{display:flex;gap:7px;margin-top:7px}.cp-line span{align-self:center;color:#8a93a2;font-weight:700;font-size:12px}.cp-price,.cp-type{border:1px solid #E5EAF2;border-radius:8px;padding:7px;font:13px inherit}.cp-price{width:130px}.cp-type{min-width:190px;flex:1}.cp-actions{display:flex;gap:6px;align-items:center;margin-top:8px}.cp-actions button,.preview-prod{border:0;border-radius:7px;padding:7px 9px;font-size:11px;font-weight:800;cursor:pointer;text-decoration:none}.save-prod{background:#2563D9;color:#fff}.remove-prod{background:#FFF0EE;color:#C0392B}.move-prod{background:#EEF4FF;color:#2563D9;width:28px}.preview-prod{background:#F1F5FB;color:#2563D9}.board-empty{text-align:center;background:#F7F9FD;border:1px dashed #C9D6EC;border-radius:12px;padding:28px;color:#8a93a2;font-size:13px}'
        '#productEditDlg label{display:block;font-size:12px;font-weight:700;color:#5a6577;margin:10px 0 5px}#productEditDlg input,#productEditDlg select,#productEditDlg textarea{width:100%;border:1px solid #E5EAF2;border-radius:9px;padding:9px;font:14px inherit;margin-bottom:4px}'
        '.photo-help{font-size:12px;color:#68758a;line-height:1.5;margin:-5px 0 12px}.photo-grid{display:grid;grid-template-columns:repeat(4,minmax(80px,1fr));gap:8px;margin-bottom:14px}.photo-cell{border:1px solid #E7ECF4;border-radius:9px;overflow:hidden}.photo-cell img{display:block;width:100%;aspect-ratio:1;object-fit:cover}.photo-cell span{display:block;padding:5px 6px;font-size:10px;font-weight:700}.photo-cell div{display:flex;gap:4px;padding:0 5px 6px}.photo-cell button{flex:1;border:0;border-radius:5px;padding:5px 3px;font-size:10px;font-weight:800;cursor:pointer}.replace-photo{background:#EEF4FF;color:#2563D9}.delete-photo{background:#FFF0EE;color:#C0392B}.photo-mode{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 8px;font-size:12px}.photo-mode .btn{padding:6px 9px;font-size:11px}'
        '.paste-box{border:2px dashed #C9D6EC;border-radius:12px;min-height:80px;display:flex;align-items:center;justify-content:center;text-align:center;padding:10px;color:#7b8798;font-size:12px;margin-bottom:10px}.paste-box:focus{outline:none;border-color:#2563D9}.paste-box img{display:none;max-width:100%;max-height:160px}.photo-upload{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px}.photo-upload select{flex:1;min-width:120px;border:1px solid #E5EAF2;border-radius:8px;padding:8px}.photo-upload input{max-width:180px}'
        '.picker{max-height:60vh;overflow-y:auto;border:1px solid #EDF1F7;border-radius:12px;margin-top:12px}'
        '.add-row{display:flex;align-items:center;gap:10px;padding:9px 10px;border-bottom:1px solid #F4F6FB;font-size:13px;cursor:pointer}.add-row img{width:46px;height:46px;border-radius:8px;object-fit:cover;background:#F0F3F8}.add-row input{width:17px;height:17px;flex:none}.add-row span{flex:1}.pmore{padding:10px;text-align:center;color:#9aa3b2;font-size:12px}'
        '@media(max-width:640px){.collection-product{grid-template-columns:26px 64px minmax(0,1fr);gap:8px}.cp-img{width:64px;height:64px}.cp-line{flex-wrap:wrap}.cp-price{width:110px}.cp-type{min-width:130px}.board-hint{display:none}.cp-actions{flex-wrap:wrap}}'
        '</style>')
    return sub_shell("专题合集", "coll", extra_css + inner)

def product_preview_page(p):
    photos = sku_photos_by_img(p.get("img", "")) if p.get("img") else []
    gallery = "".join(f'<img src="/images/{esc(f)}" alt="" loading="lazy">' for f in photos)
    body = esc(p.get("body", "") or p.get("title", "")).replace("\n", "<br>")
    price = esc(p.get("price", ""))
    price_html = f"RD$ {price}" if price else "Consultar precio por WhatsApp"
    online = f'{SITE_URL}/producto/{quote(p["handle"])}.html'
    return f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vista previa — {esc(p["title"])}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f9fd;color:#16202e;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.bar{{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #e9edf3;padding:12px 18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.bar strong{{font-size:14px}}.bar a{{background:#eef4ff;color:#2563d9;text-decoration:none;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:700}}
.wrap{{max-width:1060px;margin:0 auto;padding:28px 18px 60px}}.crumb{{color:#7b8798;font-size:13px;margin-bottom:18px}}
.detail{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(280px,.9fr);gap:34px;background:#fff;border:1px solid #edf1f7;border-radius:18px;padding:22px}}
.main{{width:100%;aspect-ratio:1;object-fit:contain;background:#f2f4f8;border-radius:12px}}.gallery{{display:flex;gap:8px;overflow:auto;margin-top:10px}}
.gallery img{{width:68px;height:68px;object-fit:cover;border-radius:8px;border:1px solid #e4eaf2}}h1{{font-size:28px;line-height:1.2;margin:18px 0 12px}}.price{{font-size:25px;font-weight:800;color:#176b50;margin-bottom:26px}}
.label{{font-size:12px;color:#718096;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}}.desc{{font-size:15px;line-height:1.65;color:#435064;white-space:normal}}
@media(max-width:720px){{.detail{{grid-template-columns:1fr;padding:14px;gap:8px}}h1{{font-size:23px}}}}
</style></head><body><div class="bar"><strong>即时详情预览</strong><span style="font-size:12px;color:#7b8798">使用当前已保存的数据，不需要构建</span><a href="{online}" target="_blank">打开线上页面</a></div>
<main class="wrap"><div class="crumb">VivaBien / {esc(p.get("type", ""))}</div><div class="detail"><div>
<img class="main" src="/images/{esc(photos[0] if photos else p.get("img", ""))}" alt="{esc(p["title"])}">
<div class="gallery">{gallery}</div></div><div><h1>{esc(p["title"])}</h1><div class="price">{price_html}</div><div class="label">Descripción</div><div class="desc">{body}</div></div></div></main></body></html>'''

LAUNCH_LABEL = os.environ.get("VIVABIEN_LAUNCH_LABEL", "com.vivabien.shop-admin")

def _launchd_managed():
    """当前后台是否由 macOS LaunchAgent 常驻托管"""
    try:
        r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCH_LABEL}"],
                           capture_output=True, timeout=6)
        return r.returncode == 0
    except Exception:
        return False

def restart_admin():
    """后台自重启：LaunchAgent 托管时交给 launchd，否则自己拉起新进程。"""
    if _launchd_managed():
        # launchd 会 kill 当前进程并按 KeepAlive 重新拉起，端口不会冲突
        try:
            subprocess.Popen(["launchctl", "kickstart", "-k",
                              f"gui/{os.getuid()}/{LAUNCH_LABEL}"],
                             start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass  # 掉到自启逻辑兜底
    script = os.path.abspath(sys.argv[0])
    cwd = os.getcwd()
    helper = (
        "import os,subprocess,sys,time; "
        "time.sleep(1.2); "
        "env=os.environ.copy(); env['VIVABIEN_NO_BROWSER']='1'; "
        "subprocess.Popen([sys.executable, sys.argv[1]], cwd=sys.argv[2], "
        "env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
    )
    subprocess.Popen([sys.executable, "-c", helper, script, cwd],
                     cwd=cwd, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

WORKER_STAMP = ".worker_deployed"

# LaunchAgent 启动的进程 PATH 很精简（常常只有 /usr/bin:/bin），
# 找不到 Homebrew/nvm 装的 npx、node、git。这里主动补齐。
_EXTRA_BIN_DIRS = [
    "/opt/homebrew/bin", "/usr/local/bin", "/opt/homebrew/opt/node/bin",
    os.path.expanduser("~/.volta/bin"), os.path.expanduser("~/.bun/bin"),
    "/usr/bin", "/bin",
]
def _bin_dirs():
    import glob as _glob
    dirs = list(_EXTRA_BIN_DIRS)
    for pat in (os.path.expanduser("~/.nvm/versions/node/*/bin"),
                "/opt/homebrew/opt/node@*/bin",
                "/usr/local/opt/node@*/bin"):
        dirs.extend(sorted(_glob.glob(pat), reverse=True))
    return [d for d in dirs if os.path.isdir(d)]

def cmd_env():
    """给子进程一个能找到 npx/node/git 的 PATH"""
    env = os.environ.copy()
    parts = [d for d in _bin_dirs()]
    for d in (env.get("PATH") or "").split(":"):
        if d and d not in parts:
            parts.append(d)
    env["PATH"] = ":".join(parts)
    return env

def find_bin(name):
    """先按当前 PATH 找，再到常见安装目录找，返回绝对路径或 None"""
    p = shutil.which(name, path=cmd_env()["PATH"])
    if p:
        return p
    for d in _bin_dirs():
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None

def worker_needs_deploy():
    """worker 源码是否比上次部署新"""
    src = "worker/src/index.js"
    if not os.path.isfile(src):
        return False
    if not os.path.isfile(WORKER_STAMP):
        return True
    return os.path.getmtime(src) > os.path.getmtime(WORKER_STAMP)

def deploy_worker():
    """部署边缘接口 Worker（短链/埋点/优惠券/统计）"""
    npx = find_bin("npx")
    if not npx:
        return False, ("找不到 npx（Node.js）。后台由系统服务启动时环境变量较少，"
                       "已尝试 Homebrew / nvm / volta 常见路径仍未找到。\n"
                       "解决：确认已安装 Node.js；或在终端执行 `which npx` 把路径告诉我。")
    r = subprocess.run([npx, "wrangler", "deploy"], cwd="worker", env=cmd_env(),
                       capture_output=True, text=True, timeout=900)
    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        with open(WORKER_STAMP, "w") as f:
            f.write(str(time.time()))
    return r.returncode == 0, out

def page_html():
    prods = products()
    cats = sorted({p["type"] for p in prods if p["type"].strip()})
    cat_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in cats)
    coll_by_sku = {}
    for coll in load_collections():
        for sku in coll.get("skus", []):
            coll_by_sku.setdefault(sku, []).append({"slug": coll.get("slug", ""), "title": coll.get("title", "")})
    # 商品数据整体下发给浏览器，前端先挂载60个、滚动懒加载（1000+商品不再卡顿）
    prods_json = json.dumps([
        {"h": p["handle"], "t": p["title"], "p": p["price"], "c": p["type"],
         "img": p["img"], "n": len(sku_photos_by_img(p["img"])) if p["img"] else 0,
         "tp": coll_by_sku.get(p["sku"], [])} for p in prods], ensure_ascii=False)
    cats_json = json.dumps(cats, ensure_ascii=False)
    return f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VivaBien 商品管理</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#F7F9FD;color:#16202E;padding-bottom:60px}}
.top{{position:sticky;top:0;background:#fff;border-bottom:1px solid #EEF1F6;padding:12px 18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:10}}
.top b{{font-size:17px;margin-right:6px}}
.top input{{flex:1;min-width:140px;border:1.5px solid #E5EAF2;border-radius:99px;padding:9px 16px;font-size:14px;outline:none}}
.btn{{border:0;border-radius:99px;padding:10px 18px;font-weight:700;font-size:13px;cursor:pointer}}
.b-add{{background:#2563D9;color:#fff}}
.b-build{{background:#64748b;color:#fff}}
.b-pub{{background:#FF6B4A;color:#fff}}
#catSel{{border:1.5px solid #E5EAF2;border-radius:99px;padding:9px 13px;font-size:13px;font-family:inherit;background:#fff;max-width:150px}}
.more{{position:relative}}
.b-more{{background:#F1F5FB;color:#2563D9;font-size:16px;padding:10px 15px}}
.more-menu{{display:none;position:absolute;right:0;top:44px;background:#fff;border:1px solid #E5EAF2;border-radius:15px;box-shadow:0 14px 40px rgba(20,40,80,.16);padding:7px;min-width:170px;z-index:30}}
.more-menu.show{{display:block}}
.more-menu a,.more-menu button{{display:block;width:100%;text-align:left;padding:11px 13px;border:0;background:none;color:#16202E;font-weight:700;font-size:13.5px;border-radius:10px;cursor:pointer;text-decoration:none;font-family:inherit}}
.more-menu a:hover,.more-menu button:hover{{background:#F1F5FB}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;padding:16px 18px}}
.card{{background:#fff;border:1px solid #EDF1F7;border-radius:16px;overflow:hidden}}
.card.focus-card{{border-color:#2563D9;box-shadow:0 0 0 4px rgba(37,99,217,.16)}}
.imgw{{position:relative}}
.card img{{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}}
.nimg{{position:absolute;bottom:8px;right:8px;background:rgba(22,32,46,.75);color:#fff;font-size:11px;font-weight:700;padding:3px 8px;border-radius:99px}}
.body{{padding:10px 12px 12px;display:flex;flex-direction:column;gap:8px}}
.ti{{width:100%;border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:12.5px;font-family:inherit;resize:vertical}}
.row{{display:flex;gap:6px;align-items:center}}
.cur{{font-weight:700;font-size:13px;color:#8a93a2}}
.pr{{flex:1;border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:14px;font-weight:700;width:100%}}
.ca{{border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:12px;background:#fff}}
.topics{{min-height:24px;font-size:11px;color:#8a93a2}}
.topic-btn{{border:0;background:#EEF4FF;color:#2563D9;border-radius:8px;padding:5px 8px;font-size:11px;font-weight:700;cursor:pointer}}
.empty-topic{{padding:3px 2px}}
.preview-link{{text-decoration:none;display:inline-flex;align-items:center;justify-content:center}}
.coll-choice{{display:block;text-decoration:none;color:#2563D9;background:#F1F5FB;border-radius:10px;padding:12px;margin:8px 0;font-weight:700;font-size:13px}}
.save{{flex:1;background:#2563D9;color:#fff;border:0;border-radius:9px;padding:9px;font-weight:700;cursor:pointer}}
.save.ok{{background:#157A4E}}
.mini{{background:#F1F5FB;color:#2563D9;border:0;border-radius:9px;padding:9px 8px;font-size:12px;font-weight:700;cursor:pointer}}
.del{{background:#fff;color:#c0392b;border:1px solid #f0d0cc;border-radius:9px;padding:9px 10px;cursor:pointer}}
dialog{{border:0;border-radius:20px;padding:24px;width:min(520px,94vw);box-shadow:0 20px 60px rgba(20,40,80,.25);max-height:92vh;overflow-y:auto}}
dialog h3{{margin-bottom:16px;font-size:17px}}
dialog input,dialog select,dialog textarea{{width:100%;border:1.5px solid #E5EAF2;border-radius:11px;padding:11px;font-size:14px;margin-bottom:12px;font-family:inherit}}
dialog input:focus,dialog select:focus,dialog textarea:focus{{outline:none;border-color:#2563D9}}
dialog::backdrop{{background:rgba(20,30,50,.45);backdrop-filter:blur(2px)}}
.flb{{display:block;font-weight:700;font-size:12px;color:#5a6577;margin:0 0 5px 2px}}
.row2{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.ferr{{display:none;background:#FDECEA;color:#c0392b;font-size:13px;font-weight:600;border-radius:10px;padding:9px 12px;margin-bottom:12px}}
.drop{{border:2px dashed #C9D6EC;border-radius:16px;background:#F7F9FD;text-align:center;padding:0;margin-bottom:14px;cursor:pointer;overflow:hidden;position:relative}}
.drop.over{{border-color:#2563D9;background:#EAF0FB}}
.drop-in{{padding:26px 10px}}
#dropPrev{{display:none;width:100%;max-height:220px;object-fit:contain;background:#fff}}
.ph-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:10px;margin-bottom:14px}}
.ph{{position:relative;border:1px solid #EDF1F7;border-radius:12px;overflow:hidden}}
.ph img{{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}}
.ph .lb{{position:absolute;top:6px;left:6px;background:rgba(37,99,217,.9);color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:99px}}
.ph .rm{{position:absolute;top:6px;right:6px;background:rgba(192,57,43,.9);color:#fff;border:0;width:22px;height:22px;border-radius:99px;font-size:12px;cursor:pointer;line-height:1}}
.uprow{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.paste-box{{border:2px dashed #C9D6EC;border-radius:14px;background:#F7F9FD;min-height:92px;margin:0 0 12px;display:flex;align-items:center;justify-content:center;text-align:center;padding:10px;cursor:pointer;color:#68758a;font-size:12px}}
.paste-box:focus,.paste-box.active{{border-color:#2563D9;background:#EAF0FB;outline:none}}
#pastePrev{{display:none;max-width:100%;max-height:180px;object-fit:contain;background:#fff;border-radius:8px}}
#log{{position:fixed;left:12px;right:12px;bottom:12px;background:#16202E;color:#9fe8c1;border-radius:14px;display:none;z-index:99;box-shadow:0 14px 40px rgba(0,0,0,.3)}}
#logTxt{{font:12px/1.6 ui-monospace,monospace;padding:12px 40px 12px 15px;white-space:pre-wrap;max-height:40vh;overflow:auto}}
#logX{{position:absolute;top:8px;right:9px;border:0;background:rgba(255,255,255,.12);color:#fff;width:24px;height:24px;border-radius:99px;cursor:pointer;font-size:12px}}
</style></head><body>
<div class="top">
<b>🛠️ VivaBien</b>
<input id="q" placeholder="搜索商品…" oninput="filt()">
<select id="catSel" onchange="filt()"><option value="*">全部分类</option>{cat_opts}</select>
<button class="btn b-add" onclick="dlg.showModal()">＋ 添加</button>
<button class="btn b-build" onclick="build(this)">🔄 预览</button>
<button class="btn b-pub" onclick="publish(this)">🚀 发布</button>
<div class="more">
<button class="btn b-more" id="moreBtn" onclick="moreMenu.classList.toggle('show');event.stopPropagation()">⋯</button>
<div class="more-menu" id="moreMenu">
<a href="/orders">订单</a>
<a href="/cart-visitors">加购访客</a>
<a href="/import">📥 流水线导入</a>
<a href="/colecciones">🪴 专题合集</a>
<a href="/marketing">📣 营销留存</a>
<a href="/stats">📊 数据</a>
<a href="/wallpaper-stats">墙纸广告</a>
<a href="{REVIEW_URL}" target="_blank">🧪 审核台</a>
<button onclick="deployWorker(this)">⚡ 部署接口</button>
<button onclick="envCheck(this)">🔎 环境自检</button>
<button onclick="restartAdmin(this)">🔄 重启后台</button>
</div>
</div>
<span id="cnt" style="color:#8a93a2;font-size:13px">{len(prods)} 个商品</span>
</div>
<div class="grid" id="grid"></div>
<div id="sentinel" style="height:60px"></div>

<dialog id="dlgColl">
<h3>🪴 选择专题</h3>
<div id="collChoices"></div>
<div class="row" style="margin-top:14px"><button class="btn" onclick="dlgColl.close()">取消</button></div>
</dialog>

<dialog id="dlg">
<h3>＋ 添加新商品</h3>
<div class="drop" id="drop">
<input type="file" id="a-f" accept="image/*" hidden>
<div class="drop-in" id="dropHint">
<div style="font-size:30px">📷</div>
<div style="font-weight:700;font-size:14px;margin-top:4px">点击或拖拽上传主图</div>
<div style="font-size:12px;color:#8a93a2;margin-top:2px">jpg / png，建议白底方图</div>
</div>
<img id="dropPrev">
</div>
<div class="ferr" id="aErr"></div>
<label class="flb">商品标题（西语，客户可见）*</label>
<input id="a-t" placeholder="Ej: Espejo decorativo redondo 50cm">
<label class="flb">中文名（只在后台和表格里，可选）</label>
<input id="a-zh" placeholder="例如：圆形装饰镜 50cm">
<div class="row2">
<div><label class="flb">价格 RD$</label><input id="a-p" type="number" step="any" placeholder="留空 = Consultar"></div>
<div><label class="flb">分类</label><select id="a-c">{cat_opts}</select></div>
</div>
<label class="flb">详情描述（西语，可选，留空自动用标题）</label>
<textarea id="a-b" rows="4" placeholder="📦 Características:&#10;• 50cm&#10;• Marco dorado"></textarea>
<div class="row" style="margin-top:6px">
<button class="btn b-add" style="flex:1;padding:13px" onclick="add(this)">保存商品</button>
<button class="btn" onclick="dlg.close()">取消</button>
</div>
</dialog>

<dialog id="dlgDesc">
<h3>✏️ 编辑详情描述（西语，客户可见）</h3>
<textarea id="d-body" rows="10"></textarea>
<div class="row">
<button class="btn b-add" style="flex:1" onclick="saveDesc(this)">保存</button>
<button class="btn" onclick="dlgDesc.close()">取消</button>
</div>
</dialog>

<dialog id="dlgPh">
<h3>📷 商品图片</h3>
<div class="ph-grid" id="phGrid"></div>
<div class="paste-box" id="pasteBox" tabindex="0">
<div id="pasteHint">点击这里后按 ⌘V 粘贴图片，或使用下面的文件选择</div>
<img id="pastePrev">
</div>
<div class="ferr" id="phErr"></div>
<div class="uprow">
<select id="ph-slot" style="flex:1;margin:0">
<option value="extra">＋ 补充图</option>
<option value="dim">＋ 尺寸图</option>
<option value="scene">＋ 场景图</option>
<option value="main">↻ 替换主图</option>
</select>
<input id="ph-f" type="file" accept="image/*" style="flex:2;margin:0">
<button class="btn b-add" onclick="stageFromFile()">预览</button>
</div>
<div class="row" style="margin-top:12px"><button class="btn b-add" style="flex:1" onclick="upPhoto(this)">确认上传</button></div>
<div class="row" style="margin-top:12px">
<button class="btn" onclick="dlgPh.close()">关闭</button>
</div>
</dialog>
<div id="log"><button id="logX" onclick="document.getElementById('log').style.display='none'">✕</button><div id="logTxt"></div></div>

<script>
let curH='', curImg='', pendingPhoto=null, logT=null;
const PRODS={prods_json}, CATS={cats_json};
// 日志面板：短消息自动消失，长日志（构建/发布）保留到手动关闭
const log = m => {{
 const d=document.getElementById('log');d.style.display='block';
 document.getElementById('logTxt').textContent=m;
 clearTimeout(logT);
 if((m||'').length<80)logT=setTimeout(()=>d.style.display='none',6000);
}};
document.addEventListener('click',()=>moreMenu.classList.remove('show'));
function eh(s){{return (s==null?'':String(s)).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
const orig={{}};
// 前端渲染商品卡：先挂载60个，滚动到底自动加载下一批
function cardHTML(p){{
 const opts=CATS.map(c=>'<option '+(c===p.c?'selected':'')+' value="'+eh(c)+'">'+eh(c)+'</option>').join('');
 const tp=(p.tp&&p.tp.length)
  ?'<div class="topics"><button class="topic-btn" data-colls="'+eh(JSON.stringify(p.tp))+'" onclick="openColls(this);event.stopPropagation()">🪴 所属专题（'+p.tp.length+'）</button></div>'
  :'<div class="topics empty-topic">尚未加入专题</div>';
 return '<div class="card" data-t="'+eh((p.t||'').toLowerCase())+'" data-h="'+eh(p.h)+'" data-img="'+eh(p.img)+'">'
  +'<div class="imgw"><img src="/images/'+encodeURIComponent(p.img)+'" loading="lazy" onerror="this.style.opacity=.15">'
  +'<span class="nimg">📸 '+p.n+'</span></div>'
  +'<div class="body"><textarea class="ti" rows="2">'+eh(p.t)+'</textarea>'
  +'<div class="row"><span class="cur">RD$</span><input class="pr" type="number" step="any" value="'+eh(p.p)+'" placeholder="价格"></div>'
  +'<select class="ca">'+opts+'</select>'+tp
  +'<div class="row"><button class="save" onclick="save(this)">保存</button>'
  +'<button class="mini" onclick="openDesc(this)">✏️ 详情</button>'
  +'<button class="mini" onclick="openPhotos(this)">📷 图片</button>'
  +'<a class="mini preview-link" href="/preview-product?handle='+encodeURIComponent(p.h)+'" target="_blank">👁 预览</a>'
  +'<button class="del" onclick="del_(this)">✕</button></div></div></div>';
}}
let flist=PRODS, shown=0;
const grid=document.getElementById('grid');
function more(){{
 const end=Math.min(shown+60,flist.length);let html='';
 for(let i=shown;i<end;i++){{const p=flist[i];html+=cardHTML(p);orig[p.h]={{t:p.t,p:String(p.p||''),c:p.c}};}}
 grid.insertAdjacentHTML('beforeend',html);shown=end;
}}
function filt(){{
 const q=(document.getElementById('q').value||'').toLowerCase();
 const cat=document.getElementById('catSel').value;
 flist=PRODS.filter(p=>(!q||(p.t||'').toLowerCase().includes(q))&&(cat==='*'||p.c===cat));
 grid.innerHTML='';shown=0;more();
 document.getElementById('cnt').textContent=flist.length+' 个商品';
}}
new IntersectionObserver(es=>{{if(es[0].isIntersecting&&shown<flist.length)more()}},{{rootMargin:'600px'}})
 .observe(document.getElementById('sentinel'));
filt();
async function save(btn){{
 const c=btn.closest('.card'),h=c.dataset.h;
 const t=c.querySelector('.ti').value,p=c.querySelector('.pr').value,ca=c.querySelector('.ca').value;
 const o=orig[h]||{{}};
 const changes=[];
 if(t!==o.t)changes.push('标题: '+o.t+'\\n  → '+t);
 if(p!==o.p)changes.push('价格: RD$ '+(o.p||'空')+' → RD$ '+(p||'空'));
 if(ca!==o.c)changes.push('分类: '+o.c+' → '+ca);
 if(!changes.length){{log('没有改动，无需保存');return}}
 if(!confirm('确认保存以下修改？\\n\\n'+changes.join('\\n')))return;
 const fd=new URLSearchParams({{handle:h,title:t,price:p,type:ca}});
 const r=await fetch('/update',{{method:'POST',body:fd}});
 if(r.ok){{orig[h]={{t:t,p:p,c:ca}};
  const pe=PRODS.find(x=>x.h===h);if(pe){{pe.t=t;pe.p=p;pe.c=ca}}
  btn.textContent='✓ 已保存';btn.classList.add('ok');setTimeout(()=>{{btn.textContent='保存';btn.classList.remove('ok')}},1500)}}
 else log('保存失败: '+await r.text());
}}
async function del_(btn){{
 if(!confirm('确定删除这个商品？图片也会一起删除。'))return;
 const c=btn.closest('.card'),h=c.dataset.h;
 const r=await fetch('/delete',{{method:'POST',body:new URLSearchParams({{handle:h}})}});
 if(r.ok){{c.remove();const i=PRODS.findIndex(x=>x.h===h);if(i>=0)PRODS.splice(i,1);}}
 else log('删除失败');
}}
async function openDesc(btn){{
 const c=btn.closest('.card');curH=c.dataset.h;
 const r=await fetch('/body?handle='+encodeURIComponent(curH));
 document.getElementById('d-body').value=await r.text();
 dlgDesc.showModal();
}}
async function saveDesc(btn){{
 if(!confirm('确认保存详情描述？客户在商品页会看到新内容。'))return;
 const fd=new URLSearchParams({{handle:curH,body:document.getElementById('d-body').value}});
 const r=await fetch('/update',{{method:'POST',body:fd}});
 if(r.ok){{dlgDesc.close();log('详情已保存')}}else log('保存失败: '+await r.text());
}}
async function openPhotos(btn){{
 const c=btn.closest('.card');curH=c.dataset.h;curImg=c.dataset.img;
 pendingPhoto=null;clearPhotoPreview();document.getElementById('phErr').style.display='none';
 await refreshPhotos();
 dlgPh.showModal();
}}
async function refreshPhotos(){{
 const r=await fetch('/photos?handle='+encodeURIComponent(curH));
 const ps=await r.json();
 document.getElementById('phGrid').innerHTML=ps.map(p=>
  '<div class="ph"><img src="/images/'+p.file+'?v='+Date.now()+'"><span class="lb">'+p.label+'</span>'
  +'<button class="rm" onclick="delPhoto(\\''+p.file+'\\')">✕</button></div>').join('');
}}
async function delPhoto(f){{
 if(!confirm('删除这张图片？'))return;
 const r=await fetch('/photo_del',{{method:'POST',body:new URLSearchParams({{handle:curH,file:f}})}});
 if(r.ok)refreshPhotos();else log('删除失败: '+await r.text());
}}
async function upPhoto(btn){{
 if(!pendingPhoto){{showPhotoError('请先选择或粘贴图片，并预览后再确认上传');return}}
 btn.disabled=true;btn.textContent='上传中…';
 const fd=new FormData();
 fd.append('handle',curH);
 fd.append('slot',document.getElementById('ph-slot').value);
 fd.append('image',pendingPhoto,'pasted-photo.jpg');
 const r=await fetch('/photo_add',{{method:'POST',body:fd}});
 btn.disabled=false;btn.textContent='上传';
 if(r.ok){{document.getElementById('ph-f').value='';pendingPhoto=null;clearPhotoPreview();await refreshPhotos();log('图片已保存')}}
 else showPhotoError('上传失败：'+await r.text());
}}
function showPhotoError(m){{const d=document.getElementById('phErr');d.textContent=m;d.style.display='block'}}
function clearPhotoPreview(){{const im=document.getElementById('pastePrev');im.removeAttribute('src');im.style.display='none';document.getElementById('pasteHint').style.display='block'}}
function stageFromFile(){{const f=document.getElementById('ph-f').files[0];if(f)stagePhoto(f);else showPhotoError('请先选择图片')}}
function stagePhoto(file){{
 if(!file||!file.type.startsWith('image/')){{showPhotoError('剪贴板或文件中没有可用的图片');return}}
 if(file.size>20*1024*1024){{showPhotoError('图片原文件超过 20 MB，请先压缩后再试');return}}
 const im=new Image(),rd=new FileReader();
 rd.onload=e=>{{im.onload=()=>{{
   const max=2400,scale=Math.min(1,max/Math.max(im.naturalWidth,im.naturalHeight));
   const cv=document.createElement('canvas');cv.width=Math.max(1,Math.round(im.naturalWidth*scale));cv.height=Math.max(1,Math.round(im.naturalHeight*scale));
   cv.getContext('2d').drawImage(im,0,0,cv.width,cv.height);
   cv.toBlob(blob=>{{if(!blob){{showPhotoError('图片无法处理，请换一张图片');return}}
     pendingPhoto=blob;document.getElementById('pastePrev').src=URL.createObjectURL(blob);document.getElementById('pastePrev').style.display='block';
     document.getElementById('pasteHint').style.display='none';document.getElementById('phErr').style.display='none';
   }},'image/jpeg',.88);
 }};im.onerror=()=>showPhotoError('图片无法读取，请换一种图片格式');im.src=e.target.result}};
 rd.readAsDataURL(file);
}}
const pasteBox=document.getElementById('pasteBox');
pasteBox.onclick=()=>pasteBox.focus();
pasteBox.addEventListener('paste',ev=>{{const items=[...(ev.clipboardData||{{}}).items||[]];const it=items.find(x=>x.type.startsWith('image/'));if(!it){{showPhotoError('剪贴板中没有图片');return}}ev.preventDefault();stagePhoto(it.getAsFile())}});
document.getElementById('ph-f').onchange=stageFromFile;
function openColls(btn){{
 const cs=JSON.parse(btn.dataset.colls||'[]');
 document.getElementById('collChoices').innerHTML=cs.map(c=>'<a class="coll-choice" href="/colecciones?edit='+encodeURIComponent(c.slug)+'&focus='+encodeURIComponent(btn.closest('.card').dataset.h)+'">🪴 '+esc(c.title)+'</a>').join('');
 dlgColl.showModal();
}}
// 添加商品：拖拽/点击传图 + 预览
const drop=document.getElementById('drop'),fInput=document.getElementById('a-f'),
      prev=document.getElementById('dropPrev'),hint=document.getElementById('dropHint');
drop.onclick=()=>fInput.click();
fInput.onchange=()=>showPrev(fInput.files[0]);
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{{ev.preventDefault();drop.classList.add('over')}}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{{ev.preventDefault();drop.classList.remove('over')}}));
drop.addEventListener('drop',ev=>{{
 const f=ev.dataTransfer.files[0];
 if(f&&f.type.startsWith('image/')){{
  const dt=new DataTransfer();dt.items.add(f);fInput.files=dt.files;showPrev(f);}}
}});
function showPrev(f){{
 if(!f)return;
 const rd=new FileReader();
 rd.onload=e=>{{prev.src=e.target.result;prev.style.display='block';hint.style.display='none'}};
 rd.readAsDataURL(f);
}}
function aerr(m){{
 const d=document.getElementById('aErr');
 if(!m){{d.style.display='none';return}}
 d.textContent=m;d.style.display='block';d.scrollIntoView({{block:'nearest'}});
}}
async function add(btn){{
 aerr('');
 const f=fInput.files[0];
 const t=document.getElementById('a-t').value.trim();
 const p=document.getElementById('a-p').value.trim();
 const c=document.getElementById('a-c').value;
 if(!f){{aerr('还没有上传主图');return}}
 if(!t){{aerr('请填写西语标题（客户看到的名字）');return}}
 if(p&&(isNaN(p)||Number(p)<0)){{aerr('价格格式不对');return}}
 if(!confirm('确认添加这个商品？\\n\\n'+t+'\\n价格: '+(p?'RD$ '+p:'Consultar（待定价）')+'\\n分类: '+c))return;
 btn.disabled=true;btn.textContent='⏳ 上传中…';
 const fd=new FormData();
 fd.append('title',t);
 fd.append('price',p);
 fd.append('type',c);
 fd.append('zh',document.getElementById('a-zh').value);
 fd.append('body',document.getElementById('a-b').value);
 fd.append('image',f);
 const r=await fetch('/add',{{method:'POST',body:fd}});
 if(r.ok)location.reload();else{{aerr('添加失败: '+await r.text());btn.disabled=false;btn.textContent='保存商品'}}
}}
async function build(btn){{
 btn.disabled=true;btn.textContent='⏳ 构建中…';
 const r=await fetch('/build',{{method:'POST'}});
 const t=await r.text();
 btn.disabled=false;btn.textContent='🔄 构建预览';
 log(t);
 if(r.ok)window.open('/preview/index.html','_blank');
}}
async function publish(btn){{
 if(!confirm('构建并发布到 vivabien.xyz？'))return;
 btn.disabled=true;btn.textContent='🚀 发布中…';
 const r=await fetch('/publish',{{method:'POST'}});
 const t=await r.text();
 btn.disabled=false;btn.textContent='🚀 发布上线';
 log(t+'\\n\\n（Cloudflare 构建约需 2-3 分钟生效）');
}}
async function restartAdmin(btn){{
 if(!confirm('确认重启后台？\\n\\n用来加载新功能。页面会断开几秒后自动回来。'))return;
 btn.disabled=true;btn.textContent='⏳ 重启中…';
 try{{await fetch('/restart',{{method:'POST'}})}}catch(e){{}}
 // 轮询等后台起来，起来了立刻刷新（比死等更快更稳）
 var tries=0;
 var t=setInterval(async function(){{
  tries++;
  try{{var r=await fetch('/ping',{{cache:'no-store'}});if(r.ok){{clearInterval(t);location.reload()}}}}catch(e){{}}
  if(tries>25){{clearInterval(t);location.reload()}}
 }},800);
}}
async function envCheck(btn){{
 btn.disabled=true;
 const r=await fetch('/env_check',{{method:'POST'}});
 btn.disabled=false;
 log(await r.text());
}}
async function deployWorker(btn){{
 if(!confirm('部署接口服务（Worker）？\\n\\n短链、埋点、优惠券、统计都靠它。约 20 秒。'))return;
 btn.disabled=true;btn.textContent='⚡ 部署中…';
 const r=await fetch('/deploy_worker',{{method:'POST'}});
 const t=await r.text();
 btn.disabled=false;btn.textContent='⚡ 部署接口';
 log(t);
}}
const focusH=new URLSearchParams(location.search).get('focus');
if(focusH){{
 const idx=flist.findIndex(p=>p.h===focusH);
 if(idx>=0){{while(shown<=idx)more();  // 懒加载模式下先把目标批次渲染出来
  const card=document.querySelector('.card[data-h="'+CSS.escape(focusH)+'"]');
  if(card){{card.scrollIntoView({{behavior:'smooth',block:'center'}});
   card.classList.add('focus-card');setTimeout(()=>card.classList.remove('focus-card'),3500);}}}}
}}
</script></body></html>"""

def import_page():
    cands = import_candidates()
    if cands is None:
        body = f"""<div class="imp-empty">⚠️ 找不到流水线目录<br>
<code>{esc(UPSTREAM_DIR)}</code><br><br>
请确认流水线在这台电脑上，或设置环境变量 VIVABIEN_UPSTREAM 后重启后台。</div>"""
    elif not cands:
        body = """<div class="imp-empty">✅ 没有待导入的新商品<br>
<span style="font-size:13px;color:#8a93a2">流水线里所有已完成（finalizado/confirmado）的商品都已经在网站库里了。</span></div>"""
    else:
        items = []
        for c in cands:
            r = c["row"]
            price = (r.get("Variant Price") or "").strip()
            price_html = f"RD$ {esc(price)}" if price else '<span class="warn-t">无价格</span>'
            warns = "".join(f'<span class="wtag">⚠ {esc(w)}</span>' for w in c["warns"])
            items.append(f"""<label class="imp-it {'has-warn' if c['warns'] else ''}">
<input type="checkbox" class="ck" value="{esc(c['sku'])}" checked>
<img src="/upimg/{esc(c['img'])}" loading="lazy" onerror="this.style.opacity=.15">
<div class="imp-t">
<div class="imp-nm">{esc(r.get('Title',''))}</div>
<div class="imp-meta"><b>{price_html}</b> · {esc(r.get('Type') or '无类目')} · {esc(c['sku'])} · {esc(c['estado'])}</div>
<div>{warns}</div>
</div></label>""")
        body = f"""<div class="imp-bar">
<label style="display:flex;align-items:center;gap:7px;font-weight:700;font-size:13px;cursor:pointer">
<input type="checkbox" id="ckAll" checked onchange="document.querySelectorAll('.ck').forEach(c=>c.checked=this.checked);cnt()"> 全选
</label>
<span id="impCnt" style="color:#8a93a2;font-size:13px"></span>
<button class="btn b-pub" style="margin-left:auto" onclick="doImport(this)">📥 导入所选</button>
</div>
<div class="imp-list">{''.join(items)}</div>"""
    return f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>流水线导入</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#F7F9FD;color:#16202E;padding-bottom:60px}}
.top{{position:sticky;top:0;background:#fff;border-bottom:1px solid #EEF1F6;padding:12px 18px;display:flex;gap:10px;align-items:center;z-index:10}}
.top b{{font-size:17px}}
.btn{{border:0;border-radius:99px;padding:10px 18px;font-weight:700;font-size:13px;cursor:pointer;text-decoration:none;display:inline-block}}
.b-pub{{background:#FF6B4A;color:#fff}}
.b-gray{{background:#F1F5FB;color:#2563D9}}
.imp-bar{{display:flex;align-items:center;gap:14px;padding:14px 18px;background:#fff;border-bottom:1px solid #EEF1F6}}
.imp-list{{display:flex;flex-direction:column;gap:10px;padding:14px 18px;max-width:760px}}
.imp-it{{display:flex;gap:12px;align-items:center;background:#fff;border:1px solid #EDF1F7;border-radius:15px;padding:10px 14px;cursor:pointer}}
.imp-it.has-warn{{background:#FFFBEB;border-color:#F5E6B8}}
.imp-it img{{width:62px;height:62px;border-radius:12px;object-fit:cover;background:#F0F3F8;flex:none}}
.imp-it .ck{{width:18px;height:18px;accent-color:#2563D9;flex:none}}
.imp-t{{min-width:0}}
.imp-nm{{font-weight:700;font-size:13.5px;line-height:1.3}}
.imp-meta{{font-size:12px;color:#5a6577;margin:3px 0}}
.wtag{{display:inline-block;background:#FDEFC8;color:#8a6d1a;font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;margin-right:5px}}
.warn-t{{color:#c0392b}}
.imp-empty{{text-align:center;padding:70px 20px;color:#5a6577;font-weight:600;font-size:15px;line-height:1.8}}
code{{background:#EEF1F6;border-radius:6px;padding:2px 8px;font-size:12px}}
#log{{position:fixed;left:12px;right:12px;bottom:12px;background:#16202E;color:#9fe8c1;font:12px/1.6 ui-monospace,monospace;border-radius:12px;padding:12px 15px;display:none;white-space:pre-wrap;max-height:40vh;overflow:auto;z-index:99}}
</style></head><body>
<div class="top">
<b>📥 流水线导入</b>
<span style="color:#8a93a2;font-size:12px">上游只读 · 已存在的SKU自动跳过 · 只增不改</span>
<a class="btn b-gray" style="margin-left:auto" href="/">← 返回商品管理</a>
</div>
{body}
<div id="log"></div>
<script>
const log=m=>{{const d=document.getElementById('log');d.style.display='block';d.textContent=m}};
function cnt(){{const n=document.querySelectorAll('.ck:checked').length;
 const el=document.getElementById('impCnt');if(el)el.textContent='已选 '+n+' 个';}}
document.querySelectorAll('.ck').forEach(c=>c.addEventListener('change',cnt));cnt();
async function doImport(btn){{
 const skus=[...document.querySelectorAll('.ck:checked')].map(c=>c.value);
 if(!skus.length){{alert('先勾选要导入的商品');return}}
 if(!confirm('确认导入 '+skus.length+' 个新商品？\\n\\n导入后不会自动上线，需要回主页构建预览+发布。'))return;
 btn.disabled=true;btn.textContent='⏳ 导入中…';
 const r=await fetch('/import_do',{{method:'POST',body:new URLSearchParams({{skus:skus.join(',')}})}});
 const t=await r.text();
 log(t);
 if(r.ok)setTimeout(()=>location.reload(),4000);
 else{{btn.disabled=false;btn.textContent='📥 导入所选'}}
}}
</script></body></html>"""

# ---------- HTTP 服务 ----------
class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def find_product(handle):
    for p in products():
        if p["handle"] == handle: return p
    return None

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = unquote(self.path.split("?")[0])
        qs = parse_qs(self.path.partition("?")[2])
        if p == "/ping":          # 重启后前端轮询探活，不需要登录
            return self.send(200, "ok", "text/plain; charset=utf-8")
        if not check_cookie(self.headers):
            return self.send(200, LOGIN_HTML.replace("__ERR__", ""))
        if p == "/":
            return self.send(200, page_html())
        if p in ("/marketing", "/links", "/coupons"):
            return self.send(200, marketing_page())
        if p == "/stats":
            return self.send(200, stats_page())
        if p == "/wallpaper-stats":
            try:
                days = int(qs.get("days", ["30"])[0])
            except ValueError:
                days = 30
            return self.send(200, wallpaper_stats_page(days))
        if p == "/orders":
            return self.send(200, orders_page())
        if p == "/cart-visitors":
            return self.send(200, cart_visitors_page())
        if p == "/colecciones":
            return self.send(200, colecciones_page(qs.get("edit", [""])[0], qs.get("focus", [""])[0]))
        if p == "/preview-product":
            pr = find_product(qs.get("handle", [""])[0])
            return self.send(200, product_preview_page(pr) if pr else "商品不存在")
        if p == "/api_timeline":
            code = qs.get("code", [""])[0]
            vid = qs.get("vid", [""])[0]
            path = f"timeline?vid={quote(vid)}" if vid else f"timeline?code={quote(code)}"
            data, err = worker_call(path)
            return self.send(200, json.dumps(data or {"error": err}), "application/json")
        if p == "/import":
            return self.send(200, import_page())
        if p.startswith("/upimg/"):
            fn = p[len("/upimg/"):]
            if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.(jpg|jpeg|png|webp)", fn, re.I):
                return self.send(404, "not found")
            fp = os.path.join(UPSTREAM_DIR, fn)
            if not os.path.isfile(fp):
                return self.send(404, "not found")
            with open(fp, "rb") as f:      # 上游只读
                return self.send(200, f.read(), "image/jpeg")
        if p == "/body":
            pr = find_product(qs.get("handle", [""])[0])
            return self.send(200, pr["body"] if pr else "", "text/plain; charset=utf-8")
        if p == "/photos":
            pr = find_product(qs.get("handle", [""])[0])
            if not pr: return self.send(404, "[]", "application/json")
            out = [{"file": f, "label": photo_label(pr["img"], f)} for f in sku_photos_by_img(pr["img"])]
            return self.send(200, json.dumps(out), "application/json")
        for prefix, root in (("/images/", IMG_DIR), ("/preview/", "dist")):
            if p.startswith(prefix):
                fp = os.path.normpath(os.path.join(root, p[len(prefix):]))
                if prefix == "/preview/" and not os.path.splitext(fp)[1]:
                    fp = os.path.join(fp, "index.html") if os.path.isdir(fp) else fp + ".html"
                if not fp.startswith(root) or not os.path.isfile(fp):
                    return self.send(404, "not found")
                ext = os.path.splitext(fp)[1].lower()
                ct = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
                      ".webp":"image/webp",".html":"text/html; charset=utf-8"}.get(ext,"application/octet-stream")
                with open(fp,"rb") as f:
                    return self.send(200, f.read(), ct)
        self.send(404, "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        p = self.path
        if p == "/login":
            q = parse_qs(body.decode("utf-8"))
            r = try_login(q.get("pw", [""])[0])
            if r is None:
                return self.send(200, LOGIN_HTML.replace("__ERR__", '<div class="err">尝试次数过多，请 5 分钟后再试</div>'))
            if not r:
                return self.send(200, LOGIN_HTML.replace("__ERR__", '<div class="err">密码不对</div>'))
            data = "已登录，跳转中…<script>location.href='/'</script>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", f"vbadmin={r}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not check_cookie(self.headers):
            return self.send(403, "请先登录")
        try:
            if p == "/update":
                q = parse_qs(body.decode("utf-8"))
                fields = {k: q[k][0] for k in ("title", "price", "type", "body") if k in q}
                n = update_product(q["handle"][0], fields)
                return self.send(200, f"updated {n}")
            if p == "/delete":
                q = parse_qs(body.decode("utf-8"))
                return self.send(200, f"deleted {delete_product(q['handle'][0])}")
            if p == "/photo_del":
                q = parse_qs(body.decode("utf-8"))
                pr = find_product(q["handle"][0])
                f = q.get("file", [""])[0]
                if not pr or not safe_photo_name(pr["img"], f):
                    return self.send(400, "无效文件")
                if f == pr["img"]:
                    photos = sku_photos_by_img(pr["img"])
                    if len(photos) <= 1:
                        return self.send(400, "商品至少需要保留一张图片")
                    # 主图不能让商品变成无图状态：把下一张提升为主图，再删除原主图。
                    promote = next(x for x in photos if x != f)
                    tmp = os.path.join(IMG_DIR, f + ".promote")
                    os.replace(os.path.join(IMG_DIR, promote), tmp)
                    os.remove(os.path.join(IMG_DIR, f))
                    os.replace(tmp, os.path.join(IMG_DIR, f))
                else:
                    os.remove(os.path.join(IMG_DIR, f))
                return self.send(200, "ok")
            if p == "/photo_add":
                ct = self.headers.get("Content-Type", "")
                m = re.search(r"boundary=(.+)", ct)
                fields, files = parse_multipart(body, m.group(1).encode())
                pr = find_product(fields.get("handle", ""))
                if not pr or not pr["img"]: return self.send(400, "商品不存在")
                fn, data = files["image"]
                fname = photo_add(pr["img"], fields.get("slot", "extra"), data)
                return self.send(200, fname)
            if p == "/photo_replace":
                ct = self.headers.get("Content-Type", "")
                m = re.search(r"boundary=(.+)", ct)
                fields, files = parse_multipart(body, m.group(1).encode())
                pr = find_product(fields.get("handle", ""))
                if not pr or not pr["img"]:
                    return self.send(400, "商品不存在")
                fn, data = files["image"]
                fname = photo_replace(pr["img"], fields.get("file", ""), data)
                return self.send(200, fname)
            if p == "/add":
                ct = self.headers.get("Content-Type", "")
                m = re.search(r"boundary=(.+)", ct)
                fields, files = parse_multipart(body, m.group(1).encode())
                fn, data = files["image"]
                ext = os.path.splitext(fn)[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".webp"): ext = ".jpg"
                h = add_product(fields.get("title", "").strip(), fields.get("price", "").strip(),
                                fields.get("type", "").strip(), data, ext,
                                body=fields.get("body", ""), zh=fields.get("zh", ""))
                return self.send(200, h)
            if p == "/import_do":
                q = parse_qs(body.decode("utf-8"))
                skus = [s for s in q.get("skus", [""])[0].split(",") if s.strip()]
                if not skus:
                    return self.send(400, "没有选择商品")
                return self.send(200, do_import(skus))
            if p == "/link_create":
                payload = json.loads(body.decode("utf-8") or "{}")
                data, err = worker_call("link/create", "POST", payload)
                return self.send(200, json.dumps(data or {"error": err}), "application/json")
            if p == "/coupon_create":
                payload = json.loads(body.decode("utf-8") or "{}")
                data, err = worker_call("coupon/create", "POST", payload)
                return self.send(200, json.dumps(data or {"error": err}), "application/json")
            if p == "/coupon_toggle":
                payload = json.loads(body.decode("utf-8") or "{}")
                data, err = worker_call("coupon/toggle", "POST", payload)
                return self.send(200, json.dumps(data or {"error": err}), "application/json")
            if p == "/coupon_welcome":
                # 把某张已存在的券设为 /enlaces 落地页的欢迎券弹窗
                b = json.loads(body.decode("utf-8") or "{}")
                code = (b.get("code") or "").strip().upper()
                if not code:
                    return self.send(400, json.dumps({"error": "缺少券码"}), "application/json")
                path = "data/social.json"
                cfg = {}
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        cfg = json.load(f)
                cup = cfg.setdefault("cupon", {})
                cup.update({
                    "activo": True, "codigo": code,
                    "valor_texto": b.get("valor_texto") or cup.get("valor_texto", ""),
                    "condicion": b.get("condicion") or cup.get("condicion", ""),
                    "nota_pie": b.get("nota_pie") or cup.get("nota_pie", ""),
                })
                cup.setdefault("titulo", "¡Felicidades!")
                cup.setdefault("subtitulo", "Ganaste un cupón de bienvenida")
                cup.setdefault("boton", "Usar mi cupón")
                cup.setdefault("mostrar_una_vez", True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                return self.send(200, json.dumps({"ok": True, "code": code}), "application/json")
            if p == "/enlaces_link":
                # 用已有优惠券生成一条「推广落地页」短链（不新建券）
                b = json.loads(body.decode("utf-8") or "{}")
                code = (b.get("code") or "").strip().upper()
                if not code:
                    return self.send(400, json.dumps({"error": "先选一张优惠券"}), "application/json")
                target = f"enlaces.html?coupon={quote(code)}"
                val = (b.get("valor_texto") or "").strip()
                cond = (b.get("condicion") or "").strip()
                if val:
                    target += f"&val={quote(val)}"
                if cond:
                    target += f"&cond={quote(cond)}"
                audience = str(b.get("audience") or "").replace("|", " ").strip() or "落地页推广"
                note = f"campaign|coupon={code}|template=enlaces|days=0|audience={audience}"
                link, err = worker_call("link/create", "POST", {"target": target, "note": note})
                if not link or not link.get("url"):
                    return self.send(502, json.dumps({"error": err or (link or {}).get("error", "链接创建失败")}),
                                     "application/json")
                return self.send(200, json.dumps({"ok": True, "url": link["url"],
                                                  "code": link.get("code", ""), "coupon": code}), "application/json")
            if p == "/coupon_welcome_off":
                path = "data/social.json"
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        cfg = json.load(f)
                    cfg.setdefault("cupon", {})["activo"] = False
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, ensure_ascii=False, indent=2)
                return self.send(200, json.dumps({"ok": True}), "application/json")
            if p == "/campaign_create":
                b = json.loads(body.decode("utf-8") or "{}")
                value = float(b.get("value") or 0)
                if value <= 0:
                    return self.send(400, json.dumps({"error": "请填写有效优惠金额"}), "application/json")
                days = max(0, int(b.get("days") or 0))
                coupon_payload = {
                    "kind": "amount" if b.get("kind") == "amount" else "percent",
                    "value": value,
                    "min_order": float(b.get("min_order") or 0),
                    "max_uses": max(0, int(b.get("max_uses") or 0)),
                    "expires_at": int(time.time() * 1000) + days * 86400000 if days else 0,
                    "scope": "all",
                }
                coupon, coupon_err = worker_call("coupon/create", "POST", coupon_payload)
                if not coupon or not coupon.get("code"):
                    return self.send(502, json.dumps({"error": coupon_err or (coupon or {}).get("error", "优惠券创建失败")}), "application/json")
                coupon_code = coupon["code"]
                target = (b.get("target") or "/").strip()
                joiner = "&" if "?" in target else "?"
                target = f"{target}{joiner}coupon={quote(coupon_code)}"
                # 落地页：把券的面值/门槛也带上，弹窗直接显示这张活动券
                if target.startswith("enlaces.html"):
                    kind = "amount" if b.get("kind") == "amount" else "percent"
                    val_txt = (f"RD${value:,.0f} OFF" if kind == "amount" else f"{value:g}% OFF")
                    mino = float(b.get("min_order") or 0)
                    cond = (f"En compras desde RD${mino:,.0f}" if mino else "Sin monto mínimo")
                    target += f"&val={quote(val_txt)}&cond={quote(cond)}"
                note = (f'campaign|coupon={coupon_code}|template={b.get("template","postpurchase")}'
                        f'|days={days}|audience={str(b.get("audience") or "").replace("|", " ")}')
                link, link_err = worker_call("link/create", "POST", {"target": target, "note": note})
                if not link or not link.get("url"):
                    return self.send(502, json.dumps({"error": link_err or (link or {}).get("error", "专属链接创建失败"),
                                                      "coupon": coupon_code}), "application/json")
                return self.send(200, json.dumps({"ok": True, "coupon": coupon_code,
                                                  "url": link["url"], "short_code": link.get("code", "")}), "application/json")
            if p == "/order_status":
                payload = json.loads(body.decode("utf-8") or "{}")
                data, err = worker_call("order/status", "POST", payload)
                code = 200 if data and data.get("ok") else 502
                return self.send(code, json.dumps(data or {"error": err}), "application/json")
            if p == "/campaign_cost":
                payload = json.loads(body.decode("utf-8") or "{}")
                data, err = worker_call("campaign-cost", "POST", payload)
                code = 200 if data and data.get("ok") else 502
                return self.send(code, json.dumps(data or {"error": err}), "application/json")
            if p == "/coleccion_save":
                b = json.loads(body.decode("utf-8") or "{}")
                colls = load_collections()
                slug = b.get("slug", "")
                if b.get("toggle"):
                    for c in colls:
                        if c.get("slug") == slug:
                            c["active"] = not (c.get("active") is not False)
                    save_collections(colls); return self.send(200, json.dumps({"ok": True}), "application/json")
                title = (b.get("title") or "").strip()
                if not title or not b.get("skus"):
                    return self.send(200, json.dumps({"ok": False, "error": "需要名字和至少一个商品"}), "application/json")
                item = {"title": title, "subtitle": (b.get("subtitle") or "").strip(),
                        "cta": (b.get("cta") or "").strip(),
                        "image": (b.get("image") or "").strip(),
                        "active": bool(b.get("active", True)), "order": int(b.get("order") or 0),
                        "skus": [s for s in b.get("skus", []) if s]}
                existing = next((c for c in colls if c.get("slug") == slug), None) if slug else None
                if existing:
                    item["slug"] = slug
                    colls[colls.index(existing)] = item
                else:
                    base = coll_slugify(title); s = base; i = 2
                    used = {c.get("slug") for c in colls}
                    while s in used:
                        s = f"{base}-{i}"; i += 1
                    item["slug"] = s
                    colls.append(item)
                save_collections(colls)
                return self.send(200, json.dumps({"ok": True, "slug": item["slug"]}), "application/json")
            if p == "/coleccion_del":
                b = json.loads(body.decode("utf-8") or "{}")
                colls = [c for c in load_collections() if c.get("slug") != b.get("slug")]
                save_collections(colls)
                return self.send(200, json.dumps({"ok": True}), "application/json")
            if p == "/restart":
                mode = "由系统服务托管，正在重启" if _launchd_managed() else "正在重启"
                self.send(200, f"后台{mode}，约 3 秒后自动刷新…")
                threading.Timer(0.25, restart_admin).start()
                threading.Timer(0.9, lambda: os._exit(0)).start()
                return
            if p == "/env_check":
                lines = ["🔎 部署环境自检", ""]
                for name in ("npx", "node", "git", "launchctl"):
                    path = find_bin(name)
                    lines.append(f"{'✓' if path else '❌'} {name}: {path or '找不到'}")
                lines.append("")
                lines.append(f"由系统服务托管: {'是' if _launchd_managed() else '否'}")
                lines.append(f"Worker 待部署: {'是' if worker_needs_deploy() else '否（已是最新）'}")
                lines.append("")
                lines.append("PATH: " + cmd_env()["PATH"][:300])
                return self.send(200, "\n".join(lines))
            if p == "/deploy_worker":
                ok, out = deploy_worker()
                ver = re.search(r"Current Version ID:\s*(\S+)", out)
                if ok:
                    return self.send(200, "✅ 接口 Worker 已部署"
                                     + (f"\n版本: {ver.group(1)}" if ver else ""))
                return self.send(500, "❌ 接口 Worker 部署失败:\n" + out[-1200:])
            if p == "/build":
                r = subprocess.run([sys.executable, "build.py"],
                                   capture_output=True, text=True, timeout=300)
                out = (r.stdout + r.stderr).strip()
                return self.send(200 if r.returncode == 0 else 500, out)
            if p == "/publish":
                r = subprocess.run([sys.executable, "build.py"],
                                   capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    return self.send(500, "构建失败:\n" + (r.stdout + r.stderr).strip())
                # 1) git 留档（失败不阻断）2) 接口 Worker（有改动才部署）3) 静态站
                logtxt = ["✅ 构建完成"]
                if worker_needs_deploy():
                    okw, outw = deploy_worker()
                    if okw:
                        logtxt.append("✓ 接口 Worker 已更新")
                    else:
                        logtxt.append("⚠️ 接口 Worker 部署失败（网站仍会继续发布）:\n   "
                                      + outw[-400:].replace("\n", "\n   "))
                git = find_bin("git") or "git"
                for cmd in ([git, "add", "-A"],
                            [git, "commit", "-m", "后台更新商品"],
                            [git, "push"]):
                    try:
                        g = subprocess.run(cmd, env=cmd_env(), capture_output=True,
                                           text=True, timeout=300)
                        out = (g.stdout + g.stderr).strip()
                        ok = g.returncode == 0 or "nothing to commit" in out
                    except Exception as e:
                        out, ok = str(e), False
                    label = "git " + cmd[1]
                    logtxt.append(f"✓ {label}" if ok else
                                  f"⚠️ {label} 跳过: {(out.splitlines() or [''])[-1][:80]}")
                npx = find_bin("npx")
                if not npx:
                    return self.send(500, "\n".join(logtxt) +
                                     "\n❌ 找不到 npx（Node.js）。后台由系统服务启动时环境变量较少，"
                                     "已尝试 Homebrew / nvm / volta 常见路径仍未找到。\n"
                                     "请在终端执行 `which npx`，把结果告诉我。")
                d = subprocess.run([npx, "wrangler", "deploy"], env=cmd_env(),
                                   capture_output=True, text=True, timeout=900)
                dout = (d.stdout + d.stderr).strip()
                if d.returncode != 0:
                    return self.send(500, "\n".join(logtxt) + "\n❌ wrangler deploy 失败:\n" + dout[-1500:])
                ver = re.search(r"Current Version ID:\s*(\S+)", dout)
                logtxt.append("✓ npx wrangler deploy")
                return self.send(200, "\n".join(logtxt)
                                 + (f"\n版本: {ver.group(1)}" if ver else "")
                                 + "\n🚀 已部署到 vivabien.xyz（1-2 分钟内全球生效）")
        except Exception as e:
            return self.send(500, f"错误: {e}")
        self.send(404, "not found")

if __name__ == "__main__":
    if not os.path.isfile(CSV_PATH):
        print(f"❌ 找不到 {CSV_PATH}，请在 vivabien-web 目录里运行"); sys.exit(1)
    print(f"🛠️  商品管理后台已启动: http://localhost:{PORT}")
    print("   按 Ctrl+C 停止")
    if os.environ.get("VIVABIEN_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
