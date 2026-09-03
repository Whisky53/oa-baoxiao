#!/usr/bin/env python3
"""从用户 Chrome 提取 oa/idaas cookie，解密并生成 Playwright storage_state。
解密格式（实测 Chrome 152 mac13）: b"v10" + salt(16) + iv(16) + ciphertext
PBKDF2(password=keychain原始base64串, salt=b"saltysalt", iterations=1003, dkLen=16) -> AES-128-CBC
用法: python chrome_cookies_to_state.pyt"""
import os, sys, sqlite3, json, shutil, subprocess, tempfile, hashlib

BASE_DIR = "/Users/mac/WorkBuddy/2026-08-31-15-15-44/差旅报销自动化"
COOKIE_DB = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies")
STATE_FILE = os.path.join(BASE_DIR, "data", "oa_state.json")

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
    tmp_db = tempfile.mktemp(suffix=".db")
    shutil.copy2(COOKIE_DB, tmp_db)
    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite, priority
        FROM cookies
        WHERE host_key LIKE '%oa.irootech%' OR host_key LIKE '%idaas.irootech%'
    """).fetchall()
    conn.close()
    os.unlink(tmp_db)
    print(f"找到 {len(rows)} 个 oa/idaas cookie")
    if not rows:
        print("[ERR] 没有 oa/idaas cookie——请先在 Chrome 里登录 OA")
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
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path or "/",
            "expires": exp_sec,
            "httpOnly": bool(httponly),
            "secure": bool(secure),
            "sameSite": ["Strict", "Lax", "None"][samesite] if 0 <= samesite <= 2 else "Lax",
        }
        cookies.append(cookie)
        print(f"  [OK] {host} {name}")
    state = {"cookies": cookies, "origins": []}
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    print(f"\n[OK] 会话已保存到 {STATE_FILE}（{len(cookies)} 个 cookie）")

if __name__ == "__main__":
    main()
