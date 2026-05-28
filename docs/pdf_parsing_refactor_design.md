# PDF 解析产物改造设计

## 1. 背景

当前项目是一个最小可运行的文档问答原型，已经具备上传 PDF、探测 PDF 类型、页面渲染、OCR、表格候选区域检测、chunk 构建、TF-IDF 检索、抽取式问答、自检和人工复核记录能力。

本设计聚焦下一阶段改造：把“初次解析后的内容”保存为可追溯、可复核、可供 LLM 使用的中间产物。目标不是立即替换问答链路，而是先把解析事实层稳定下来，避免隐藏文本、OCR 文本、可见文本、表格和人工复核结果混在一起。

## 2. 当前项目现状

### 2.1 现有处理链路

当前主链路如下：

```text
upload PDF
  -> save_upload/copy_sample
  -> probe_pdf
  -> render every page to PNG
  -> ocr_image
  -> detect_table_regions
  -> build_chunks
  -> save meta/pages/chunks
  -> retrieval + QA + validation + human_reviews
```

关键模块：

- `app/core/pdf_probe.py`：文档级 PDF 类型判断，统计文本字符数和图片 block 数，给出策略建议。
- `app/core/parser.py`：统一调度解析流程。
- `app/core/ocr.py`：页面渲染、Tesseract OCR、表格候选区域检测。
- `app/core/schemas.py`：`PdfProbeResult`、`OCRLine`、`PageRecognition`、`Chunk`。
- `app/core/storage.py`：保存 `meta.json`、`pages.json`、`chunks.json` 和 `human_reviews.jsonl`。
- `app/core/chunker.py`：按 OCR 行和简单标题规则构建 chunk。
- `app/core/validators.py`：文档识别、检索和答案自检。

### 2.2 现有存储结构

当前每个文档大致保存为：

```text
storage/{doc_id}/
  source.pdf
  meta.json
  pages.json
  chunks.json
  human_reviews.jsonl
  pages/
    page-1.png
    page-2.png
```

现有结构适合演示闭环，但不够适合后续做复杂 PDF 解析、LLM 复核和人工标注。

### 2.3 主要差距

| 维度 | 当前实现 | 改造目标 |
| --- | --- | --- |
| PDF 类型判断 | 文档级粗判断 | 文档级 + 页级 + block 级判断 |
| 文本来源 | 主要是 OCR 行 | 区分 `visible_text`、`hidden_text`、`image_ocr`、`form_field`、`annotation` |
| 解析事实层 | `pages.json` 保存 OCR 结果 | `blocks.jsonl` 保存所有可追溯内容块 |
| LLM 输入 | 主要来自 chunk | 由 blocks 派生 Markdown/LLM chunks |
| 人工复核 | 问答结果复核为主 | 页面、block、chunk、答案多层复核 |
| 表格 | 候选区域 + OCR 文本 | 表格区域、单元格结构、原文、OCR 结果分层保存 |
| 隐藏文本 | 未单独建模 | 单独标记、评分、去重或降权 |
| 可追溯性 | chunk 追溯到 line_id | chunk 追溯到 block_id、page、bbox、source_type |
| 产物格式 | JSON 文件为主 | JSONL 主事实源，Markdown 给 LLM，HTML 给人工 |

### 2.4 PDF 类型覆盖反思

当前文档已经提出了“文档级 + 页级 + block 级判断”，也设计了 `visible_text`、`hidden_text`、`image_ocr`、`form_field` 等来源类型，但原版本没有把常见 PDF 类型显式列成处理矩阵。实际改造时应把 PDF 类型判断作为解析入口的第一层分流，再在页级和 block 级细化。

推荐类型矩阵：

