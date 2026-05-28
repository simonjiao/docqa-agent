# 智能文档问答 Agent 原型

这是一个面向技术笔试作业的最小可运行原型。目标不是做完整商业系统，而是把“扫描 PDF 识别、可检索知识库、问答证据、自检、人工复核”串成一个可以演示和迭代的闭环。

## 1. 原型能力

- Web 交互：左侧查看 PDF 页面图像，右侧查看 OCR 行级识别结果、疑似表格区域、验证结果。
- PDF 策略判断：自动识别文本层 PDF、扫描 PDF、混合 PDF，并选择解析策略。
- OCR 识别：默认使用 Tesseract，语言为 `chi_sim+eng`，适配中文扫描件与英文/数字混排。
- 表格候选区：基于页面横竖线检测表格区域，供后续表格 OCR 与人工复核。
- RAG 检索：使用 TF-IDF 字符 n-gram 建立轻量索引，检索结果作为 QA 事实来源。
- 问答输出：集成 `vendor/mini-agent`，必须配置 OpenAI-compatible LLM，由 LLM 只基于检索证据组织答复；证据不足时拒答。
- 多流程验证：包括文档识别验证、检索验证、答案依据验证、LLM 事实约束、人工验证记录。
- 可复现测试：提供单元测试和评估脚本，覆盖正文、表格、无答案问题。

## 2. 快速启动

### 2.1 安装系统 OCR

Linux 示例：

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-script-hans
```

如果本机 Tesseract 语言包名称不是 `HanS`，可以通过以下命令查看：

```bash
tesseract --list-langs
```

然后设置环境变量，例如：

```bash
export OCR_LANG=chi_sim+eng
export OCR_DPI=120
export OCR_TIMEOUT=30
```

### 2.2 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 启动 Web 原型

QA 功能必须配置 LLM；未配置时 `/ask` 接口会返回 503，不会回退到抽取式答案。

```bash
export DOCQA_LLM_BASE_URL=http://127.0.0.1:8080/v1
export DOCQA_LLM_API_KEY=your-api-key
export DOCQA_LLM_MODEL=your-model
```

也兼容 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`。

项目根目录 `.env` 会被 `run.sh` 和 QA 配置加载器读取；`.env` 不应提交。

```bash
./run.sh
```

浏览器打开：

```text
http://localhost:8000
```

可以上传新的 PDF。项目包内保留了样例识别缓存，便于评估脚本和接口验证；如需强制重新 OCR，可设置 `FORCE_REPROCESS=1` 或清空 `storage/`。

## 3. 代码结构

```text
app/
  main.py                 FastAPI 接口与页面入口
  core/
    pdf_probe.py          PDF 类型判断与解析策略选择
    ocr.py                页面渲染、OCR、表格候选区域检测
    parser.py             元素图谱、硬关系边、派生产物构建
    chunker.py            基于 block 的检索 chunk 构建
    retrieval.py          TF-IDF 检索
    qa.py                 mini-agent LLM 事实约束问答与拒答逻辑
    validators.py         文档识别、检索、答案、LLM、人工验证
    storage.py            文档、识别结果、复核记录持久化
  web/
    templates/index.html  Web 页面
    static/app.js         前端交互
    static/style.css      样式
docs/
  architecture.md         架构说明
  validation_workflow.md  验证流程说明
  demo_script.md          演示脚本
  demo_materials.md       5-10 分钟演示材料入口
  demo_assets/            演示截图、QA 返回、测试与评估输出
  pdf_element_graph_implementation_checklist.md  元素图谱实现清单
  debug_trace.md          调试过程跟踪记录
docs-for-test/
  sample_scan.pdf         自动测试和评估使用的 PDF 样本
scripts/
  evaluate.py             样例问题评估脚本
tests/
  pytest 单元测试
vendor/
  mini-agent/             本项目内置 Agent/LLM 客户端支持
AGENTS.md                 项目协作规则与调试跟踪要求
```

## 4. 处理流程

1. 上传 PDF。
2. `pdf_probe` 判断 PDF 类型、文本层、图片、表单、矢量和权限信号。
3. 渲染页面并执行 OCR。
4. 将页面、页面图、OCR 文本、表格候选、PDF 文本层、图片、矢量、链接等写入 `elements.jsonl`。
5. 将包含、渲染、OCR 派生、候选等价、主备选择、block/chunk 贡献关系写入 `edges.jsonl`。
6. 从元素图谱派生 `blocks.jsonl` 和 `chunks.jsonl`；未匹配文本层的图片 OCR 文本进入主 chunk，同区域未采用候选保留为 alternative block。
7. 根据用户问题检索相关 chunk，并保留 source block/type 追溯信息。
8. 将检索证据交给 vendored mini-agent 的 OpenAI-compatible LLM 客户端组织答案；Prompt 明确禁止使用证据外事实。
9. 执行自检：证据分数、答案和证据重合度、无答案保护、LLM 事实约束。
10. 前端支持人工确认、退回或标记不确定，并保存复核记录到 `reviews.jsonl`，同时追加 `review` element 和 `review_of` edge。

