import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from core.cdp_connector import CDPConnector
from core.config_loader import AppConfig, SelectorsConfig


@pytest.mark.asyncio
async def test_cdp_connector_tab_matching():
    app_config = AppConfig(cdp_url="http://localhost:9222")
    selectors = SelectorsConfig(
        perplexity={"url_match": "perplexity.ai"},
        chatgpt={"url_match": "chatgpt.com"},
    )
    connector = CDPConnector(app_config, selectors)

    mock_p1 = MagicMock()
    mock_p1.url = "https://www.perplexity.ai/search"
    mock_p1.is_closed.return_value = False

    mock_p2 = MagicMock()
    mock_p2.url = "https://chatgpt.com/c/12345"
    mock_p2.is_closed.return_value = False

    mock_p3 = MagicMock()
    mock_p3.url = "https://google.com"
    mock_p3.is_closed.return_value = False

    mock_context = MagicMock()
    mock_context.pages = [mock_p1, mock_p2, mock_p3]
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]
    mock_browser.is_connected.return_value = True

    connector.browser = mock_browser
    connector.is_connected = True
    p_tab, c_tab = await connector.find_tabs()

    assert p_tab == mock_p1
    assert c_tab == mock_p2


def test_cdp_connector_connected_property():
    app_config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)

    # Initial: False
    assert connector.connected is False

    # is_connected True but browser None
    connector.is_connected = True
    assert connector.connected is False

    # Browser connected
    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = True
    connector.browser = mock_browser
    assert connector.connected is True

    # Browser throws
    mock_browser.is_connected.side_effect = Exception("error")
    assert connector.connected is False


@pytest.mark.asyncio
async def test_cdp_connector_connect_success():
    app_config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)

    mock_browser = MagicMock()
    mock_browser.contexts = [MagicMock()]
    mock_browser.is_connected.return_value = True

    mock_playwright = AsyncMock()
    mock_playwright.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    with patch("core.cdp_connector.async_playwright") as mock_ap:
        mock_ctx = AsyncMock()
        mock_ctx.start = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value = mock_ctx

        ok = await connector.connect()
        assert ok is True
        assert connector.is_connected is True
        assert mock_browser.on.called

        # Calling connect again when already connected
        ok2 = await connector.connect()
        assert ok2 is True


@pytest.mark.asyncio
async def test_cdp_connector_connect_no_context():
    app_config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)

    mock_browser = MagicMock()
    mock_browser.contexts = []  # No contexts!

    mock_playwright = AsyncMock()
    mock_playwright.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    with patch("core.cdp_connector.async_playwright") as mock_ap:
        mock_ctx = AsyncMock()
        mock_ctx.start = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value = mock_ctx

        ok = await connector.connect()
        assert ok is False
        assert connector.is_connected is False


@pytest.mark.asyncio
async def test_cdp_connector_reconnect_success():
    app_config = AppConfig(reconnect_attempts=2, reconnect_delay_seconds=0.01)
    selectors = SelectorsConfig(
        perplexity={"url_match": "perplexity.ai"},
        chatgpt={"url_match": "chatgpt.com"},
    )
    connector = CDPConnector(app_config, selectors)

    calls = 0

    async def fake_connect():
        nonlocal calls
        calls += 1
        return calls == 2

    connector.connect = AsyncMock(side_effect=fake_connect)
    p_mock = MagicMock()
    connector.find_tabs = AsyncMock(return_value=(p_mock, None))

    ok = await connector.reconnect()
    assert ok is True
    assert calls == 2


@pytest.mark.asyncio
async def test_cdp_connector_reconnect_exhausted():
    app_config = AppConfig(reconnect_attempts=2, reconnect_delay_seconds=0.01)
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)

    connector.connect = AsyncMock(return_value=False)
    ok = await connector.reconnect()
    assert ok is False


@pytest.mark.asyncio
async def test_cdp_connector_close():
    app_config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)

    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = True
    mock_browser.close = AsyncMock()
    mock_playwright = AsyncMock()
    connector.browser = mock_browser
    connector.playwright = mock_playwright
    connector.is_connected = True
    connector.perplexity_tab = MagicMock()

    await connector.close()
    assert connector.is_connected is False
    assert connector.browser is None
    assert connector.perplexity_tab is None
    assert mock_browser.close.called
    assert mock_playwright.stop.called


@pytest.mark.asyncio
async def test_cdp_connector_open_page_timeout():
    app_config = AppConfig(navigation_timeout_ms=100)
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)

    mock_page = MagicMock()
    mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))
    mock_page.is_closed.return_value = False
    mock_page.close = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    res = await connector._open_page(mock_context, "https://test.com")
    assert res is None
    assert mock_page.close.called


def test_cdp_connector_handle_browser_disconnected():
    app_config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    connector = CDPConnector(app_config, selectors)
    mock_browser = MagicMock()
    connector.browser = mock_browser
    connector.is_connected = True
    connector.perplexity_tab = MagicMock()

    # Disconnected event from a different (stale) browser instance should be ignored
    stale_browser = MagicMock()
    connector._handle_browser_disconnected(stale_browser)
    assert connector.is_connected is True

    # Disconnected event matching current browser resets state
    connector._handle_browser_disconnected(mock_browser)
    assert connector.is_connected is False
    assert connector.perplexity_tab is None


def test_cdp_connector_find_page_aliases():
    p1 = MagicMock()
    p1.url = "https://chat.openai.com/c/abc"
    p2 = MagicMock()
    p2.url = "https://perplexity.ai"

    # Testing alias resolution for chatgpt
    found = CDPConnector._find_page([p1, p2], "chatgpt.com")
    assert found == p1

    found_perplexity = CDPConnector._find_page([p1, p2], "perplexity.ai")
    assert found_perplexity == p2

    not_found = CDPConnector._find_page([p1, p2], "claude.ai")
    assert not_found is None
