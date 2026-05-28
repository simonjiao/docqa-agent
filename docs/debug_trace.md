# 项目调试跟踪

## 2026-05-28 OCR 中文语言包

运行文档问答原型时，项目默认 OCR 语言为 `HanS+eng`。本机初始 Tesseract 语言列表只有英文相关语言，强制重新 OCR 中文扫描 PDF 时会缺少中文识别能力。

## 调试记录

- 时间：2026-05-28 09:00 CST
- 工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`
- 现象：启动前检查发现 Tesseract 只包含 `eng`、`osd`、`snum`。
- 检查命令：

```bash
tesseract --list-langs
```

- 初始结果摘要：

```text
eng
osd
snum
```

## 原因

本机已安装 Tesseract 主程序，但未安装额外语言数据包。中文 OCR 需要 `chi_sim`、`chi_tra` 或 `script/HanS` 等语言数据。

## 处理

通过 Homebrew 查询并安装额外语言包：

```bash
brew info tesseract-lang
brew install tesseract-lang
```

安装结果摘要：

```text
tesseract-lang 4.1.0
installed to /opt/homebrew/Cellar/tesseract-lang/4.1.0
```

相关版本：

```text
tesseract 5.5.2
tesseract-lang 4.1.0
libunistring 1.4.2
```

## 验证

安装后再次检查语言列表：

```bash
tesseract --list-langs | rg 'chi|Han|eng|osd|snum'
```

确认可用语言包括：

```text
chi_sim
chi_sim_vert
chi_tra
chi_tra_vert
eng
osd
script/HanS
script/HanS_vert
script/HanT
script/HanT_vert
snum
```

使用现有样例页面图做一次不落盘 OCR 验证：

```bash
tesseract 'storage/GBT1568-2008键技术条件-e724ad081078fa41/pages/page-3.png' stdout -l chi_sim+eng --psm 6
```

输出能正常识别中文正文，例如：

```text
本标准规定了除花键外的各种键的技术要求,验收检查、标志与包装。
```

## 后续运行建议

默认运行可以继续使用：

```bash
./run.sh
```

如果 `HanS+eng` 在某些环境下不可用，改用简体中文语言包启动：

```bash
OCR_LANG=chi_sim+eng ./run.sh
```

如需强制用新语言包重新生成 OCR 缓存：

```bash
FORCE_REPROCESS=1 OCR_LANG=chi_sim+eng ./run.sh
```

注意：`storage/` 是本地运行缓存目录。提交前应检查是否有不希望提交的 OCR 缓存或上传文档。

## 2026-05-28 提交后运行服务

用户要求生成一次提交并运行程序。

调试记录：

- 时间：2026-05-28 09:05 CST
- 工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`
- 提交前验证命令：

```bash
.venv/bin/python -m pytest -q
```

- 结果摘要：

```text
6 passed, 5 warnings
```

- 生成提交：

```bash
git commit -m "Add project debug trace guidance"
```

- 初次后台启动尝试：

```bash
nohup env OCR_LANG=chi_sim+eng STORAGE_DIR=./storage .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > /tmp/docqa_agent_prototype_uvicorn.log 2>&1 &
```

- 现象：HTTP 探针返回 `000`，`/api/load-sample` 没有 JSON 输出，8000 端口未监听；日志文件为空。
- 处理：改用前台命令验证应用本身可启动，确认问题不在应用导入或接口逻辑。

```bash
env OCR_LANG=chi_sim+eng STORAGE_DIR=./storage .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 验证结果：

```text
GET / -> 200
POST /api/load-sample -> 200
```

后续运行建议：后台运行时优先不带 `--reload`，避免本地后台启动行为受 reloader 进程管理影响；开发调试需要热加载时再前台运行 `./run.sh`。

## 2026-05-28 使用 tmux 运行服务

用户要求使用 `tmux` 运行程序。

处理命令：

```bash
tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype 'OCR_LANG=chi_sim+eng STORAGE_DIR=./storage .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000'
```

验证命令：

```bash
curl -s -o /tmp/docqa_index.html -w '%{http_code}\n' http://127.0.0.1:8000/
curl -s -X POST http://127.0.0.1:8000/api/load-sample
lsof -iTCP:8000 -sTCP:LISTEN -n -P
```

结果摘要：

```text
GET / -> 200
POST /api/load-sample -> 200
127.0.0.1:8000 is listening, PID 72086
```

查看 tmux 窗口和日志：

```bash
tmux list-windows -t docqa_agent_prototype
tmux capture-pane -pt docqa_agent_prototype:1.1 -S -80
```

注意：该 session 的窗口编号为 `1`，pane 编号为 `1`；使用 `docqa_agent_prototype:0` 会报 `can't find window: 0`。

## 2026-05-28 上传控件布局调整

用户要求将上传区域合并成一行，并去掉“加载样例 PDF”按钮。

处理摘要：

- 删除前端模板中的 `sampleBtn` 按钮。
- 删除前端脚本中的 `loadSample()` 和 `sampleBtn` 绑定。
- 将无文档时的问答提示从“请先上传或加载 PDF。”改为“请先上传 PDF。”。
- 为 `.actions input[type="file"]` 添加局部样式，覆盖全局 `input { width: 100% }`，避免文件选择控件单独占满一行。
- 同步 README、演示脚本和面试答复文档，避免继续描述 UI 上已删除的样例按钮。

验证命令：

```bash
rg -n "sampleBtn|加载样例 PDF|请先上传或加载" app README.md docs --glob '!docs/debug_trace.md'
.venv/bin/python -m pytest -q
```

结果摘要：

```text
功能代码和说明文档无残留匹配，调试跟踪保留历史记录
6 passed, 5 warnings
```

运行验证：

- 重启时发现原 `docqa_agent_prototype` tmux session 已不存在，8000 端口未监听。
- 重新创建 tmux session 后，第一次 HTTP 探针过早返回 `000`；随后端口监听正常，`GET /` 返回 `200`。
- 使用浏览器检查 `http://127.0.0.1:8000/`：`#sampleBtn` 不存在，`.actions` 为 `display: flex` 且 `flex-wrap: nowrap`，页面视觉上文件选择控件和“上传并解析”在同一行。

## 2026-05-28 PDF 解析产物设计文档验证

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：不要改业务代码，基于当前项目生成 PDF 初次解析产物改造设计文档，说明如何保存隐藏文本、OCR、Markdown、HTML 和人工/LLM 复核相关内容。

处理摘要：

- 新增 `docs/pdf_parsing_refactor_design.md`，只做设计文档，不改业务代码。
- 文档对比当前 `meta.json`、`pages.json`、`chunks.json` 存储方式与目标 `manifest.json`、`pages.jsonl`、`blocks.jsonl`、`chunks.jsonl`、Markdown、HTML 派生产物。
- 文档明确隐藏文本应作为独立 `source_type=hidden_text` 候选文本源保存，不直接和 OCR 文本混合。

遇到的问题：

```bash
pytest -q
```

结果：

```text
zsh:1: command not found: pytest
```

当前假设：本机全局 PATH 未暴露 `pytest`，但项目虚拟环境中存在 `.venv/bin/pytest`。

验证命令：

```bash
.venv/bin/pytest -q
```

结果摘要：

```text
6 passed, 5 warnings in 0.84s
```

剩余风险：本次只新增设计文档，没有执行 PDF 解析流程或评估脚本；后续实现改造时仍需补充 JSONL 产物、隐藏文本、Markdown/HTML 派生物的专项测试。

## 2026-05-28 PDF 元素图谱设计文档补强

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：目标是支持多种类型 PDF，尽可能识别 PDF 中的所有元素，并建立硬联系规则，不要折中；检查是否需要再次完善设计文档。

处理摘要：

- 将 `docs/pdf_parsing_refactor_design.md` 从 block-centric 设计补强为 element/edge-centric 设计。
- 新增 `elements.jsonl`、`edges.jsonl`、`tables.jsonl`、`forms.jsonl`、`annotations.jsonl`、`attachments.jsonl` 等目标产物。
- 明确 `elements.jsonl` 是最细粒度事实源，`blocks.jsonl`、`chunks.jsonl`、Markdown、HTML 都是派生视图。
- 补充 PDF 元素类型清单、不同 PDF 类型的最低元素覆盖要求、硬联系边类型和生成规则。
- 强化约束：不可静默丢弃未支持元素，需记录 `unsupported_element`、`blocked_by_permission` 或 `needs_specialized_parser`。

遇到的问题：

