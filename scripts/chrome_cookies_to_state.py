#!/usr/bin/env python3
"""从本机 Chrome 提取 OA 会话 cookie 生成 Playwright storage_state（仅 macOS）
用法: python chrome_cookies_to_state.py
前提: 已在本机 Chrome 里登录过 OA（OA 域名以 config.json 的 oa.portal / oa.login_url 为准）
说明: macOS 专用（依赖 Keychain 的 Chrome Safe Storage 密钥）。
      Windows/Linux 请改用 login_browser.py 打开浏览器引导登录。
"""
import os, sys, json, sqlite3, shutil, subprocess, tempfile, hashlib
from urllib.parse import urlparse

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_DB = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies")
STATE_FILE = os.path.join(SKILL_DIR, "data", "oa_state.json")


def load_config():
    with open(os.path.join(SKILL_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def oa_hosts(cfg):
    """返回需提取 cookie 的 host 片段集合（OA 门户 + SSO 登录域）"""
    hosts = set()
    for key in ("portal", "login_url", "reimburse_new_url"):
        url = cfg.get("oa", {}).get(key, "")
        h = urlparse(url).hostname or ""
        if h:
            hosts.add(h)
            # SSO 常与 OA 不同域；去掉 www 后作为片段匹配
            hosts.add(h[4:] if h.startswith("www.") else h)
    return sorted(hosts)

def get_key_raw():
    out = subprocess.run(["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
                         capture_output=True, text=True)
    return out.stdout.strip().encode()

def decrypt_v10(enc_value, key):
    if not enc_value.startswith(b"v10") or len(enc_value) < 35:
        return None
    iv = enc_value[19:35]
    ct = enc_value[35:]
    key_hex = hashlib.pbkdf2_hmac("sha1", key, b"saltysalt", 1003, 16).hex()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(ct)
        tmpf = f.name
    out = subprocess.run(
        ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key_hex, "-iv", iv.hex(), "-in", tmpf],
        capture_output=True)
    os.unlink(tmpf)
    if out.returncode != 0 or not out.stdout:
        return None
    d = out.stdout
    pad = d[-1]
    if 1 <= pad <= 16:
        d = d[:-pad]
    return d.decode("utf-8", errors="replace")

def chrome_time_to_epoch(us):
    if us <= 0:
        return None
    return us / 1e6 - 11644473600

def main():
    key = get_key_raw()
    print("keychain 密钥获取成功（长度", len(key), "字节）")
    if not os.path.exists(COOKIE_DB):
        print("[ERR] 未找到 Chrome Cookie 数据库")
        sys.exit(1)
    cfg = load_config()
    hosts = oa_hosts(cfg)
    if not hosts:
        print("[ERR] config.json 未配置 oa.portal / oa.login_url，请先完成环境配置")
        sys.exit(1)
    likes = " OR ".join(["host_key LIKE ?"] * len(hosts))
    params = ["%" + h + "%" for h in hosts]
    tmp_db = tempfile.mktemp(suffix=".db")
    shutil.copy2(COOKIE_DB, tmp_db)
    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()
    rows = cur.execute(f"""
        SELECT host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite, priority
        FROM cookies
        WHERE {likes}
    """, params).fetchall()
    conn.close()
    os.unlink(tmp_db)
    print(f"找到 {len(rows)} 个 OA/SSO 域 cookie（匹配: {', '.join(hosts)}）")
    if not rows:
        print("[ERR] 未找到 OA 域 cookie——请先在 Chrome 里登录 OA 后重试")
        sys.exit(1)
    cookies = []
    for host, name, enc, path, exp, secure, httponly, samesite, priority in rows:
        value = decrypt_v10(enc, key)
        if value is None:
            print(f"[WARN] 无法解密: {host} {name}")
            continue
        domain = host if host.startswith(".") else host
        exp_sec = chrome_time_to_epoch(exp)
        if exp_sec is None:
            exp_sec = -1
        cookies.append({
            "name": name, "value": value, "domain": domain, "path": path or "/",
            "expires": exp_sec, "httpOnly": bool(httponly), "secure": bool(secure),
            "sameSite": ["Strict", "Lax", "None"][samesite] if 0 <= samesite <= 2 else "Lax",
        })
        print(f"  [OK] {host} {name}")
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookies": cookies, "origins": []}, f, ensure_ascii=False)
    print(f"\n[OK] 会话已保存到 {STATE_FILE}（{len(cookies)} 个 cookie）")

if __name__ == "__main__":
    main()
