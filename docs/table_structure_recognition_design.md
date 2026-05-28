# 结构化表格识别设计

## 1. 背景

当前系统已经能在页面图像中检测疑似表格区域，并把结果写成 `table_region` element。现有实现的边界是：能定位表格，但不会恢复行、列、合并单元格和单元格文本归属。对问答来说，表格文本仍然会被拉平成普通 block，容易丢失“某一行某一列”的语义关系。

本设计的目标是把表格从“候选区域”升级为可追溯、可复核、可检索的结构化事实。最终验收不能停在 `table_region`，必须产出可用的 row/column/cell 结构，或者明确产出 `failed` / `needs_review` 状态并阻断其作为确定答案。

## 2. 与既有设计的关系

本文是 `docs/pdf_parsing_refactor_design.md` 中“阶段 5：表格和复杂版面增强”的深化设计，不替换既有 PDF 元素图谱设计。

硬约束：

- `elements.jsonl` 和 `edges.jsonl` 仍是事实源；`tables.jsonl`、Markdown、HTML、API 返回值都是派生视图。
- `tables.jsonl` 必须可以从 `elements.jsonl` 和 `edges.jsonl` 重新生成；如果二者不一致，以元素图谱为准并触发 validation failed。
- 继续使用既有 `table_region`、`table_row`、`table_cell` element 类型；本文新增的 `table_line`、`table_column`、`table_structure` 是对既有模型的扩展，不引入第二套事实模型。
- 继续使用既有 `contains`、`cropped_from`、`ocr_derived_from`、`text_candidate_for`、`equivalent_to`、`conflicts_with`、`chosen_over`、`contributes_to_block`、`contributes_to_chunk`、`review_of` 关系；新增表格专用关系只能补足语义，不能绕过这些硬联系。
- block、chunk、问答证据只能从元素图谱派生；不允许由表格解析器直接写入无法反查 source element 的裸文本。
- `table_region` 只是入口，不是成功状态。无法恢复结构时必须落 `needs_specialized_parser`、`needs_review` 或 `failed`，并阻止其被当作结构化表格证据使用。

## 3. 目标

必须覆盖三类表格：

1. 有线表格：存在清晰横线、竖线或边框，例如检测报告、标准表、合同清单。
2. 无线或弱线表格：没有完整边框，但文本按行列视觉对齐，例如报价单、目录式参数表、部分导出的 PDF 表格。
3. 扫描或 OCR 低质量表格：页面是图片或 OCR PDF，文本层不可用、不可信，OCR 可能乱码、漏字或拆行。

目标能力：

- 从 `table_region` 派生 `table_row`、`table_cell` 和结构化行记录。
- 将文本层、隐藏文本层和 OCR 候选分配到具体 cell。
- 对结构可靠性打分，低可靠结果进入人工复核而不是静默进入问答。
- 生成 `kind=table` 的 block/chunk，供检索和问答使用。
- 所有结构化结果都能通过 `edges.jsonl` 反查到 page、table_region、cell、文本候选和原始 bbox。

非目标：

- 不把 LLM 视觉理解作为唯一事实源；LLM 可以做校验或建议修复，但结构事实必须落在可审计 artifact 中。
- 不在无证据时猜测缺失单元格内容。
- 分阶段实施只影响交付顺序，不降低最终验收标准。

## 4. 总体流水线

```text
page_render + text elements + ocr elements
  -> detect_table_regions
  -> normalize_table_region
  -> choose_table_strategy
     -> ruled_grid_parser
     -> borderless_alignment_parser
     -> scanned_ocr_table_parser
  -> assign_text_candidates_to_cells
  -> validate_table_structure
  -> write table elements / edges / tables.jsonl
  -> derive table blocks / table chunks / review view
```

策略选择依据：

- `ruling_line_score` 高：进入有线表格解析。
- 文本元素密集且 x/y 对齐明显：进入无线表格解析。
- 文本层缺失、OCR 置信度低或候选冲突多：进入扫描/OCR 低质量解析。
- 多个策略同时可用时，不做隐式丢弃；必须保留候选结构，按质量分选择 primary，其他写成 alternative，并通过 edge 说明选择原因。

