# 差旅费报销自动化（oa-baoxiao）

识别差旅票据并填写企业 OA 差旅费报销单（适配蓝凌 OA 流程表单）。流程只自动填报和暂存，不自动提交。

跨平台：macOS / Windows / Linux。

## 一、环境配置（每个新环境首次执行，一次性；先配置再运行）

Skill 不携带任何机构私有配置。新机器/新环境按以下顺序操作：

1. 把本文件夹（Skill 包）放到目标机器。
2. 准备本机配置 `config.json`（放置真实机构参数，不入仓库）：
   - `oa.portal` / `oa.login_url` / `oa.reimburse_new_url` → 贵司 OA 门户、统一认证地址、报销流程模板地址；
   - `company` → 报销公司名；`fee_type` → 默认费用类型；
   - `project`、`invoice_dir` 默认可为 null，运行时用 `--project` 与票据目录参数指定。
3. 运行 `python install.py`（Windows 可用 `py -3 install.py`）。脚本会自动：
   - 检查 Python 与 Chrome、安装 `playwright` + `pypdf`；
   - 引导登录 OA 并保存会话到本机 `data/oa_state.json`。
4. 重新运行 `python install.py` 完成登录与自检；看到「会话有效」即配置完成。

> 会话文件 `data/oa_state.json` 只保存在本机，不纳入分发、不提交仓库。

## 二、报销使用

1. 把同一批次发票及其它凭证放入 `config.json` 配置的票据目录。
2. 启动带调试端口的 Chrome 并登录 OA（见下），或在 WorkBuddy 中说「报销差旅费用」/「提交差旅报销」，确认项目后执行。
3. 自动识别 → 分流上传 → 填表 → 按「暂存前检查清单」核对 → 暂存；提交前由用户人工复核。

### 启动带调试端口的 Chrome（沿用登录会话）

- macOS：
  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-debug-profile"
  ```
- Windows（cmd）：
  ```bat
  start "" "C:\Program Files\Google Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-debug-profile"
  ```

在调试浏览器里登录 OA 后，脚本通过 `OA_CDP_URL=http://127.0.0.1:9222` 连接它填报，无需重复登录。

## 三、命令行运行

```bash
python scripts/fill_oa_batch.py "票据目录" --project "项目名"
python scripts/fill_oa_auto.py "发票.pdf" --project "项目名"
```

可选参数：`--trip`、`--headless`、`--no-save`。批量模式推荐用于滴滴电子发票与行程单、自驾发票与 Excel 明细。
Windows 下把 `python` 换成 `py -3` 或本机 Python 路径。

## 四、核心规则

- 目录内全部非隐藏文件都要识别；真实发票上传到发票栏，其它凭证上传到其它附件栏。
- 发票栏文件数、去重发票数和 OA 发票张数必须一致，否则停止。
- 滴滴开始/结束日期取行程报销单的行程起止日期，分别写入对应字段；日期为空不得暂存。
- 自驾发票只上传一次；Excel 有效业务行逐条对应 OA 明细，排除空行和表尾说明行；
  自驾行程表 Excel 只上传“自驾行程表”专用控件，禁止再出现在其它附件栏。
- 只点击暂存，不点击提交；只有明确取得“已点暂存”回执才报告成功。

## 五、配置

本机配置：`config.json`（含真实机构参数，不入仓库，不入分发）。
配置优先级：命令行参数 > `config.json` > 人工确认。

## 六、反馈

使用完整提示词“差旅报销问题反馈”。只记录脱敏后的技术问题，格式为：

`日期｜分类｜现象｜影响｜复现条件｜处理结论｜待验证｜状态`

## 目录结构

```text
oa-baoxiao/
├── SKILL.md
├── README.md
├── config.json           # 本机配置（含真实机构参数，不入仓库）
├── install.py            # 环境配置器（装依赖 / 登录 / 自检）
├── data/                 # 本机运行数据（oa_state.json 会话，不入分发）
└── scripts/
    ├── rail_invoice_parse.py
    ├── chrome_cookies_to_state.py   # 仅 macOS：自动提取本机 Chrome 的 OA 会话
    ├── login_browser.py             # 跨平台：打开浏览器引导登录
    ├── fill_oa_auto.py
    └── fill_oa_batch.py
```