| 类型 | 识别信号 | 初次解析策略 | 主要产物 |
| --- | --- | --- | --- |
| `text_pdf` | 可抽取文本充足，字体和文本 block 正常，图片不是主体 | 直接抽取 PDF 文本，保留 bbox 和阅读顺序；必要时抽样渲染校验 | `visible_text` blocks |
| `scan_pdf` | 文本层为空或极少，每页大图覆盖主体内容 | 整页渲染后 OCR；OCR 置信度低时进入人工复核 | `image_ocr` blocks、page image |
| `ocr_pdf` | 页面像扫描图，但存在可搜索文本层或不可见文本层 | 抽取隐藏文本并做质量评估；必要时重新 OCR 对照，不直接信任文本层 | `hidden_text` blocks、可选 `image_ocr` blocks |
| `mixed_pdf` | 不同页或同页同时出现文本、扫描图、表格、批注 | 逐页选择文本抽取、OCR 或混合策略；chunk 保留多来源 metadata | 多种 source_type blocks |
| `form_pdf` | 存在 AcroForm/XFA 字段或字段值不完整显示在页面文本中 | 读取表单字段；同时渲染页面用于视觉核对；字段值单独保存 | `form_field` blocks |
| `protected_pdf` | 加密、需要密码，或权限限制复制/抽取/打印 | 先做权限预检；不能打开则提示用户提供授权密码；权限不足时不静默绕过 | manifest permission 状态、错误或降级策略 |
| `drawing_pdf` | 大量矢量线条、CAD/图纸/地图，普通文本抽取很少 | 保留页面图和图形/文本候选；OCR 只处理标签文字；标记需要版面/视觉理解 | `image`、`visible_text`、低置信 review blocks |

`pdf_type` 不应只能有一个全局值。更稳妥的做法是：

- `manifest.json` 保存文档级主类型和候选类型。
- `pages.jsonl` 保存每页 `page_type` 和 `strategy`。
- `blocks.jsonl` 保存每个内容块的 `source_type`。

这样可以避免把混合文档误判成单一 PDF 类型。

## 3. 设计目标

1. 保留当前最小闭环，不破坏现有上传、问答、复核功能。
2. 新增一个稳定的“解析事实层”，用结构化 JSONL 保存初次解析结果。
3. 明确区分隐藏文本、可见文本、重新 OCR 文本、表单字段、批注和表格。
4. 支持按页复核、按 block 复核、按 chunk 复核。
5. 让 LLM 使用的是从事实层派生出的 Markdown 或 chunks，而不是直接依赖 OCR 原始输出。
6. 保留足够元信息，方便后续重跑 OCR、换 OCR 引擎、做表格专用解析或接入版面模型。

## 4. 非目标

- 不在本阶段实现完整商业级版面分析。
- 不要求一次性替换 TF-IDF 检索。
- 不要求当前 Web UI 立即升级为完整标注平台。
- 不要求隐藏文本一定优先于 OCR；它只是候选文本源。

## 5. 目标目录结构

建议在保持兼容的前提下扩展存储目录：

```text
storage/{doc_id}/
  raw/
    source.pdf
  manifest.json
  pages.jsonl
  blocks.jsonl
  chunks.jsonl
  reviews.jsonl
  derived/
    full.md
    page-0001.md
    review.html
  images/
    page-0001.png
    page-0002.png
  legacy/
    meta.json
    pages.json
    chunks.json
```

短期也可以不移动现有文件，只新增：

```text
storage/{doc_id}/
  manifest.json
  pages.jsonl
  blocks.jsonl
  chunks.jsonl
  derived/
    full.md
    review.html
```

这样可以避免一次性破坏现有接口。

## 6. 核心数据模型

### 6.1 manifest.json

文档级清单，记录可复现信息。

```json
{
  "schema_version": "parse-artifact-v1",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "source_filename": "source.pdf",
  "source_sha256": "...",
  "created_at": "2026-05-28T12:00:00+08:00",
  "parser": {
    "name": "docqa_agent_prototype",
    "version": "0.2.0"
  },
  "pdf_probe": {
    "pdf_type": "mixed_pdf",
    "pdf_type_candidates": ["ocr_pdf", "scan_pdf"],
    "pages": 4,
    "has_text_layer": true,
    "has_hidden_text": true,
    "has_images": true,
    "has_forms": false,
    "has_vector_drawings": false,
    "is_encrypted": false,
    "permission": {
      "requires_password": false,
      "authenticated": true,
      "allows_text_extraction": true,
      "allows_rendering": true,
      "action": "parse"
    }
  },
  "outputs": {
    "pages": "pages.jsonl",
    "blocks": "blocks.jsonl",
    "chunks": "chunks.jsonl",
    "markdown": "derived/full.md",
    "review_html": "derived/review.html"
  }
}
```

