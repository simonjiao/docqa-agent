from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Protocol, Set
import asyncio
import inspect
import os
import re
import shlex
import sys

from .validators import answer_self_checks
from .retrieval import normalize_for_retrieval

MIN_EVIDENCE_SCORE = 0.055

STOP_TERMS = {
    "本标", "标准", "规定", "什么", "多少", "是否", "该标", "要求", "哪些", "有关", "回答", "内容", "进行", "应有",
}


class LLMConfigurationError(RuntimeError):
    """Raised when QA is called without required LLM configuration."""


class LLMGroundingError(RuntimeError):
    """Raised when the LLM does not respect the evidence-only answer policy."""


class QACompletionClient(Protocol):
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return a final answer organized by an LLM."""


class MiniAgentOpenAICompletionClient:
    """OpenAI-compatible completion client backed by vendored mini-agent."""

    def __init__(self, *, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self._client: Any = None
        self._message_cls: Any = None

    @classmethod
    def from_env(cls) -> "MiniAgentOpenAICompletionClient":
        _load_local_env_if_needed()
        api_key = os.getenv("DOCQA_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("DOCQA_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        model = os.getenv("DOCQA_LLM_MODEL") or os.getenv("OPENAI_MODEL")
        missing = []
        if not api_key:
            missing.append("DOCQA_LLM_API_KEY 或 OPENAI_API_KEY")
        if not api_base:
            missing.append("DOCQA_LLM_BASE_URL 或 OPENAI_BASE_URL")
        if not model:
            missing.append("DOCQA_LLM_MODEL 或 OPENAI_MODEL")
        if missing:
            raise LLMConfigurationError("QA 必须配置 LLM，缺少：" + "；".join(missing))
        return cls(api_key=api_key, api_base=api_base, model=model)

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self._ensure_client()
        response = await self._client.generate(
            messages=[
                self._message_cls(role="system", content=system_prompt),
                self._message_cls(role="user", content=user_prompt),
            ],
            tools=None,
        )
        return (response.content or "").strip()

    async def aclose(self) -> None:
        if self._client is None:
            return
        raw_client = getattr(self._client, "client", None)
        close = getattr(raw_client, "close", None)
        if close is None:
            close = getattr(raw_client, "aclose", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        _ensure_mini_agent_path()
        try:
            from mini_agent.llm.openai_client import OpenAIClient
            from mini_agent.schema import Message
        except ModuleNotFoundError as exc:
            if exc.name == "openai":
                raise LLMConfigurationError("QA 已配置 LLM，但缺少 openai 依赖；请安装 requirements.txt。") from exc
            raise
        self._client = OpenAIClient(api_key=self.api_key, api_base=self.api_base, model=self.model)
        self._message_cls = Message


def _ensure_mini_agent_path() -> None:
    project_root = Path(__file__).resolve().parents[2]
    vendor_path = project_root / "vendor" / "mini-agent"
    if not vendor_path.exists():
        raise LLMConfigurationError(f"未找到 vendored mini-agent：{vendor_path}")
    path_text = str(vendor_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _load_local_env_if_needed() -> None:
    if os.getenv("DOCQA_DISABLE_DOTENV") == "1":
        return
    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        try:
            token = shlex.split(stripped, comments=True, posix=True)[0]
        except (ValueError, IndexError):
            continue
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def _salient_terms(question: str) -> Set[str]:
    normalized = normalize_for_retrieval(question)
    # Remove generic question scaffolding so that no-answer checks focus on
    # business terms instead of common words such as "标准" and "规定".
    for phrase in [
        "该标准", "本标准", "是否", "是不是", "有没有", "规定了", "规定",
        "要求", "是多少", "是什么", "有哪些", "哪些", "什么", "多少",
        "表1中", "表一中", "和哪些", "有关", "应有", "应该", "可以", "以及", "或者", "或",
    ]:
        normalized = normalized.replace(phrase, "")
    terms: Set[str] = set()
    for m in re.finditer(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", normalized):
        token = m.group(0)
        if re.fullmatch(r"[a-zA-Z0-9]+", token):
            if len(token) >= 2:
                terms.add(token.lower())
            continue
        if len(token) == 1:
            terms.add(token)
        else:
            for n in (2, 3, 4):
                for i in range(0, max(0, len(token) - n + 1)):
                    terms.add(token[i:i+n])
    return {t for t in terms if t not in STOP_TERMS}


def _is_out_of_scope(question: str, evidence: List[Dict]) -> bool:
    if not evidence:
        return True
    terms = _salient_terms(question)
    if not terms:
        return False
    evidence_text = normalize_for_retrieval("\n".join(item.get("text", "") for item in evidence))
    # Require at least one salient term. For very specific questions, this blocks
    # generic hits caused by words such as "标准" or "规定".
    return not any(term in evidence_text for term in terms)


def _format_evidence(evidence: List[Dict]) -> str:
    if not evidence:
        return "（无可用证据）"
    lines = []
    for idx, item in enumerate(evidence, start=1):
        text = re.sub(r"\s+", " ", item.get("text", "")).strip()
        if len(text) > 900:
            text = text[:900] + "..."
        source = f"第{item.get('page', '?')}页"
        lines.append(f"[{idx}] {source}\n{text}")
    return "\n\n".join(lines)


def _system_prompt() -> str:
    return (
        "你是文档问答助手。必须以提供的检索证据为唯一事实来源，不得使用外部知识、常识补全或猜测。"
        "问答上下文已经限定在当前打开或当前上传的单个文档内；如果用户省略主语或使用“这个、该、它”等指代，默认指当前文档或当前标准。"
        "如果证据不足以回答问题，必须明确拒答并说明需要补充资料或人工复核。"
        "回答应使用中文，必要时引用页码；不要暴露检索分数、chunk id 或内部实现细节。"
    )


def _user_prompt(question: str, evidence: List[Dict], *, insufficient: bool) -> str:
    policy = "证据不足，必须拒答。" if insufficient else "证据初步可用，但仍需只根据证据回答。"
    return f"""问题：
{question}