## 5. 验证流程

原型集成了三层验证：

- 文档识别过程验证：OCR 平均置信度、文本密度、表格候选区域。
- LLM/答案验证：QA 必须配置 LLM；`llm_validation` 会记录实际模型已基于检索证据组织答复。未配置时接口失败，不生成回退答案。
- 人工验证：Web 页面中可对答案做通过、退回修正、不确定记录，形成审计轨迹。

## 6. 示例问题

建议演示至少 5 个问题：

1. 本标准规定了什么范围？
2. 键的抗拉强度要求是多少？
3. 表 1 中合格质量水平 AQL 和哪些检查项目有关？
4. 包装箱或盒外表面应有哪些标志？
5. 该标准是否规定了电机噪声测试？

第 5 个问题应触发无答案保护。

## 7. 测试

```bash
.venv/bin/pytest -q
```

运行评估脚本需要先配置 LLM；如果项目根目录已有 `.env`，脚本会自动读取：

```bash
.venv/bin/python scripts/evaluate.py --sample
```

## 8. 演示材料与截图

完整 5-10 分钟演示材料入口：

- [docs/demo_materials.md](docs/demo_materials.md)

截图和原始输出都保存在 `docs/demo_assets/`。每张截图对应的演示内容如下：

| 内容 | 说明 | 路径 |
| --- | --- | --- |
| 部署 / 启动完整流程 | 展示 `.venv/bin/python`、`./run.sh`、服务会话、健康检查和样本文档信息。 | [docs/demo_assets/01_startup_flow.png](docs/demo_assets/01_startup_flow.png) |
| PDF 正文解析结果 | 展示第 3 页原图、OCR 置信度、正文块和条款识别结果。 | [docs/demo_assets/02_pdf_body.png](docs/demo_assets/02_pdf_body.png) |
| PDF 表格解析结果 | 展示第 4 页表 1 原图、结构化表格、`needs_review` 状态和表格置信度。 | [docs/demo_assets/03_pdf_table.png](docs/demo_assets/03_pdf_table.png) |
| 问答结果 | 展示 6 个问题的回答，包含正文问题、表格问题和无答案拒答问题。 | [docs/demo_assets/04_qa_results.png](docs/demo_assets/04_qa_results.png) |
| 来源引用和自检结果 | 展示表格问题与无答案问题的证据 chunk、页码、检索分和自检状态。 | [docs/demo_assets/05_sources_checks.png](docs/demo_assets/05_sources_checks.png) |
| 测试与评估脚本结果 | 展示 `pytest` 和 `scripts/evaluate.py` 的运行结果。 | [docs/demo_assets/06_tests_eval.png](docs/demo_assets/06_tests_eval.png) |

相关机器可读输出：

- `docs/demo_assets/demo_summary.json`：截图与 QA 用例摘要。
- `docs/demo_assets/qa/*.json`：每个演示问题的 `/ask` 接口返回。
- `docs/demo_assets/pytest_output.txt`：完整测试输出。
- `docs/demo_assets/evaluate_output.json`：评估脚本 JSON 输出。

## 9. 当前取舍与限制

- QA 不提供抽取式回退；必须配置 OpenAI-compatible LLM。检索结果仍是唯一事实来源，LLM 只负责组织答复。
- 表格识别实现为“表格区域检测 + OCR 文本”，不是完整单元格结构恢复；这是本原型的主要迭代点。
- 新存储格式不再把旧 `meta.json`、`pages.json`、`chunks.json` 作为主输出；事实源为 `manifest.json`、`pages.jsonl`、`elements.jsonl`、`edges.jsonl`、`blocks.jsonl`、`chunks.jsonl`。
- OCR 结果受 Tesseract 语言包、DPI、扫描质量影响；低置信度页面会进入人工复核。默认 `OCR_DPI=120`、`OCR_TIMEOUT=30`，防止扫描噪声导致识别过程长时间阻塞。
- 轻量检索使用 TF-IDF，适合原型和小规模文档；生产可替换为向量索引、BM25 + embedding 混合检索。

## 10. AI 使用说明模板

本项目允许使用 AI 辅助开发，但结果需要自己负责。建议在提交时如实说明：

- 使用 AI 辅助梳理架构、生成样板代码、设计测试用例。
- 对生成代码进行了本地运行、单元测试和人工阅读。
- 对 OCR 和问答结果设置了自检与人工复核，不把 AI 输出直接作为最终事实。
- 未提交 API Key、账号密码或其他敏感信息。
