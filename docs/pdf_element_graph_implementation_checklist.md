# PDF 元素图谱实现 Checklist

目标：一次性完成不兼容改造，用 `elements.jsonl` + `edges.jsonl` 作为事实源，`blocks.jsonl`、`chunks.jsonl`、Markdown/HTML/API 视图全部从元素图谱派生。测试文件和测试样本统一放在 `docs-for-test/`。

## 1. 范围约束

- [x] 不再写入旧 `meta.json`、`pages.json`、`chunks.json` 作为主输出。
- [x] `load_document()` 只读取新产物并返回新结构。
- [x] 旧 Web/API 如需展示页面识别结果，必须由 `pages.jsonl`、`elements.jsonl`、`edges.jsonl` 派生。
- [x] 所有 OCR 文本必须有 `ocr_derived_from` 边。
- [x] 所有 block 必须有 `contributes_to_block` 边。
- [x] 所有 chunk 必须有 `contributes_to_chunk` 边。
- [x] 无法完整解析的元素必须记录为 `unsupported_element` 或 `needs_specialized_parser`，不能静默丢弃。

## 2. 数据模型

- [x] 新增/调整 `PageArtifact`。
- [x] 新增/调整 `ElementArtifact`。
- [x] 新增/调整 `EdgeArtifact`.
- [x] 新增/调整 `BlockArtifact`。
- [x] 调整 `Chunk`，使用 `source_block_ids`、`alternative_block_ids`、`source_group_ids`、`source_types`。
- [x] `PdfProbeResult` 增加候选类型、权限、表单、图片、矢量图等字段。

## 3. 存储层

- [x] 新增 JSONL 读写函数。
- [x] 新增 `manifest.json` 写入。
- [x] 新增 `pages.jsonl` 写入。
- [x] 新增 `elements.jsonl` 写入。
- [x] 新增 `edges.jsonl` 写入。
- [x] 新增 `blocks.jsonl` 写入。
- [x] 新增 `chunks.jsonl` 写入。
- [x] 新增 `reviews.jsonl` 替代旧 `human_reviews.jsonl`。
- [x] 新增 artifact 完整性校验：edge 两端 ID 必须存在。

## 4. 解析流水线

- [x] 页面渲染生成 `page_render` element。
- [x] 页面归属生成 `contains` edge。
- [x] OCR 行生成 `ocr_text` element。
- [x] OCR 行与页面渲染生成 `ocr_derived_from` edge。
- [x] 表格候选区生成 `table_region` element。
- [x] 表格候选区与页面生成 `contains` edge。
- [x] PDF 文本层生成 `text_span` 或 `hidden_text_span` element。
- [x] PDF 图片对象生成 `image_object` element。
- [x] PDF 矢量路径生成 `vector_path` element 或 `unsupported_element`。
- [x] PDF 链接、批注、表单、附件、签名、元数据尽可能生成对应 element；不支持时生成 unsupported element。

## 5. 硬联系规则

- [x] `contains`：页面包含元素，bbox 包含关系。
- [x] `renders_to`：PDF 页面渲染成页面图。
- [x] `ocr_derived_from`：OCR 文本来自页面图或区域。
- [x] `text_candidate_for`：hidden/visible/OCR 同区域候选。
- [x] `equivalent_to`：bbox 重叠 + 文本相似度达标。
- [x] `conflicts_with`：bbox 重叠但文本冲突。
- [x] `chosen_over`：质量评估后的主备选择。
- [x] `contributes_to_block`：element 合并成 block。
- [x] `contributes_to_chunk`：block 进入 chunk。
- [x] `alternative_for_chunk`：未采用但相关候选。
- [x] `review_of`：人工复核生成 `review` element，并通过 edge 绑定 element/block/chunk。

## 6. 派生产物

- [x] 从 elements/edges 派生 blocks。
- [x] 从 blocks/edges 派生 chunks。
- [x] 从 elements/edges/blocks/chunks 派生页面识别视图。
- [x] 从 chunks 构建检索器。
- [x] 从 elements/edges/blocks/chunks 派生 Markdown。
- [x] 从 elements/edges/blocks/chunks 派生 HTML 或前端识别视图。

## 7. API 与前端

- [x] `/api/upload` 返回 manifest/meta 新结构。
- [x] `/api/docs/{doc_id}` 返回 manifest、pages、elements、edges、blocks、chunks。
- [x] `/api/docs/{doc_id}/pages/{page_no}/recognition` 从新图谱派生 OCR lines/table regions/checks。
- [x] `/api/docs/{doc_id}/ask` 使用新 chunk schema。
- [x] `/api/docs/{doc_id}/reviews` 写入 `reviews.jsonl`，并追加 `review_of` edge。
- [x] 前端证据展示支持 `source_block_ids`、`source_types`。

## 8. docs-for-test

- [x] 创建 `docs-for-test/README.md`。
- [x] 将测试用 PDF 放入 `docs-for-test/`，不再依赖 `data/sample/`。
- [x] 至少包含当前样例 PDF 作为 `docs-for-test/sample_scan.pdf`。
- [x] 后续补充 `ocr_pdf`、`form_pdf` 样本。已补 `text_pdf`、`mixed_pdf`、`protected_pdf`、`drawing_pdf` 样本。

## 9. 测试

- [x] 更新 chunker 单元测试。
- [x] 更新 retriever 单元测试。
- [x] 更新 pdf probe 单元测试，使用 `docs-for-test/`。
- [x] 新增 artifact 生成测试：存在 `manifest.json`、`pages.jsonl`、`elements.jsonl`、`edges.jsonl`、`blocks.jsonl`、`chunks.jsonl`。
- [x] 新增 edge 完整性测试：所有 edge 两端 ID 可解析。
- [x] 新增 OCR 追溯测试：每个 `ocr_text` 都有 `ocr_derived_from`。
- [x] 新增 chunk 追溯测试：每个 chunk 都有 `contributes_to_chunk`。
- [x] 新增 OCR PDF 主备测试：图片 OCR 文本进入主 chunk，同区域未采用候选进入 `alternative_for_chunk`。
- [x] 新增人工复核测试：`reviews.jsonl` 记录必须生成 `review` element 和 `review_of` edge。
- [x] 运行 `.venv/bin/pytest -q`。
- [x] 运行 `.venv/bin/python scripts/evaluate.py --sample`。

## 10. 文档与提交

- [x] 更新 README 的存储结构和处理流程。
- [x] 更新 `docs/architecture.md`。
- [x] 更新 `docs/validation_workflow.md`。
- [x] 必要时更新 `docs/debug_trace.md`。
- [x] 检查 `git status --short`。
- [x] 提交，提交说明中文且不超过 3 行。