### 6.2 pages.jsonl

一行一页，保存页级策略和质量信号。

```json
{
  "page_id": "p0001",
  "page_no": 1,
  "width": 991,
  "height": 1403,
  "image_path": "images/page-0001.png",
  "page_type": "mixed_page",
  "strategy": "text_layer_plus_ocr_check",
  "text_layer_chars": 1200,
  "ocr_chars": 1180,
  "image_blocks": 1,
  "table_region_count": 2,
  "average_ocr_confidence": 83.2,
  "warnings": ["hidden_text_needs_quality_check"]
}
```

### 6.3 blocks.jsonl

主事实源。一行一个解析块。

```json
{
  "block_id": "p0001-b0007",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "page_id": "p0001",
  "page_no": 1,
  "block_type": "paragraph",
  "source_type": "hidden_text",
  "text": "本标准规定了键的技术条件...",
  "bbox": [72, 120, 500, 40],
  "confidence": 0.72,
  "reading_order": 7,
  "language": "zh-CN",
  "quality": {
    "status": "warn",
    "signals": ["copied_text_may_be_ocr_layer", "needs_visual_alignment_check"]
  },
  "links": {
    "image_path": "images/page-0001.png"
  }
}
```

`source_type` 建议固定枚举：

- `visible_text`：PDF 可见文本对象。
- `hidden_text`：隐藏 OCR 文本层或不可见文本。
- `image_ocr`：对渲染图重新 OCR 得到的文本。
- `form_field`：PDF 表单字段值。
- `annotation`：批注、签名、注释。
- `table_cell`：表格单元格。
- `image`：图片或非文本区域。
- `drawing_element`：图纸、地图、CAD 类矢量线条或区域。

### 6.4 protected_pdf 权限处理

受保护 PDF 应在正文解析前先进入权限预检，不应等 OCR 或文本抽取失败后才发现。

建议处理：

1. 打开前记录文件 hash 和基础元信息。
2. 检查是否加密、是否需要用户密码、当前权限是否允许文本抽取和页面渲染。
3. 如果需要密码，返回 `protected_pdf` 状态并提示用户提供授权密码；密码只用于本次解析，不写入持久化产物。
4. 如果可以打开但权限禁止文本抽取，默认不要静默绕过；在 `manifest.permission.action` 中标记为 `needs_authorization` 或 `render_only_with_authorization`。
5. 如果业务流程明确拥有授权且允许渲染，可降级为页面渲染 + OCR，但必须在 manifest 中保留权限状态和降级原因。
6. 如果既不能抽取也不能渲染，则保存失败状态，不生成伪造的空 blocks。

示例权限状态：

```json
{
  "pdf_type": "protected_pdf",
  "permission": {
    "requires_password": true,
    "authenticated": false,
    "allows_text_extraction": false,
    "allows_rendering": false,
    "action": "request_password"
  }
}
```

### 6.5 chunks.jsonl

给检索和 LLM 使用的派生产物。一行一个 chunk。

```json
{
  "chunk_id": "c0001",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "text": "本标准规定了键的技术条件...",
  "kind": "text",
  "page_range": [1, 1],
  "source_block_ids": ["p0001-b0007", "p0001-b0008"],
  "source_types": ["visible_text", "image_ocr"],
  "confidence": 0.86,
  "warnings": [],
  "review_status": "pending"
}
```

## 7. 隐藏文本处理策略

隐藏文本需要单独区分，不建议直接和 OCR 文本合并。

推荐策略：

