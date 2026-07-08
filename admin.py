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
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, unquote

PORT     = 8765
CSV_PATH = "data/products.csv"
IMG_DIR  = "images"

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
