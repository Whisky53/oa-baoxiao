#!/usr/bin/env python3
"""fill_oa_auto v0.7 - 差旅费报销单自动填表（全字段正确）
用法: python fill_oa_auto.pyt <发票PDF> [--trip 关键字] [--headless]
"""
import os, sys, time, json
from playwright.sync_api import sync_playwright

BASE_DIR = "/Users/mac/WorkBuddy/2026-08-31-15-15-44/差旅报销自动化"
CHROME = "/Users/mac/.agent-browser/browsers/chrome-152.0.7977.64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
STATE_FILE = os.path.join(BASE_DIR, "data", "oa_state.json")
sys.path.insert(0, BASE_DIR)
from importlib.machinery import SourceFileLoader
rip = SourceFileLoader("rip", os.path.join(BASE_DIR, "rail_invoice_parse.pyt")).load_module()

URL = "https://oa.irootech.com/km/review/km_review_main/kmReviewMain.do?method=add&fdTemplateId=16bb0944803d4d32a9ab22f4f0180733&fdTemplate=16bb0944803d4d32a9ab22f4f0180733"
FEE = "fd_fee_item.0."

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
    page.click(f"#{tmp_id}", timeout=8000)
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
    page.click(f"#{tmp_id}", timeout=8000)
    time.sleep(2.5)
    # 方案1：直接点结果（选项可能已加载）
    try:
        loc = page.locator(".select2-drop-active li:has-text('" + result_contains + "')").first
        loc.click(timeout=3000)
        close_mask(page)
        return "OK(direct)"
    except Exception:
        pass
    # 方案2：填搜索框
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
        print("用法: python fill_oa_auto.pyt <发票PDF> [--trip 关键字] [--headless]")
        sys.exit(1)
    pdf = sys.argv[1]
    headless = "--headless" in sys.argv
    trip_kw = arg("--trip", None)
    inv = rip.parse_rail_pdf(pdf)
    print("发票:", inv["出发站"], "->", inv["到达站"], inv["乘车日期"], inv["票价(含税)"] + "元")
    start_date = inv["乘车日期"]

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=headless, slow_mo=30)
        ctx = browser.new_context(storage_state=STATE_FILE, viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        page.goto(URL, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)

        # 主表单
        print("[1] 选择公司:", select2_click_pick(page, "fd_company_code", "__comp", keyword="树根互联股份有限公司"))
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
        time.sleep(4)
        if trip_kw:
            r = select2_click_pick(page, "fd_378057c5573e88.0.fd_377fb4b73ae7d2", "__trip", keyword=trip_kw)
        else:
            r = select2_click_pick(page, "fd_378057c5573e88.0.fd_377fb4b73ae7d2", "__trip", first=True)
        print("[8] 出差申请:", r)
        time.sleep(2)

        # 等待系统上传发票后自动生成 .0. 行（不点添加行，避免多生空行）
        time.sleep(5)
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
        print("[10] 明细行已填: 出发地/目的地/开始/结束日期/金额/OCR/发票号码")
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
                const trip = document.querySelector('input[name="extendDataFormInfo.value(fd_378057c5573e88.0.fd_377fb4b73ae7d2_text)"]');
                out['trip'] = trip ? trip.value : '?';
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
