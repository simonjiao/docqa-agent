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
| PDF 类型判断 | 文档级粗判断 | 文档级 + 页级 + element/block 级判断 |
| 文本来源 | 主要是 OCR 行 | 区分 `visible_text`、`hidden_text`、`image_ocr`、`form_field`、`annotation` |
| 元素覆盖 | 只保存 OCR 行和表格候选区 | 保存 PDF 原生元素、渲染元素、派生 OCR 元素和关系边 |
| 解析事实层 | `pages.json` 保存 OCR 结果 | `elements.jsonl` + `edges.jsonl` 保存元素图谱，`blocks.jsonl` 作为派生内容层 |
| LLM 输入 | 主要来自 chunk | 由元素图谱派生 blocks、chunks、Markdown |
| 人工复核 | 问答结果复核为主 | 页面、element、block、chunk、答案多层复核 |
| 表格 | 候选区域 + OCR 文本 | 表格区域、单元格结构、原文、OCR 结果分层保存 |
| 隐藏文本 | 未单独建模 | 单独标记、评分、去重或降权 |
| 可追溯性 | chunk 追溯到 line_id | chunk 经 block/edge 追溯到 element、page、bbox、source_type |
| 产物格式 | JSON 文件为主 | 元素/关系 JSONL 是事实源，Markdown 给 LLM，HTML 给人工 |

### 2.4 PDF 类型覆盖反思

实际改造时应把 PDF 类型判断作为解析入口的第一层分流，再在页级、element 级和 block 级细化。类型判断不能只决定 OCR 或文本抽取，还要决定最低元素覆盖要求和必须生成的硬联系。

推荐类型矩阵：

| 类型 | 识别信号 | 初次解析策略 | 主要产物 |
| --- | --- | --- | --- |
| `text_pdf` | 可抽取文本充足，字体和文本 block 正常，图片不是主体 | 直接抽取 PDF 文本，保留 bbox 和阅读顺序；必要时抽样渲染校验 | `text_span` elements、`visible_text` blocks |
| `scan_pdf` | 文本层为空或极少，每页大图覆盖主体内容 | 整页渲染后 OCR；OCR 置信度低时进入人工复核 | `page_render`、`image_region`、`ocr_text` elements |
| `ocr_pdf` | 页面像扫描图，但存在可搜索文本层或不可见文本层 | 抽取隐藏文本并做质量评估；必要时重新 OCR 对照，不直接信任文本层 | `hidden_text_span`、`ocr_text` elements 和候选关系边 |
| `mixed_pdf` | 不同页或同页同时出现文本、扫描图、含文字图片、表格、批注 | 逐页、逐区域选择文本抽取、图片保留或区域 OCR；chunk 保留多来源 metadata | 多种 element/source_type 和关系边 |
| `form_pdf` | 存在 AcroForm/XFA 字段或字段值不完整显示在页面文本中 | 读取表单字段；同时渲染页面用于视觉核对；字段值单独保存 | `form_field` elements 和 `field_value_of` 边 |
| `protected_pdf` | 加密、需要密码，或权限限制复制/抽取/打印 | 先做权限预检；不能打开则提示用户提供授权密码；权限不足时不静默绕过 | manifest permission 状态、错误或降级策略 |
| `drawing_pdf` | 大量矢量线条、CAD/图纸/地图，普通文本抽取很少 | 保留页面图和图形/文本候选；OCR 只处理标签文字；标记需要版面/视觉理解 | `vector_path`、标签文本、`unsupported_element` |

`pdf_type` 不应只能有一个全局值。更稳妥的做法是：

- `manifest.json` 保存文档级主类型和候选类型。
- `pages.jsonl` 保存每页 `page_type` 和 `strategy`。
- `elements.jsonl` 保存每个原生或派生元素的 `element_type`、`source_type`。
- `edges.jsonl` 保存元素、block、chunk、复核结果之间的硬联系。
- `blocks.jsonl` 只保存从元素图谱派生的内容块。

这样可以避免把混合文档误判成单一 PDF 类型。

## 3. 设计目标