1. 从 PDF text layer 抽取文本对象，记录可见性、字体、颜色、bbox、字符数。
2. 如果文本不可见、透明、被图片覆盖，或疑似 OCR layer，标记为 `hidden_text`。
3. 同页渲染图仍然保留，必要时重新 OCR 得到 `image_ocr`。
4. 对 `hidden_text` 和 `image_ocr` 做质量比较：
   - 字符量是否接近。
   - 是否乱码。
   - 是否大量重复。
   - 是否和视觉 bbox 对齐。
   - 是否覆盖表格、印章、手写、图片文字。
5. 质量好时可以用隐藏文本生成 chunk，但 chunk metadata 必须保留 `source_type=hidden_text`。
6. 质量差时降权或替换为 `image_ocr`，但不要删除原始隐藏文本 block。

原则：隐藏文本是候选事实源，不是默认可信正文。

## 8. Markdown 与 HTML 派生物

### 8.1 Markdown 给 LLM

Markdown 由 `blocks.jsonl` 派生，不作为主事实源。

建议格式：

```markdown
<!-- doc_id: GBT1568-2008-e724ad081078fa41 -->
<!-- generated_from: blocks.jsonl -->

# 第 1 页

<!-- block_id: p0001-b0007 source_type: image_ocr confidence: 0.86 -->
本标准规定了键的技术条件...

<!-- block_id: p0001-b0012 source_type: table_cell confidence: 0.78 -->
| 检查项目 | AQL |
| --- | --- |
| 尺寸 | 1.5 |
```

LLM prompt 使用 Markdown 时，应同时传入 block_id 或 chunk_id，避免模型回答后无法追溯来源。

### 8.2 HTML 给人工复核

HTML 同样由结构化事实层派生，适合展示：

- 页面图片。
- block bbox 覆盖层。
- source_type 颜色标记。
- OCR 置信度。
- hidden_text 与 image_ocr 差异。
- 表格候选区域。
- 人工复核按钮和备注。

HTML 不应作为解析主存储；人工复核结果应写回 `reviews.jsonl` 或现有 `human_reviews.jsonl` 的扩展版本。

## 9. 改造后的处理流程

```text
upload PDF
  -> save source
  -> document probe
  -> page probe
  -> extract visible/hidden text blocks
  -> render page images
  -> OCR pages or regions when needed
  -> table region detection / table extraction
  -> normalize all sources into blocks.jsonl
  -> quality checks and dedup
  -> build chunks.jsonl
  -> derive Markdown for LLM
  -> derive HTML for human review
  -> retrieval / QA / validation
  -> reviews.jsonl
```

相比当前实现，核心变化是把 `process_pdf` 从“直接 OCR 到 pages/chunks”改成“先生成 blocks，再由 blocks 派生后续产物”。

## 10. 与现有模块的映射

| 现有模块 | 保留方式 | 改造点 |
| --- | --- | --- |
| `pdf_probe.py` | 保留 | 扩展页级 probe、隐藏文本识别、加密/表单/附件检测 |
| `parser.py` | 保留调度入口 | 拆成 probe、extract、render、ocr、block normalize、derive 多阶段 |
| `ocr.py` | 保留 | OCR 输出从 `PageRecognition` 同步转成 `Block` |
| `schemas.py` | 保留旧 schema | 新增 `DocumentManifest`、`PageArtifact`、`BlockArtifact`、`ChunkArtifact` |
| `storage.py` | 保留现有 JSON | 新增 JSONL 读写；短期双写，长期迁移 |
| `chunker.py` | 保留 | 输入从 `PageRecognition` 改为 blocks；chunk 记录 source_block_ids |
| `validators.py` | 保留 | 增加 hidden text 质量、block 覆盖率、文本源冲突检查 |
| `app/main.py` | 保留 API | 新增 artifact 查询接口，旧接口可由新格式适配 |
| Web UI | 保留页面查看 | 增加 source_type、block bbox、hidden/OCR 对比复核 |

## 11. 分阶段实施建议