## 5. 数据模型

### 5.1 新增或扩展 element 类型

- `table_region`：现有表格候选区域，继续作为入口。
- `table_line`：检测到的横线、竖线或弱分隔线。
- `table_row`：表格逻辑行。
- `table_column`：表格逻辑列。
- `table_cell`：单元格，包含 row/col 坐标、bbox、span 信息。
- `table_structure`：一次结构化解析结果的根 element，可挂载质量、策略和 warning。

### 5.2 关系边

- `contains`：page 包含 table_structure/table_region，table_structure 包含 row/column/cell，cell 包含文本候选。
- `cropped_from`：table_region 或 cell crop 来自 page_render。
- `ocr_derived_from`：cell OCR 文本来自具体 cell crop。
- `text_candidate_for`：visible/hidden/OCR/cell OCR 是同一 cell 的文本候选。
- `equivalent_to` / `conflicts_with`：候选文本等价或冲突。
- `chosen_over`：某个 cell 文本候选优于其他候选。
- `contributes_to_block`：table_cell 或 table_structure 进入 table block。
- `contributes_to_chunk`：table block 进入 table chunk。
- `review_of`：人工复核结果指向 table_structure/table_cell/table block/table chunk。

可新增表格专用 edge，但必须只作为补充说明：

- `table_boundary_from_line`：cell 边界由 table_line 推导。
- `cell_in_row`：cell 属于逻辑行。
- `cell_in_column`：cell 属于逻辑列。

### 5.3 `tables.jsonl`

必须增加专用派生产物，便于 API 和测试读取：

```json
{
  "table_id": "p0001-t0001",
  "doc_id": "doc",
  "page_no": 1,
  "region_element_id": "p0001-e0277",
  "strategy": "ruled_grid",
  "bbox": [33, 631, 936, 216],
  "row_count": 3,
  "column_count": 5,
  "headers": ["样本名", "评级", "编码", "检测结果", "结果解释"],
  "rows": [
    {
      "row_index": 1,
      "cells": {
        "样本名": "CHP01",
        "评级": "",
        "编码": "0",
        "检测结果": "46,XN,-5(...),+15(...)",
        "结果解释": "异常"
      }
    }
  ],
  "cell_ids": ["p0001-cell0001"],
  "confidence": 0.86,
  "warnings": []
}
```

`tables.jsonl` 是派生视图，事实源仍是 `elements.jsonl` 和 `edges.jsonl`。

## 6. 三类表格处理策略

### 6.1 有线表格

适用场景：

- 表格有完整或大部分横线、竖线。
- 当前检测报告页属于此类。

核心算法：

1. 裁剪 `table_region`，做灰度、去噪、二值化和必要的倾斜校正。
2. 用形态学分别提取水平线和垂直线。
3. 合并接近线段，去掉短线、装饰线、页眉页脚干扰线。
4. 根据横竖线交点生成网格。
5. 允许缺线和合并单元格：如果相邻 cell 边界缺失或文本跨越多个列宽，生成 `row_span` / `col_span`。
6. 把文本候选按 bbox overlap 或中心点归属到 cell。
7. 对多行文本 cell 做行内合并，例如长 CNV 结果不能拆成多个普通 block。

质量信号：

- 横竖线覆盖率。
- 交点完整度。
- 文本分配率。
- 每行列数一致性。
- 表头识别成功率。

失败处理：

- 如果网格残缺但文本对齐明显，继续执行无线表格解析并保留有线解析候选，不把残缺网格当作成功。
- 如果 OCR 文本质量差，继续执行扫描/OCR 低质量解析并标记 `needs_review`。

### 6.2 无线或弱线表格

适用场景：

- 没有完整 ruling lines。
- 文本按 x/y 坐标呈行列排列。
- PDF 文本层可信，或者 OCR bbox 质量尚可。

核心算法：

