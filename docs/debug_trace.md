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