### 阶段 1：只新增事实层，不改问答行为

- 新增 `blocks.jsonl` 和 `manifest.json`。
- 当前 OCR 行转换为 `source_type=image_ocr` blocks。
- `chunks.json` 继续保持旧格式，同时新增 `chunks.jsonl`。
- 单元测试覆盖 JSONL 写入、block id、source_block_ids。

收益：风险低，不影响现有 Web 和评估脚本。

### 阶段 2：接入文本层和隐藏文本识别

- 在 PyMuPDF 中抽取 text dict/rawdict。
- 区分 visible text 和 hidden text。
- 对 text layer 和 OCR 做页级质量比较。
- 对明显可信文本层页面跳过整页 OCR，或只做抽样 OCR 校验。

收益：文本型 PDF 更快，OCR PDF 更可控。

### 阶段 3：由 blocks 驱动 chunk 和检索

- `build_chunks` 改为读取 blocks。
- chunk 保存 `source_block_ids`、`source_types`、`confidence`、`warnings`。
- Markdown 由 chunks/blocks 派生。
- 旧 `pages.json` 作为兼容视图生成。

收益：检索证据可追溯到原始 block 和 bbox。

### 阶段 4：人工复核升级

- 前端展示 block overlay。
- 支持按 block 标记 `pass`、`needs_fix`、`ignore`、`replace_text`。
- 复核结果写入 `reviews.jsonl`，并能生成修订后的 `blocks.reviewed.jsonl`。

收益：人工复核不只停留在问答结果，而能修正解析事实。

### 阶段 5：表格和复杂版面增强

- 表格候选区域进入 blocks。
- 增加 table structure artifact，例如 `tables.jsonl`。
- LLM 验证时显式提示表格风险。
- 对双栏、页眉页脚、水印、印章等做 block 级规则。

收益：处理技术标准、合同、扫描档案时更稳。

## 12. 测试与验收

建议新增测试：

- 文本型 PDF：能产生 `visible_text` blocks。
- 扫描型 PDF：能产生 `image_ocr` blocks。
- OCR PDF：能产生 `hidden_text` blocks，并保留质量 warning。
- 混合 PDF：不同页面策略不同。
- chunk 追溯：每个 chunk 都有 `source_block_ids`。
- Markdown 派生：包含 block_id/source_type 注释。
- HTML 派生：能引用页面图片和 block bbox。
- 兼容性：现有 `pytest -q` 和 `python scripts/evaluate.py --sample` 仍能通过。

基础验收命令：

```bash
pytest -q
python scripts/evaluate.py --sample
```

## 13. 风险与取舍

- JSONL 比单个 JSON 更适合大文档增量写入，但前端读取需要聚合接口。
- hidden text 的可见性判断在不同 PDF 生成器里可能不稳定，需要保留人工复核入口。
- OCR 与隐藏文本去重不能只靠字符串相似度，还要结合 bbox 和阅读顺序。
- 表格结构恢复复杂，第一阶段应只保存候选区域和文本，不要过早承诺完整单元格准确率。
- 为兼容现有 Demo，短期建议双写旧格式和新格式；等新链路稳定后再迁移旧接口。

## 14. 推荐结论

当前项目已经具备可演示的 OCR + RAG + 人工复核闭环，但解析产物还停留在“页 OCR 结果”和“问答 chunk”层。下一步应优先建立 `blocks.jsonl` 事实层，并把隐藏文本、可见文本、OCR 文本、表格和复核信息分开保存。

推荐落地顺序是：

1. 新增 `manifest.json`、`blocks.jsonl`、`chunks.jsonl`，先从现有 OCR 结果派生。
2. 增加文本层和隐藏文本抽取，不直接改变问答行为。
3. 让 chunk 和 LLM Markdown 从 blocks 派生。
4. 升级人工复核界面，让人可以复核 block，而不仅是复核答案。

这样既能保持现有原型可运行，又能为后续 LLM 复核、人工校正、表格增强和生产级解析打基础。
