import pytest
from unittest.mock import AsyncMock, MagicMock
from core.cdp_connector import CDPConnector
from core.config_loader import AppConfig, SelectorsConfig

@pytest.mark.asyncio
async def test_cdp_connector_tab_matching():
    app_config = AppConfig(cdp_url="http://localhost:9222")
    selectors = SelectorsConfig(
        perplexity={"url_match": "perplexity.ai"},
        chatgpt={"url_match": "chatgpt.com"}
    )
    connector = CDPConnector(app_config, selectors)
    
    mock_p1 = AsyncMock()
    mock_p1.url = "https://www.perplexity.ai/search"
    mock_p2 = AsyncMock()
    mock_p2.url = "https://chatgpt.com/c/12345"
    mock_p3 = AsyncMock()
    mock_p3.url = "https://google.com"

    mock_context = MagicMock()
    mock_context.pages = [mock_p1, mock_p2, mock_p3]
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]
    
    connector.browser = mock_browser
    p_tab, c_tab = await connector.find_tabs()
    
    assert p_tab == mock_p1
    assert c_tab == mock_p2
