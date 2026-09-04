#!/usr/bin/env python3
import os,sys,time,re
from pathlib import Path
from pypdf import PdfReader
from playwright.sync_api import sync_playwright
from importlib.machinery import SourceFileLoader
BASE=Path('/Users/mac/.workbuddy/skills/oa-baoxiao'); auto=SourceFileLoader('auto',str(BASE/'scripts/fill_oa_auto.py')).load_module()
PDF=sys.argv[1] if len(sys.argv)>1 and not sys.argv[1].startswith('-') else '/Users/mac/Desktop/待使用/酒店票.pdf'
URL='https://oa.irootech.com/km/review/km_review_main/kmReviewMain.do?method=add&fdTemplateId=16bb0944803d4d32a9ab22f4f0180733&fdTemplate=16bb0944803d4d32a9ab22f4f0180733'
PROJECT='工业可视化DV'
text='\n'.join((p.extract_text() or '') for p in PdfReader(PDF).pages)
if '住宿' not in text and '酒店' not in text and '代订' not in text: raise SystemExit('不是酒店票')
num=re.search(r'(?<!\d)(\d{20})(?!\d)',text); date=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日',text); total=re.search(r'¥\s*([0-9]+(?:\.[0-9]{1,2})?)',text)
ex=re.search(r'金\s*额\s*税率.*?\n.*?([0-9]+(?:\.[0-9]{1,2})?)\s+6%\s+([0-9]+(?:\.[0-9]{1,2})?)',text,re.S)
invno=num.group(1) if num else ''; d=f'{date.group(1)}-{int(date.group(2)):02d}-{int(date.group(3)):02d}' if date else ''; amount=float(total.group(1)) if total else 0; excl=float(ex.group(1)) if ex else amount; tax=float(ex.group(2)) if ex else 0
print('[票种预检] 酒店'); print('[酒店解析]',invno,d,amount)
with sync_playwright() as p:
 cdp=os.environ.get('OA_CDP_URL'); browser=p.chromium.connect_over_cdp(cdp) if cdp else p.chromium.launch(executable_path=auto.CHROME,headless=False,slow_mo=30)
 ctx=browser.contexts[0] if cdp and browser.contexts else browser.new_context(storage_state=os.environ.get('OA_STATE_FILE',str(BASE/'data/oa_state.json')),viewport={'width':1600,'height':1000}); page=ctx.pages[-1] if cdp and ctx.pages else ctx.new_page()
 page.goto(URL,timeout=60000); page.wait_for_load_state('domcontentloaded'); time.sleep(5)
 auto.select2_click_pick(page,'fd_company_code','__comp',keyword='树根互联股份有限公司'); auto.js_select2(page,'fd_paper_type','电子票'); auto.js_select2(page,'fd_377ebcdd332a46','是'); auto.js_set(page,'fd_377f75c5120d22','出差客户现场'); auto.js_select2(page,'fd_reimbursement_money_type','人民币'); auto.js_set(page,'fd_377ebcbaabff4c','1')
 page.locator('input[name="__landray_filefd_invoice_att"]').set_input_files(PDF); time.sleep(8)
 water='/Users/mac/Desktop/待使用/酒店水单_按发票修改.png'
 if os.path.exists(water): page.locator('input[name="__landray_filefd_other_att"]').set_input_files(water); time.sleep(2)
 auto.select2_click_pick(page,'fd_378057c5573e88.0.fd_377fb4b73ae7d2','__trip',first=True); time.sleep(5)
 pre='fd_fee_item.0.'; auto.select2_search_pick(page,pre+'fd_erp_type','__erp',keyword='住宿',result_contains='住宿');
 for k,v in {pre+'fd_377ebdd6f64cee':'',''+pre+'fd_377f76fb2a4068':'',''+pre+'fd_377ebe019348aa':d,''+pre+'fd_377ebe06621da2':d,''+pre+'fd_38da1066e1ec68':amount,''+pre+'fd_ocr_excltax_amount':excl,''+pre+'fd_ocr_tax_amount':tax,''+pre+'fd_receipt_no':invno}.items(): auto.js_set(page,k,v)
 auto.js_select2(page,pre+'fd_Invoice_currency','人民币'); auto.js_select2(page,pre+'fd_receipt_type','普票'); auto.relation_choose_pick(page,pre+'fd_project_name',PROJECT); auto.apply_post_rules(page)
 result=auto.save_draft(page); print('暂存结果:',result)
 if '已点暂存' not in str(result): raise SystemExit('未获得已点暂存回执')
 print('酒店报销单已暂存，项目:',PROJECT); time.sleep(5)
