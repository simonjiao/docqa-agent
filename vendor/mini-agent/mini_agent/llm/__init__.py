"""LLM clients package supporting both Anthropic and OpenAI protocols."""

__all__ = ["LLMClientBase", "AnthropicClient", "OpenAIClient", "LLMClient"]


def __getattr__(name):
    """Lazy-load provider clients so optional provider SDKs stay optional."""
    if name == "LLMClientBase":
        from .base import LLMClientBase

        return LLMClientBase
    if name == "AnthropicClient":
        from .anthropic_client import AnthropicClient

        return AnthropicClient
    if name == "OpenAIClient":
        from .openai_client import OpenAIClient

        return OpenAIClient
    if name == "LLMClient":
        from .llm_wrapper import LLMClient

        return LLMClient
    raise AttributeError(f"module 'mini_agent.llm' has no attribute {name!r}")