1. 保留当前最小闭环，不破坏现有上传、问答、复核功能。
2. 新增一个稳定的“解析事实层”，用结构化 JSONL 保存初次解析结果。
3. 明确区分隐藏文本、可见文本、重新 OCR 文本、表单字段、批注和表格。
4. 支持按页复核、按 block 复核、按 chunk 复核。
5. 让 LLM 使用的是从事实层派生出的 Markdown 或 chunks，而不是直接依赖 OCR 原始输出。
6. 保留足够元信息，方便后续重跑 OCR、换 OCR 引擎、做表格专用解析或接入版面模型。
7. 尽可能识别 PDF 中的所有元素，包括文字、图片、路径/矢量图、表格、表单、批注、链接、书签、附件、签名和元数据。
8. 为所有元素建立硬联系规则，任何派生文本、chunk、Markdown、HTML 和复核结果都必须能追溯到原始元素、页面和生成规则。

## 4. 非目标

- 不要求在第一阶段一次性实现所有解析器，但设计层不做降级；所有缺失能力必须显式记录为 `unsupported_element` 或 `needs_specialized_parser`，不能静默丢弃。
- 不要求一次性替换 TF-IDF 检索，但检索输入必须来自可追溯的元素图谱。
- 不要求当前 Web UI 立即升级为完整标注平台，但复核记录必须能绑定到 element/block/chunk。
- 不要求隐藏文本一定优先于 OCR；它只是候选文本源，必须通过硬联系和质量规则决定是否采用。

## 5. 硬约束

后续实现不能以“足够好”为理由丢失元素关系。解析产物必须满足以下约束：

1. 每个页面必须有 `page_id`，每个元素必须有稳定 `element_id`。
2. 每个派生对象必须记录来源：OCR 文本要指向图片或页面区域，chunk 要指向 block，block 要指向 element。
3. 每个关系必须写入 `edges.jsonl`，不能只存在于代码内存或字段注释里。
4. 无法解析的对象也要记录为元素，例如 `unsupported_xfa_form`、`unknown_vector_group`、`encrypted_attachment`。
5. 任何合并、去重、替换、降权都不能删除原始候选，只能通过关系边声明主备关系。
6. Markdown、HTML、LLM 输入和人工复核都是派生视图，不能成为事实源。
7. 页面坐标系统必须统一，所有 bbox 记录坐标系、单位和来源。
8. 权限受限 PDF 必须先记录权限状态，不能绕过权限后伪装成普通解析结果。

## 6. 目标目录结构

建议在保持兼容的前提下扩展存储目录：

```text
storage/{doc_id}/
  raw/
    source.pdf
  manifest.json
  pages.jsonl
  elements.jsonl
  edges.jsonl
  blocks.jsonl
  chunks.jsonl
  tables.jsonl
  forms.jsonl
  annotations.jsonl
  attachments.jsonl
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
  elements.jsonl
  edges.jsonl
  blocks.jsonl
  chunks.jsonl
  derived/
    full.md
    review.html
```

这样可以避免一次性破坏现有接口。

## 7. 核心数据模型

