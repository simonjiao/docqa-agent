# 架构说明

## 1. 总体架构

```text
Web UI
  ├─ PDF 图像查看
  ├─ OCR 结果查看
  ├─ LLM 校订查看
  ├─ HTML 预览
  ├─ 问答与来源证据
  └─ 人工复核记录

FastAPI Backend
  ├─ PDF Probe：类型判断与策略选择
  ├─ OCR Pipeline：页面渲染、OCR、表格区域检测
  ├─ Rule Engine：外置识别规则、页眉页脚/页码/国标规则
  ├─ Table Parser：表格结构化、table_markdown/table_json
  ├─ Knowledge Builder：元素图谱、block/chunk 构建
  ├─ Retriever：TF-IDF 字符 n-gram 检索
  ├─ Page Polish：LLM 段落/列表校订
  ├─ QA：mini-agent LLM 事实约束答复与拒答
  └─ Validators：识别验证、答案验证、LLM 事实约束、人工验证

Storage
  ├─ raw/source.pdf
  ├─ images/page-0001.png
  ├─ manifest.json
  ├─ pages.jsonl
  ├─ elements.jsonl
  ├─ edges.jsonl
  ├─ blocks.jsonl
  ├─ chunks.jsonl
  ├─ tables.jsonl
  └─ reviews.jsonl

Project Docs
  ├─ README.md
  ├─ FOLLOWUP.md
  ├─ docs/architecture.md
  ├─ docs/validation_workflow.md
  ├─ docs/demo_materials.md
  └─ docs/debug_trace.md
```

## 2. 为什么采用这个架构

作业要求强调“能解释、能测试、能定位问题、能适配不同业务”。因此原型没有把所有逻辑堆在一个脚本里，而是按可替换模块拆分：

- PDF 类型判断独立，方便支持文本层 PDF、扫描件、混合件。
- OCR 独立，便于从 Tesseract 替换到 PaddleOCR、云 OCR 或版面分析模型。
- 元素图谱独立，便于把 OCR 文本、文本层、图片、表格、表单、批注、链接等统一追溯。
- 规则层独立，便于按国标、检测报告、表单等文档类型外置识别规则，避免把领域规则写死在 LLM prompt 中。
- 表格解析独立，便于把扫描表格先稳定转换成 `table_markdown/table_json`，再进入检索和人工复核。
- chunker 独立，从元素图谱派生的 block 构建检索 chunk。
- retriever 独立，便于从 TF-IDF 升级为 BM25 + embedding + rerank。
- QA 独立，通过 `vendor/mini-agent` 调用 OpenAI-compatible LLM；检索证据是唯一事实来源，LLM 只负责组织答复。
- validators 独立，便于形成可审计的质量门禁。
- `FOLLOWUP.md` 独立记录后续负责人视角的推进方式、LLM 增强位置、外部规则建设、安全合规和 AI 辅助工作边界。

## 3. Agent/RAG 流程

当前原型采用确定性工具链 + 轻量 RAG：

1. 工具选择：根据 PDF probe 结果选择 OCR 或文本抽取。
2. 工具执行：渲染页面、OCR、表格候选区检测、文本/图片/矢量/链接等元素抽取。
3. 元素图谱：写入 `elements.jsonl` 和 `edges.jsonl`，建立包含、渲染、OCR 派生、候选、主备选择、贡献、复核绑定等硬关系。
4. 表格结构化：表格区域进入 table parser，产出 `tables.jsonl`、table block 和 `kind=table` chunk；低置信扫描表格保留 `needs_review`。
5. 知识构建：从元素图谱派生 block 和 chunk，并保留 source block/type；图片内文字 OCR 如果没有同区域文本层匹配，会作为主 block 进入 chunk，已被文本层覆盖的 OCR 候选保留为 alternative block。
6. 检索：问题进入 TF-IDF 检索，表格意图会优先保留明确 table chunk，返回 top-k 证据。
7. 回答：证据和证据策略交给 mini-agent LLM 客户端；证据足够则组织答复，不足则必须拒答。
8. 页面校订：用户需要时，LLM 可整理当前页段落、列表和明显 OCR 错别字，但不覆盖原始识别产物。
9. 验证：检索分、答案证据覆盖、无答案保护、LLM 事实约束、人工验证。

在生产环境中，可将第 1 步扩展为真正的 Agent Planner：根据文档类型、用户问题和已有结果，动态选择 OCR、表格抽取、检索、重排、LLM 判断、人工队列等工具。

## 4. 边界情况处理

- 扫描件无文本层：走 OCR。
- OCR 置信度低：标记 warn，进入人工复核。
- OCR PDF 图片文字：文本层和 OCR 同区域时用 `text_candidate_for`、`equivalent_to`/`conflicts_with`、`chosen_over` 关联；未采用候选通过 `alternative_for_chunk` 保留。
- 表格问题：`table_region` 只作为入口，结构化表格抽取按 `docs/table_structure_recognition_design.md` 执行，最终必须进入元素图谱、table block 和 `kind=table` chunk。
- 表格证据过长：`table_json` 进入 LLM 前转换为紧凑 Markdown 表格，避免 JSON 前缀挤占 rows 内容。
- 领域规则：国标页眉标准号、页码、目录、正文条款、图表和公式等应走外置规则，命中结果记录 rule id。
- 无答案问题：检索分低于阈值时仍调用 LLM，但 Prompt 强制基于证据不足拒答；如果 LLM 不拒答，则视为事实约束失败。
- 模糊问题：返回证据和自检状态，不假装确定。
- 回归风险：评估脚本固定样例问题，后续可加入 golden set。

## 5. 负责人交付说明

`FOLLOWUP.md` 是本架构文档的补充材料，说明如果后续继续负责该系统，如何推进 LLM 增强、流程嵌入、外部规则、安全合规和 AI 辅助开发流程。它不替代架构设计，而是记录系统负责人的取舍和交付方式。
