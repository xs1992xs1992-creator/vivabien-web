#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Caoba / VivaBien 本地商品管理后台
用法: cd ~/vivabien-web && python3 admin.py
浏览器自动打开 http://localhost:8765
功能: 网页上直接改价格/标题/分类、上传图片加新商品、删商品、一键重新构建
数据直接读写 data/products.csv，与 build.py 共用同一数据源
"""
import csv, os, io, re, sys, json, html, uuid, shutil, subprocess, threading, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote

PORT     = 8765
CSV_PATH = "data/products.csv"
IMG_DIR  = "images"

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
    """返回去重后的商品列表(取每个handle第一行)"""
    seen, out = set(), []
    for i, r in enumerate(load_rows()[1:], 1):
        m = IDX.get(len(r))
        if not m: continue
        h = r[m["handle"]].strip()
        t = r[m["title"]].strip()
        if not h or not t or h in seen: continue
        seen.add(h)
        out.append(dict(handle=h, title=t, type=r[m["type"]],
                        price=r[m["price"]], img=r[m["img"]], sku=r[m["sku"]]))
    return out

def update_product(handle, title, price, ptype):
    rows = load_rows()
    n = 0
    for r in rows[1:]:
        if row_get(r, "handle") == handle:
            row_set(r, "title", title)
            row_set(r, "price", price)
            row_set(r, "type", ptype)
            n += 1
    if n: save_rows(rows)
    return n

def delete_product(handle):
    rows = load_rows()
    kept = [rows[0]] + [r for r in rows[1:] if row_get(r, "handle") != handle]
    n = len(rows) - len(kept)
    if n: save_rows(kept)
    return n

def add_product(title, price, ptype, img_bytes, img_ext):
    sku = "VB" + uuid.uuid4().hex[:8].upper()
    handle = sku.lower()
    fname = f"{sku}{img_ext}"
    os.makedirs(IMG_DIR, exist_ok=True)
    with open(os.path.join(IMG_DIR, fname), "wb") as f:
        f.write(img_bytes)
    rows = load_rows()
    # 按16字段格式追加
    rows.append([handle, title, title, "VivaBien", ptype, ptype, "TRUE",
                 sku, price, "", fname, "", "", ptype, "Shopify", "后台添加"])
    save_rows(rows)
    return handle

# ---------- 简易 multipart 解析（不依赖已废弃的 cgi 模块） ----------
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
        price_val = esc(p["price"])
        cards.append(f"""<div class="card" data-t="{esc(p['title'].lower())}">