```bash
rg -n "主事实源|blocks\.jsonl 保存|generated_from|block overlay|block 级|visible_text` blocks|image_ocr` blocks|hidden_text` blocks|^## |^### |blocked_by_permission|needs_specialized_parser" docs/pdf_parsing_refactor_design.md
```

结果：

```text
zsh:1: unmatched "
```

根因：搜索表达式中同时包含双引号和反引号，shell 解析失败。后续改用单引号包裹 rg pattern。

验证命令：

```bash
.venv/bin/pytest -q
```

结果摘要：

```text
6 passed, 5 warnings in 0.84s
```

剩余风险：本次仍是设计文档更新，未实现元素图谱、关系边生成器或专项 PDF 样本测试。pytest 警告来自 PyMuPDF/SWIG 相关 DeprecationWarning，未影响现有测试通过。

## 2026-05-28 PDF 元素图谱不兼容实现

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：分阶段但一次性完成元素图谱实现，生成 checklist，不兼容旧格式，测试文件放在 `docs-for-test/`，并及时提交。

处理摘要：

- 新增 `docs/pdf_element_graph_implementation_checklist.md`。
- 新增 `docs-for-test/`，放入扫描样本和合成的 text/ocr/mixed/form/drawing/protected PDF fixture。
- 将主输出改为 `manifest.json`、`pages.jsonl`、`elements.jsonl`、`edges.jsonl`、`blocks.jsonl`、`chunks.jsonl`、`reviews.jsonl`。
- 停止写入旧 `meta.json`、`pages.json`、`chunks.json` 主输出。
- OCR 行生成 `ocr_text` element，页面图生成 `page_render` element，block/chunk 通过 edge 追溯来源。
- API 的页面识别视图改为从元素图谱派生。

遇到的问题：

```text
scripts/evaluate.py --sample 首次运行失败，原因是同 doc_id 下残留旧 storage 缓存，只有旧 meta/pages/chunks，没有新 manifest。
```

修复：

- `save_upload()` 在同 doc_id 已存在时清理旧目录，避免不兼容格式混用。
- `pdf_probe` 对 protected PDF 提前返回 `protected_pdf`，避免访问加密页面触发 `document closed or encrypted`。
- 修正 PyMuPDF `page.widgets()` 判断，避免空 widgets 生成器被误判为 `form_pdf`。
- 最后一次评估摘要命令使用裸 `python` 失败，改用 `.venv/bin/python`。
- 并行运行 `pytest` 和 `evaluate.py --sample` 时，测试中的 `clean_storage()` 会清理同一个 `storage/`，导致评估中的页面 PNG 被破坏；最终改为串行验证。

验证命令：

```bash
.venv/bin/pytest -q
.venv/bin/python scripts/evaluate.py --sample
```

结果摘要：

```text
8 passed, 5 warnings
evaluate.py --sample completed; sample probe pdf_type=scan_pdf
```

剩余风险：当前元素图谱已覆盖现有 OCR、文本层、图片对象、矢量路径、链接、表单、批注、附件元数据等基础元素；`ocr_pdf` 和 `form_pdf` 已有合成 fixture，但还没有授权可提交的真实业务样本，也没有完整表格单元格恢复或签名深解析。

## 2026-05-28 元素图谱 checklist 审计补齐

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：核对 checklist 是否真正完成，继续工作并及时提交；不能只看勾选状态提前宣布完成。

处理摘要：

- 审计发现 `review_of` 仅以 `target_chunk_ids`/`target_block_ids` 元数据落盘，没有真实 edge。
- 审计发现 `alternative_for_chunk` 虽有 chunker 代码路径，但解析器没有生成 alternative block，现有测试也未证明该 edge 会实际落盘。
- 审计发现 OCR PDF 中未匹配文本层的图片文字只保存为 `ocr_text` element，没有进入主 block/chunk，检索会漏掉图片内文字。

修复：

- 人工复核写入 `reviews.jsonl` 时，同时追加 `review` element，并为有效目标追加 `review_of` edge。
- OCR PDF 解析时，将未匹配文本层的图片 OCR 文本作为 primary block 进入 chunk。
- 同区域但未被采用的 visible/hidden/OCR 候选保存为 alternative block，并通过 `alternative_for_chunk` edge 指向相关 chunk。
- 更新 checklist、README、架构说明和验证流程，去掉 “review target metadata 可替代 edge” 的折中描述。

验证命令：

```bash
.venv/bin/pytest -q
.venv/bin/python scripts/evaluate.py --sample
```

结果摘要：

```text
10 passed, 5 warnings
evaluate.py --sample completed; sample probe pdf_type=scan_pdf
```

剩余风险：PyMuPDF/SWIG DeprecationWarning 仍存在，不影响当前测试；真实业务 PDF 的隐藏文本可见性、签名深解析和表格单元格恢复仍需后续专项样本验证。

## 2026-05-28 11:16:38 CST 程序重启记录

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：重启程序。

处理摘要：

- 发现 8000 端口原监听进程 PID 80322，已停止。
- 直接用 `nohup ./run.sh` 后没有形成监听进程；排查发现当前非交互 shell 中 `uvicorn` 不在 PATH，但 `.venv/bin/uvicorn` 可用。
- 前台使用 `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` 验证成功，HTTP `/` 返回 200。
- 为避免服务绑定在当前工具会话上，改用 detached `tmux` 会话 `docqa_agent_prototype` 持久运行。

验证命令：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
curl -sS -o /tmp/docqa_agent_prototype_root.html -w '%{http_code}\n' http://127.0.0.1:8000/
tmux list-sessions | rg '^docqa_agent_prototype:'
```

结果摘要：

```text
Python 16916/16919 listening on *:8000
HTTP 200
docqa_agent_prototype: 1 windows
```

剩余风险：`run.sh` 依赖 `uvicorn` 在 PATH 中；当前重启采用 `.venv/bin/uvicorn`，后续如需一键脚本在非交互 shell 中稳定运行，可考虑让 `run.sh` 优先使用 `.venv/bin/uvicorn`。

## 2026-05-28 11:25:51 CST 识别行定位滚动与 Playwright 安装

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：点击识别内容某一行时，PDF 应滑动到相关位置；如果相关位置已经在当前显示区域内，则不要移动。随后要求安装 Playwright。

处理摘要：

- 前端点击 `ocr-line` 和 `table-card` 时，不再只画 bbox；现在会检查 bbox 是否完整落在 PDF 可视区域内。
- 如果 bbox 已经可见，保持当前 PDF 滚动位置；如果不可见，按 bbox 中心平滑滚动到对应位置。
- 增加当前识别行/表格卡片 active 状态，便于确认当前定位对象。
- 更新静态资源 query string，避免浏览器继续使用旧 `app.js`/`style.css`。
- 安装 Playwright Chromium 浏览器缓存，后续可直接使用 headless Chromium 做本地 UI 验证。
- 顺手补齐本地启动脚本的同类问题：`run.sh` 优先使用 `.venv/bin/uvicorn`，文档中的测试/评估命令改为 `.venv/bin/...`。

遇到的问题：

```text
Playwright 包存在，但初次运行缺少 Chromium/headless-shell 浏览器缓存。
```

修复命令：

```bash
NODE_PATH=/Users/simon/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
/Users/simon/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
/Users/simon/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.60.0/node_modules/playwright/cli.js install chromium
```

验证命令：

```bash
node --check app/web/static/app.js
curl -sS -o /tmp/docqa_agent_prototype_root.html -w '%{http_code}\n' http://127.0.0.1:8000/
PATH=/usr/bin:/bin OCR_LANG=HanS+eng STORAGE_DIR=./storage PORT=8010 ./run.sh
```

Playwright 验证摘要：

```text
可见第一行点击后 scrollTop=0。
不可见底部行首次点击后 scrollTop=259。
同一底部行再次点击后 scrollTop=259，scrollDeltaSecondClick=0。
```

剩余风险：本次验证覆盖了样本文档当前页面的 OCR 行定位；多页证据点击自动翻页仍未实现，当前问题只涉及当前页识别内容列表。

## 2026-05-28 11:28:43 CST Web 测试环境约束

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：不要启动多个 Web 测试环境。

处理摘要：

- 检查当前监听端口，项目只保留 `8000` 上的 `docqa_agent_prototype` 服务。
- 确认此前临时验证端口 `8010` 没有残留监听。
- 后续 Web/UI 验证默认复用当前 `8000` 服务；如确需临时端口，必须先检查现有服务并在验证结束后清理。

