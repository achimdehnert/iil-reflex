"""Tests for reflex.llm_providers — AifwProvider, LiteLLMProvider, get_provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reflex.llm_providers import AifwProvider, LiteLLMProvider, get_provider


class TestLiteLLMProvider:
    """LiteLLMProvider unit tests (litellm mocked)."""

    def test_should_create_with_defaults(self):
        with patch.object(LiteLLMProvider, "_ensure_api_key"):
            p = LiteLLMProvider()
        assert p.model == "groq/llama-3.3-70b-versatile"
        assert p.temperature == 0.3
        assert p.max_tokens == 4096

    def test_should_accept_custom_model(self):
        with patch.object(LiteLLMProvider, "_ensure_api_key"):
            p = LiteLLMProvider(model="openai/gpt-4o-mini")
        assert p.model == "openai/gpt-4o-mini"

    @patch("litellm.completion")
    def test_should_call_litellm_completion(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_completion.return_value = mock_response

        with patch.object(LiteLLMProvider, "_ensure_api_key"):
            p = LiteLLMProvider(model="groq/llama-3.3-70b-versatile")

        result = p.complete(
            [{"role": "user", "content": "Hello"}],
            action_code="test.action",
        )

        assert result == "test response"
        mock_completion.assert_called_once_with(
            model="groq/llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.3,
            max_tokens=4096,
        )
        assert len(p.call_log) == 1
        assert p.call_log[0]["action_code"] == "test.action"

    @patch("litellm.completion")
    def test_should_handle_empty_content(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 0
        mock_completion.return_value = mock_response

        with patch.object(LiteLLMProvider, "_ensure_api_key"):
            p = LiteLLMProvider()

        result = p.complete([{"role": "user", "content": "test"}])
        assert result == ""


class TestAifwProvider:
    """AifwProvider unit tests (aifw mocked)."""

    def test_should_create_with_defaults(self):
        p = AifwProvider()
        assert p.quality_level is None
        assert p.priority is None

    def test_should_accept_quality_level(self):
        p = AifwProvider(quality_level=7, priority="fast")
        assert p.quality_level == 7
        assert p.priority == "fast"

    @patch("reflex.llm_providers.AifwProvider.complete")
    def test_should_log_calls(self, mock_complete):
        mock_complete.return_value = "response"
        p = AifwProvider()
        result = p.complete(
            [{"role": "user", "content": "test"}],
            action_code="reflex.domain-research",
        )
        mock_complete.assert_called_once()


class TestGetProvider:
    """Factory function tests."""

    def test_should_create_litellm_provider(self):
        with patch.object(LiteLLMProvider, "_ensure_api_key"):
            p = get_provider(backend="litellm", model="openai/gpt-4o-mini")
        assert isinstance(p, LiteLLMProvider)
        assert p.model == "openai/gpt-4o-mini"

    def test_should_create_aifw_provider(self):
        p = get_provider(backend="aifw")
        assert isinstance(p, AifwProvider)

    def test_should_raise_on_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            get_provider(backend="unknown")

    def test_should_auto_fallback_to_litellm(self):
        with patch.object(LiteLLMProvider, "_ensure_api_key"):
            p = get_provider(backend="auto", model="groq/llama-3.3-70b-versatile")
        assert isinstance(p, LiteLLMProvider)
