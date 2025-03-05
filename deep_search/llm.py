from typing import List, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_ollama import ChatOllama
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from .configuration import Configuration, LLMProvider
from .env import get_env_or_raise

def get_llm(config: Configuration, temperature: float = 0, format: Optional[str] = None):
    """Factory function to create LLM instances based on configuration."""
    
    # 处理配置中的 llm_provider，可能是字符串或枚举
    if isinstance(config.llm_provider, str):
        provider = config.llm_provider
    else:
        provider = config.llm_provider.value
    
    if provider == "ollama":
        return ChatOllama(
            model=config.local_llm,
            temperature=temperature,
            format=format
        )
    elif provider == "deepseek":
        return ChatDeepSeek(
            api_key=get_env_or_raise("DEEPSEEK_API_KEY"),
            model="deepseek-chat",
            temperature=temperature
        )
    elif provider == "gpt":
        return ChatOpenAI(
            api_key=get_env_or_raise("OPENAI_API_KEY"),
            model="gpt-4o-mini",
            temperature=temperature
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}") 