验证命令：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8010 -sTCP:LISTEN
tmux list-sessions | rg 'docqa|uvicorn|8010|8000'
```

结果摘要：

```text
8000: Python 16916/16919 listening
8010: no listener
tmux: docqa_agent_prototype: 1 windows
```

## 2026-05-28 11:31:19 CST 识别行选中态不明显

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：识别内容点击某一行后，没有高亮选中。

处理摘要：

- 复用当前 `8000` 服务验证，没有启动新的 Web 测试环境。
- Playwright 检查确认点击后 DOM 已有 `ocr-line active`，但样式只有浅色背景和 1px 边框，视觉上不够明确。
- 加强 `.ocr-line.active` 和 `.table-card.active` 选中态：更明显的蓝色背景、左侧色条和外层高亮阴影。
- 更新静态资源 query string，避免浏览器继续使用旧 CSS。

验证摘要：

```text
点击识别行后 activeCount=1。
选中项 className=ocr-line active。
选中态包含明显 box-shadow 和高亮背景。
```

## 2026-05-28 11:40:16 CST 中文文本层 PDF 被误判和 OCR 乱码

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：排查 `多智能体平台JD.pdf` 看着像文本 PDF，但 UI 识别内容显示乱码，怀疑中文不支持；要求继续并记录 debug trace。

处理摘要：

- 在上层目录找到 `../docs-for-test/多智能体平台JD.pdf`，复制到项目内 `docs-for-test/` 作为回归 fixture。
- 用 PyMuPDF 检查第 1 页，确认文本层可直接抽取中文：`text_len=851`，包含 `多智能体平台JD` 和中文正文。
- 原 `pdf_probe` 因页面有少量 vector drawings，把主类型判为 `drawing_pdf`；实际应以可用文本层为主，vector 只作为候选/辅助视觉元素。
- 原识别内容 API 只返回 `ocr_text`，导致文本层中文虽然已进入 blocks/chunks，但右侧仍显示 OCR 行。
- 本机 Tesseract 语言列表有 `chi_sim`、`eng`、`script/HanS`，没有 plain `HanS.traineddata`；`HanS+eng` 会导致中文 OCR 退化或报错。
- 另发现该 PDF 的中文文本层由 Type3 字体产生，PyMuPDF span 很多是单字级；需要把同视觉行 span 合并成 block，避免一字一行。

修复：

- 默认 OCR 语言改为 `chi_sim+eng`。
- 新增 `resolve_ocr_lang()`，把旧配置 `HanS+eng` 映射到本机可用的 `chi_sim+eng` 或 `script/HanS+eng`。
- `pdf_probe` 在文本层充足且无图片时主判 `text_pdf`，同时保留 `drawing_pdf` 候选。
- 页面识别 API 优先返回 primary blocks；没有 block 时才回退到原始 OCR 行。
- parser 将同一视觉行的 text spans 合并为一个 block。

验证摘要：

```text
probe_pdf(多智能体平台JD.pdf): pdf_type=text_pdf, candidates=['drawing_pdf', 'text_pdf']
第 1 页识别内容 line_count=25
前几行 source_type=visible_text:
多智能体平台JD
1.Senior Multi-Agent Platform Engineer
我们在做什么
我们正在建设一个面向复杂知识工作和长期自主任务的新一代多智能体AI平台。
```

测试命令：

```bash
STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_ocr_lang.py tests/test_pdf_probe_sample.py tests/test_recognition_view.py tests/test_chunker.py
STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
```

结果摘要：

```text
7 passed, 5 warnings
15 passed, 5 warnings
evaluate.py --sample completed; sample probe pdf_type=scan_pdf
```

剩余风险：真实文本层 PDF 的阅读顺序和断行仍依赖 PDF span/bbox 质量；当前按视觉行合并，尚未做跨行段落重组。

## 2026-05-28 11:56:31 CST 置信度展示语义

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：继续说明并处理“置信度数值代表什么”。

处理摘要：

- 复用当前 `8000` 服务，没有启动新的 Web 测试环境。
- 原 UI 对所有识别行统一显示 `置信度 <number>`，会把文本层 block 的 `1.0` 误解为 OCR 百分比。
- 后端识别行增加 `confidence_display` 字段，按来源生成展示文案。
- OCR 来源显示 `OCR置信度 x/100`；文本层来源显示 `文本层抽取`；隐藏文本、表单字段等来源显示对应来源说明。
- 前端识别列表优先显示 `confidence_display`，没有该字段时才回退旧的数字显示。

验证摘要：

```text
visible_text primary block: confidence_display=文本层抽取
image_ocr fallback line: confidence_display=OCR置信度 96.4/100
```

## 2026-05-28 12:25:59 CST 当前页表格识别检查

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：检查正在查看的页面中表格识别情况。当前 Firefox 页面为 `http://127.0.0.1:8000`，文档 `20251229陈海平-e23bf7f4264dfe2c` 第 1 页。

检查命令：

```bash
curl -s http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/1/recognition | jq '{checks, page: {image_width: .page.image_width, image_height: .page.image_height, average_confidence: .page.average_confidence, table_regions: .page.table_regions, line_count: (.page.lines|length), lines: .page.lines}}'
jq -c 'select(.page_no==1 and .element_type=="table_region") | {element_id,page_no,bbox,raw_ref,extractor}' storage/20251229陈海平-e23bf7f4264dfe2c/elements.jsonl
jq -c 'select(.page_no==1) | {block_id,role,text,bbox,confidence,source_types,source_group_ids,warnings}' storage/20251229陈海平-e23bf7f4264dfe2c/blocks.jsonl
jq -c 'select(.page==1) | {id,kind,page,text,source_block_ids,alternative_block_ids,source_types,confidence,warnings}' storage/20251229陈海平-e23bf7f4264dfe2c/chunks.jsonl
```

结果摘要：

```text
第 1 页 image_size=992x1404，line_count=15。
checks: ocr_confidence=warn，average_confidence=47.86；text_density=pass；table_region_detection=pass。
检测到 2 个疑似表格区域：
- table-2 / p0001-e0276 bbox=[33,122,932,454]，覆盖上方“基本信息”表。
- table-1 / p0001-e0277 bbox=[33,631,936,216]，覆盖下方“结果信息”表。
primary blocks 来源为 visible_text，右侧识别内容显示“文本层抽取”。
image_ocr alternative blocks 对表格区域识别质量较差，例如 "asf ww [el |"、"Com Ls I ae |"，均带 low_ocr_confidence。
```

当前判断：

- 表格区域检测基本命中，能把第 1 页两个带 ruling lines 的表格框出来。
- 当前实现只生成 `table_region`，并标记 `needs_specialized_parser`；没有生成 `table_row` / `table_cell` 结构。
- 识别列表仍是按文本层 block 展示，表格内容被拉平成行文本。下方结果表中，`CHP01` 行的检测结果被拆成多条 block，行列关系没有被结构化保留。

修复或 workaround：本次只做检查，未改代码。若后续要让问答可靠使用表格，应增加专门的表格结构解析，至少把 `样本名/评级/编码/检测结果/结果解释` 恢复为行列单元格。

验证结果：本地 API 返回 HTTP 200，识别视图与落盘 `elements.jsonl`、`blocks.jsonl`、`chunks.jsonl` 一致。

## 2026-05-28 12:33:42 CST 结构化表格识别设计要求

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：将提升结构化表格识别的方案做成设计文档，目标必须处理有线表格、无线或弱线表格、扫描或 OCR 低质量表格三种复杂情况；随后明确要求不能与既有设计冲突，不能折中。

处理摘要：

- 新增 `docs/table_structure_recognition_design.md`，作为 `docs/pdf_parsing_refactor_design.md` 阶段 5 的深化设计。
- 明确 `elements.jsonl` 和 `edges.jsonl` 仍是事实源，`tables.jsonl` 只是可重新派生的视图。
- 明确 `table_region` 只是入口，不是成功状态；最终必须生成 row/column/cell 结构，或明确 `failed` / `needs_review` 并阻断其作为确定答案。
- 设计覆盖三类解析策略：有线表格 grid parser、无线表格 alignment parser、扫描低质量表格 cell-level OCR parser。
- 同步更新 `docs/architecture.md` 和 `docs/pdf_parsing_refactor_design.md` 的交叉引用，避免形成另一套路线。

验证结果：`rg` 检查关键术语和交叉引用命中预期，`git diff --check` 通过；本次是文档设计变更，不涉及运行时代码。

## 2026-05-28 12:49:35 CST 结构化表格识别实现

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：根据结构化表格识别设计生成 checklist，并完成 checklist；不要折中，不要提前宣布胜利，必须测试。

处理摘要：

- 新增 `docs/table_structure_recognition_checklist.md`，按设计拆出事实源、元素/关系、三类策略、API、测试和提交验收项。
- 新增 `app/core/table_parser.py`，实现有线表格 grid parser、无线表格 alignment parser、扫描/OCR 低质量表格 cell-level OCR parser。
- storage/manifest 增加 `tables.jsonl`，但 `elements.jsonl` 和 `edges.jsonl` 仍是事实源。
- parser 写入 `table_structure`、`table_row`、`table_column`、`table_cell`、`table_line`、`cell_ocr` element，以及结构、候选、block/chunk 追溯边。
- 生成 `table_markdown` 和 `table_json` 两类 table block，并由 chunker 生成独立 `kind=table` chunk。
- API 新增 `/api/docs/{doc_id}/tables`、`/api/docs/{doc_id}/pages/{page_no}/tables`、`/api/docs/{doc_id}/tables/{table_id}`；页面识别接口返回结构化表格摘要。
- 前端识别页支持表格结构化网格展示、cell 点击定位 bbox、cell 需复核入口；问答证据中的 table chunk 按表格渲染。
- 表格页级检查补充 `table_region_coverage`、`table_grid_confidence`、`table_text_assignment`、`table_header_quality`、`table_ocr_quality`、`table_chunk_traceability`。
- 新增 `docs-for-test/sample_table_ruled.pdf`、`sample_table_borderless.pdf`、`sample_table_scanned_low_conf.pdf` 三类 fixture。
- 新增 `tests/test_table_structure.py` 覆盖三类表格、edge 完整性、table chunk 追溯和 API 读取。

验证命令：

```bash
STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py
node --check app/web/static/app.js
STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
```