证据策略：
{policy}

检索证据：
{_format_evidence(evidence)}

输出要求：
1. 只依据上述证据组织答复。
2. 如果证据不能直接支持答案，回答必须包含“没有找到足够依据”或“证据不足”。
3. 不要因为问题省略“当前文件、当前标准、当前文档”而要求用户澄清；除非证据本身不能支持答案。
4. 如果可以回答，给出简洁结论，并在句中标明来源页码。
5. 不要编造证据中没有出现的事实。"""


def _mark_llm_check_configured(checks: List[Dict], *, model: str) -> List[Dict]:
    updated = []
    for check in checks:
        if check.get("name") == "llm_judge":
            updated.append({
                **check,
                "status": "pass",
                "detail": f"已通过 mini-agent OpenAI-compatible LLM 组织答复；model={model}；事实来源限制为检索证据。",
            })
        else:
            updated.append(check)
    return updated


def _is_refusal_answer(answer: str) -> bool:
    return any(marker in answer for marker in ["没有找到足够依据", "证据不足", "无法根据现有证据", "不能根据现有证据"])


async def build_answer_async(
    question: str,
    evidence: List[Dict],
    *,
    llm_client: QACompletionClient | None = None,
) -> Dict:
    """Build a fact-grounded answer; LLM configuration is mandatory."""
    owns_client = llm_client is None
    client = llm_client or MiniAgentOpenAICompletionClient.from_env()
    try:
        best_score = max([item.get("score", 0.0) for item in evidence] or [0.0])
        out_of_scope = _is_out_of_scope(question, evidence)
        insufficient = not evidence or best_score < MIN_EVIDENCE_SCORE or out_of_scope
        selected = evidence[:4]
        answer = await client.complete(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(question, selected, insufficient=insufficient),
        )
        if insufficient and not _is_refusal_answer(answer):
            raise LLMGroundingError("LLM 输出未遵守证据不足拒答要求。")

        checks = answer_self_checks(question, answer, evidence, min_score=MIN_EVIDENCE_SCORE)
        checks = _mark_llm_check_configured(checks, model=getattr(client, "model", "custom"))
        if out_of_scope:
            checks.insert(1, {
                "stage": "answer_policy",
                "name": "specific_term_guard",
                "status": "pass",
                "detail": "问题中的关键业务词未被证据覆盖，已要求 LLM 基于证据不足拒答。",
            })
        return {
            "answer": answer,
            "evidence": evidence,
            "checks": checks,
            "mode": "llm_grounded_refusal" if insufficient else "llm_grounded",
        }
    finally:
        close = getattr(client, "aclose", None)
        if owns_client and close is not None:
            await close()


def build_answer(
    question: str,
    evidence: List[Dict],
    *,
    llm_client: QACompletionClient | None = None,
) -> Dict:
    """Synchronous wrapper for scripts/tests; async routes should await build_answer_async."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(build_answer_async(question, evidence, llm_client=llm_client))
    raise RuntimeError("build_answer() cannot run inside an active event loop; use build_answer_async().")