<img src="/images/{esc(p['img'])}" loading="lazy" onerror="this.style.opacity=.15">
<div class="body">
<textarea class="ti" rows="2">{esc(p['title'])}</textarea>
<div class="row">
<span class="cur">RD$</span><input class="pr" type="number" step="any" value="{price_val}" placeholder="价格">
</div>
<select class="ca">{''.join(f'<option {"selected" if c==p["type"] else ""} value="{esc(c)}">{esc(c)}</option>' for c in cats)}</select>
<div class="row">
<button class="save" onclick="save(this,'{p['handle']}')">保存</button>
<button class="del" onclick="del(this,'{p['handle']}')">删除</button>
</div>
</div></div>""")
    return f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>商品管理后台</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#F7F9FD;color:#16202E;padding-bottom:60px}}
.top{{position:sticky;top:0;background:#fff;border-bottom:1px solid #EEF1F6;padding:12px 18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:10}}
.top b{{font-size:17px;margin-right:6px}}
.top input{{flex:1;min-width:160px;border:1.5px solid #E5EAF2;border-radius:99px;padding:9px 16px;font-size:14px;outline:none}}
.btn{{border:0;border-radius:99px;padding:10px 18px;font-weight:700;font-size:13px;cursor:pointer}}
.b-add{{background:#2563D9;color:#fff}}
.b-build{{background:#FF6B4A;color:#fff}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;padding:16px 18px}}
.card{{background:#fff;border:1px solid #EDF1F7;border-radius:16px;overflow:hidden}}
.card img{{width:100%;aspect-ratio:1;object-fit:cover;background:#F0F3F8}}
.body{{padding:10px 12px 12px;display:flex;flex-direction:column;gap:8px}}
.ti{{width:100%;border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:12.5px;font-family:inherit;resize:vertical}}
.row{{display:flex;gap:8px;align-items:center}}
.cur{{font-weight:700;font-size:13px;color:#8a93a2}}
.pr{{flex:1;border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:14px;font-weight:700;width:100%}}
.ca{{border:1px solid #E5EAF2;border-radius:9px;padding:7px;font-size:12px;background:#fff}}
.save{{flex:1;background:#2563D9;color:#fff;border:0;border-radius:9px;padding:9px;font-weight:700;cursor:pointer}}
.save.ok{{background:#157A4E}}
.del{{background:#fff;color:#c0392b;border:1px solid #f0d0cc;border-radius:9px;padding:9px 12px;cursor:pointer}}
dialog{{border:0;border-radius:18px;padding:22px;width:min(420px,92vw);box-shadow:0 20px 60px rgba(20,40,80,.25)}}
dialog h3{{margin-bottom:14px}}
dialog input,dialog select{{width:100%;border:1.5px solid #E5EAF2;border-radius:10px;padding:10px;font-size:14px;margin-bottom:10px;font-family:inherit}}
#log{{position:fixed;left:12px;right:12px;bottom:12px;background:#16202E;color:#9fe8c1;font:12px/1.5 ui-monospace,monospace;border-radius:12px;padding:10px 14px;display:none;white-space:pre-wrap;max-height:30vh;overflow:auto}}
</style></head><body>
<div class="top">
<b>🛠️ 商品管理</b>
<input id="q" placeholder="搜索商品…" oninput="filt()">
<button class="btn b-add" onclick="dlg.showModal()">＋ 添加商品</button>
<button class="btn b-build" onclick="build(this)">🔄 重新构建网站</button>
<span id="cnt" style="color:#8a93a2;font-size:13px">{len(prods)} 个商品</span>
</div>
<div class="grid" id="grid">{''.join(cards)}</div>

<dialog id="dlg">
<h3>添加新商品</h3>
<input id="a-t" placeholder="商品标题（西语）">
<input id="a-p" type="number" step="any" placeholder="价格 RD$（可留空）">
<select id="a-c">{cat_opts}</select>
<input id="a-f" type="file" accept="image/*">
<div class="row">
<button class="btn b-add" style="flex:1" onclick="add(this)">保存商品</button>
<button class="btn" onclick="dlg.close()">取消</button>
</div>
</dialog>
<div id="log"></div>

<script>
const log = m => {{const d=document.getElementById('log');d.style.display='block';d.textContent=m;setTimeout(()=>d.style.display='none',6000)}};
function filt(){{
 const q=document.getElementById('q').value.toLowerCase();let n=0;
 document.querySelectorAll('.card').forEach(c=>{{const s=c.dataset.t.includes(q);c.style.display=s?'':'none';if(s)n++}});
 document.getElementById('cnt').textContent=n+' 个商品';
}}
async function save(btn,h){{
 const c=btn.closest('.card');
 const fd=new URLSearchParams({{handle:h,title:c.querySelector('.ti').value,price:c.querySelector('.pr').value,type:c.querySelector('.ca').value}});
 const r=await fetch('/update',{{method:'POST',body:fd}});
 if(r.ok){{btn.textContent='✓ 已保存';btn.classList.add('ok');setTimeout(()=>{{btn.textContent='保存';btn.classList.remove('ok')}},1500)}}
 else log('保存失败: '+await r.text());
}}
async function del(btn,h){{
 if(!confirm('确定删除这个商品？'))return;
 const r=await fetch('/delete',{{method:'POST',body:new URLSearchParams({{handle:h}})}});
 if(r.ok)btn.closest('.card').remove();else log('删除失败');
}}
async function add(btn){{
 const f=document.getElementById('a-f').files[0];
 if(!f){{alert('请选择商品图片');return}}
 if(!document.getElementById('a-t').value.trim()){{alert('请填写标题');return}}
 btn.disabled=true;btn.textContent='上传中…';
 const fd=new FormData();
 fd.append('title',document.getElementById('a-t').value);
 fd.append('price',document.getElementById('a-p').value);
 fd.append('type',document.getElementById('a-c').value);
 fd.append('image',f);
 const r=await fetch('/add',{{method:'POST',body:fd}});
 if(r.ok)location.reload();else{{log('添加失败: '+await r.text());btn.disabled=false;btn.textContent='保存商品'}}
}}
async function build(btn){{
 btn.disabled=true;btn.textContent='⏳ 构建中…';
 const r=await fetch('/build',{{method:'POST'}});
 const t=await r.text();
 btn.disabled=false;btn.textContent='🔄 重新构建网站';
 log(t);
 if(r.ok)window.open('/preview/index.html','_blank');
}}
</script></body></html>"""

# ---------- HTTP 服务 ----------
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
        if p == "/":
            return self.send(200, page_html())
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
        try:
            if p == "/update":
                q = parse_qs(body.decode("utf-8"))
                n = update_product(q["handle"][0], q.get("title",[""])[0],
                                   q.get("price",[""])[0], q.get("type",[""])[0])
                return self.send(200, f"updated {n}")
            if p == "/delete":
                q = parse_qs(body.decode("utf-8"))
                return self.send(200, f"deleted {delete_product(q['handle'][0])}")
            if p == "/add":
                ct = self.headers.get("Content-Type","")
                m = re.search(r"boundary=(.+)", ct)
                fields, files = parse_multipart(body, m.group(1).encode())
                fn, data = files["image"]
                ext = os.path.splitext(fn)[1].lower() or ".jpg"
                if ext not in (".jpg",".jpeg",".png",".webp"): ext = ".jpg"
                h = add_product(fields.get("title","").strip(), fields.get("price","").strip(),
                                fields.get("type","").strip(), data, ext)
                return self.send(200, h)
            if p == "/build":
                r = subprocess.run([sys.executable, "build.py"],
                                   capture_output=True, text=True, timeout=120)
                out = (r.stdout + r.stderr).strip()
                return self.send(200 if r.returncode == 0 else 500, out)
        except Exception as e:
            return self.send(500, f"错误: {e}")
        self.send(404, "not found")

if __name__ == "__main__":
    if not os.path.isfile(CSV_PATH):
        print(f"❌ 找不到 {CSV_PATH}，请在 vivabien-web 目录里运行"); sys.exit(1)
    print(f"🛠️  商品管理后台已启动: http://localhost:{PORT}")
    print("   按 Ctrl+C 停止")
    threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