结果摘要：

```text
tests/test_table_structure.py: 3 passed, 5 warnings
node --check app/web/static/app.js: passed
full pytest: 19 passed, 5 warnings
evaluate.py --sample completed; all sample cases returned validation checks
```

补充记录：最终验证时组合命令中使用系统 `python` 读取 `/tmp/docqa_table_eval.json`，本机 shell 返回 `zsh:1: command not found: python`；改用 `.venv/bin/python` 读取同一评估产物成功，确认 5 个 case 均返回验证检查。

剩余风险：规则解析已覆盖三类目标 fixture；真实复杂财报、跨页表格、旋转表格和嵌套表格仍需要后续 golden set 扩展，但当前实现不会把失败结构当作确定答案。

## 2026-05-28 13:06:06 CST 合并单元格跨列文本复制修复

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户指出：类似“样本类型 / 单细胞”这种表格行，内容视觉上横跨多列，但语义上是一个合并值，不应把同一内容复制到多个 cell。

根因：

- ruled grid parser 先按整张表的全局竖线切列。
- cell 文本分配按 bbox overlap 判断，同一个跨列文本候选可能命中多个 cell。
- 对行级缺失竖线没有生成 `col_span`，因此合并单元格被错误拆成多个普通 cell。

修复：

- 有线表格按每一行实际存在的竖线生成 row-level cell 边界。
- 当某一行内部竖线缺失时，生成单个合并 cell，并在 `table_cell.raw_ref.col_span` 记录跨列数。
- 同一行内每个文本候选只分配给得分最高的一个 cell，避免跨列值复制。
- 新增 `docs-for-test/sample_table_merged_row.pdf` 和回归测试，断言 `Single Cell` 只出现一次且 `col_span=3`。

验证结果：

```text
STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py
4 passed, 5 warnings

node --check app/web/static/app.js
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
20 passed, 5 warnings

STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
5 cases completed with validation checks
```

## 2026-05-28 13:14:32 CST 第 2 页说明文字被误判为无框表格

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户指出：正在查看的文档 `20251229陈海平-e23bf7f4264dfe2c` 第 2 页被识别为表格，需解释原因。

诊断命令与关键输出：

```text
curl -sS http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/2/recognition | jq '{table_regions: .page.table_regions}'

table_regions[0].reason = "text_alignment"
table_regions[0].bbox = [52, 82, 888, 970]
structured table strategy = "borderless_alignment"
row_count = 25
column_count = 14
```

页面级 OCR 检测显示 `table_region_count=0`，说明原始 ruling-line 检测没有发现表格线；后续 `table_parser.v1.borderless_region` 由于文本 bbox 对齐触发了无框表格候选。

根因：

- 第 2 页是说明文字和编号列表，不是表格。
- `parse_tables()` 在没有表格线区域时会调用 `_infer_borderless_region()`。
- `_infer_borderless_region()` 只要求多行文本中存在至少 2 个对齐的 x 中心点。
- 本页大量编号、英文缩写、百分比、斜杠和长句片段具有重复 x 坐标；复现统计中 `rows>=2` 为 25，aligned centers 为 14 个，因此被当成 25 行 x 14 列的无框表格。
- 当前质量门禁虽然给出 `table_text_assignment=warn` 和 `table_header_quality=warn`，但没有把这类高空单元格、列表型文本、伪表头的候选降级或拒绝，最终状态仍为 `pass`。

当前结论：这是无框表格检测阈值过宽造成的 false positive；应增加无框表格的负样本门禁，例如列表密度、伪表头比例、空单元格率、全文段落连续性、列稳定性和候选区域覆盖范围约束。

## 2026-05-28 13:22:11 CST 无框表格误判修复与当前文档恢复

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：修复第 2 页说明文字被识别为表格的问题。

修复：

- `table_parser` 新增无框表格布局门禁：对齐列必须在页面行中有足够高的支持比例，且多数行要稳定命中同一组列。
- 增加列表/段落型负样本过滤：当首列是 `1.`、`a.` 这类列表标记，且伴随长段落或过多伪列时，不再生成 `text_alignment` 表格候选。
- 新增 `docs-for-test/sample_text_numbered_notes.pdf`，覆盖“编号说明文字 + 重复缩进”不是无框表格的回归测试。

调试过程中的环境恢复：

- 排查时误用测试 helper，触发默认 `storage` 清理；随后定位到源文件 `/Users/simon/ai-agents/docs-for-test/20251229陈海平.pdf`。
- 删除误生成的默认存储样本目录 `storage/sample_table_borderless-7abf4319b87a171d`。
- 使用源文件重新写入并解析默认存储，恢复文档 `20251229陈海平-e23bf7f4264dfe2c`。

验证结果：

```text
.venv/bin/python -m py_compile app/core/table_parser.py
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py
5 passed, 5 warnings

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
21 passed, 5 warnings

node --check app/web/static/app.js
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
5 cases completed with validation checks

STORAGE_DIR=$(mktemp -d) .venv/bin/python - <<'PY'
# parse /Users/simon/ai-agents/docs-for-test/20251229陈海平.pdf
# doc_id 20251229陈海平-e23bf7f4264dfe2c
# total_tables 3
# page2_tables 0
PY

curl -sS http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/2/recognition
# page.table_regions = []
# page.tables = []
```

剩余风险：无框表格检测现在更保守；真实无框表格仍由 `sample_table_borderless.pdf` 回归覆盖，但后续需要继续扩充真实无框财报/检验报告样本，防止过严门禁漏掉特殊布局。

## 2026-05-28 13:26:22 CST 第 3 页图表被同时识别为表格候选

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户指出：文档 `20251229陈海平-e23bf7f4264dfe2c` 第 3 页中的图片/图表也被识别成表格，需解释为何主动归为表格而不是图片或其他特殊格式图表。

诊断命令与关键输出：

```text
curl -sS http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/3/recognition

table_regions:
- bbox=[81,414,824,55], reason="ruling_lines", structured_tables=[]
- bbox=[83,689,822,55], reason="ruling_lines", structured table p0003-t0002

tables:
- table_id=p0003-t0002
- strategy=scanned_ocr_table
- bbox=[83,689,822,55]
- row_count=2
- column_count=1
- status=needs_review
- warnings=low_cell_ocr_confidence, needs_review, scanned_table_needs_review

image elements:
- p0003-e0577 image_object bbox=[62,411,852,107] ext=jpeg
- p0003-e0578 image_object bbox=[62,686,852,107] ext=jpeg
```

结论：

- 第 3 页的两个图表已被 PyMuPDF 识别为 `image_object`，所以不是“没有识别成图片”。
- 表格候选检测 `detect_table_regions()` 是独立的 OpenCV 线条检测流程，会在整页渲染图上寻找长横线/竖线；图表里的坐标轴、外框、水平网格线满足 `ruling_lines` 条件，因此又额外生成了 `table_region`。
- 当前 `parse_tables()` 对有线候选优先尝试 `_parse_ruled_grid()`，当候选区域位于图片内且没有可用文本层时，策略会变成 `scanned_ocr_table`。
- 第二个图表区域被恢复成 2 行 x 1 列，但 OCR 单元格为空，质量状态已是 `needs_review`，说明它不是可信表格。
- 现有系统还没有 chart/plot 专用 artifact，也没有“如果 ruling-line 候选被 image_object 大面积包含且单元格结构退化，就降级为图表/图片”的抑制逻辑。

后续修复方向：增加图表/图片优先级门禁，至少对被 `image_object` 高覆盖的 `ruling_lines` 候选执行退化表格过滤，例如 1 列、填充率 0、低 OCR、无表头、区域高度很小且横向很长时，不生成 table chunk，改为保留 image/figure 候选。

## 2026-05-28 13:31:48 CST 图表线条表格候选与图内 OCR 噪声修复

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户指出：第 3 页图表区域内的识别也有问题，截图中图表被框选并出现低置信 OCR 文本“了”“辣 人”。

修复：

- 在 parser 层增加图片覆盖区域门禁：如果 `ruling_lines` 表格候选被 `image_object` 高比例覆盖，且区域呈现“超宽、很矮、横向线条”特征，则抑制该 table region，不再进入 `parse_tables()`。
- 对图片内部的低置信短 OCR 噪声增加过滤：低置信、短文本或超宽扁平的图内 OCR 不进入主文本 block、候选链接和表格文本候选。
- 保留原始 `image_object`，不把图表降级丢失；当前仍没有独立 chart artifact，先以图片优先避免错误表格和错误正文。
- 新增 `docs-for-test/sample_chart_image_not_table.pdf`，覆盖“带坐标轴/网格线的内嵌图表不是表格”的回归测试。

验证结果：

```text
.venv/bin/python -m py_compile app/core/parser.py app/core/table_parser.py
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py
6 passed, 5 warnings

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
22 passed, 5 warnings

node --check app/web/static/app.js
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
5 cases completed with validation checks

curl -sS http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/3/recognition
# page.table_regions = []
# page.tables = []
# page.text contains no "辣"
# page.lines has no exact "了" line
# table_region_detection: 检测到 0 个疑似表格区域；已抑制 2 个图片内图表线条候选。
```

