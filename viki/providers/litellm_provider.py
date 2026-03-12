from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .._log import structlog

from ..config import settings
from .base import LLMProvider

logger = structlog.get_logger()


@dataclass(frozen=True)
class Backend:
    name: str
    env_var: str
    candidates: List[str]


KNOWN_BACKENDS: List[Backend] = [
    Backend("dashscope", "DASHSCOPE_API_KEY", [
        os.getenv("VIKI_REASONING_MODEL") or "openai/qwen3.5-plus",
        os.getenv("VIKI_CODING_MODEL") or "openai/qwen3-coder-next",
        os.getenv("VIKI_FAST_MODEL") or "openai/qwen3.5-plus",
    ]),
    Backend("openrouter", "OPENROUTER_API_KEY", [
        os.getenv("VIKI_REASONING_MODEL") or "openrouter/openai/gpt-4o",
        os.getenv("VIKI_CODING_MODEL") or "openrouter/deepseek/deepseek-chat",
        os.getenv("VIKI_FAST_MODEL") or "openrouter/anthropic/claude-3-haiku",
    ]),
    Backend("openai", "OPENAI_API_KEY", ["gpt-4o", "gpt-4o-mini"]),
    Backend("anthropic", "ANTHROPIC_API_KEY", ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"]),
    Backend("google", "GOOGLE_API_KEY", ["gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro"]),
    Backend("deepseek", "DEEPSEEK_API_KEY", ["deepseek/deepseek-chat"]),
    Backend("groq", "GROQ_API_KEY", ["groq/llama-3.3-70b-versatile"]),
    Backend("mistral", "MISTRAL_API_KEY", ["mistral/mistral-large-latest"]),
    Backend("together", "TOGETHERAI_API_KEY", ["together_ai/meta-llama/Llama-3.1-70B-Instruct-Turbo"]),
    Backend("fireworks", "FIREWORKS_API_KEY", ["fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct"]),
    Backend("xai", "XAI_API_KEY", ["xai/grok-beta"]),
    Backend("cerebras", "CEREBRAS_API_KEY", ["cerebras/llama3.1-70b"]),
    Backend("sambanova", "SAMBANOVA_API_KEY", ["sambanova/Meta-Llama-3.1-70B-Instruct"]),
]


class LiteLLMProvider(LLMProvider):
    """Multi-provider router backed by LiteLLM."""

    def __init__(self) -> None:
        self._litellm = None
        self._available = False
        try:
            import litellm

            self._litellm = litellm
            self._litellm.set_verbose = False
            self._available = True
        except Exception as exc:
            logger.warning(f"litellm unavailable: {exc}")

    def validate_config(self) -> bool:
        if not self._available:
            return False
        if any(os.getenv(b.env_var) for b in KNOWN_BACKENDS):
            return True
        if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
            return True
        if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_API_BASE"):
            return True
        if os.getenv("OLLAMA_BASE_URL"):
            return True
        return False

    def available_backends(self) -> List[str]:
        active = [b.name for b in KNOWN_BACKENDS if os.getenv(b.env_var)]
        if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
            active.append("openai-compatible")
        if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_API_BASE"):
            active.append("azure-openai")
        if os.getenv("OLLAMA_BASE_URL"):
            active.append("ollama")
        return active

    def get_available_models(self) -> List[str]:
        models: List[str] = []
        for backend in KNOWN_BACKENDS:
            if os.getenv(backend.env_var):
                models.extend(backend.candidates)
        if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
            models.append(os.getenv("OPENAI_COMPAT_MODEL", "openai/gpt-4o-mini"))
        if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_API_BASE"):
            models.append(os.getenv("AZURE_MODEL", "azure/gpt-4o"))
        if os.getenv("OLLAMA_BASE_URL"):
            models.append(os.getenv("OLLAMA_MODEL", settings.local_model))
        return list(dict.fromkeys(m for m in models if m))

    def _resolve_candidates(self, model: Optional[str]) -> List[str]:
        if model and model not in {"reasoning", "coding", "fast"}:
            return [model]

        requested = model or "coding"
        env_override = {
            "reasoning": os.getenv("VIKI_REASONING_MODEL"),
            "coding": os.getenv("VIKI_CODING_MODEL"),
            "fast": os.getenv("VIKI_FAST_MODEL"),
        }.get(requested)
        candidates: List[str] = []
        if env_override:
            candidates.append(env_override)

        for backend in KNOWN_BACKENDS:
            if os.getenv(backend.env_var):
                idx = 0 if requested == "reasoning" else 1 if requested == "coding" else 2
                if idx < len(backend.candidates):
                    candidates.append(backend.candidates[idx])

        if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
            candidates.append(os.getenv("OPENAI_COMPAT_MODEL", "openai/gpt-4o-mini"))
        if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_API_BASE"):
            candidates.append(os.getenv("AZURE_MODEL", "azure/gpt-4o"))
        if os.getenv("OLLAMA_BASE_URL"):
            candidates.append(os.getenv("OLLAMA_MODEL", settings.local_model))

        if not candidates:
            candidates.extend([settings.reasoning_model, settings.coding_model, settings.quick_model])
        return list(dict.fromkeys(c for c in candidates if c))

    def _candidate_kwargs(self, candidate: str) -> Dict[str, Any]:
        if candidate.startswith("openai/qwen") and os.getenv("DASHSCOPE_API_KEY"):
            return {
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "api_base": os.getenv("OPENAI_API_BASE") or settings.dashscope_api_base,
            }
        if os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"):
            return {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "api_base": os.getenv("OPENAI_API_BASE"),
            }
        return {}

    async def complete(self, model: Optional[str], messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self._available:
            raise RuntimeError("litellm is not installed")

        candidates = self._resolve_candidates(model)
        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                response = await self._litellm.acompletion(
                    model=candidate,
                    messages=messages,
                    temperature=kwargs.get("temperature", 0.1),
                    max_tokens=kwargs.get("max_tokens", 4000),
                    timeout=kwargs.get("timeout", 120),
                    **self._candidate_kwargs(candidate),
                )
                usage = getattr(response, "usage", None)
                return {
                    "content": response.choices[0].message.content,
                    "usage": {
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(usage, "completion_tokens", 0),
                        "total_tokens": getattr(usage, "total_tokens", 0),
                    },
                    "model": candidate,
                    "provider": candidate.split("/", 1)[0] if "/" in candidate else "direct",
                    "attempts": candidates,
                }
            except Exception as exc:
                logger.warning(f"provider attempt failed for {candidate}: {exc}")
                last_error = exc
                continue
        raise RuntimeError(f"All provider attempts failed: {last_error}")
