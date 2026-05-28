# 架构说明

## 1. 总体架构

```text
Web UI
  ├─ PDF 图像查看
  ├─ OCR 结果查看
  ├─ 问答与来源证据
  └─ 人工复核记录

FastAPI Backend
  ├─ PDF Probe：类型判断与策略选择
  ├─ OCR Pipeline：页面渲染、OCR、表格区域检测
  ├─ Knowledge Builder：条款分块、页码/行号索引
  ├─ Retriever：TF-IDF 字符 n-gram 检索
  ├─ QA：抽取式答案与拒答
  └─ Validators：识别验证、答案验证、LLM 验证占位、人工验证

Storage
  ├─ raw/source.pdf
  ├─ images/page-0001.png
  ├─ manifest.json
  ├─ pages.jsonl
  ├─ elements.jsonl
  ├─ edges.jsonl
  ├─ blocks.jsonl
  ├─ chunks.jsonl
  └─ reviews.jsonl
```

## 2. 为什么采用这个架构

作业要求强调“能解释、能测试、能定位问题、能适配不同业务”。因此原型没有把所有逻辑堆在一个脚本里，而是按可替换模块拆分：

- PDF 类型判断独立，方便支持文本层 PDF、扫描件、混合件。
- OCR 独立，便于从 Tesseract 替换到 PaddleOCR、云 OCR 或版面分析模型。
- 元素图谱独立，便于把 OCR 文本、文本层、图片、表格、表单、批注、链接等统一追溯。
- chunker 独立，从元素图谱派生的 block 构建检索 chunk。
- retriever 独立，便于从 TF-IDF 升级为 BM25 + embedding + rerank。
- QA 独立，便于从抽取式答案升级为 LLM 生成。
- validators 独立，便于形成可审计的质量门禁。

## 3. Agent/RAG 流程

当前原型采用确定性工具链 + 轻量 RAG：

1. 工具选择：根据 PDF probe 结果选择 OCR 或文本抽取。
2. 工具执行：渲染页面、OCR、表格候选区检测、文本/图片/矢量/链接等元素抽取。
3. 元素图谱：写入 `elements.jsonl` 和 `edges.jsonl`，建立包含、渲染、OCR 派生、候选、主备选择、贡献、复核绑定等硬关系。
4. 知识构建：从元素图谱派生 block 和 chunk，并保留 source block/type；图片内文字 OCR 如果没有同区域文本层匹配，会作为主 block 进入 chunk，已被文本层覆盖的 OCR 候选保留为 alternative block。
5. 检索：问题进入 TF-IDF 检索，返回 top-k 证据。
6. 回答：证据足够则抽取式回答；不足则拒答。
7. 验证：检索分、答案证据覆盖、无答案保护、LLM 验证占位、人工验证。

在生产环境中，可将第 1 步扩展为真正的 Agent Planner：根据文档类型、用户问题和已有结果，动态选择 OCR、表格抽取、检索、重排、LLM 判断、人工队列等工具。

## 4. 边界情况处理

- 扫描件无文本层：走 OCR。
- OCR 置信度低：标记 warn，进入人工复核。
- OCR PDF 图片文字：文本层和 OCR 同区域时用 `text_candidate_for`、`equivalent_to`/`conflicts_with`、`chosen_over` 关联；未采用候选通过 `alternative_for_chunk` 保留。
- 表格问题：`table_region` 只作为入口，结构化表格抽取按 `docs/table_structure_recognition_design.md` 执行，最终必须进入元素图谱、table block 和 `kind=table` chunk。
- 无答案问题：检索分低于阈值时拒答。
- 模糊问题：返回证据和自检状态，不假装确定。
- 回归风险：评估脚本固定样例问题，后续可加入 golden set。