默认 Web 存储已用 `/Users/simon/ai-agents/docs-for-test/20251229陈海平.pdf` 重新解析恢复；第 3 页当前可见 API 结果已生效。

剩余风险：当前策略是图表/图片优先的保守门禁；如果真实文档把很矮的单行表格嵌在图片中，可能被抑制。扫描表格 fixture `sample_table_scanned_low_conf.pdf` 已覆盖普通图片内表格不被误杀。

## 2026-05-28 13:37:46 CST 图表孤立刻度 OCR 行修复

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户指出：第 3 页图表区域右侧识别列表最后仍出现单独一行 `3`，OCR 置信度 65/100。

诊断：

```text
jq 'select(.page_no==3 and .element_type=="ocr_text" and (.text|test("^\\s*3\\s*$")))'

id=p0003-e0603
text=3
bbox=[62,690,16,11]
confidence=65.0

image_object:
p0003-e0578 bbox=[62,686,852,107]
```

结论：该 `3` 不是正文，而是第二张染色体拷贝数图表左侧/坐标轴区域的孤立刻度。上一轮只过滤了图片内低置信短 OCR，因此置信度 65 的单数字刻度仍进入了主识别列表。

修复：

- 对“薄图表图片”内的轴刻度式短标签增加过滤，不再只依赖低置信阈值。
- 过滤范围限定为宽高比很大的嵌入式薄图表图片；全页扫描图片中的短 OCR 文本仍保留，避免误伤扫描文档。
- 新增单元回归测试：薄图表内 `3` 被过滤，全页扫描图内 `3` 不被过滤。

验证结果：

```text
.venv/bin/python -m py_compile app/core/parser.py
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py
7 passed, 5 warnings

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
23 passed, 5 warnings

node --check app/web/static/app.js
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
5 cases completed with validation checks

curl -sS http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/3/recognition
# has_exact_3_line=false
# table_regions=[]
# tables=[]
```

默认 Web 存储已重新解析恢复；第 3 页当前 API 中不再出现单独 `3` 行。

## 2026-05-28 13:47:43 CST HTML 预览标签新增

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：在“识别内容”标签旁添加一个 HTML 预览标签，并继续实现。

实现：

- 前端新增 `HTML预览` tab，与 `识别内容`、`问答与证据`、`人工复核记录` 并列。
- `/api/docs/{doc_id}/pages/{page_no}/recognition` 增加 `page.images`，返回当前页 `image_object` 的 bbox、元素 ID 和扩展名。
- HTML 预览按 bbox 阅读顺序合成正文、结构化表格和图片/图表占位。
- 点击 HTML 预览中的文本、表格或图片占位，会复用已有 PDF bbox 高亮和滚动定位。
- 表格仍用结构化 table artifact 渲染；识别内容 tab 保留原始行、置信度、bbox、表格候选和复核细节。

验证：

```text
.venv/bin/python -m py_compile app/main.py
passed

node --check app/web/static/app.js
passed

curl -sS http://127.0.0.1:8000/api/docs/20251229陈海平-e23bf7f4264dfe2c/pages/3/recognition
# page.images includes p0003-e0577 and p0003-e0578

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
23 passed, 5 warnings
```

浏览器验证：

- 打开 `http://127.0.0.1:8000/` 后 DOM 中可见 `识别内容`、`HTML预览`、`问答与证据`、`人工复核记录` 四个 tab。
- 当前 Browser 自动化运行时不支持 `locator(...).setInputFiles()`，无法通过浏览器工具完成真实文件上传；数据渲染路径已通过 API、JS 语法检查和后端测试验证。

## 2026-05-28 14:08:32 CST 当前文档第 1 页段落误判为无边框表格

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户指出：当前打开文档第 1 页也有段落/列表被识别为表格；随后提醒前一次排查看的文档错了。

诊断：

- 重新按服务日志和当前 `storage/` 确认，当前文档是 `多智能体平台JD-abce43f968ec7210`，不是此前排查的 `20251229陈海平-e23bf7f4264dfe2c`。
- 第 1 页没有真实线框表格，`table_region_detection` 原始线框候选为 0。
- 后续 `table_parser.v1.borderless_region` 仍通过文本对齐推断出 `p0001-alignment-region`，bbox 为 `[40,113,914,1178]`，并生成 `borderless_alignment` 表格。
- 误判表格为 25 行 9 列，表头为 `多 / 智 / 能 体 / 平 / 台 / JD / col_7...`，实际是标题“多智能体平台JD”和正文段落被文本层拆成多个短片段。
- 旧规则只拦截典型列表和单个超长行；本页不是传统编号列表，且正文被拆成多列短片段，导致 `list_like_first_cell_ratio=0.04`、`long_row_ratio=0.04`，没有触发负例门。

遇到的问题：

```text
zsh:1: command not found: python
```

根因：当前非交互环境没有裸 `python` 命令；本项目调试继续使用 `.venv/bin/python`。

修复：

- 在无边框表格推断中新增“拆字标题”负例：宽列数布局下，首行由多个 CJK 单字/短片段组成且未覆盖全部列时，不作为表格。
- 新增“多列正文碎片”负例：宽列数布局下，多行短片段拼接成连续中文正文、带标点或足够长 CJK 文本，且完整行比例不足时，不作为表格。
- 新增回归测试 `test_split_heading_paragraphs_are_not_inferred_as_borderless_table`。
- 对当前文档强制重新解析，保留同一个 doc_id。

验证结果：

```text
.venv/bin/python -m py_compile app/core/parser.py app/core/table_parser.py app/main.py
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py
8 passed, 5 warnings

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
24 passed, 5 warnings

node --check app/web/static/app.js
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
5 cases completed with validation checks

GET /api/docs/多智能体平台JD-abce43f968ec7210/pages/1/recognition
status=200
table_regions=0
tables=0
```

剩余风险：该规则只作用于无边框表格文本对齐推断；有真实 ruling lines 的表格和图片内图表过滤仍走各自已有规则。

## 2026-05-28 13:58:52 CST 项目 Python 命令规则固化

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：将“这个项目应继续用 `.venv/bin/python`”加入项目规则。

处理：

- 在 `AGENTS.md` 新增“本地 Python 命令规则”小节。
- 明确非交互 shell 中不要使用裸 `python` 命令；运行 Python 脚本、内联调试片段、编译检查和项目验证时默认使用 `.venv/bin/python`。

背景：

- 此前调试中遇到 `zsh:1: command not found: python`。
- 项目虚拟环境中的 `.venv/bin/python` 可用，且已用于测试、评估和解析命令。

验证：

```text
.venv/bin/python --version
Python 3.13.1

git diff --check
passed
```

剩余风险：该规则约束 Codex/项目内命令习惯；不修改系统 PATH，也不创建 `python` shim。

## 2026-05-28 14:09:56 CST mini-agent 集成与强制 LLM QA

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：

- 将 `/Users/simon/darkfactory/workmate/vendor/mini-agent` 复制到本项目。
- 为项目加入 Agent 支持，支持 QA 功能。
- QA 回答必须以事实为准，由 LLM 组织答复。
- 不要抽取式回退，必须配置 LLM。

处理：

- 将 mini-agent 源码复制到 `vendor/mini-agent/`，排除 `__pycache__`、`.pyc` 和 egg-info 生成物。
- 对 vendored `mini_agent.__init__` 和 `mini_agent.llm.__init__` 做懒加载，避免 QA 只使用 OpenAI-compatible 客户端时提前加载 Anthropic/MCP/完整工具链依赖。
- 对 vendored `mini_agent.llm.llm_wrapper` 做 provider 级懒加载，避免仅导入 Agent/OpenAI 路径时要求 Anthropic SDK。
- `app/core/qa.py` 改为强制 LLM：
  - 读取 `DOCQA_LLM_API_KEY`、`DOCQA_LLM_BASE_URL`、`DOCQA_LLM_MODEL`，兼容 `OPENAI_*`。
  - 未配置时抛出 `LLMConfigurationError`，API 返回 503。
  - 使用 vendored mini-agent 的 OpenAI-compatible client 组织答案。
  - 检索证据是唯一事实来源，Prompt 禁止使用证据外事实。
  - 证据不足时仍调用 LLM，但要求拒答；若 LLM 不拒答，抛出 `LLMGroundingError`，API 返回 502，不生成回退答案。
