import pytest
from unittest.mock import AsyncMock, MagicMock
from core.stream_detector import StreamDetector
from core.config_loader import AppConfig, SelectorsConfig

@pytest.mark.asyncio
async def test_stream_detector_send_prompt():
    config = AppConfig()
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "textarea", "send_button": "button.submit"},
        chatgpt={"prompt_textarea": "#prompt-textarea", "send_button": "button.send"}
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    
    await detector.send_prompt(mock_page, "Hello World", agent_type="perplexity")
    mock_page.fill.assert_called_with("textarea", "Hello World")
    mock_page.click.assert_called_with("button.submit")
