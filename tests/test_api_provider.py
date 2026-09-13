from unittest.mock import AsyncMock, MagicMock

import pytest

from core.providers.api_provider import ApiProvider
from core.providers.base import AgentRequest, AgentRole, ProviderKind


def test_api_provider_kind():
    assert ApiProvider.kind is ProviderKind.API


def test_api_provider_raises_when_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY or PERPLEXITY_API_KEY required"):
        ApiProvider()


def test_api_provider_initializes_with_direct_key():
    provider = ApiProvider(api_key="direct-test-key")
    assert provider._client.api_key == "direct-test-key"


def test_api_provider_initializes_with_env_key(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
    provider = ApiProvider()
    assert provider._client.api_key == "pplx-test-key"


def test_api_provider_custom_base_url():
    provider = ApiProvider(api_key="test-key", base_url="https://custom.gateway.internal/v1")
    assert str(provider._client.base_url).rstrip("/") == "https://custom.gateway.internal/v1"


def test_api_provider_env_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://env.gateway.internal/v1")
    provider = ApiProvider()
    assert str(provider._client.base_url).rstrip("/") == "https://env.gateway.internal/v1"


@pytest.mark.asyncio
async def test_api_provider_sends_tech_lead_request_to_sonar_pro():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "[STATUS: READY_FOR_DEV]\nTask spec created."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    provider = ApiProvider(client=mock_client)

    progress_events: list[str] = []

    request = AgentRequest(
        role=AgentRole.TECH_LEAD,
        system_prompt="You are a tech lead.",
        user_prompt="Define spec for repo",
        on_progress=progress_events.append,
        timeout_s=120,
    )

    response = await provider.send(request)

    mock_client.chat.completions.create.assert_awaited_once_with(
        model="sonar-pro",
        messages=[
            {"role": "system", "content": "You are a tech lead."},
            {"role": "user", "content": "Define spec for repo"},
        ],
        timeout=120,
    )

    assert response.content == "[STATUS: READY_FOR_DEV]\nTask spec created."
    assert response.elapsed_s >= 0
    assert len(progress_events) == 2
    assert "sonar-pro" in progress_events[0]


@pytest.mark.asyncio
async def test_api_provider_sends_core_dev_request_to_gpt4o():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "[STATUS: COMMITTED]\n[PR_URL: https://github.com/test/repo/pull/1]"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    provider = ApiProvider(client=mock_client)

    request = AgentRequest(
        role=AgentRole.CORE_DEV,
        system_prompt="",
        user_prompt="Implement task spec",
    )

    response = await provider.send(request)

    mock_client.chat.completions.create.assert_awaited_once_with(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Implement task spec"},
        ],
        timeout=600,
    )

    assert "[STATUS: COMMITTED]" in response.content


@pytest.mark.asyncio
async def test_api_provider_rejects_unsupported_role():
    mock_client = MagicMock()
    provider = ApiProvider(client=mock_client)

    fake_request = MagicMock()
    fake_request.role = "unsupported_role"
    fake_request.on_progress = None

    with pytest.raises(ValueError, match="Unsupported agent role"):
        await provider.send(fake_request)


@pytest.mark.asyncio
async def test_api_provider_handles_empty_response():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = []
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    provider = ApiProvider(client=mock_client)
    request = AgentRequest(
        role=AgentRole.TECH_LEAD,
        system_prompt="",
        user_prompt="Hello",
    )
    response = await provider.send(request)
    assert response.content == ""


@pytest.mark.asyncio
async def test_api_provider_health_check(monkeypatch):
    mock_client = MagicMock()
    mock_client.api_key = "valid-key"
    provider = ApiProvider(client=mock_client)
    assert await provider.health_check() is True

    mock_client.api_key = None
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_api_provider_close():
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    provider = ApiProvider(client=mock_client)

    await provider.close()
    mock_client.close.assert_awaited_once()
