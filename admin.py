#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VivaBien 本地商品管理后台
用法: cd ~/vivabien-web && python3 admin.py
浏览器自动打开 http://localhost:8765（公网走 Cloudflare Tunnel + Access）
功能: 改价格/标题/分类/详情描述、商品多图管理（补充图/尺寸图/替换/删除）、
     上传新商品、删商品、一键重新构建、一键发布上线（构建+git push）
数据直接读写 data/products.csv，与 build.py 共用同一数据源
"""
import csv, os, io, re, sys, json, html, uuid, shutil, subprocess, threading, webbrowser
import hmac, hashlib, secrets, time
import urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, unquote, quote

PORT     = 8765
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
    req = urllib.request.Request(url, data=data, method=method,
        headers={"X-Admin-Key": WORKER_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}"), None
    except urllib.error.HTTPError as e:
        try:    return json.loads(e.read().decode()), f"HTTP {e.code}"
        except Exception: return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"连接后端失败：{e}"

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
body{font-family:-apple-system,'PingFang SC',sans-serif;background:#F7F9FD;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #EDF1F7;border-radius:20px;padding:34px 28px;width:min(360px,92vw);text-align:center;box-shadow:0 10px 40px rgba(20,40,80,.08)}
.box h2{font-size:19px;margin-bottom:6px}.box p{font-size:13px;color:#8a93a2;margin-bottom:18px}
input{width:100%;border:1.5px solid #E5EAF2;border-radius:12px;padding:13px;font-size:15px;margin-bottom:12px;text-align:center}
button{width:100%;background:#2563D9;color:#fff;border:0;border-radius:12px;padding:13px;font-weight:700;font-size:15px;cursor:pointer}
.err{color:#c0392b;font-size:13px;margin-bottom:10px;font-weight:600}</style></head><body>
<form class="box" method="POST" action="/login">
<h2>🛠️ VivaBien 商品管理</h2><p>请输入后台密码</p>
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

def sku_photos_by_img(img):
    """按主图文件名列出该商品全部图片文件"""
    stem = img[:-4] if img.lower().endswith(".jpg") else img
    out = []
    if os.path.isfile(os.path.join(IMG_DIR, img)):
        out.append(img)
    for suf in ("_scene.jpg", "_dim.jpg"):
        f = stem + suf
        if os.path.isfile(os.path.join(IMG_DIR, f)): out.append(f)
    for i in range(2, 10):
        f = f"{stem}_{i}.jpg"
        if os.path.isfile(os.path.join(IMG_DIR, f)): out.append(f)
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
        for i in range(2, 10):
            c = f"{stem}_{i}.jpg"
            if not os.path.isfile(os.path.join(IMG_DIR, c)):
                fname = c; break
        if not fname: raise ValueError("补充图最多 8 张")
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
        # 拷图：主图 + _2.._9 + 尺寸/场景图 + 附加行引用的图（上游只读，只复制出来）
        stem = c["img"][:-4] if c["img"].lower().endswith(".jpg") else c["img"]
        names = {c["img"]} | {f"{stem}_{i}.jpg" for i in range(2, 10)} \
                | {stem + "_dim.jpg", stem + "_scene.jpg"} \
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
            f'<a class="{c("links")}" href="/links">🔗 短链</a>'
            f'<a class="{c("coupons")}" href="/coupons">🎟️ 优惠券</a>'
            f'<a class="{c("stats")}" href="/stats">📊 数据</a></div>')

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
  var m={click:'🔗 点击短链',view:'👁️ 浏览',addcart:'🛒 加购',checkout:'✅ 进入结算'};
  tl.innerHTML='<div class="tls">'+d.events.map(function(e){
   return '<div class="tle"><span>'+(m[e.type]||e.type)+'</span>'
    +(e.sku?' <code>'+e.sku+'</code>':'')+(e.code?' <i>'+e.code+'</i>':'')
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
             '<table><thead><tr><th>短码</th><th>链接</th><th>备注</th>'
             '<th>点击</th><th>访客</th><th>加购</th></tr></thead><tbody>'
             + (rows or '<tr><td colspan="6" class="empty">还没有短链</td></tr>')
             + '</tbody></table>' + _LINKS_JS)
    return sub_shell("短链接", "links", inner)

def coupons_page():
    data, err = worker_call("coupons")
    rows = ""
    for c in (data or {}).get("coupons", []):
        val = f'{c["value"]:g}%' if c["kind"] == "percent" else f'RD$ {c["value"]:,.0f}'
        act = bool(c.get("active"))
        rows += (f'<tr><td><code>{esc(c["code"])}</code></td><td>{val}</td>'
                 f'<td>{"百分比" if c["kind"]=="percent" else "固定金额"}</td>'
                 f'<td class="n">{c.get("used_count",0)}</td>'
                 f'<td><span class="tag {"on" if act else "off"}">{"启用" if act else "停用"}</span></td>'
                 f'<td><button class="cp" onclick="tog(\'{esc(c["code"])}\')">{"停用" if act else "启用"}</button></td></tr>')
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
             '<table><thead><tr><th>券码</th><th>面值</th><th>方式</th><th>已用</th><th>状态</th><th></th></tr></thead><tbody>'
             + (rows or '<tr><td colspan="6" class="empty">还没有优惠券</td></tr>')
             + '</tbody></table>' + _COUPONS_JS)
    return sub_shell("优惠券", "coupons", inner)

def stats_page():
    data, err = worker_call("overview")
    d = data or {}
    def card(v, l): return f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>'
    inner = (f'{_warn(err)}<h1>📊 访问数据 <span class="sub">近30天</span></h1>'
             '<div class="stats">'
             + card(d.get("clicks30", 0), "短链点击")
             + card(d.get("visitors30", 0), "独立访客")
             + card(d.get("addcarts30", 0), "加购次数")
             + card(d.get("links", 0), "短链总数")
             + card(d.get("active_coupons", 0), "启用中的券")
             + '</div>'
             '<div class="cardp"><div class="frm">'
             '<label>查访客足迹（按短码看这条链接的全部事件，或按访客ID看单人时间线）</label>'
             '<div class="seg2"><input id="q" placeholder="短码 或 访客ID">'
             '<select id="qt"><option value="code">按短码</option><option value="vid">按访客ID</option></select>'
             '<button class="pri" style="width:auto;margin:0" onclick="look()">查询</button></div>'
             '<div id="tl"></div></div></div>' + _STATS_JS)
    return sub_shell("访问数据", "stats", inner)

def page_html():
    prods = products()
    cats = sorted({p["type"] for p in prods if p["type"].strip()})
    cat_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in cats)
    cards = []
    for p in prods:
        nimg = len(sku_photos_by_img(p["img"])) if p["img"] else 0
        cards.append(f"""<div class="card" data-t="{esc(p['title'].lower())}" data-h="{esc(p['handle'])}" data-img="{esc(p['img'])}">