- `scripts/evaluate.py` 遇到 LLM 配置或事实约束失败时退出 2。
- 更新 README、架构说明、验证流程和演示脚本，删除“默认不依赖外部 API/抽取式答案”的旧描述。
- `requirements.txt` 增加 `openai` 和 `tiktoken`，分别支持 mini-agent OpenAI 客户端和完整 Agent 懒加载后的运行。
- 新增 `pytest.ini`，限制本项目测试只收集 `tests/`，不收集 vendored mini-agent 自带测试。
- 将 `/Users/simon/darkfactory/workmate/.env` 中的必要 LLM 配置复制为本项目 `.env` 的 `DOCQA_LLM_BASE_URL`、`DOCQA_LLM_API_KEY`、`DOCQA_LLM_MODEL`，未复制 workmate 的 app secret、adapter、工具开关等无关配置。
- `run.sh` 启动时自动加载本项目 `.env`，`.env` 继续由 `.gitignore` 排除，不提交密钥。
- QA 配置加载器也会读取项目根目录 `.env`，便于 `scripts/evaluate.py` 等非 `run.sh` 入口使用同一份本地 LLM 配置。
- 测试可通过 `DOCQA_DISABLE_DOTENV=1` 禁用自动读取 `.env`，用于验证未配置 LLM 必须失败的路径。
- 当前 `.venv` 已安装新增依赖 `openai` 和 `tiktoken`。
- 重启现有 tmux 服务 `docqa_agent_prototype`，复用 8000 端口加载 `.env`。

验证：

```text
.venv/bin/python -m py_compile app/core/qa.py app/main.py scripts/evaluate.py vendor/mini-agent/mini_agent/__init__.py vendor/mini-agent/mini_agent/llm/__init__.py vendor/mini-agent/mini_agent/llm/llm_wrapper.py
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
26 passed, 5 warnings

node --check app/web/static/app.js
passed

.venv/bin/python - <<'PY'
from app.core.qa import LLMConfigurationError, build_answer
try:
    build_answer('是否规定电机噪声测试？', [])
except LLMConfigurationError as exc:
    print(str(exc))
PY
QA 必须配置 LLM，缺少：DOCQA_LLM_API_KEY 或 OPENAI_API_KEY；DOCQA_LLM_BASE_URL 或 OPENAI_BASE_URL；DOCQA_LLM_MODEL 或 OPENAI_MODEL

POST /api/docs/多智能体平台JD-abce43f968ec7210/ask
HTTP 503

.venv/bin/python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path('vendor/mini-agent').resolve()))
from mini_agent import Agent
from mini_agent.llm import LLMClient
from mini_agent.llm.openai_client import OpenAIClient
from mini_agent.schema import Message
print(Agent.__name__, LLMClient.__name__, OpenAIClient.__name__, Message(role='user', content='ok').content)
PY
Agent LLMClient OpenAIClient ok

GET /
HTTP 200

POST /api/docs/多智能体平台JD-abce43f968ec7210/ask
HTTP 200
mode=llm_grounded
llm_judge=pass
model=MiniMax-M2.7
internal chunk references in answer=false

set -a; source .env; set +a; STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample
cases=5
llm_judge=pass for q1_scope, q2_strength, q3_table, q4_mark, q5_no_answer
internal chunk references in answers=false
```

遇到的问题：

- 首次全量 pytest 自动收集了 `vendor/mini-agent/tests/`，由于 vendored 项目完整测试需要 `anthropic`、`mcp`、`agent-client-protocol` 等依赖，收集阶段失败。
- 处理方式：本项目将 mini-agent 作为 vendored 运行依赖，不把其上游测试纳入本项目测试范围；新增 `pytest.ini` 限定 `testpaths=tests`。
- 首次导入 `mini_agent.Agent` 仍因 `llm_wrapper.py` 顶层导入 AnthropicClient 失败；已改成 provider 分支内懒加载，OpenAI 路径和 Agent 导入通过。
- 第一次真实 LLM 评估中，同步 `build_answer()` 每题创建 async client 后出现 `RuntimeError('Event loop is closed')` 的后台清理告警；已给 `MiniAgentOpenAICompletionClient` 增加 `aclose()`，同步包装器在自有 client 场景下显式关闭底层 AsyncOpenAI client。
- 真实 LLM 评估时发现 prompt 中包含 chunk id 后，模型可能把内部 id 写入答案；已从 LLM prompt 的证据块中移除 chunk id、kind、score，只保留证据序号、页码和文本。
- 一次 shell 后处理命令使用变量名 `status`，在 zsh 中触发 `read-only variable: status`；改用不冲突变量或直接读取评估产物。
- `git diff --cached --check` 发现 vendored mini-agent 上游文本文件有尾随空白和多余 EOF 空行；对 vendored 文本文件做了机械空白清理，未处理二进制资源。
- 编译和导入检查会生成 `__pycache__`，提交前已从 `vendor/mini-agent` 清理。

剩余风险：真实 LLM 已通过 `/ask` smoke 和 5 个样例问题评估；后续仍需按真实业务 PDF 继续扩展 golden set。

## 2026-05-28 14:27:00 CST env.example 模板

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：生成 `env.example`。

处理：

- 新增 `.env.example`，用于复制为本地 `.env`。
- 只写占位值，不包含真实 API key。
- 包含 QA 必需的 `DOCQA_LLM_BASE_URL`、`DOCQA_LLM_API_KEY`、`DOCQA_LLM_MODEL`。
- 同时列出 OCR 和运行默认项：`OCR_LANG`、`OCR_DPI`、`OCR_TIMEOUT`、`STORAGE_DIR`、`PORT`。

验证：

```text
git diff --check
passed
```

剩余风险：`.env.example` 是模板；真实 `.env` 仍由 `.gitignore` 排除，不能提交。

## 2026-05-28 14:44:46 CST 国标 OCR 外置规则与页码处理

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户现象与要求：

- 当前打开的 `GBT1568-2008键技术条件` 国标文件第一页封面 OCR 把 `ICS 21.120.30` 识别成 `40°" 120. 30 a`，把 GB 标识图形识别成 `( = =` 等正文块。
- 需要改进实现，并考虑外置规则，允许针对此类国标文件定制。
- 补充要求：文档中可能有文字缺失、页码在左下角或右下角、页码可能为阿拉伯数字或罗马数字；还可能存在公式、符号、数据、物理或化学领域内容，不能被粗暴噪声规则误删。

处理：

- 新增 `rules/document_recognition_rules.json`，将国标类规则外置。
- 新增 `app/core/recognition_rules.py`，主流程在 OCR element 进入 block/chunk 前执行外置规则。
- 国标规则命中条件为 GB/GB-T 编号 + 标准语境；封面规则包括：
  - 对左上 `ICS/J` 区域做局部 OCR + 2 倍放大，恢复为 `ICS 21.120.30` 和 `J 18`。
  - 抑制封面 GB 图形区域误识别出的 `( = =`、`ee | 2` 等噪声。
  - 规范 CJK 空格、`GB/T xxxx—yyyy` 年份连接、`代替`、`发布` 等封面文本。
- 新增页脚页码规则：底部区域的阿拉伯数字或罗马数字标记为 `page_number/not_body_text`，保留在 `elements.jsonl`，但不进入正文 block/chunk。
- 收紧表格 chunk 判定：普通文本里出现 `表`、`AQL`、`检查项目` 不再自动把 chunk 标成 `table`；只有真实 table block 进入 `kind=table`。
- 没有增加通用“短文本/符号多即噪声”的抑制规则，避免误删公式、化学式、物理符号或数据。

验证：

```text
.venv/bin/python -m py_compile app/core/recognition_rules.py app/core/parser.py app/core/chunker.py app/main.py
passed

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_recognition_rules.py tests/test_chunker.py tests/test_table_structure.py
12 passed, 5 warnings

FORCE_REPROCESS=1 .venv/bin/python - <<'PY'
from pathlib import Path
from app.core.parser import process_pdf
from app.core.storage import load_document

doc_id = 'GBT1568-2008键技术条件-e724ad081078fa41'
pdf_path = Path('storage') / doc_id / 'raw' / 'source.pdf'
process_pdf(doc_id, pdf_path)
doc = load_document(doc_id)
print([block['text'] for block in doc['blocks'] if block.get('page_no') == 1][:5])
print([(e['page_no'], e['text']) for e in doc['elements'] if 'page_number' in e.get('quality', {}).get('signals', [])])
PY
['ICS 21.120.30\nJ 18', '中华人民共和国国家标准', 'GB/T 1568—2008', '代替 GB/T 1568—1997', '键 技术条件']
[(2, 'I'), (3, '1')]

GET /api/docs/GBT1568-2008键技术条件-e724ad081078fa41/pages/1/recognition
HTTP 200
第一页文本包含 ICS 21.120.30、J 18、中华人民共和国国家标准、GB/T 1568—2008。

tmux kill-session -t docqa_agent_prototype
tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype './run.sh'
GET /
HTTP 200
```

剩余风险：当前规则覆盖了这类扫描国标封面和页脚页码；跨行业公式、符号和复杂排版仍需要通过更多真实样本扩展外置规则与 golden set。

## 2026-05-28 14:48:46 CST 国标第二页标点 OCR 诊断

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户现象：当前国标文件第二页前言行 `将 3.2“裂缝”改为“裂纹”...` 中，引号、顿号、逗号、省略号附近标点识别不稳定。

诊断：