### 7.1 manifest.json

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
    "elements": "elements.jsonl",
    "edges": "edges.jsonl",
    "blocks": "blocks.jsonl",
    "chunks": "chunks.jsonl",
    "tables": "tables.jsonl",
    "forms": "forms.jsonl",
    "annotations": "annotations.jsonl",
    "attachments": "attachments.jsonl",
    "markdown": "derived/full.md",
    "review_html": "derived/review.html"
  }
}
```

### 7.2 pages.jsonl

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

### 7.3 elements.jsonl

`elements.jsonl` 是最细粒度事实源。一行一个 PDF 原生元素或派生元素。block、chunk、Markdown 和 HTML 都从 element 图谱派生。

示例：

```json
{
  "element_id": "p0001-e0042",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "page_id": "p0001",
  "page_no": 1,
  "element_type": "text_span",
  "source_type": "visible_text",
  "text": "键 技术条件",
  "bbox": [72, 120, 180, 24],
  "bbox_unit": "px",
  "coordinate_space": "page_image_120dpi",
  "z_order": 12,
  "reading_order": 4,
  "raw_ref": {
    "pdf_object": "12 0 R",
    "xref": 12
  },
  "extractor": {
    "name": "pymupdf",
    "version": "..."
  },
  "quality": {
    "status": "pass",
    "signals": []
  }
}
```

必须覆盖的 `element_type`：

- `page`：页面本身。
- `text_span`：PDF 原生可见文本。
- `hidden_text_span`：不可见或疑似 OCR layer 文本。
- `image_object`：PDF 内嵌图片对象。
- `page_render`：整页渲染图。
- `image_region`：从页面图中裁剪出的区域。
- `ocr_text`：OCR 派生文本。
- `vector_path`：线条、路径、CAD 图元、图形轮廓。
- `table_region`、`table_row`、`table_cell`：表格结构。
- `form_field`：AcroForm/XFA 字段和值。
- `annotation`：批注、高亮、签名外观、注释。
- `link`：内部跳转或外部 URL。
- `outline`：书签/目录项。
- `attachment`：嵌入文件。
- `signature`：数字签名或签章信息。
- `metadata`：标题、作者、创建时间、PDF/A 标记等文档元数据。
- `unsupported_element`：识别到但暂不支持解析的元素。

不同 PDF 类型的最低元素覆盖要求：

| PDF 类型 | 必须识别的元素 | 必须生成的关系 |
| --- | --- | --- |
| `text_pdf` | page、page_render、text_span、image_object、link、metadata | `contains`、`renders_to`、`contributes_to_block` |
| `scan_pdf` | page、page_render、image_region、ocr_text、table_region 候选 | `renders_to`、`ocr_derived_from`、`contributes_to_block` |
| `ocr_pdf` | page_render、hidden_text_span、image_region、ocr_text 对照 | `text_candidate_for`、`equivalent_to` 或 `conflicts_with`、`chosen_over` |
| `mixed_pdf` | 每页按实际元素覆盖 text/image/vector/form/annotation/table | 所有跨来源候选必须有候选、冲突或主备关系 |
| `form_pdf` | form_field、字段外观、字段值文本、page_render | `field_value_of`、`contains`、`review_of` |
| `protected_pdf` | permission 状态、可见元数据、失败或授权状态元素 | `blocked_by_permission` 或授权后的正常关系 |
| `drawing_pdf` | vector_path、text_span 或 ocr_text 标签、page_render、unsupported_element | `contains`、`renders_to`、`needs_specialized_parser` |

### 7.4 edges.jsonl

`edges.jsonl` 保存元素之间的硬联系。一行一条关系边。所有派生、包含、等价、选择、复核关系都必须落盘。

示例：

```json
{
  "edge_id": "edge-p0001-00042",
  "from_id": "p0001-e0042",
  "to_id": "p0001-b0007",
  "edge_type": "contributes_to_block",
  "rule_id": "block_builder.v1.reading_order_merge",
  "evidence": {
    "page_id": "p0001",
    "bbox_overlap": 1.0,
    "text_similarity": 1.0
  },
  "created_by": "parser",
  "confidence": 1.0
}
```

核心关系类型：

| `edge_type` | 含义 |
| --- | --- |
| `contains` | page 包含 element，table 包含 cell，image 包含 text region |
| `renders_to` | PDF page 或 image object 渲染为 page image / block image |
| `cropped_from` | 局部图片区域来自整页渲染图 |
| `ocr_derived_from` | OCR 文本来自页面、图片或区域 |
| `text_candidate_for` | hidden/visible/OCR 文本都是同一视觉区域的候选 |
| `equivalent_to` | 两个候选文本经规则判定为等价 |
| `conflicts_with` | 两个候选文本位置接近但内容冲突 |
| `chosen_over` | 主文本候选优先于备选候选 |
| `contributes_to_block` | element 合并成 block |
| `contributes_to_chunk` | block 或 element 进入 chunk |
| `alternative_for_chunk` | 未采用但与 chunk 相关的备选来源 |
| `caption_of` | 文本是图片或表格标题 |
| `annotates` | 批注指向页面区域或文本 |
| `links_to` | 链接元素指向 URL、页码或目标元素 |
| `field_value_of` | 表单字段值属于表单控件 |
| `review_of` | 人工复核结果指向 element/block/chunk |
| `blocked_by_permission` | 元素或解析阶段受 PDF 权限限制 |
| `needs_specialized_parser` | 已识别元素需要专门解析器继续处理 |

硬联系生成规则：

1. `contains` 必须由 PDF 对象结构、页面归属或 bbox 包含关系生成。
2. `ocr_derived_from` 必须指向具体页面、图片或区域，不能只指向文档。
3. `equivalent_to` 必须同时满足 bbox 重叠阈值和文本相似度阈值，阈值写入 `rule_id` 或 `evidence`。
4. `chosen_over` 只能在质量评估之后生成，并记录选择原因。
5. `conflicts_with` 不允许自动删除任何一方，必须进入复核或低置信队列。
6. `contributes_to_chunk` 必须保证 chunk 可反查到 element，不允许只有裸文本。

### 7.5 blocks.jsonl

内容块派生层。一行一个解析块。block 不是最细事实源，必须能通过 `contributes_to_block` 边反查到一个或多个 element。

```json
{
  "block_id": "p0001-b0007",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "page_id": "p0001",
  "page_no": 1,
  "block_type": "paragraph",
  "source_type": "hidden_text",
  "source_group_id": "p0001-g0003",
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
- `image_ocr`：对整页渲染图或局部图片区域 OCR 得到的文本。
- `form_field`：PDF 表单字段值。
- `annotation`：批注、签名、注释。
- `table_cell`：表格单元格。
- `image`：图片或非文本区域。
- `drawing_element`：图纸、地图、CAD 类矢量线条或区域。

图片相关 block 应区分 `source_type` 和 `block_type`：

- `source_type=image` 表示原始视觉证据，例如照片、截图、扫描图、印章、Logo、图表。
- `source_type=image_ocr` 表示从图片或页面区域 OCR 派生出的文字。
- `block_type=figure|screenshot|stamp|chart|scan_region|text_in_image` 用于描述图片或图片 OCR 的业务形态。

### 7.6 protected_pdf 权限处理

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

### 7.7 chunks.jsonl

给检索和 LLM 使用的派生产物。一行一个 chunk。

```json
{
  "chunk_id": "c0001",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "text": "本标准规定了键的技术条件...",
  "kind": "text",
  "page_range": [1, 1],
  "source_block_ids": ["p0001-b0007", "p0001-b0008"],
  "alternative_block_ids": ["p0001-b0012"],
  "source_types": ["visible_text", "image_ocr"],
  "confidence": 0.86,
  "warnings": [],
  "review_status": "pending"
}
```

### 7.8 图片与图片内文字的父子关系

图片不应简单等同于可检索文本。改造后应先保留原始图片 block，再按需要对图片区域做 OCR，并把 OCR 结果作为子 block 保存。

处理规则：

1. 明确的纯图片，例如照片、Logo、装饰图、无文字示意图，保存为 `source_type=image`，默认不进入文本 chunk。
2. 混合了文字的图片，例如截图、扫描表格、图片格式说明、印章文字，先保存原图片 block，再对图片区域 OCR。
3. OCR 产生的文字保存为 `source_type=image_ocr`，通过 `parent_block_id` 指向原图片 block。
4. 如果图片 OCR 和同区域 `visible_text` 或 `hidden_text` 重复，按 bbox 重叠和文本相似度去重；不能确定时保留两份并加 warning。
5. chunk 默认只引用 `image_ocr`、`visible_text`、`hidden_text`、`form_field` 等文本 block；如果答案需要视觉证据，再附带父图片 block。

原图片 block 示例：

```json
{
  "block_id": "p0002-b0010",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "page_id": "p0002",
  "page_no": 2,
  "block_type": "screenshot",
  "source_type": "image",
  "bbox": [80, 300, 600, 240],
  "reading_order": 10,
  "links": {
    "image_path": "images/blocks/p0002-b0010.png",
    "page_image_path": "images/page-0002.png"
  },
  "quality": {
    "status": "info",
    "signals": ["contains_text_candidate"]
  }
}
```

图片 OCR 子 block 示例：

```json
{
  "block_id": "p0002-b0011",
  "parent_block_id": "p0002-b0010",
  "doc_id": "GBT1568-2008-e724ad081078fa41",
  "page_id": "p0002",
  "page_no": 2,
  "block_type": "text_in_image",
  "source_type": "image_ocr",
  "text": "检验项目 合格质量水平 AQL",
  "bbox": [95, 330, 560, 80],
  "confidence": 0.78,
  "reading_order": 11,
  "quality": {
    "status": "warn",
    "signals": ["derived_from_image", "needs_visual_review"]
  }
}
```

这样做的好处是：原图可以给人工和视觉模型复核，图片文字可以进入 RAG，二者通过 `parent_block_id` 保持可追溯关系。

## 8. 隐藏文本处理策略

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

### 8.1 OCR PDF 隐藏文本关联方式

OCR PDF 的隐藏文本通常来自扫描图上的 OCR layer。它和页面图像、重新 OCR 文本、可见文本之间应通过“页 + 位置 + 等价组 + chunk 引用”四层关系关联。

关联规则：

1. 页级关联：`hidden_text`、`image_ocr`、`visible_text`、页面图像和表格区域都保留相同的 `page_id`、`page_no`。
2. 位置关联：所有文本候选都保留 `bbox`；通过 bbox 重叠判断是否对应同一视觉区域。
3. 等价组关联：同一视觉区域的多个文本候选使用同一个 `source_group_id`，例如隐藏文本和重新 OCR 文本都属于 `p0001-g0003`。
4. 主备关系：质量评估后，chunk 的 `source_block_ids` 只引用最终采用的主文本 block；未采用但相关的候选写入 `alternative_block_ids`。
5. 复核关系：人工或 LLM 复核时同时展示主文本、备选文本和页面 bbox，避免只看到脱离页面的隐藏文本。

隐藏文本 block 示例：

```json
{
  "block_id": "p0001-b0010",
  "page_id": "p0001",
  "page_no": 1,
  "source_type": "hidden_text",
  "source_group_id": "p0001-g0003",
  "text": "本标准规定了键的技术条件",
  "bbox": [80, 120, 500, 40],
  "confidence": 0.72,
  "quality": {
    "status": "warn",
    "signals": ["hidden_ocr_layer", "needs_visual_alignment_check"]
  }
}
```

重新 OCR 对照 block 示例：

```json
{
  "block_id": "p0001-b0011",
  "page_id": "p0001",
  "page_no": 1,
  "source_type": "image_ocr",
  "source_group_id": "p0001-g0003",
  "text": "本标准规定了键的技术条件",
  "bbox": [82, 121, 498, 42],
  "confidence": 0.89,
  "quality": {
    "status": "pass",
    "signals": ["matches_hidden_text"]
  }
}
```

chunk 采用关系示例：

```json
{
  "chunk_id": "c0001",
  "text": "本标准规定了键的技术条件",
  "source_block_ids": ["p0001-b0011"],
  "alternative_block_ids": ["p0001-b0010"],
  "source_group_ids": ["p0001-g0003"],
  "source_types": ["image_ocr"],
  "warnings": ["hidden_text_available_but_not_primary"]
}
```

如果 `hidden_text` 和 `image_ocr` 内容一致且隐藏文本质量更高，可以反过来让 chunk 采用 `hidden_text`，并把 `image_ocr` 放入 `alternative_block_ids`。关键是保留关联和选择原因，而不是丢弃未采用的候选。

## 9. Markdown 与 HTML 派生物

### 9.1 Markdown 给 LLM

Markdown 由元素图谱、blocks 和 chunks 派生，不作为主事实源。

建议格式：

```markdown
<!-- doc_id: GBT1568-2008-e724ad081078fa41 -->
<!-- generated_from: elements.jsonl edges.jsonl blocks.jsonl -->

# 第 1 页

<!-- block_id: p0001-b0007 source_type: image_ocr confidence: 0.86 -->
本标准规定了键的技术条件...

<!-- block_id: p0001-b0012 source_type: table_cell confidence: 0.78 -->
| 检查项目 | AQL |
| --- | --- |
| 尺寸 | 1.5 |
```

LLM prompt 使用 Markdown 时，应同时传入 block_id 或 chunk_id，避免模型回答后无法追溯来源。

### 9.2 HTML 给人工复核

HTML 同样由结构化事实层派生，适合展示：

- 页面图片。
- element/block bbox 覆盖层。
- source_type 颜色标记。
- OCR 置信度。
- hidden_text 与 image_ocr 差异。
- 表格候选区域。
- 人工复核按钮和备注。

HTML 不应作为解析主存储；人工复核结果应写回 `reviews.jsonl` 或现有 `human_reviews.jsonl` 的扩展版本。

## 10. 改造后的处理流程

```text
upload PDF
  -> save source
  -> document probe
  -> page probe
  -> enumerate all native PDF elements into elements.jsonl
  -> extract visible/hidden text elements
  -> detect image blocks and text-in-image candidates
  -> extract vector paths, annotations, forms, links, outlines, attachments, signatures
  -> render page images
  -> OCR pages, image blocks, or regions when needed
  -> table region detection / table extraction
  -> write hard relationship edges into edges.jsonl
  -> normalize selected elements into blocks.jsonl
  -> link equivalent elements/blocks by source_group_id and edges
  -> quality checks and dedup
  -> build chunks.jsonl
  -> derive Markdown for LLM
  -> derive HTML for human review
  -> retrieval / QA / validation
  -> reviews.jsonl
```

相比当前实现，核心变化是把 `process_pdf` 从“直接 OCR 到 pages/chunks”改成“先生成 `elements.jsonl` 和 `edges.jsonl`，再由元素图谱派生 blocks、chunks、Markdown、HTML 和复核视图”。

## 11. 与现有模块的映射

| 现有模块 | 保留方式 | 改造点 |
| --- | --- | --- |
| `pdf_probe.py` | 保留 | 扩展页级 probe、隐藏文本识别、加密/表单/附件/矢量图检测 |
| `parser.py` | 保留调度入口 | 拆成 probe、element extract、edge build、render、ocr、block normalize、derive 多阶段 |
| `ocr.py` | 保留 | OCR 输出先转成 `ocr_text` element，再经 edge 关联到页面、图片或区域 |
| `schemas.py` | 保留旧 schema | 新增 `DocumentManifest`、`PageArtifact`、`ElementArtifact`、`EdgeArtifact`、`BlockArtifact`、`ChunkArtifact` |
| `storage.py` | 保留现有 JSON | 新增 JSONL 读写和元素图谱索引；短期双写，长期迁移 |
| `chunker.py` | 保留 | 输入从 `PageRecognition` 改为 blocks/elements；chunk 记录 source_block_ids 和元素边 |
| `validators.py` | 保留 | 增加 hidden text 质量、element 覆盖率、edge 完整性、文本源冲突检查 |
| `app/main.py` | 保留 API | 新增 artifact 查询接口，旧接口可由新格式适配 |
| Web UI | 保留页面查看 | 增加 element/source_type、bbox、关系边、hidden/OCR 对比复核 |

## 12. 分阶段实施建议

### 阶段 1：建立元素图谱，不改问答行为

- 新增 `manifest.json`、`pages.jsonl`、`elements.jsonl`、`edges.jsonl`、`blocks.jsonl`。
- 当前 OCR 行先转换为 `ocr_text` elements，再通过 `contributes_to_block` 生成兼容 blocks。
- 页面图像、OCR 文本、表格候选区都必须有 element 记录和 edge 记录。
- `chunks.json` 继续保持旧格式，同时新增 `chunks.jsonl`。
- 单元测试覆盖 JSONL 写入、element id、edge id、block id、source_block_ids。

收益：风险低，不影响现有 Web 和评估脚本。

### 阶段 2：接入文本层和隐藏文本识别

- 在 PyMuPDF 中抽取 text dict/rawdict。
- 区分 visible text 和 hidden text。
- 对 text layer 和 OCR 做页级质量比较。
- 对明显可信文本层页面跳过整页 OCR，或只做抽样 OCR 校验。
- 为 hidden/visible/OCR 候选生成 `text_candidate_for`、`equivalent_to`、`conflicts_with`、`chosen_over` 边。

收益：文本型 PDF 更快，OCR PDF 更可控。

### 阶段 3：由元素图谱驱动 block、chunk 和检索

- `build_chunks` 改为读取 blocks/elements/edges。
- chunk 保存 `source_block_ids`、`alternative_block_ids`、`source_group_ids`、`source_types`、`confidence`、`warnings`。
- 每个 chunk 必须有 `contributes_to_chunk` 或 `alternative_for_chunk` 边。
- Markdown 由元素图谱、blocks、chunks 派生。
- 旧 `pages.json` 作为兼容视图生成。

收益：检索证据可追溯到原始 element、block 和 bbox。

### 阶段 4：人工复核升级

- 前端展示 element/block overlay。
- 支持按 element/block/chunk 标记 `pass`、`needs_fix`、`ignore`、`replace_text`。
- 复核结果必须通过 `review_of` edge 绑定到具体对象。
- 复核结果写入 `reviews.jsonl`，并能生成修订后的 `elements.reviewed.jsonl` 和 `blocks.reviewed.jsonl`。

收益：人工复核不只停留在问答结果，而能修正解析事实。

### 阶段 5：表格和复杂版面增强

- 表格候选区域进入 elements、edges 和 blocks。
- 增加 table structure artifact，例如 `tables.jsonl`。
- LLM 验证时显式提示表格风险。
- 对双栏、页眉页脚、水印、印章等做 element/block 级规则。
- 无法恢复单元格结构时，仍必须记录 `table_region`、线条、OCR 文本和 `needs_specialized_parser`，不能只保存普通文本。

收益：处理技术标准、合同、扫描档案时更稳。

## 13. 测试与验收

建议新增测试：

- 文本型 PDF：能产生 `text_span` elements 和 `visible_text` blocks。
- 扫描型 PDF：能产生 `page_render`、`image_region`、`ocr_text` elements 和 `image_ocr` blocks。
- OCR PDF：能产生 `hidden_text_span` elements 和 `hidden_text` blocks，并保留质量 warning。
- 混合 PDF：不同页面策略不同。
- 元素覆盖：每页至少有 page/page_render element，所有 OCR 文本都能追溯到页面或区域。
- 关系完整性：所有 block/chunk 的来源必须能通过 `edges.jsonl` 反查到 element。
- 未支持元素：XFA、附件、签名、复杂矢量图等不能静默丢失，必须生成 `unsupported_element` 或专用 element。
- chunk 追溯：每个 chunk 都有 `source_block_ids`。
- 主备追溯：hidden/OCR/visible 候选必须能通过 `source_group_id` 或 edge 关联。
- Markdown 派生：包含 block_id/source_type 注释。
- HTML 派生：能引用页面图片和 block bbox。
- 兼容性：现有 `.venv/bin/pytest -q` 和 `.venv/bin/python scripts/evaluate.py --sample` 仍能通过。

基础验收命令：

```bash
.venv/bin/pytest -q
.venv/bin/python scripts/evaluate.py --sample
```

## 14. 风险与取舍

- JSONL 比单个 JSON 更适合大文档增量写入，但前端读取需要聚合接口。
- hidden text 的可见性判断在不同 PDF 生成器里可能不稳定，需要保留人工复核入口。
- OCR 与隐藏文本去重不能只靠字符串相似度，还要结合 bbox 和阅读顺序。
- 表格结构恢复复杂，但第一阶段也不能只保存普通文本；至少要保存 table_region、相关线条、OCR 候选和未支持原因。
- 为兼容现有 Demo，短期建议双写旧格式和新格式；等新链路稳定后再迁移旧接口。

## 15. 推荐结论

当前项目已经具备可演示的 OCR + RAG + 人工复核闭环，但解析产物还停留在“页 OCR 结果”和“问答 chunk”层。为了支持多种 PDF 并尽可能识别所有元素，下一步应优先建立 `elements.jsonl` + `edges.jsonl` 元素图谱，再由它派生 `blocks.jsonl`、`chunks.jsonl`、Markdown、HTML 和复核视图。

推荐落地顺序是：

1. 新增 `manifest.json`、`pages.jsonl`、`elements.jsonl`、`edges.jsonl`，先把现有 OCR 结果纳入元素图谱。
2. 增加文本层、隐藏文本、图片、表格、表单、批注、链接、附件、签名、矢量图等元素识别。
3. 用硬联系边表达包含、派生、等价、冲突、主备、chunk 采用和人工复核关系。
4. 让 blocks、chunks、LLM Markdown 和 HTML 全部从元素图谱派生。
5. 升级人工复核界面，让人可以复核 element、block、chunk，而不仅是复核答案。

这样既能保持现有原型可运行，又能为后续 LLM 复核、人工校正、表格增强、复杂版面解析和生产级 PDF 元素追溯打基础。
