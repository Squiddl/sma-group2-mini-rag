import logging
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from .settings import settings

logger = logging.getLogger(__name__)


def create_llm(streaming: bool = False, max_tokens: int = None, temperature: float = None, **kwargs):
    provider = settings.get_active_provider()
    temp = temperature or settings.llm_temperature
    max_tok = max_tokens or settings.llm_max_tokens
    timeout = kwargs.pop("timeout", settings.llm_timeout)

    logger.info("=" * 80)
    logger.info("🤖 LLM Factory - Creating LLM Instance")
    logger.info("=" * 80)
    logger.info(f"   • Provider: {provider}")
    logger.info(f"   • Model: {settings.llm_model}")
    logger.info(f"   • Streaming: {streaming}")
    logger.info(f"   • Temperature: {temp}")
    logger.info(f"   • Max Tokens: {max_tok}")
    logger.info(f"   • Timeout: {timeout}s")

    try:
        if provider == "anthropic":
            logger.info(
                f"   • API Key: {'***' + settings.anthropic_api_key[-4:] if settings.anthropic_api_key else 'NOT SET'}")

            llm = ChatAnthropic(
                model=settings.llm_model,
                anthropic_api_key=settings.anthropic_api_key,
                temperature=temp,
                max_tokens=max_tok,
                streaming=streaming,
                timeout=timeout,
                **kwargs
            )
            logger.info(f"✅ ChatAnthropic instance created successfully")

        elif provider == "openai":
            logger.info(
                f"   • API Key: {'***' + settings.openai_api_key[-4:] if settings.openai_api_key else 'NOT SET'}")

            llm = ChatOpenAI(
                model=settings.llm_model,
                openai_api_key=settings.openai_api_key,
                temperature=temp,
                max_tokens=max_tok,
                streaming=streaming,
                timeout=timeout,
                **kwargs
            )
            logger.info(f"✅ ChatOpenAI instance created successfully")

        else:  # ollama
            logger.info(f"   • Base URL: {settings.ollama_base_url}")
            logger.info(
                f"   • Target: http://{settings.ollama_base_url.replace('http://', '').replace('https://', '')}/api/chat")

            if kwargs:
                logger.info(f"   • Additional kwargs: {kwargs}")

            llm = ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=temp,
                num_predict=max_tok,
                **kwargs
            )
            logger.info(f"✅ ChatOllama instance created successfully")
            logger.info(f"   → Will request model '{settings.llm_model}' from Ollama")
            logger.info(f"   → Ensure model is downloaded: docker exec rag-ollama ollama list")

        logger.info("=" * 80)
        return llm

    except Exception as exc:
        logger.error("=" * 80)
        logger.error(f"❌ LLM Factory - Failed to create LLM instance")
        logger.error(f"   • Provider: {provider}")
        logger.error(f"   • Model: {settings.llm_model}")
        logger.error(f"   • Error: {type(exc).__name__}: {exc}")
        logger.error("=" * 80)
        raise