<div class="imgw"><img src="/images/{esc(p['img'])}" loading="lazy" onerror="this.style.opacity=.15">
<span class="nimg">📸 {nimg}</span></div>
<div class="body">
<textarea class="ti" rows="2">{esc(p['title'])}</textarea>
<div class="row">
<span class="cur">RD$</span><input class="pr" type="number" step="any" value="{esc(p['price'])}" placeholder="价格">
</div>
<select class="ca">{''.join(f'<option {"selected" if c==p["type"] else ""} value="{esc(c)}">{esc(c)}</option>' for c in cats)}</select>
<div class="row">
<button class="save" onclick="save(this)">保存</button>
<button class="mini" onclick="openDesc(this)">✏️ 详情</button>
<button class="mini" onclick="openPhotos(this)">📷 图片</button>
<button class="del" onclick="del_(this)">✕</button>
</div>
</div></div>""")
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
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;padding:16px 18px}}
.card{{background:#fff;border:1px solid #EDF1F7;border-radius:16px;overflow:hidden}}
.imgw{{position:relative}}
.card img{{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}}
.nimg{{position:absolute;bottom:8px;right:8px;background:rgba(22,32,46,.75);color:#fff;font-size:11px;font-weight:700;padding:3px 8px;border-radius:99px}}
.body{{padding:10px 12px 12px;display:flex;flex-direction:column;gap:8px}}
.ti{{width:100%;border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:12.5px;font-family:inherit;resize:vertical}}
.row{{display:flex;gap:6px;align-items:center}}
.cur{{font-weight:700;font-size:13px;color:#8a93a2}}
.pr{{flex:1;border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:14px;font-weight:700;width:100%}}
.ca{{border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:12px;background:#fff}}
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
#log{{position:fixed;left:12px;right:12px;bottom:12px;background:#16202E;color:#9fe8c1;font:12px/1.5 ui-monospace,monospace;border-radius:12px;padding:10px 14px;display:none;white-space:pre-wrap;max-height:35vh;overflow:auto;z-index:99}}
</style></head><body>
<div class="top">
<b>🛠️ VivaBien 商品管理</b>
<input id="q" placeholder="搜索商品…" oninput="filt()">
<button class="btn b-add" onclick="dlg.showModal()">＋ 添加商品</button>
<a class="btn" style="background:#F1F5FB;color:#2563D9;text-decoration:none" href="/import">📥 流水线导入</a>
<a class="btn" style="background:#F1F5FB;color:#2563D9;text-decoration:none" href="/links">🔗 短链</a>
<a class="btn" style="background:#F1F5FB;color:#2563D9;text-decoration:none" href="/coupons">🎟️ 优惠券</a>
<a class="btn" style="background:#F1F5FB;color:#2563D9;text-decoration:none" href="/stats">📊 数据</a>
<a class="btn" style="background:#F1F5FB;color:#2563D9;text-decoration:none" href="{REVIEW_URL}" target="_blank">🧪 审核台</a>
<button class="btn b-build" onclick="build(this)">🔄 构建预览</button>
<button class="btn b-pub" onclick="publish(this)">🚀 发布上线</button>
<span id="cnt" style="color:#8a93a2;font-size:13px">{len(prods)} 个商品</span>
</div>
<div class="grid" id="grid">{''.join(cards)}</div>

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
<div class="uprow">
<select id="ph-slot" style="flex:1;margin:0">
<option value="extra">＋ 补充图</option>
<option value="dim">＋ 尺寸图</option>
<option value="scene">＋ 场景图</option>
<option value="main">↻ 替换主图</option>
</select>
<input id="ph-f" type="file" accept="image/*" style="flex:2;margin:0">
<button class="btn b-add" onclick="upPhoto(this)">上传</button>
</div>
<div class="row" style="margin-top:12px">
<button class="btn" onclick="dlgPh.close()">关闭</button>
</div>
</dialog>
<div id="log"></div>

<script>
let curH='', curImg='';
const log = m => {{const d=document.getElementById('log');d.style.display='block';d.textContent=m;setTimeout(()=>d.style.display='none',8000)}};
function filt(){{
 const q=document.getElementById('q').value.toLowerCase();let n=0;
 document.querySelectorAll('.card').forEach(c=>{{const s=c.dataset.t.includes(q);c.style.display=s?'':'none';if(s)n++}});
 document.getElementById('cnt').textContent=n+' 个商品';
}}
// 记录初始值，保存时比对出改动
const orig={{}};
document.querySelectorAll('.card').forEach(c=>{{
 orig[c.dataset.h]={{t:c.querySelector('.ti').value,p:c.querySelector('.pr').value,c:c.querySelector('.ca').value}};
}});
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
 if(r.ok){{orig[h]={{t:t,p:p,c:ca}};btn.textContent='✓ 已保存';btn.classList.add('ok');setTimeout(()=>{{btn.textContent='保存';btn.classList.remove('ok')}},1500)}}
 else log('保存失败: '+await r.text());
}}
async function del_(btn){{
 if(!confirm('确定删除这个商品？图片也会一起删除。'))return;
 const c=btn.closest('.card');
 const r=await fetch('/delete',{{method:'POST',body:new URLSearchParams({{handle:c.dataset.h}})}});
 if(r.ok)c.remove();else log('删除失败');
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
 await refreshPhotos();
 dlgPh.showModal();
}}
async function refreshPhotos(){{
 const r=await fetch('/photos?handle='+encodeURIComponent(curH));
 const ps=await r.json();
 document.getElementById('phGrid').innerHTML=ps.map(p=>
  '<div class="ph"><img src="/images/'+p.file+'?v='+Date.now()+'"><span class="lb">'+p.label+'</span>'
  +(p.label!=='主图'?'<button class="rm" onclick="delPhoto(\\''+p.file+'\\')">✕</button>':'')+'</div>').join('');
}}
async function delPhoto(f){{
 if(!confirm('删除这张图片？'))return;
 const r=await fetch('/photo_del',{{method:'POST',body:new URLSearchParams({{handle:curH,file:f}})}});
 if(r.ok)refreshPhotos();else log('删除失败: '+await r.text());
}}
async function upPhoto(btn){{
 const f=document.getElementById('ph-f').files[0];
 if(!f){{alert('请选择图片');return}}
 btn.disabled=true;btn.textContent='上传中…';
 const fd=new FormData();
 fd.append('handle',curH);
 fd.append('slot',document.getElementById('ph-slot').value);
 fd.append('image',f);
 const r=await fetch('/photo_add',{{method:'POST',body:fd}});
 btn.disabled=false;btn.textContent='上传';
 if(r.ok){{document.getElementById('ph-f').value='';refreshPhotos()}}
 else log('上传失败: '+await r.text());
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
        if not check_cookie(self.headers):
            return self.send(200, LOGIN_HTML.replace("__ERR__", ""))
        if p == "/":
            return self.send(200, page_html())
        if p == "/links":
            return self.send(200, links_page())
        if p == "/coupons":
            return self.send(200, coupons_page())
        if p == "/stats":
            return self.send(200, stats_page())
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
                if not pr or not safe_photo_name(pr["img"], f) or f == pr["img"]:
                    return self.send(400, "无效文件")
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
                steps = [["git", "add", "-A"],
                         ["git", "commit", "-m", "后台更新商品"],
                         ["git", "push"]]
                logtxt = ["✅ 构建完成"]
                for cmd in steps:
                    g = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    out = (g.stdout + g.stderr).strip()
                    if g.returncode != 0 and "nothing to commit" not in out:
                        return self.send(500, "\n".join(logtxt) + f"\n❌ {' '.join(cmd)} 失败:\n{out}")
                    logtxt.append(f"✓ {' '.join(cmd)}")
                return self.send(200, "\n".join(logtxt) + "\n🚀 已推送，Cloudflare 正在部署")
        except Exception as e:
            return self.send(500, f"错误: {e}")
        self.send(404, "not found")

if __name__ == "__main__":
    if not os.path.isfile(CSV_PATH):
        print(f"❌ 找不到 {CSV_PATH}，请在 vivabien-web 目录里运行"); sys.exit(1)
    print(f"🛠️  商品管理后台已启动: http://localhost:{PORT}")
    print("   按 Ctrl+C 停止")
    threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
