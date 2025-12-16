from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]
from.services.settings import settings

def create_llm(
    streaming: bool = False,
    max_tokens: int = None,
    temperature: float = None,
    **extra_kwargs
) -> ChatAnthropic:
    """
    Create a Claude LLM instance with optimized settings.

    Args:
        streaming: Enable streaming responses
        max_tokens: Maximum tokens (defaults to settings)
        temperature: Temperature (defaults to settings)
        **extra_kwargs: Additional arguments for ChatAnthropic

    Returns:
        Configured ChatAnthropic instance
    """
    return ChatAnthropic(
        model=settings.llm_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=temperature or settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
        streaming=streaming,
        timeout=settings.llm_timeout,
        **extra_kwargs
    )