1. 收集 region 内的 `visible_text`、`hidden_text` 和 `ocr_text` 候选。
2. 按 y 坐标聚类成视觉行，使用字符高度和行距自适应阈值。
3. 按 x 坐标分布、表头位置和列间空白推断列边界。
4. 将每个文本片段分配到最近的 row/column。
5. 对跨列文本使用 overlap 宽度、文本长度和邻近空白判断 `col_span`。
6. 对表头做归一化，生成字段名；如果表头不可靠，保留列号 `col_1`、`col_2`。

质量信号：

- 行聚类稳定性。
- 列边界稳定性。
- 表头覆盖率。
- 每行非空 cell 数分布。
- 文本候选冲突率。

失败处理：

- 如果列边界不稳定，不生成字段名，只生成 cell bbox 和文本列表。
- 如果多种列切分都合理，保留 alternatives，要求人工复核。

### 6.3 扫描或 OCR 低质量表格

适用场景：

- 页面是扫描图。
- OCR 平均置信度低。
- 文本层缺失或 hidden text 与图像 OCR 冲突。
- 表格线清楚但 cell 内 OCR 乱码。

核心算法：

1. 优先用图像结构恢复 cell bbox，不先信任 OCR 文本。
2. 对每个 cell 单独 OCR，而不是整页 OCR 后再切分。
3. 根据 cell 类型选择 OCR 参数：短字段、数字列、中文列、长文本列使用不同 `psm` 或白名单。
4. 多 OCR 候选并存：整页 OCR、cell OCR、文本层候选都保留，通过 bbox 和文本相似度做主备选择。
5. 对低置信 cell 生成 `needs_review`，并在 UI 中支持按 cell 修正。
6. 如果结构可恢复但文本不可恢复，仍写入空 cell、bbox、候选和 warning，避免丢失结构。

质量信号：

- cell OCR 置信度。
- 字符类型是否符合列约束，例如日期、编号、金额、样本名。
- 同一行字段是否满足业务规则。
- hidden text 与 image OCR 是否冲突。

失败处理：

- 不把低置信 OCR 文本直接作为 final cell value。
- 输出 `table_structure` 和 cell bbox，但将表格状态标成 `needs_review`。
- 问答检索默认避开 `needs_review` 的表格值，除非用户显式要求查看未确认候选。

## 7. 文本候选选择

候选来源按优先级和质量共同判断，而不是固定优先级：

- `visible_text`：优先级高，但要检查 bbox 和阅读顺序。
- `hidden_text`：需验证是否可见、是否与图像 OCR 一致。
- `image_ocr`：适合扫描件，但低置信时只能作为候选。
- `cell_ocr`：适合扫描表格，是低质量整页 OCR 的补救。

选择规则：

1. bbox 与 cell overlap 达标才可进入候选。
2. 多候选文本相同或高度相似，选择质量高者为 primary。
3. 候选冲突时保留全部，并生成 `conflicts_with`。
4. primary 候选通过 `chosen_over` 指向被替代候选。
5. 低置信 cell 不生成 final value，只生成候选和 warning。

## 8. Block 与 Chunk 派生

表格应派生两类 block：

- `table_markdown_block`：适合 LLM 和人阅读。
- `table_json_block`：适合检索、问答和程序处理。

chunk 规则：

- `kind=table`。
- `source_block_ids` 指向 table block。
- table block 通过 edge 追溯到 table_structure 和所有参与 cell。
- 如果表格状态是 `needs_review`，chunk warning 必须包含 `table_needs_review`。
- 问答返回证据时显示 table_id、页码、行号、列名和 cell bbox。

示例 Markdown：

```markdown
| 样本名 | 评级 | 编码 | 检测结果 | 结果解释 |
| --- | --- | --- | --- | --- |
| CHP01 |  | 0 | 46,XN,-5(...),+15(...) | 异常 |
| CHP02 |  | 1 | 48,XN,+14(×3),+16(×3) | 异常 |
```

## 9. API 与前端

新增 API：

