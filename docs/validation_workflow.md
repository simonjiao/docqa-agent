# 验证流程说明

## 1. 文档识别本身的验证

识别阶段不只输出文本，还输出质量信号：

- OCR 平均置信度：低于阈值时提示人工复核。
- 文本密度：扫描页如果识别文本过短，说明 OCR 可能失败。
- 表格区域检测：如果页面包含明显表格线，应能检测到候选区域。
- 来源定位：每一行 OCR 文本保留 page、line_id、bbox，支持在 Web 页面回看原图。

## 2. 检索验证

检索阶段输出 top-k 证据和分数：

- 分数低于阈值：进入无答案保护。
- 证据来自多个页面：前端显示每个 chunk 的页码和片段。
- 表格问题：如果证据来自表格候选页，标记为 table 类型或提示人工确认。

## 3. 答案验证

答案阶段执行基础自检：

- evidence_score：最高检索分是否达到阈值。
- answer_evidence_overlap：答案字符是否主要来自证据。
- no_answer_guard：证据不足时是否拒答。
- llm_judge：默认未配置，但保留阶段用于接入大模型判断。
- human_review：人工复核状态，默认 pending。

## 4. LLM 验证的接入方案

当前原型默认不依赖外部 API。实际项目中建议 LLM 验证 prompt 只做裁判，不重新发挥：

输入：问题、答案、证据片段、页码、OCR 置信度、是否表格问题。

输出 JSON：

```json
{
  "supported": true,
  "needs_refusal": false,
  "missing_evidence": false,
  "table_risk": "low|medium|high",
  "reason": "..."
}
```

规则：

- LLM 不能补充证据中不存在的事实。
- LLM 判断为 unsupported 时，答案不能直接返回给用户。
- 表格风险高时必须进入人工复核或表格专用解析。

## 5. 人工验证

前端提供三类人工结果：

- pass：答案可以进入交付记录。
- needs_fix：需要重新 OCR、补充表格解析或调整检索。
- uncertain：证据不足，需要业务专家确认。

所有记录写入 `human_reviews.jsonl`，便于审计和复盘。
