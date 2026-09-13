from unittest.mock import AsyncMock

import pytest

from core.config_loader import AppConfig
from core.providers.base import AgentRequest, AgentRole, ProviderKind
from core.providers.cdp_provider import CdpProvider


@pytest.fixture
def provider():
    return CdpProvider(AppConfig(), selectors=None)


@pytest.mark.asyncio
async def test_cdp_provider_ensures_tabs_and_sends_to_tech_lead(provider):
    perplexity_tab = object()
    chatgpt_tab = object()
    provider.connector.connect = AsyncMock(return_value=True)
    provider.connector.find_tabs = AsyncMock(return_value=(perplexity_tab, chatgpt_tab))
    provider.detector.send_prompt = AsyncMock()
    provider.detector.wait_for_completion = AsyncMock(return_value="[STATUS: READY_FOR_DEV] result")

    def progress(message: str) -> None:
        pass

    response = await provider.send(
        AgentRequest(
            role=AgentRole.TECH_LEAD,
            system_prompt="system",
            user_prompt="review this",
            on_progress=progress,
        )
    )

    provider.connector.connect.assert_awaited_once()
    provider.connector.find_tabs.assert_awaited_once()
    provider.detector.send_prompt.assert_awaited_once_with(
        perplexity_tab, "review this", "perplexity"
    )
    provider.detector.wait_for_completion.assert_awaited_once_with(
        perplexity_tab, "perplexity", on_progress=progress
    )
    assert response.content == "[STATUS: READY_FOR_DEV] result"
    assert response.elapsed_s >= 0


@pytest.mark.asyncio
async def test_cdp_provider_routes_core_dev_to_chatgpt(provider):
    perplexity_tab = object()
    chatgpt_tab = object()
    provider.connector.connect = AsyncMock(return_value=True)
    provider.connector.find_tabs = AsyncMock(return_value=(perplexity_tab, chatgpt_tab))
    provider.detector.send_prompt = AsyncMock()
    provider.detector.wait_for_completion = AsyncMock(return_value="[STATUS: COMMITTED] result")

    response = await provider.send(
        AgentRequest(
            role=AgentRole.CORE_DEV,
            system_prompt="system",
            user_prompt="implement this",
        )
    )

    provider.detector.send_prompt.assert_awaited_once_with(
        chatgpt_tab, "implement this", "chatgpt"
    )
    provider.detector.wait_for_completion.assert_awaited_once_with(
        chatgpt_tab, "chatgpt", on_progress=None
    )
    assert response.content == "[STATUS: COMMITTED] result"


@pytest.mark.asyncio
async def test_cdp_provider_caches_tabs_between_requests(provider):
    tabs = (object(), object())
    provider.connector.connect = AsyncMock(return_value=True)
    provider.connector.find_tabs = AsyncMock(return_value=tabs)
    provider.detector.send_prompt = AsyncMock()
    provider.detector.wait_for_completion = AsyncMock(return_value="stable response")

    request = AgentRequest(
        role=AgentRole.TECH_LEAD,
        system_prompt="system",
        user_prompt="first",
    )
    await provider.send(request)
    await provider.send(
        AgentRequest(
            role=AgentRole.TECH_LEAD,
            system_prompt="system",
            user_prompt="second",
        )
    )

    provider.connector.connect.assert_awaited_once()
    provider.connector.find_tabs.assert_awaited_once()


@pytest.mark.asyncio
async def test_cdp_provider_rejects_failed_connection(provider):
    provider.connector.connect = AsyncMock(return_value=False)

    with pytest.raises(RuntimeError, match="CDP connect failed"):
        await provider.health_check()


@pytest.mark.asyncio
async def test_cdp_provider_reports_missing_tab(provider):
    provider.connector.connect = AsyncMock(return_value=True)
    provider.connector.find_tabs = AsyncMock(return_value=(object(), None))

    with pytest.raises(RuntimeError, match="Tab chatgpt không sẵn sàng"):
        await provider.send(
            AgentRequest(
                role=AgentRole.CORE_DEV,
                system_prompt="system",
                user_prompt="implement this",
            )
        )


@pytest.mark.asyncio
async def test_cdp_provider_health_check_requires_both_tabs(provider):
    provider.connector.connect = AsyncMock(return_value=True)
    provider.connector.find_tabs = AsyncMock(return_value=(object(), object()))

    assert await provider.health_check() is True


@pytest.mark.asyncio
async def test_cdp_provider_close_keeps_browser_connection_and_invalidates_tabs(provider):
    provider.connector.perplexity_tab = object()
    provider.connector.chatgpt_tab = object()
    provider._tabs_ready = True

    provider.connector.close = AsyncMock()
    await provider.close()

    assert provider._tabs_ready is False
    assert provider.connector.perplexity_tab is None
    assert provider.connector.chatgpt_tab is None
    provider.connector.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_cdp_provider_reconnects_after_close(provider):
    first_tabs = (object(), object())
    second_tabs = (object(), object())
    provider.connector.connect = AsyncMock(return_value=True)
    provider.connector.find_tabs = AsyncMock(side_effect=[first_tabs, second_tabs])
    provider.detector.send_prompt = AsyncMock()
    provider.detector.wait_for_completion = AsyncMock(return_value="response")

    request = AgentRequest(
        role=AgentRole.TECH_LEAD,
        system_prompt="system",
        user_prompt="first",
    )
    await provider.send(request)
    await provider.close()
    await provider.send(
        AgentRequest(
            role=AgentRole.TECH_LEAD,
            system_prompt="system",
            user_prompt="second",
        )
    )

    assert provider.connector.connect.await_count == 2
    assert provider.connector.find_tabs.await_count == 2
    assert provider.detector.send_prompt.await_count == 2


# Keep the provider-kind contract visible in this focused test module.
def test_cdp_provider_kind():
    assert CdpProvider.kind is ProviderKind.CDP


@pytest.mark.live
@pytest.mark.asyncio
async def test_cdp_provider_live_health_check():
    """Live smoke test verifying connection to real Chrome on port 9222 and tab detection."""
    config = AppConfig()
    provider = CdpProvider(config)
    try:
        is_healthy = await provider.health_check()
        assert is_healthy is True
        p_tab, c_tab = await provider._ensure_tabs()
        assert p_tab is not None
        assert c_tab is not None
        assert "perplexity" in (getattr(p_tab, "url", "") or "")
        assert "chatgpt" in (getattr(c_tab, "url", "") or "") or "openai" in (
            getattr(c_tab, "url", "") or ""
        )
    finally:
        await provider.close()


@pytest.mark.live
@pytest.mark.asyncio
async def test_cdp_provider_live_tabs_evaluation():
    """Live smoke test verifying that both tabs can evaluate basic JavaScript."""
    config = AppConfig()
    provider = CdpProvider(config)
    try:
        p_tab, c_tab = await provider._ensure_tabs()
        assert p_tab is not None and c_tab is not None
        p_eval = await p_tab.evaluate("() => document.location.hostname")
        c_eval = await c_tab.evaluate("() => document.location.hostname")
        assert "perplexity" in p_eval
        assert "chatgpt" in c_eval or "openai" in c_eval
    finally:
        await provider.close()