- `GET /api/docs/{doc_id}/tables`：列出文档表格。
- `GET /api/docs/{doc_id}/pages/{page_no}/tables`：列出页面表格。
- `GET /api/docs/{doc_id}/tables/{table_id}`：返回结构化表格、cell bbox、候选和 warning。

识别页增强：

- 表格区域点击后，不只高亮 bbox，还展示结构化网格。
- cell 可点击，高亮原图位置和候选文本。
- 对 `needs_review` cell 提供人工修正入口。
- 表格证据在问答页按行列展示，而不是只显示拉平文本。

## 10. 质量门禁

建议新增 validator：

- `table_region_coverage`：表格区域是否覆盖足够文本。
- `table_grid_confidence`：网格结构是否可信。
- `table_text_assignment`：文本分配到 cell 的比例。
- `table_header_quality`：表头是否可识别。
- `table_ocr_quality`：cell OCR 平均置信度和低置信 cell 数。
- `table_chunk_traceability`：table chunk 是否能反查到 table/cell/source text。

状态规则：

- `pass`：结构和文本都可信，可进入问答。
- `warn`：结构可信但部分文本低置信，可进入证据展示但提示风险。
- `needs_review`：结构或文本存在关键不确定，不应作为确定答案。
- `failed`：不能形成有意义结构，只保留 table_region 和候选。

## 11. 测试与验收

测试样本应放入 `docs-for-test/`：

- `sample_table_ruled.pdf`：有线表格，含合并单元格和长文本 cell。
- `sample_table_borderless.pdf`：无线表格，依赖文本对齐。
- `sample_table_scanned_low_conf.pdf`：扫描表格，含低置信 OCR 和人工复核场景。
- 当前 `20251229陈海平` 类检测报告可作为真实回归样本，但不建议直接提交私人文档。

核心验收：

- 有线表格能恢复 row/column/cell，当前检测报告“结果信息”表应恢复出 `样本名/评级/编码/检测结果/结果解释`。
- 无线表格能基于文本坐标恢复行列，列边界不稳定时必须给 warning。
- 扫描低质量表格能恢复 cell bbox；低置信文本进入候选和复核，不作为确定值。
- `tables.jsonl`、`elements.jsonl`、`edges.jsonl`、`blocks.jsonl`、`chunks.jsonl` 追溯一致。
- `.venv/bin/pytest -q` 和 `.venv/bin/python scripts/evaluate.py --sample` 继续通过。

## 12. 分阶段实施

### 阶段 1：有线表格结构化

- 新增 `table_parser.py`。
- 从现有 `table_region` 生成 grid、row、column、cell。
- 把文本层 block 分配到 cell。
- 写入 `tables.jsonl` 和相关 elements/edges。
- 先覆盖当前检测报告类表格。
- 验收不允许只输出 `table_region`；必须输出至少一个 `table_structure` 和若干 `table_cell`，否则状态为 `failed`。

### 阶段 2：表格 block/chunk 和 API

- 派生 table markdown/json block。
- 检索结果支持 `kind=table`。
- 前端展示 table evidence 和 cell bbox。
- 增加 table validators。

### 阶段 3：无线表格

- 基于文本 bbox 聚类行列。
- 支持弱线、无边框和列间空白推断。
- 对不稳定列切分写 alternatives 和 warning。

### 阶段 4：扫描/OCR 低质量表格

- 增加 cell-level OCR。
- 增加候选选择和冲突关系。
- 前端支持按 cell 人工复核。

### 阶段 5：复核闭环和回归集

- 人工修正写入 review element。
- 修正后的 table block/chunk 可再派生。
- 建立三类表格 golden set，覆盖结构、文本、追溯和问答。

## 13. 风险与硬约束

- 表格结构恢复比普通 OCR 更依赖 bbox 质量，必须保留人工复核路径。
- 无线表格容易过拟合坐标阈值，应以 warning 和 alternatives 降低误用风险。
- 扫描表格的文本质量不能靠一次整页 OCR 解决，cell OCR 和候选保留是必要成本。
- 结构化表格进入问答前必须通过质量门禁，否则会把“看起来像表格”的错误结构放大成错误答案。
