#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
login_browser.py - 跨平台 OA 登录引导（macOS / Windows / Linux）
打开浏览器窗口 → 用户手动登录 OA → 自动保存会话到 data/oa_state.json

这是 Windows/Linux 的标准会话获取方式；macOS 也可用（无需 keychain）。

用法: python login_browser.py
"""
import os
import sys
import time
import json
from urllib.parse import urlparse

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "oa_state.json")


def load_config():
    with open(os.path.join(SKILL_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def portal_url(cfg):
    return cfg.get("oa", {}).get("portal", "") or cfg.get("oa", {}).get("reimburse_new_url", "")


def detect_chrome():
    """跨平台探测本机 Chrome（与 install.py 一致）"""
    import platform
    sysname = platform.system()
    candidates = []
    if sysname == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif sysname == "Windows":
        candidates = [
            os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        ]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                      "/usr/bin/chromium", "/usr/bin/chromium-browser"]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    base = os.path.expanduser("~/.agent-browser/browsers/")
    if os.path.isdir(base):
        for d in sorted(os.listdir(base), reverse=True):
            cand = os.path.join(base, d)
            if sysname == "Darwin":
                c2 = os.path.join(cand, "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
            elif sysname == "Windows":
                c2 = os.path.join(cand, "chrome-win64", "chrome.exe")
            else:
                c2 = os.path.join(cand, "chrome-linux64", "chrome")
            if os.path.exists(c2):
                return c2
    return None


def oa_hostname(cfg):
    return (urlparse(portal_url(cfg)).hostname or "").lower()


def is_logged_in(url, host):
    """到达 OA 自身域名、且当前路径不含 login 视为已登录；停留在 SSO/统一认证页不算。"""
    if not host:
        return False
    cur = (urlparse(url).hostname or "").lower()
    return cur == host and "login" not in url.lower()


def main():
    print("=" * 56)
    print("  OA 登录引导")
    print("=" * 56)
    print("  1) 将打开一个浏览器窗口")
    print("  2) 请在窗口中用你的账号登录 OA")
    print("  3) 登录成功后本脚本自动保存会话并关闭窗口")
    print("  （最多等待 10 分钟，请勿手动关闭浏览器窗口）")
    print("=" * 56)

    from playwright.sync_api import sync_playwright

    chrome = detect_chrome()
    cfg = load_config()
    url0 = portal_url(cfg)
    host = oa_hostname(cfg)
    if not url0:
        print("config.json 未配置 oa.portal / oa.reimburse_new_url，请先完成环境配置")
        return 1
    with sync_playwright() as p:
        kw = {}
        if chrome:
            kw["executable_path"] = chrome
        browser = p.chromium.launch(headless=False, slow_mo=30, **kw)
        ctx = browser.new_context(viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        page.goto(url0, timeout=60000)
        try:
            page.bring_to_front()
        except Exception:
            pass
        deadline = time.time() + 600
        logged = False
        while time.time() < deadline:
            try:
                if is_logged_in(page.url, host):
                    logged = True
                    break
            except Exception:
                pass
            time.sleep(2)
        if logged:
            time.sleep(3)
            os.makedirs(DATA_DIR, exist_ok=True)
            ctx.storage_state(path=STATE_FILE)
            print(f"\n[OK] 登录成功，会话已保存到: {STATE_FILE}")
        else:
            print("\n[ERR] 等待登录超时（10 分钟），请重新运行")
        browser.close()


if __name__ == "__main__":
    main()
