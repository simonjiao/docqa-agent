"""Mini Agent - Minimal single agent with basic tools and MCP support."""

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "LLMClient",
    "LLMProvider",
    "Message",
    "LLMResponse",
    "ToolCall",
    "FunctionCall",
]


def __getattr__(name):
    """Lazy-load optional Mini Agent surfaces.

    The doc QA integration only needs the OpenAI-compatible LLM client and
    schema objects. Importing the full Agent eagerly pulls optional runtime
    dependencies such as tokenizers and MCP clients, so keep package imports
    lightweight until a caller explicitly requests those symbols.
    """
    if name == "Agent":
        from .agent import Agent

        return Agent
    if name == "LLMClient":
        from .llm import LLMClient

        return LLMClient
    if name in {"FunctionCall", "LLMProvider", "LLMResponse", "Message", "ToolCall"}:
        from .schema import FunctionCall, LLMProvider, LLMResponse, Message, ToolCall

        return {
            "FunctionCall": FunctionCall,
            "LLMProvider": LLMProvider,
            "LLMResponse": LLMResponse,
            "Message": Message,
            "ToolCall": ToolCall,
        }[name]
    raise AttributeError(f"module 'mini_agent' has no attribute {name!r}")
