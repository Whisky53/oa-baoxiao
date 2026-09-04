#!/usr/bin/env python3
"""fill_oa_auto - 差旅费报销单自动填表（可移植版）
读取同目录 ../config.json，自动探测 Chrome，填入 OA 差旅费报销单。
用法: python fill_oa_auto.py <发票PDF路径> [--trip 关键字] [--headless]
依赖: pip install playwright pypdf
"""
import os, sys, time, json, platform
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from rail_invoice_parse import parse_rail_pdf

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.environ.get("OA_STATE_FILE") or os.path.join(SKILL_DIR, "data", "oa_state.json")

def load_config():
    with open(os.path.join(SKILL_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)

def detect_chrome():
    """自动探测本机 Chrome"""
    if sys.platform == "darwin":
        p = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(p):
            return p
    elif sys.platform == "win32":
        for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]:
            if os.path.exists(p):
                return p
    else:
        for p in ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]:
            if os.path.exists(p):
                return p
    # 兜底：agent-browser 的 Chrome for Testing
    p = os.path.expanduser("~/.agent-browser/browsers/")
    if os.path.exists(p):
        for d in sorted(os.listdir(p), reverse=True):
            cand = os.path.join(p, d, "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
            if os.path.exists(cand):
                return cand
    raise FileNotFoundError("未找到 Chrome，请安装或设置 CHROME 环境变量")

CHROME = os.environ.get("CHROME") or detect_chrome()

def arg(key, default=None):
    for i, a in enumerate(sys.argv):
        if a == key and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default

def full(name):
    return f"extendDataFormInfo.value({name})"

def js_set(page, name, value):
    return page.evaluate(f"""() => {{
        const el = document.querySelector('input[name="{full(name)}"], textarea[name="{full(name)}"]');
        if (!el) return 'NOT_FOUND';
        el.value = '{value}';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        if (window.jQuery) {{ try {{ jQuery(el).trigger('change'); }} catch(e) {{}} }}
        return 'OK';
    }}""")

def js_select2(page, name, label):
    return page.evaluate(f"""() => {{
        const sel = document.querySelector('select[name="{full(name)}"]');
        if (!sel) return 'SELECT_NOT_FOUND';
        const opt = [...sel.options].find(o => o.text.trim() === '{label}');
        if (!opt) return 'OPTION_NOT_FOUND';
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        if (window.jQuery) {{ try {{ jQuery(sel).trigger('change'); }} catch(e) {{}} }}
        return 'OK';
    }}""")

def close_mask(page):
    page.keyboard.press("Escape")
    time.sleep(0.4)
    page.evaluate("() => { const m = document.querySelector('.select2-drop-mask'); if (m) m.remove(); }")

def select2_click_pick(page, name, tmp_id, keyword=None, first=False, contains="出差申请"):
    r = page.evaluate(f"""() => {{
        const sel = document.querySelector('select[name="{full(name)}"]');
        if (!sel) return 'NO_SELECT';
        let node = sel.closest('.xform_relation_select') || sel.parentElement;
        const a = node.querySelector('a.select2-choice');
        if (!a) return 'NO_CHOICE';
        a.id = '{tmp_id}';
        a.scrollIntoView({{block: 'center'}});
        return 'OK';
    }}""")
    if r != "OK":
        return r
    time.sleep(0.5)
    page.click(f"#{tmp_id}", timeout=8000, no_wait_after=True)
    time.sleep(2.5)
    try:
        if first:
            loc = page.locator(".select2-drop-active li:has-text('" + contains + "')").first
        else:
            loc = page.locator(".select2-drop-active li:has-text('" + keyword + "')").first
        loc.click(timeout=5000)
        close_mask(page)
        return "OK"
    except Exception as e:
        drop_txt = page.evaluate("() => { const d = document.querySelector('.select2-drop-active'); return d ? (d.innerText||'').slice(0,80) : 'NO_DROP'; }")
        close_mask(page)
        return "FAIL:" + str(e)[:50] + " drop=[" + str(drop_txt) + "]"

def select2_search_pick(page, name, tmp_id, keyword, result_contains):
    close_mask(page)
    r = page.evaluate(f"""() => {{
        const sel = document.querySelector('select[name="{full(name)}"]');
        if (!sel) return 'NO_SELECT';
        let node = sel.closest('.xform_relation_select') || sel.parentElement;
        const a = node.querySelector('a.select2-choice');
        if (!a) return 'NO_CHOICE';
        a.id = '{tmp_id}';
        a.scrollIntoView({{block: 'center'}});
        return 'OK';
    }}""")
    if r != "OK":
        return r
    time.sleep(0.5)
    page.click(f"#{tmp_id}", timeout=8000, no_wait_after=True)
    time.sleep(2.5)
    try:
        loc = page.locator(".select2-drop-active li:has-text('" + result_contains + "')").first
        loc.click(timeout=3000)
        close_mask(page)
        return "OK(direct)"
    except Exception:
        pass
    try:
        box = page.locator(".select2-drop-active input.select2-input, .select2-drop-active input.select2-search__field, .select2-drop input.select2-input")
        box.first.fill(keyword, timeout=5000)
        time.sleep(2.5)
        loc = page.locator(".select2-drop-active li:has-text('" + result_contains + "')").first
        loc.click(timeout=5000)
        close_mask(page)
        return "OK(search)"
    except Exception as e:
        drop_txt = page.evaluate("() => { const d = document.querySelector('.select2-drop-active'); return d ? (d.innerText||'').slice(0,150) : 'NO_DROP'; }")
        close_mask(page)
        return "FAIL:" + str(e)[:50] + " drop=[" + str(drop_txt) + "]"

def main():
    if len(sys.argv) < 2:
        print("用法: python fill_oa_auto.py <发票PDF> [--trip 关键字] [--headless]")
        sys.exit(1)
    pdf = sys.argv[1]
    headless = "--headless" in sys.argv
    cfg = load_config()
    trip_kw = arg("--trip", None) or cfg.get("trip_keyword")
    project = arg("--project", None) or cfg.get("project")
    URL = cfg["oa"]["reimburse_new_url"]
    COMPANY = cfg.get("company", "树根互联股份有限公司")
    FEE_TYPE = cfg.get("fee_type", "火车/高铁费用")
    FEE = "fd_fee_item.0."

    inv = parse_rail_pdf(pdf)
    print("发票:", inv["出发站"], "->", inv["到达站"], inv["乘车日期"], inv["票价(含税)"] + "元")
    start_date = inv["乘车日期"]

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=headless, slow_mo=30)
        ctx = browser.new_context(storage_state=STATE_FILE, viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        page.goto(URL, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)

        print("[1] 选择公司:", select2_click_pick(page, "fd_company_code", "__comp", keyword=COMPANY))
        time.sleep(1)
        print("[2] 票据类型:", js_select2(page, "fd_paper_type", "电子票"))
        time.sleep(1)
        print("[3] 是否有出差申请:", js_select2(page, "fd_377ebcdd332a46", "是"))
        time.sleep(2)
        print("[4] 申请事由:", js_set(page, "fd_377f75c5120d22", "出差客户现场"))
        time.sleep(1)
        print("[5] 报销币种:", js_select2(page, "fd_reimbursement_money_type", "人民币"))
        time.sleep(1)
        print("[6] 发票张数:", js_set(page, "fd_377ebcbaabff4c", "1"))
        time.sleep(1)
        try:
            page.set_input_files('input[name="__landray_filefd_invoice_att"]', pdf)
            print("[7] 发票已上传")
        except Exception as e:
            print("[7] 发票上传失败:", str(e)[:100])
        time.sleep(5)  # 等系统自动解析生成 .0. 行
        if trip_kw:
            r = select2_click_pick(page, "fd_378057c5573e88.0.fd_377fb4b73ae7d2", "__trip", keyword=trip_kw)
        else:
            r = select2_click_pick(page, "fd_378057c5573e88.0.fd_377fb4b73ae7d2", "__trip", first=True)
        print("[8] 出差申请:", r)
        time.sleep(2)

        r = select2_search_pick(page, FEE + "fd_erp_type", "__erp", keyword="火车", result_contains="火车/高铁")
        print("[9] 费用类型:", r)
        time.sleep(2)
        fields = {
            FEE + "fd_377ebdd6f64cee": inv["出发站"],
            FEE + "fd_377f76fb2a4068": inv["到达站"],
            FEE + "fd_377ebe019348aa": start_date,
            FEE + "fd_377ebe06621da2": start_date,
            FEE + "fd_38da1066e1ec68": inv["票价(含税)"],
            FEE + "fd_ocr_excltax_amount": inv["不含税金额"],
            FEE + "fd_ocr_tax_amount": inv["税额"],
            FEE + "fd_receipt_no": inv["发票号码"],
        }
        for k, v in fields.items():
            js_set(page, k, v)
            time.sleep(0.4)
        if project:
            r = select2_search_pick(page, FEE + "fd_project_name", "__proj", keyword=project, result_contains=project)
            print("[10.5] 项目相关信息:", r)
            time.sleep(1)
        print("[10] 明细行已填")
        print("[11] 发票币种:", js_select2(page, FEE + "fd_Invoice_currency", "人民币"))
        time.sleep(1)
        print("[12] 发票类型:", js_select2(page, FEE + "fd_receipt_type", "专票"))
        time.sleep(1)

        if headless:
            time.sleep(3)
            check = page.evaluate("""() => {
                const names = ['fd_company_code_text','fd_paper_type','fd_377ebcdd332a46','fd_377f75c5120d22','fd_377ebcbaabff4c'];
                const out = {};
                names.forEach(n => {
                    const el = document.querySelector('[name*="' + n + '"]');
                    out[n] = el ? el.value : 'N/A';
                });
                const fee = ['fd_377ebdd6f64cee','fd_377f76fb2a4068','fd_377ebe019348aa','fd_377ebe06621da2','fd_38da1066e1ec68','fd_receipt_no','fd_erp_type_text'];
                fee.forEach(n => {
                    const el = document.querySelector('[name*="fd_fee_item.0.' + n + ')"]');
                    out[n] = el ? el.value : 'N/A';
                });
                return JSON.stringify(out);
            }""")
            print("验证:", check)
            browser.close()
        else:
            print("=" * 50)
            print("已自动完成: 表头9项 + 报销明细行(费用类型/出发地/目的地/日期/金额/发票币种/发票类型/发票号码)")
            print("请手动补(如需): 项目相关信息 / 本月资金计划编号 / 支付明细")
            print("窗口 20 分钟后自动关闭")
            print("=" * 50)
            time.sleep(1200)
            browser.close()

if __name__ == "__main__":
    main()


# ============ 表单级操作：5 条新规则 ============

def check_radio_by_label(page, label_text, option_text):
    """按文本标签定位并勾选 radio（不依赖字段名，OA改字段也能用）
    策略：找含 label_text 的节点，向上找最近 table，在该 table 内按 Y 坐标最近
    配对含 option_text（"否"/"是"）的 radio。"""
    return page.evaluate(f"""() => {{
        const labels = [...document.querySelectorAll('td,th,div')]
            .filter(e => (e.innerText||'').trim().includes('{label_text}'));
        if (!labels.length) return 'NO_LABEL';
        const label = labels[0];
        const tbl = label.closest("table");
        if (!tbl) return "NO_TABLE";

        const radios = [...tbl.querySelectorAll("input[type=radio]")];
        const targets = radios.filter(r => {{
            const lab = r.closest("label");
            let txt = lab ? lab.textContent.trim() : '';
            if (!txt) {{
                let n = r.nextSibling;
                while (n && n.nodeType !== 3 && n.tagName !== 'SPAN') n = n.nextSibling;
                txt = n ? (n.textContent||'').trim() : '';
            }}
            if (!txt) {{
                const td = r.closest('td');
                if (td) txt = (td.innerText||'').replace(/[ \\t\\n]+/g,' ').trim();
            }}
            return txt === '{option_text}' || txt.includes('{option_text}');
        }});

        if (!targets.length) return 'NO_RADIO_FOR_' + '{option_text}';

        // 蓝凌 OA：每个 radio的所属 tr.innerText 含其 label 文字，直接按 tr 文本配对
        let best = null;
        for (const r of targets) {{
            const rTr = r.closest('tr');
            if (!rTr) continue;
            if ((rTr.innerText||'').includes('{label_text}')) {{
                best = r;
                break;
            }}
        }}
        if (!best) return 'NO_RADIO_IN_LABEL_TR';

        best.click();
        best.dispatchEvent(new Event('change', {{bubbles:true}}));
        if (window.jQuery) {{ try {{ jQuery(best).trigger('change'); }} catch(e) {{}} }}
        return 'OK: ' + (best.name||'') + '=' + best.value + ' trtxt_match=true';
    }}""")

def click_button_by_label(page, label_text, button_text):
    """按文本标签定位并点击按钮
    策略：找含 label_text 节点所在 table 的所有按钮，按 closest('tr').innerText
    是否含 label_text 配对（蓝凌 OA 按钮在同一 tr）。"""
    return page.evaluate(f"""() => {{
        const labels = [...document.querySelectorAll('td,th,div')]
            .filter(e => (e.innerText||'').trim().includes('{label_text}'));
        if (!labels.length) return 'NO_LABEL';
        const tbl = labels[0].closest('table');
        if (!tbl) return 'NO_TABLE';

        const cands = [...tbl.querySelectorAll('a,button,span,input')]
            .filter(b => {{
                const t = (b.innerText||b.value||'').trim();
                return t === '{button_text}' || t.includes('{button_text}');
            }});

        let best = null;
        for (const b of cands) {{
            const bTr = b.closest('tr');
            if (!bTr) continue;
            if ((bTr.innerText||'').includes('{label_text}')) {{
                best = b;
                break;
            }}
        }}
        if (!best) return 'NO_BTN_IN_LABEL_TR';

        best.click();
        return 'OK: ' + best.tagName + ' ' + (best.innerText||'').trim().slice(0,10);
    }}""")

def click_button_by_text(page, button_text, exact=True):
    """全页面找按钮并点击"""
    js_expr = ("(b.innerText||b.value||'').trim() === '{button_text}'"
               if exact else
               "(b.innerText||b.value||'').includes('{button_text}')")
    return page.evaluate(f"""() => {{
        const btns = [...document.querySelectorAll('a,button,span,input')];
        const match = btns.find(b => {js_expr});
        if (!match) return 'NOT_FOUND';
        match.click();
        return 'OK: ' + match.tagName;
    }}""")


def apply_post_rules(page):
    """5 条新规则中的 4 条前置动作（不含暂存）"""
    out = {}
    out["只报账不付款=否"] = check_radio_by_label(page, "只报账不付款", "否")
    time.sleep(0.5)
    out["是否冲销借款=否"] = check_radio_by_label(page, "是否冲销借款", "否")
    time.sleep(0.5)
    out["支付对象=本人"] = check_radio_by_label(page, "支付对象", "本人")
    time.sleep(0.5)
    # 本月资金计划编号：Relation_Choose 弹窗本轮未攻破，跳过（不卡点，用户检查时手动补）
    time.sleep(4)  # 等弹窗系统自动带出
    return out


def select2_input_pick(page, input_name, tmp_id, keyword=None, first=False):
    """蓝凌 inputsgl 输入型 select2（如"项目相关信息"）：点击容器 a.select2-choice → 选结果
    远程搜索型：点击后下拉为空，填搜索框关键字加载结果。控件是 input 而非 select。"""
    r = page.evaluate(f"""() => {{
        const inp = document.querySelector('input[name="extendDataFormInfo.value({input_name})"]');
        if (!inp) return 'NO_INPUT';
        let node = inp.closest('tr');
        const a = node ? node.querySelector('a.select2-choice') : null;
        if (!a) return 'NO_CHOICE';
        a.id = '{tmp_id}';
        a.scrollIntoView({{block: 'center'}});
        return 'OK';
    }}""")
    if r != "OK":
        return r
    time.sleep(0.5)
    page.click(f"#{tmp_id}", timeout=8000, no_wait_after=True)
    time.sleep(2)
    # 方案1：直接点结果（预加载）
    try:
        if first:
            loc = page.locator(".select2-drop-active li").first
        else:
            loc = page.locator(f".select2-drop-active li:has-text('{keyword}')").first
        loc.click(timeout=3000)
        close_mask(page)
        return "OK(direct)"
    except Exception:
        pass
    # 方案2：远程搜索——填搜索框
    try:
        box = page.locator(".select2-drop-active input.select2-input, .select2-drop-active input.select2-search__field, .select2-drop input.select2-input")
        box.first.fill(keyword, timeout=5000)
        time.sleep(2.5)
        loc = page.locator(f".select2-drop-active li:has-text('{keyword}')").first
        loc.click(timeout=5000)
        close_mask(page)
        return "OK(search)"
    except Exception as e:
        drop_txt = page.evaluate("() => { const d = document.querySelector('.select2-drop-active'); return d ? (d.innerText||'').slice(0,150) : 'NO_DROP'; }")
        close_mask(page)
        return "FAIL:" + str(e)[:50] + " drop=[" + str(drop_txt) + "]"


def relation_choose_pick(page, input_name, keyword, wait=6):
    """蓝凌 Relation_Choose 关联选择（如"项目相关信息"）：
    点 td 内 div[onclick*=Relation_Choose_Run] → 弹窗 iframe(relation_event_dialog_list)
    → 填搜索框(outerSearchCondition) → 点搜索(btn_search) → 选结果行(List_Selected) → 点确定。
    返回 OK/失败原因。"""
    # 1. 打开弹窗
    r = page.evaluate(f"""() => {{
        const inp = document.querySelector('input[name="extendDataFormInfo.value({input_name})"]');
        if (!inp) return 'NO_INPUT';
        const td = inp.closest('td');
        const div = td.querySelector('div[onclick*="Relation_Choose_Run"]');
        if (!div) return 'NO_RUN_DIV';
        div.click();
        return 'OPENED';
    }}""")
    if r != "OPENED":
        return f"FAIL: {r}"
    time.sleep(wait)
    # 2. 定位弹窗 iframe
    fl = page.frame_locator('iframe[src*="relation_event_dialog_list"]')
    try:
        fl.locator('input[name="outerSearchCondition"]').first.fill(keyword, timeout=8000)
    except Exception as e:
        close_mask(page)
        return f"FAIL: 弹窗搜索框不可用 {str(e)[:60]}"
    time.sleep(1)
    # 3. 触发搜索：在搜索框按 Enter（实测 btn_search 点击无效，Enter 才触发加载）
    try:
        fl.locator('input[name="outerSearchCondition"]').first.press("Enter")
    except Exception:
        try:
            fl.locator('input[name="btn_outerSearch"]').first.click(timeout=4000, no_wait_after=True)
        except Exception:
            fl.locator('body').evaluate("() => { const b = document.querySelector('input[name=btn_search]'); if (b) b.click(); }")
    time.sleep(4)
    # 4. 找结果行：List_Selected 所在行含关键字
    try:
        rows = fl.locator('input[name="List_Selected"]').all()
        target = None
        for i, row_el in enumerate(rows):
            try:
                row_text = fl.locator('table tr').nth(i + 1).inner_text()  # 表头占第1行
            except Exception:
                row_text = ""
            if keyword in row_text:
                target = row_el
                break
        if target is None:
            # 兜底：点第一行
            if rows:
                target = rows[0]
        if target:
            target.check(timeout=5000)
            time.sleep(0.5)
            # 5. 点确定
            try:
                fl.locator('input[value="确定"]').first.click(timeout=4000, no_wait_after=True)
            except Exception:
                fl.locator('a').filter(has_text="确定").first.click(timeout=4000, no_wait_after=True)
            time.sleep(2)
            return "OK"
        return "FAIL: 无结果行"
    except Exception as e:
        close_mask(page)
        return f"FAIL: 选择/确定异常 {str(e)[:60]}"


def save_draft(page):
    """点暂存按钮。
    蓝凌 lui 工具栏：div.lui_toolbar_btn_l 含"暂存"文本（在表单填了内容后才渲染）；
    若暂存按钮不存在则安全降级，不自动点提交文档（避免误进审批流）。"""
    # 先滚动到顶部（工具栏可能 fixed 在顶部）
    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    # 方案1：真实点击蓝凌工具栏按钮
    try:
        loc = page.locator("div.lui_toolbar_btn_l").filter(has_text="暂存").first
        loc.click(timeout=4000, no_wait_after=True)
        return "OK: 已点暂存"
    except Exception:
        pass
    # 方案2：JS 兜底（div/text 节点都行）
    r = page.evaluate("""() => {
        const candidates = [...document.querySelectorAll('div,a,button,span')].filter(el => {
            const t = (el.innerText||el.textContent||'').trim();
            return t === '暂存' && el.offsetParent !== null;
        });
        if (!candidates.length) return 'NOT_FOUND';
        candidates[0].click();
        return 'OK(JS)';
    }""")
    if r.startswith("OK"):
        return f"OK: 已点暂存({r})"
    return "WARN: 暂存按钮不可见（可能表单未填完），未自动提交——请手动确认"
