"""
REFLEX LLM Providers — Concrete implementations via iil-aifw.

Architecture (3 layers):
    1. AifwProvider    — Django context: uses aifw.sync_completion()
                         DB-driven model routing, usage logging, fallback
    2. LiteLLMProvider — Standalone CLI: uses litellm directly
                         No Django needed, reads env vars for API keys
    3. MockLLMProvider — Tests: deterministic responses (in providers.py)

All implement the LLMProvider protocol from reflex.providers.

Usage (Django hub):
    from reflex.llm_providers import AifwProvider
    llm = AifwProvider()  # uses aifw DB config
    response = llm.complete(messages, action_code="reflex.domain-research")

Usage (CLI / standalone):
    from reflex.llm_providers import LiteLLMProvider
    llm = LiteLLMProvider(model="groq/llama-3.3-70b-versatile")
    response = llm.complete(messages)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


__all__ = ["AifwProvider", "LiteLLMProvider", "get_provider"]

# ── AifwProvider (Django context) ─────────────────────────────────────────


@dataclass
class AifwProvider:
    """LLM provider using iil-aifw (Django DB-driven config).

    Requires Django to be configured and aifw tables to exist.
    Uses aifw.sync_completion() which provides:
      - DB-driven model routing via action_code
      - Automatic usage logging
      - Fallback model support
      - Quality-level routing
    """

    quality_level: int | None = None
    priority: str | None = None
    call_log: list[dict] = field(default_factory=list)

    def complete(
        self,
        messages: list[dict[str, str]],
        action_code: str = "",
    ) -> str:
        """Send completion via aifw.sync_completion()."""
        from aifw import sync_completion

        self.call_log.append({"action_code": action_code})

        result = sync_completion(
            action_code=action_code or "reflex.default",
            messages=messages,
            quality_level=self.quality_level,
            priority=self.priority,
        )

        if not result.success:
            raise RuntimeError(f"aifw completion failed: {result.error}")

        logger.info(
            "aifw response: action=%s model=%s tokens=%d/%d latency=%dms",
            action_code,
            result.model,
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
        )
        return result.content


# ── LiteLLMProvider (standalone / CLI) ────────────────────────────────────


@dataclass
class LiteLLMProvider:
    """LLM provider using litellm directly (no Django required).

    Model string format follows litellm convention:
        "groq/llama-3.3-70b-versatile"
        "openai/gpt-4o-mini"
        "anthropic/claude-3-haiku-20240307"

    API keys are read from environment variables:
        GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
    """

    model: str = "groq/llama-3.3-70b-versatile"
    temperature: float = 0.3
    max_tokens: int = 4096
    call_log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.model:
            self.model = "groq/llama-3.3-70b-versatile"
        self._ensure_api_key()

    def _ensure_api_key(self) -> None:
        """Load API key from secrets file if env var is not set."""
        provider = self.model.split("/")[0] if "/" in self.model else "openai"
        env_map = {
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        env_var = env_map.get(provider, "")
        if env_var and os.environ.get(env_var):
            return

        secrets_dir = os.environ.get(
            "REFLEX_SECRETS_DIR",
            os.path.expanduser("~/shared/secrets"),
        )
        key_file = os.path.join(secrets_dir, env_var.lower() if env_var else "")
        if key_file and os.path.isfile(key_file):
            with open(key_file) as f:
                os.environ[env_var] = f.read().strip()
            logger.debug("Loaded %s from %s", env_var, key_file)

    def complete(
        self,
        messages: list[dict[str, str]],
        action_code: str = "",
    ) -> str:
        """Send completion via litellm."""
        import litellm

        litellm.suppress_debug_info = True

        self.call_log.append({"action_code": action_code, "model": self.model})
        logger.debug("litellm request: model=%s action=%s", self.model, action_code)

        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        content = response.choices[0].message.content or ""
        usage = response.usage
        logger.info(
            "litellm response: action=%s model=%s tokens=%d/%d",
            action_code,
            self.model,
            getattr(usage, "prompt_tokens", 0),
            getattr(usage, "completion_tokens", 0),
        )
        return content


# ── Factory ───────────────────────────────────────────────────────────────


def get_provider(
    backend: str = "auto",
    **kwargs,
) -> AifwProvider | LiteLLMProvider:
    """Factory function to create the best available LLM provider.

    Args:
        backend: "aifw", "litellm", or "auto" (try aifw first, fall back to litellm)
        **kwargs: Passed to provider constructor (model, temperature, etc.)
    """
    if backend == "aifw":
        return AifwProvider(**kwargs)
    if backend == "litellm":
        return LiteLLMProvider(**kwargs)

    # auto: try aifw (needs Django), fall back to litellm
    if backend == "auto":
        try:
            import django.conf  # noqa: F401
            from aifw import sync_completion  # noqa: F401

            logger.debug("Auto-detected aifw — using AifwProvider")
            return AifwProvider(**kwargs)
        except (ImportError, Exception):
            logger.debug("aifw not available — falling back to LiteLLMProvider")
            return LiteLLMProvider(**kwargs)

    raise ValueError(f"Unknown backend: {backend!r}. Choose from: aifw, litellm, auto")