- 当前落盘 block `p0002-b0016` 文本为 `一一将 3.2“ 裂缝 ? 改为 “裂纹 ”, 删去和影响使用的条痕 \` 四痕 ……?”;`。
- 对应 OCR element `p0002-e0025` 的 `raw_ref.original_text` 已经包含 `裂 缝 ?`、反引号和半角标点，说明错误来自 Tesseract 原始 OCR，不是外置规则后处理引入。
- 该行 OCR 置信度约 `70.08`，明显低于同页多数正文行；标点字号小、扫描边缘模糊、中文弯引号/顿号/省略号与噪点相近，是主要原因。
- 对同一区域做 300 DPI 局部 OCR 时，正文汉字有所改善，但闭引号仍被读成 `?`，`凹痕` 仍可能读成 `四痕`，说明单纯提高 DPI 不能完全解决。

当前结论：这类错误应进入国标/扫描件标点归一化或低置信复核规则；不能用通用符号清理规则处理，否则会误删公式、化学式、物理符号和数据。

## 2026-05-28 14:52:36 CST 国标第三页标题英文误识别

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户现象：当前国标文件第三页标题区域，图片上为中文 `键 技术条件`，识别结果为 `键 RARE`。

诊断：

- 对应 OCR element 为 `p0003-e0039`，文本 `键 RARE`，bbox `[394, 193, 155, 24]`，置信度约 `74.0`。
- 该 element 没有 `raw_ref.original_text` 和外置规则记录，说明这是 Tesseract 原始 OCR 将黑体中文标题误读成英文大写，不是后处理替换造成。

处理：

- 扩展 `app/core/recognition_rules.py`，让 `text_rewrites` 支持 `page_numbers` 与 `bbox_ratio` 区域约束。
- 在 `rules/document_recognition_rules.json` 增加 `chinese_national_standard.running_title_subject`，只修正第 3 页标题区域内的 `键 RARE` 为 `键 技术条件`。
- 新增测试确认该规则是区域约束的：标题区会修正，正文中的 `键 RARE` 示例变量不会被全局替换。

验证：

```text
FORCE_REPROCESS=1 .venv/bin/python - <<'PY'
from pathlib import Path
from app.core.parser import process_pdf
from app.core.storage import load_document

doc_id='GBT1568-2008键技术条件-e724ad081078fa41'
pdf_path=Path('storage')/doc_id/'raw'/'source.pdf'
process_pdf(doc_id,pdf_path)
doc=load_document(doc_id)
for chunk in doc['chunks']:
    if chunk.get('page')==3 and 'GB/T 1568' in chunk.get('text',''):
        print(repr(chunk['text']))
PY
'GB/T 1568—2008\n键 技术条件'

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
30 passed, 5 warnings

tmux kill-session -t docqa_agent_prototype && tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype './run.sh'
GET /
HTTP 200
```

剩余风险：该规则是当前国标样本的区域化修正；其他标准文件的跑题页眉、不同题名或不同页面位置需要继续通过外置规则扩展。

## 2026-05-28 14:59:25 CST 国标问答证据检索别名失败

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户现象：在当前国标文件中提问 `这是什么国标` 时，问答返回“证据不足，无法回答”，验证流程里 `retrieval_validation / evidence_score` 失败。

诊断：

- `这是什么国标` 初始检索结果为空。
- `这是什么国家标准` 能召回封面 chunk，说明文档内容存在，问题在查询归一化。
- 原因是检索只做字符 n-gram 和标点/空格归一，`国标` 与文档中的 `国家标准`、`GB/T`、`标准编号`、`标准名称` 没有同义扩展。
- QA 的 no-answer guard 也基于同一归一化逻辑判断关键业务词覆盖，因此即使后续召回到封面，也需要让 `国标` 与 `国家标准/GB/T` 共享归一化。

处理：

- 在 `app/core/retrieval.py` 的 `normalize_for_retrieval()` 中增加标准类别名扩展：`国标`、`国家标准`、`GB/T`、`GBT`、`标准编号`、`标准号`、`标准名称`。
- 新增检索测试，确认 `这是什么国标` 能召回封面标准 chunk。
- 新增 QA 测试，确认 `这是什么国标` 在证据包含 `中华人民共和国国家标准 / GB/T 1568—2008 / 键 技术条件` 时不会触发证据不足策略。

验证：

```text
.venv/bin/python - <<'PY'
from app.core.storage import load_document
from app.core.retrieval import TfidfRetriever
from app.core.schemas import Chunk

doc_id='GBT1568-2008键技术条件-e724ad081078fa41'
doc=load_document(doc_id)
retriever=TfidfRetriever([Chunk(**item) for item in doc['chunks']])
for item in retriever.search('这是什么国标', top_k=4):
    print(item['score'], item['chunk_id'], item['page'], item['text'].replace('\n',' | ')[:80])
PY
0.6456 c0008 3 GB/T 1568—2008 | 键 技术条件
0.5002 c0007 2 一一 GB 1568—1979,GB/T 1568—1997。
0.4752 c0001 1 ICS 21.120.30 | J 18 | 中华人民共和国国家标准 | GB/T 1568—2008 | 代替 GB/T 1568—1997 | 键 技术条件

POST /api/docs/GBT1568-2008键技术条件-e724ad081078fa41/ask
question=这是什么国标
mode=llm_grounded
evidence_score=pass
llm_judge=pass

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
32 passed, 5 warnings

tmux kill-session -t docqa_agent_prototype && tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype './run.sh'
GET /
HTTP 200
```

剩余风险：当前修复覆盖标准身份类问题；如果后续出现行业缩写、产品型号、公式别名等检索失败，需要继续以同义词/查询扩展方式补充，而不是在 QA 阶段编造答案。

## 2026-05-28 15:05:03 CST 正文页页眉国标标准号处理

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：正文部分左上角或右上角出现的是国标标准号，应按页眉元数据处理。

诊断：

- 当前国标样本中，第 2 页右上、第 3 页右上、第 4 页左上分别有 `GB/T 1568—2008`。
- 这些元素此前作为普通 OCR 文本进入 block/chunk，污染正文识别和问答证据。
- 封面页的 `GB/T 1568—2008` 位于页面中部，是文档身份信息，不应按正文页页眉过滤。

处理：

- 在 `rules/document_recognition_rules.json` 增加 `metadata_line_rules.body_standard_number_header`。
- 匹配页面顶部 12% 区域内的 `GB/T xxxx—yyyy` 或 `GB xxxx—yyyy`，并限制高度/宽度，避免匹配正文标准引用。
- 在 `app/core/recognition_rules.py` 增加通用 metadata line 标记逻辑，将命中项标记为 `semantic_type=standard_number_header`、`standard_number_header`、`not_body_text`。
- `app/main.py` 和 parser 的正文候选过滤统一使用 `not_body_text`，页码和页眉标准号都保留在 `elements.jsonl`，但不进入正文 block/chunk 或识别内容列表。

验证：

```text
FORCE_REPROCESS=1 .venv/bin/python - <<'PY'
from pathlib import Path
from app.core.parser import process_pdf
from app.core.storage import load_document

doc_id='GBT1568-2008键技术条件-e724ad081078fa41'
pdf_path=Path('storage')/doc_id/'raw'/'source.pdf'
process_pdf(doc_id,pdf_path)
doc=load_document(doc_id)
for e in doc['elements']:
    if e.get('raw_ref', {}).get('semantic_type') == 'standard_number_header':
        print(e['page_no'], e['bbox'], e['text'], e['quality']['signals'])
PY
2 [739, 94, 138, 15] GB/T 1568—2008 ['external_rule_applied', 'standard_number_header', 'not_body_text']
3 [718, 101, 138, 31] GB/T 1568—2008 ['external_rule_applied', 'standard_number_header', 'not_body_text']
4 [87, 105, 137, 15] GB/T 1568—2008 ['external_rule_applied', 'standard_number_header', 'not_body_text']

GET /api/docs/GBT1568-2008键技术条件-e724ad081078fa41/pages/3/recognition
前 4 行：键 技术条件；1 范围；本标准规定了...；2 规范性引用文件

STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q
33 passed, 5 warnings

tmux kill-session -t docqa_agent_prototype && tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype './run.sh'
GET /
HTTP 200
```

剩余风险：当前规则覆盖正文页顶部页眉标准号；如果其他标准文件的页眉区域更低、标准号格式不同，继续通过外置规则扩展。

## 2026-05-28 15:07:56 CST 第四页扫描表格识别差诊断

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户反馈：当前国标样本文档第 4 页 `表 1` 的表格识别结果质量差，右侧识别内容出现 `|`、`=-`、`ok mee`、空单元格等异常。

诊断：

- 样本表格为扫描图像表格，缺少可用文本层，解析进入 `scanned_ocr_table` 路径。
- 当前产物 `p0004-t0001`：`bbox=[85,174,776,275]`，`row_count=9`，`column_count=4`，`status=needs_review`，`confidence=0.806`。
- 表格被标记为 `low_cell_ocr_confidence`、`needs_review`、`scanned_table_needs_review`，说明结构进入 chunk 不代表内容质量通过。
- 表头实际是多级合并表头：`检查项目`、`合格质量水平 AQL`、`平键/半圆键/楔键`、`普通/导向/薄型/普通/薄型/钩头`。当前 `_table_artifact()` 只按单行扁平表头映射，导致逻辑列被压成 4 列，表头变成 `| 检查 项 目 |`、`| *# |`、`| ok mee |`、`col_4`。
- 单元格 OCR 使用整格裁剪和 Tesseract `--psm 6`，裁剪中保留边框线，导致边框被识别为 `|`、`=`、`-`，小字号中文、数字、小数和长横线被误识别或低置信度置空。

