from __future__ import annotations
from typing import Any, Dict, List
import asyncio
import inspect
import re

from .qa import MiniAgentOpenAICompletionClient, QACompletionClient


def _system_prompt() -> str:
    return (
        "你是文档 OCR 校订助手。只能处理用户提供的当前页识别文本，不得使用外部知识补全内容。"
        "你的任务是识别疑似错别字或 OCR 错误，并把当前页内容整理为更清晰的段落和列表。"
        "数字、公式、标准号、单位、日期、化学式和专有名词必须保守处理；没有把握时列为不确定项。"
    )


def _user_prompt(page_no: int, page_text: str) -> str:
    return f"""当前页：第 {page_no} 页

识别文本：
{page_text}

输出格式：
## 疑似错别字/OCR错误
- 原文片段 -> 建议修正：依据或不确定性说明

## 整理后的段落和列表
按原文顺序整理段落、标题和列表；只修正有证据支持的明显 OCR 错误。

## 不确定项
- 无法确认的文字、符号、公式或标点。

要求：
1. 不要新增原文没有的信息。
2. 不要删除数字、公式、标准号、单位、日期、化学式或特殊符号。
3. 如果没有发现明显错别字，明确写“未发现明显错别字/OCR错误”。"""


def page_text_from_lines(lines: List[Dict[str, Any]]) -> str:
    parts = []
    for line in lines:
        text = re.sub(r"\s+", " ", str(line.get("text") or "")).strip()
        if not text:
            continue
        line_id = str(line.get("id") or line.get("element_id") or "").strip()
        parts.append(f"[{line_id}] {text}" if line_id else text)
    return "\n".join(parts)


async def polish_page_text_async(
    *,
    page_no: int,
    lines: List[Dict[str, Any]],
    llm_client: QACompletionClient | None = None,
) -> Dict[str, Any]:
    page_text = page_text_from_lines(lines)
    if not page_text:
        return {
            "page": page_no,
            "output": "当前页没有可整理的识别文本。",
            "source_line_ids": [],
            "model": None,
        }

    owns_client = llm_client is None
    client = llm_client or MiniAgentOpenAICompletionClient.from_env()
    try:
        output = await client.complete(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(page_no, page_text),
        )
        return {
            "page": page_no,
            "output": output,
            "source_line_ids": [
                str(line.get("id") or line.get("element_id"))
                for line in lines
                if line.get("id") or line.get("element_id")
            ],
            "model": getattr(client, "model", "custom"),
        }
    finally:
        close = getattr(client, "aclose", None)
        if owns_client and close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


def polish_page_text(
    *,
    page_no: int,
    lines: List[Dict[str, Any]],
    llm_client: QACompletionClient | None = None,
) -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(polish_page_text_async(page_no=page_no, lines=lines, llm_client=llm_client))
    raise RuntimeError("polish_page_text() cannot run inside an active event loop; use polish_page_text_async().")
