# 结构化表格识别实现 Checklist

目标：完成 `docs/table_structure_recognition_design.md` 的实现，不把 `table_region` 当作成功状态，不引入与元素图谱冲突的事实源，并用自动化测试覆盖三类复杂表格。

## 1. 设计一致性

- [x] `elements.jsonl` 和 `edges.jsonl` 仍是事实源。
- [x] `tables.jsonl` 只作为可重新派生的视图写入 manifest 和 storage。
- [x] 表格解析不直接写入无法反查 source element 的裸文本 block/chunk。
- [x] `table_region` 只是入口；成功状态必须包含 `table_structure` 和 `table_cell`。
- [x] 失败或低可信结构必须标记 `failed` / `needs_review`，不能作为确定答案。

## 2. 元素与关系

- [x] 生成或保留 `table_region`。
- [x] 生成 `table_structure`。
- [x] 生成 `table_row`、`table_column`、`table_cell`。
- [x] 有线表格生成 `table_line`。
- [x] cell-level OCR 结果生成 `ocr_text`，source_type 为 `cell_ocr`。
- [x] 写入 `contains`、`cropped_from`、`ocr_derived_from`、`text_candidate_for`、`chosen_over`、`contributes_to_block`、`contributes_to_chunk`、`review_of` 可兼容关系。
- [x] 表格专用关系只补充语义，不替代既有硬联系。

## 3. 三类解析策略

- [x] 有线表格：从 ruling lines 恢复 grid、row、column、cell。
- [x] 有线表格：多行长文本 cell 归并到同一 cell。
- [x] 无线或弱线表格：从文本 bbox 聚类行列并生成结构。
- [x] 无线或弱线表格：列边界不稳定时给出 warning。
- [x] 扫描或 OCR 低质量表格：先恢复 cell bbox，再做 cell-level OCR。
- [x] 扫描或 OCR 低质量表格：低置信文本进入候选和复核，不作为确定答案。

## 4. 派生产物和 API

- [x] `tables.jsonl` 包含 table_id、region_element_id、strategy、headers、rows、cell_ids、confidence、warnings。
- [x] 生成 `table_markdown_block`。
- [x] 生成 `table_json_block`。
- [x] table block 进入 `kind=table` chunk。
- [x] table chunk warning 反映 `needs_review`。
- [x] 新增 `/api/docs/{doc_id}/tables`。
- [x] 新增 `/api/docs/{doc_id}/pages/{page_no}/tables`。
- [x] 新增 `/api/docs/{doc_id}/tables/{table_id}`。
- [x] 页面识别接口返回结构化表格摘要。

## 5. 验证与测试

- [x] 增加有线表格测试。
- [x] 增加无线或弱线表格测试。
- [x] 增加扫描或 OCR 低质量表格测试。
- [x] 增加 edge 完整性和 table chunk 追溯测试。
- [x] `git diff --check` 通过。
- [x] `.venv/bin/pytest -q` 通过。
- [x] `.venv/bin/python scripts/evaluate.py --sample` 通过。

## 6. 文档与提交

- [x] 更新 `docs/debug_trace.md`。
- [x] 提交说明使用中文，且不超过 3 行。

## 验证证据

- `STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q tests/test_table_structure.py` -> `3 passed, 5 warnings`
- `STORAGE_DIR=$(mktemp -d) .venv/bin/pytest -q` -> `19 passed, 5 warnings`
- `STORAGE_DIR=$(mktemp -d) .venv/bin/python scripts/evaluate.py --sample` -> completed with all sample cases returning validation checks