命令和重要输出：

```text
.venv/bin/python - <<'PY'
... 读取 storage/GBT1568-2008键技术条件-e724ad081078fa41/tables.jsonl 的第 4 页表格摘要 ...
PY
table_id=p0004-t0001
strategy=scanned_ocr_table
status=needs_review
warnings=['low_cell_ocr_confidence', 'needs_review', 'scanned_table_needs_review']
headers=['| 检查 项 目 |', '| *# |', '| ok mee |', 'col_4']
```

当前结论：

- 主要原因不是表格区域未检测到，而是扫描图像表格的单元格 OCR 与多级合并表头重建能力不足。
- 下一步修复应保持通用规则：提高扫描表格裁剪分辨率、OCR 前去除网格线、重建多级表头层级，并保留 `needs_review`，不能用 LLM 猜测补齐单元格。

验证结果：本次为原因诊断和追踪记录，尚未改动解析逻辑。

剩余风险：国标表格中常见多级表头、合并单元格、符号列、长横线和小数值，需后续加入扫描表格专用预处理与层级表头恢复。

## 2026-05-28 15:12:40 CST 当前文档省略主语问答拒答修复

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户现象：在当前国标文件中追问 `哪一年发布的`，问答返回“没有找到足够依据”，并要求用户明确标准或文件。用户指出当前问答应默认指向正在查看的文件。

诊断：

- `/api/docs/{doc_id}/ask` 已经由 URL 限定在单个当前文档内，但 QA Prompt 没有明确“省略主语默认指当前文档/当前标准”。
- 检索层对 `哪一年发布的` 可以召回第 1 页 `2008-09-22 发布 2009-05-01 实施`，但证据列表中也混入正文的 `一年内不生锈`、历次版本发布情况等片段，LLM 因问题省略对象和证据混杂而主动要求澄清。
- 运行全量测试时发现测试使用默认 `storage/`，`clean_storage()` 清掉了当前 Web 文档目录，导致真实 `/ask` 验证先出现 `FileNotFoundError: storage/GBT1568-2008键技术条件-e724ad081078fa41/manifest.json`。

处理：

- 在 `app/core/retrieval.py` 增加发布/实施日期类元数据问题的确定性排序加权：优先包含 `YYYY-MM-DD 发布/实施` 或 `YYYY年M月D日发布/实施` 的 chunk，降低 `制造或出厂日期`、`自出厂之日起` 等正文条款干扰。
- 在 `app/core/qa.py` 的 system/user prompt 中明确：当前接口已限定在当前打开或上传的单个文档内，省略主语或使用 `这个/该/它` 时默认指当前文档或当前标准；不能仅因省略对象要求用户澄清。
- 在 `tests/conftest.py` 增加 pytest autouse fixture，将测试 `STORAGE_DIR` 指向临时目录，避免全量测试破坏默认 Web 存储。
- 从 `data/sample/GBT 1568-2008 键 技术条件.pdf` 恢复默认服务存储中的国标样本文档，并重启 `docqa_agent_prototype` tmux Web 服务。

验证：

```text
.venv/bin/python - <<'PY'
... TfidfRetriever 当前国标样本检索 ...
PY
Q: 哪一年发布的
0.3488 c0002 第1页 Technical specifications for keys | 2008-09-22 发布 2009-05-01 实施

.venv/bin/pytest -q tests/test_retrieval.py tests/test_qa_and_validators.py
10 passed

.venv/bin/pytest -q
35 passed, 5 warnings

tmux kill-session -t docqa_agent_prototype && tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype './run.sh'
GET /
HTTP 200

POST /api/docs/GBT1568-2008键技术条件-e724ad081078fa41/ask
question=哪一年发布的
answer=根据提供的证据，标准发布日期为 2008年（具体为2008-09-22发布，2009-05-01实施）【第1页】。
mode=llm_grounded
evidence_score=pass
llm_judge=pass
```

剩余风险：当前修复覆盖当前文档内发布/实施日期省略主语问题；如果后续出现“谁发布的”“替代哪个版本”等其他元数据追问，需要继续补充对应元数据意图排序规则。

## 2026-05-28 15:37:57 CST 第四页扫描表格识别提升

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：第 4 页表格识别需要提升；如果识别程度太低，可以先识别表格，复杂公式或符号先不处理。

诊断：

- 第 4 页 `表 1` 是扫描图片中的有线表格，没有文本层，仍需走 `scanned_ocr_table`。
- 旧结果只识别出 4 个粗列，短竖线被形态学竖线核过滤掉，导致 `普通/导向/薄型/钩头` 等子列没有进入结构。
- 单元格 OCR 使用外扩裁剪，边框线进入 OCR，产生 `|`、`=-`、纯拉丁噪声等错误。
- 表头存在合并单元格和跨列值，复杂符号如 `b/h/L/d1`、长横线等仍不应强行猜测。

处理：

- 调整有线表格竖线检测：降低短竖线长度门槛，要求竖线贴近行边界，避免正文笔画误判为表格分隔线。
- 单元格 OCR 改为多策略候选：内缩裁剪、2x/3x 放大、`psm 6/11`、可选去除单元格边框线。
- 增加单元格 OCR 清理：去除边框噪声 `|`、孤立 `=-`、纯拉丁噪声；低置信单字符 `一` 不作为确定文本。
- 表格落盘时按真实 `column_index` 写入单元格，跨列值只放在起始列，不复制到占用的多列。

验证：

```text
FORCE_REPROCESS=1 .venv/bin/python - <<'PY'
... 重新解析 GBT1568-2008键技术条件-e724ad081078fa41 ...
PY
table p0004-t0001 scanned_ocr_table 9 8 needs_review 0.925
headers ['检查 项 目', '平 键', 'col_3', 'col_4', 'col_5', 'col_6', 'col_7', 'col_8']
row 2: 普通 / 导向 / 薄型 / 普通 / 薄型 / 钩 头
row 3: 键 宽 6 / 1.0 / 1.0 / 1.5
row 4: 键 高 / 2.5 / 2.5 / 2.5
row 8: 1 : 100 斜 度 / 1.5

.venv/bin/pytest -q tests/test_table_structure.py
9 passed, 5 warnings

.venv/bin/pytest -q
39 passed, 5 warnings
```

当前结论：结构从原来的 4 列提升到 8 个逻辑列，边框噪声明显减少，简单中文和数字已可用；仍保留 `needs_review`，不对复杂符号和低置信表头做推断补齐。

剩余风险：`半圆键/楔键` 等合并表头仍有 OCR 不确定项，`b/h/L/d1` 这类变量符号可能被识别为近似字符或留空。后续如需继续提升，应加入合并表头 row-span 恢复或国标外置表格规则。

## 2026-05-28 16:16:06 CST 演示材料生成与表格问答检索修复

工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`

用户要求：检查并生成 5-10 分钟演示材料，覆盖启动、PDF 正文/表格解析、至少 5 个问答、来源引用、自检结果、测试或评估脚本输出。

诊断：

- 当前 GB/T 样本文档第 4 页表格已生成 `table_markdown` 和 `table_json` chunk，但表格问法会被正文中的 `AQL/检查项目` 片段抢占排序。
- `table_json` 作为证据进入 LLM prompt 时会被通用 900 字截断，LLM 看不到完整 rows，导致表格问题回答不完整。
- 问题 `包装箱或盒外表面应有哪些标志？` 中的 `表面` 不能被误判为表格意图。
- 演示 QA 过程中出现一次 LLM 请求超过 75 秒未返回；重试后成功，说明外部 LLM 延迟仍是演示风险。

处理：

- 在 `app/core/retrieval.py` 增加表格意图加权，仅匹配 `表1/表一/表格/AQL/检查项目/合格质量水平` 等明确表格查询，不匹配普通词 `表面`。
- 在 `app/core/qa.py` 将 `table_json` 证据转换为紧凑 Markdown 表格后再进入 LLM prompt，避免行数据被 JSON 前缀截断。
- 生成演示材料到 `docs/demo_materials.md` 和 `docs/demo_assets/`，截图包括启动、正文、表格、问答、证据自检、测试评估。

验证：

```text
.venv/bin/pytest -q tests/test_retrieval.py tests/test_qa_and_validators.py
13 passed

.venv/bin/pytest -q
42 passed, 5 warnings in 57.21s

.venv/bin/python scripts/evaluate.py --pdf 'data/sample/GBT 1568-2008 键 技术条件.pdf'
q1_scope/q2_strength/q3_table/q4_mark/q5_no_answer 均返回 pass 自检结果

GET /
HTTP 200
```

剩余风险：LLM 服务偶发慢响应会影响现场演示节奏；建议演示时使用已生成的 `docs/demo_assets/qa/*.json` 和截图作为兜底材料，同时保留实时问答演示。
