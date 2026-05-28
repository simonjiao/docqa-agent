# 验证流程说明

## 1. 文档识别本身的验证

识别阶段不只输出文本，还输出质量信号：

- OCR 平均置信度：低于阈值时提示人工复核。
- 文本密度：扫描页如果识别文本过短，说明 OCR 可能失败。
- 表格区域检测：如果页面包含明显表格线，应能检测到候选区域。
- 来源定位：每一行 OCR 文本保存为 `ocr_text` element，保留 page、element_id、bbox，并通过 `ocr_derived_from` edge 指向页面图。
- 关系完整性：block/chunk 必须通过 `contributes_to_block`、`contributes_to_chunk` edge 反查到原始 element。
- 主备完整性：OCR PDF 中同区域文本层和 OCR 文本必须通过候选/等价/冲突/选择边关联，未采用候选通过 `alternative_for_chunk` 反查到 chunk。

## 2. 检索验证

检索阶段输出 top-k 证据和分数：

- 分数低于阈值：进入无答案保护。
- 证据来自多个页面：前端显示每个 chunk 的页码和片段。
- 证据保留 `source_block_ids`、`source_types`，支持继续追溯到 `elements.jsonl` 和 `edges.jsonl`。
- 表格问题：如果证据来自表格候选页，标记为 table 类型或提示人工确认。

## 3. 答案验证

答案阶段执行基础自检：

- evidence_score：最高检索分是否达到阈值。
- answer_evidence_overlap：答案字符是否主要来自证据。
- no_answer_guard：证据不足时是否拒答。
- llm_judge：QA 必须配置 LLM；该检查记录 mini-agent LLM 是否已按检索证据组织答复。
- human_review：人工复核状态，默认 pending。

## 4. LLM 事实约束方案

当前 QA 不提供抽取式回退。`/ask` 必须配置 OpenAI-compatible LLM，并通过 `vendor/mini-agent` 组织最终答复；检索证据是唯一事实来源。

必须配置以下环境变量，或使用同名 `OPENAI_*` 变量：

```bash
export DOCQA_LLM_BASE_URL=http://127.0.0.1:8080/v1
export DOCQA_LLM_API_KEY=your-api-key
export DOCQA_LLM_MODEL=your-model
```

规则：

- LLM 不能补充证据中不存在的事实。
- 检索分低或关键业务词没有被证据覆盖时，仍调用 LLM，但 Prompt 明确要求“证据不足”拒答。
- 如果证据不足场景下 LLM 没有拒答，后端返回事实约束失败，不生成回退答案。
- 表格风险高时必须进入人工复核或表格专用解析。

## 5. 人工验证

前端提供三类人工结果：

- pass：答案可以进入交付记录。
- needs_fix：需要重新 OCR、补充表格解析或调整检索。
- uncertain：证据不足，需要业务专家确认。

所有记录写入 `reviews.jsonl`，同时生成 `review` element，并用 `review_of` edge 指向被复核的 block/chunk，便于审计和复盘。
