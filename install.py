#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install.py - 差旅费报销自动化 Skill 环境配置器（跨平台：macOS / Windows / Linux）

每个新环境使用前先运行本脚本完成「环境配置」，之后每次报销直接触发即可：

  0. 环境配置  ：生成 config.json（从模板复制）并提示替换 OA 地址/项目/票据目录占位符
  1. 环境检查  ：Python 版本、Chrome 浏览器
  2. 依赖安装  ：playwright + pypdf（Chromium 失败自动回退本机 Chrome）
  3. 配置向导  ：发票目录等个性化设置
  4. 会话引导  ：引导你在浏览器登录 OA 一次，保存登录会话（macOS 可自动提取本机 Chrome 会话）
  5. 自检      ：无头验证会话有效，输出配置报告

用法:
  python install.py               # 完整环境配置（推荐，交互式）
  python install.py --skip-deps   # 跳过依赖安装（已有环境时）
  python install.py --skip-login  # 跳过登录引导（仅检查/装依赖）
  python install.py --check-only  # 只检查环境，不装任何东西

依赖: Python 3.8+（安装脚本本身只用标准库）
"""
import os
import sys
import json
import shutil
import subprocess
import platform

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SKILL_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "oa_state.json")
CONFIG_FILE = os.path.join(SKILL_DIR, "config.json")
EXAMPLE_FILE = os.path.join(SKILL_DIR, "config.example.json")

OK = "\033[92m[OK]\033[0m"
WARN = "\033[93m[!!]\033[0m"
ERR = "\033[91m[XX]\033[0m"
INFO = "\033[96m[..]\033[0m"


def c(text, color=None):
    if color == "ok":
        return f"{OK} {text}"
    if color == "warn":
        return f"{WARN} {text}"
    if color == "err":
        return f"{ERR} {text}"
    if color == "info":
        return f"{INFO} {text}"
    return text


def run(cmd, **kw):
    """执行命令并返回 (returncode, stdout)"""
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p.returncode, p.stdout.strip()


def which_python():
    """当前运行本脚本的 Python"""
    return sys.executable or "python"


def step1_check_env():
    """环境检查：Python + Chrome"""
    print("\n" + "=" * 56)
    print("  步骤 1/4  环境检查")
    print("=" * 56)
    ok = True

    # Python 版本
    ver = sys.version_info
    if ver.major >= 3 and ver.minor >= 8:
        print(c(f"Python {ver.major}.{ver.minor}.{ver.micro} ✓", "ok"))
    else:
        print(c(f"Python {ver.major}.{ver.minor} 过旧，需要 3.8+", "err"))
        ok = False

    # Chrome 探测
    chrome = detect_chrome()
    if chrome:
        print(c(f"检测到 Chrome: {chrome}", "ok"))
    else:
        print(c("未检测到 Chrome，后续将尝试下载 Chromium（约 150MB）", "warn"))
    return ok


def detect_chrome():
    """跨平台探测本机 Chrome"""
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
        candidates = [
            "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium", "/usr/bin/chromium-browser",
        ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    # 兜底：agent-browser 的 Chrome for Testing
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


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def oa_portal(cfg):
    """优先取 portal，其次取 reimburse_new_url 作为登录目标地址"""
    oa = cfg.get("oa", {}) or {}
    return oa.get("portal") or oa.get("reimburse_new_url") or ""


def oa_hostname(cfg):
    from urllib.parse import urlparse
    return (urlparse(oa_portal(cfg)).hostname or "").lower()


def ensure_config():
    """环境配置第 0 步：确保 config.json 存在且占位符已替换。
    缺失时从 config.example.json 复制生成，并提示用户填写本机构 OA 参数。
    未完成替换返回 False（后续登录/自检跳过，先配置再运行）。"""
    if not os.path.exists(CONFIG_FILE):
        if not os.path.exists(EXAMPLE_FILE):
            print(c("缺少 config.json 且缺少 config.example.json 模板，无法自动生成", "err"))
            return False
        shutil.copy2(EXAMPLE_FILE, CONFIG_FILE)
        print(c(f"已由 config.example.json 生成: {CONFIG_FILE}", "ok"))
        print(c("请先用文本编辑器打开 config.json，完成以下替换：", "warn"))
        print(c("  1) OA_HOST / SSO_HOST / TEMPLATE_ID 占位符 → 贵司 OA 门户、统一认证与报销流程模板地址", "warn"))
        print(c("  2) invoice_dir → 票据目录（同一批次发票及其它凭证所在文件夹）", "warn"))
        print(c("  3) project → 报销项目名（也可运行时用 --project 传入）", "warn"))
        print(c("填写完成后重新运行本安装器即可继续；不填写则无法登录与报销。", "warn"))
        try:
            cfg = json.load(open(CONFIG_FILE, encoding="utf-8"))
        except Exception:
            cfg = {}
        if not cfg or "OA_HOST" in oa_portal(cfg) or not oa_portal(cfg):
            return False
    # 已存在但仍是占位符（可能由旧 example 复制而来）
    try:
        cfg = load_config()
    except Exception:
        return False
    if "OA_HOST" in oa_portal(cfg) or "SSO_HOST" in json.dumps(cfg.get("oa", {}), ensure_ascii=False):
        print(c("config.json 仍含 OA_HOST/SSO_HOST 占位符，请先替换为贵司实际地址", "warn"))
        return False
    return True


def step2_install_deps(skip_deps=False):
    """依赖安装：playwright + pypdf"""
    print("\n" + "=" * 56)
    print("  步骤 2/4  依赖安装")
    print("=" * 56)
    if skip_deps:
        print(c("已跳过（--skip-deps）", "info"))
        return True

    # 先检查是否已装
    rc, _ = run([which_python(), "-c", "import playwright, pypdf"])
    if rc == 0:
        print(c("playwright + pypdf 已安装 ✓", "ok"))
        return True

    print(c("正在安装 playwright + pypdf ...", "info"))
    rc, out = run([which_python(), "-m", "pip", "install", "-q", "playwright", "pypdf"])
    if rc != 0:
        print(c(f"pip 安装失败: {out[-200:]}", "err"))
        print(c("请手动执行: pip install playwright pypdf", "warn"))
        return False

    # 尝试下载 chromium（失败不影响，有本机 Chrome 兜底）
    print(c("正在下载 Chromium（首次约 150MB，失败会自动用本机 Chrome）...", "info"))
    rc, out = run([which_python(), "-m", "playwright", "install", "chromium"])
    if rc == 0:
        print(c("Chromium 下载完成 ✓", "ok"))
    else:
        print(c("Chromium 下载失败/跳过，将使用本机 Chrome（已自动探测）", "warn"))
    return True


def step3_config():
    """配置向导：发票目录等"""
    print("\n" + "=" * 56)
    print("  步骤 3/4  配置检查")
    print("=" * 56)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(c(f"config.json 读取失败: {e}", "err"))
        return False

    inv_dir = cfg.get("invoice_dir", "")
    if inv_dir and os.path.isdir(inv_dir):
        print(c(f"发票目录: {inv_dir} ✓", "ok"))
    elif inv_dir and not os.path.isdir(inv_dir):
        print(c(f"发票目录不存在: {inv_dir}", "warn"))
        try:
            os.makedirs(inv_dir, exist_ok=True)
            print(c(f"已自动创建: {inv_dir} ✓", "ok"))
        except Exception as e:
            print(c(f"目录创建失败: {e}", "warn"))
    else:
        # 首次运行：询问用户发票目录（回车用默认，默认目录会自动创建）
        default_dir = os.path.join(os.path.expanduser("~"), "Desktop", "reimburse_tickets")
        print(c("发票目录未配置（首次运行需确认一次）", "warn"))
        try:
            ans = input(f"    发票目录（直接回车用默认 {default_dir}）: ").strip()
            if not ans:
                ans = default_dir
            os.makedirs(ans, exist_ok=True)
            cfg["invoice_dir"] = ans
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(c(f"已写入 config.json: {ans} ✓", "ok"))
        except Exception as e:
            print(c(f"目录创建失败: {e}", "warn"))

    # 展示当前关键配置
    print(c("当前配置: 公司=%s | 费用类型=%s" % (
        cfg.get("company", "?"), cfg.get("fee_type", "?")), "info"))
    return True


def step4_login(skip_login=False):
    """会话引导：登录 OA 一次，保存会话（平台自适应）"""
    print("\n" + "=" * 56)
    print("  步骤 4/4  登录会话")
    print("=" * 56)
    if skip_login:
        print(c("已跳过（--skip-login）", "info"))
        return True

    if os.path.exists(STATE_FILE):
        print(c(f"检测到已有会话: {STATE_FILE}", "info"))
        ans = input("    是否重新登录？(y/N): ").strip().lower()
        if ans != "y":
            print(c("保留现有会话", "ok"))
            return True

    sysname = platform.system()
    scripts_dir = os.path.join(SKILL_DIR, "scripts")

    # macOS：优先自动提取本机 Chrome 已登录的 OA 会话（无需重新输密码）
    if sysname == "Darwin":
        print(c("正在尝试从本机 Chrome 提取已登录的 OA 会话（无需输入密码）...", "info"))
        rc, out = run([which_python(), os.path.join(scripts_dir, "chrome_cookies_to_state.py")])
        if rc == 0 and os.path.exists(STATE_FILE):
            print(c("已从 Chrome 提取会话 ✓", "ok"))
            return True
        print(c("Chrome 中未找到 OA 登录态（可能没登录过或已过期），改用浏览器引导登录", "warn"))
        print()

    # 通用：打开浏览器引导登录
    print(c("将打开浏览器窗口，请在弹出的窗口中登录 OA（账号+密码）", "info"))
    print(c("登录成功后窗口会自动关闭并保存会话，请勿手动关闭浏览器", "info"))
    print()
    rc, out = run([which_python(), os.path.join(scripts_dir, "login_browser.py")])
    if rc == 0 and os.path.exists(STATE_FILE):
        print(c("会话已保存 ✓", "ok"))
        return True
    else:
        print(c(f"登录引导失败: {out[-200:]}", "err"))
        print(c("请检查: 1)网络可访问 OA  2)账号密码正确", "warn"))
        return False


def step5_verify():
    """自检：无头打开 OA 页面验证会话"""
    print("\n" + "=" * 56)
    print("  自检  会话验证")
    print("=" * 56)
    if not os.path.exists(STATE_FILE):
        print(c("无会话文件，跳过自检", "warn"))
        return True
    try:
        cfg = load_config()
    except Exception:
        print(c("config.json 读取失败，跳过自检", "warn"))
        return True
    portal = oa_portal(cfg)
    host = oa_hostname(cfg)
    if not portal:
        print(c("config.json 未配置 OA 地址，跳过自检", "warn"))
        return True
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(c("playwright 未安装，跳过自检", "warn"))
        return True
    chrome = detect_chrome()
    try:
        with sync_playwright() as p:
            kw = {}
            if chrome:
                kw["executable_path"] = chrome
            browser = p.chromium.launch(headless=True, **kw)
            ctx = browser.new_context(storage_state=STATE_FILE, viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            page.goto(portal, timeout=45000)
            page.wait_for_load_state("domcontentloaded")
            import time
            time.sleep(2)
            from urllib.parse import urlparse
            cur = (urlparse(page.url).hostname or "").lower()
            if cur != host or "login" in page.url.lower():
                print(c(f"会话已过期（未到达 OA 或跳转登录页: {page.url[:60]}）", "err"))
                print(c("请重新运行本安装器完成登录，或手动在 Chrome 登录 OA 后运行 scripts/chrome_cookies_to_state.py", "warn"))
                browser.close()
                return False
            print(c(f"会话有效 ✓（已打开 OA: {page.url[:70]}）", "ok"))
            browser.close()
            return True
    except Exception as e:
        print(c(f"自检异常: {str(e)[:120]}", "warn"))
        return True


def print_report(results):
    print("\n" + "=" * 56)
    print("  安装报告")
    print("=" * 56)
    for name, ok in results.items():
        print(c(f"{name}: {'通过 ✓' if ok else '失败 ✗'}", "ok" if ok else "err"))
    if all(results.values()):
        print()
        print(c("安装完成！现在可以用了：", "ok"))
        print(c("  1) 把同批次发票及其它凭证放进发票目录（config.json 里配置的路径）", "info"))
        print(c("  2) 启动带调试端口的 Chrome 并登录 OA，然后说「报销差旅费用」/「提交差旅报销」，或手动运行:", "info"))
        print(c("     python scripts/fill_oa_batch.py --project 项目名", "info"))
        print(c("  3) 弹窗核对后确认“已点暂存”即完成（本流程不自动提交）", "info"))
    else:
        print()
        print(c("有步骤未通过，请按上面提示处理后再运行: python install.py", "err"))


def main():
    args = sys.argv[1:]
    skip_deps = "--skip-deps" in args
    skip_login = "--skip-login" in args
    check_only = "--check-only" in args

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║   差旅费报销自动化 Skill 安装器 v1.0             ║")
    print("  ║   企业 OA · 差旅票据自动填单（跨平台）            ║")
    print("  ╚══════════════════════════════════════════════════╝")

    results = {}

    results["环境检查"] = step1_check_env()
    if check_only:
        print(c("\n（--check-only 模式，仅检查环境）", "info"))
        print_report(results)
        return

    results["依赖安装"] = step2_install_deps(skip_deps)
    # 环境配置先行：config.json 必须存在且不含占位符，登录/自检才可继续
    configured = ensure_config()
    results["环境配置(config.json)"] = configured
    if not configured:
        print(c("环境配置未完成：请编辑 config.json 替换占位符后再运行 python install.py", "warn"))
        print_report(results)
        return
    results["配置检查"] = step3_config()
    results["登录会话"] = step4_login(skip_login)
    results["会话自检"] = step5_verify()

    print_report(results)


if __name__ == "__main__":
    main()
