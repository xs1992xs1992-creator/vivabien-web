#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键给商品后台开公网地址 shop-admin.vivabien.xyz
用法: cd ~/vivabien-web && python3 setup_admin_tunnel.py
做三件事:
 1. 注册 DNS: shop-admin.vivabien.xyz → 你的隧道
 2. 修改 ~/.cloudflared/config.yml，把 shop-admin.vivabien.xyz 指到本机 8766 端口
 3. 告诉你下一步怎么启动
改动前会自动备份原配置为 config.yml.bak
"""
import os, re, shutil, subprocess, sys

TUNNEL   = "vivabien-review"
TUNNEL_ID = "8e017a14-0c22-4174-9585-a2504a225a47"
HOSTNAME = "shop-admin.vivabien.xyz"
SERVICE  = "http://localhost:8766"
CFG_DIR  = os.path.expanduser("~/.cloudflared")
CFG      = os.path.join(CFG_DIR, "config.yml")

def run(cmd):
    print("→", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if out: print(" ", out.replace("\n", "\n  "))
    return r.returncode == 0, out

def main():
    # 1) DNS 路由
    ok, out = run(["cloudflared", "tunnel", "route", "dns", TUNNEL, HOSTNAME])
    if not ok and "already exists" not in out and "already configured" not in out:
        print("⚠️ DNS 注册失败（如果之前注册过可忽略），继续…")

    # 2) 改 config.yml
    if os.path.isfile(CFG):
        txt = open(CFG, encoding="utf-8").read()
        if HOSTNAME in txt:
            print(f"✅ {CFG} 里已经有 {HOSTNAME}，不用改")
        else:
            shutil.copy2(CFG, CFG + ".bak")
            entry = f"  - hostname: {HOSTNAME}\n    service: {SERVICE}\n"
            # 插到 catch-all（http_status:404）那一行之前
            m = re.search(r"^(\s*-\s*service:\s*http_status:404\s*)$", txt, re.M)
            if m:
                txt = txt[:m.start()] + entry + txt[m.start():]
            elif re.search(r"^ingress:\s*$", txt, re.M):
                txt = re.sub(r"^(ingress:\s*)$", r"\1\n" + entry, txt, count=1, flags=re.M)
            else:
                txt += f"\ningress:\n{entry}  - service: http_status:404\n"
            open(CFG, "w", encoding="utf-8").write(txt)
            print(f"✅ 已修改 {CFG}（原文件备份为 config.yml.bak）")
    else:
        # 没有配置文件就新建一个（包含审核台 + 后台两条路由）
        os.makedirs(CFG_DIR, exist_ok=True)
        cred = os.path.join(CFG_DIR, f"{TUNNEL_ID}.json")
        open(CFG, "w", encoding="utf-8").write(f"""tunnel: {TUNNEL_ID}
credentials-file: {cred}

ingress:
  - hostname: review.vivabien.xyz
    service: http://localhost:5001
  - hostname: {HOSTNAME}
    service: {SERVICE}
  - service: http_status:404
""")
        print(f"✅ 新建了 {CFG}（含审核台和后台两条路由）")

    print("""
====================================
配置完成！接下来：
 1. 如果隧道正在跑，先按 Ctrl+C 停掉，再重新启动：
      cloudflared tunnel run vivabien-review
 2. 另开一个终端窗口，启动后台：
      cd ~/vivabien-web && python3 admin.py
 3. 打开 https://shop-admin.vivabien.xyz，使用商品后台密码登录。
    （后台已有密码保护，不要把地址和密码发给无关人员）
====================================""")

if __name__ == "__main__":
    main()
