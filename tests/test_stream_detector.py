import pytest
from unittest.mock import AsyncMock, MagicMock
from core.stream_detector import StreamDetector, check_terminal_signal
from core.config_loader import AppConfig, SelectorsConfig

def test_check_terminal_signal():
    # Perplexity
    is_term, label = check_terminal_signal("Plan ready.\n[STATUS: READY_FOR_DEV]", "perplexity")
    assert is_term is True
    assert label == "READY_FOR_DEV"

    is_term, label = check_terminal_signal("Need fix.\n[STATUS: NEEDS_REVISION]", "perplexity")
    assert is_term is True
    assert label == "NEEDS_REVISION"

    is_term, label = check_terminal_signal("All good.\n[STATUS: COMPLETED]", "perplexity")
    assert is_term is True
    assert label == "COMPLETED"

    # ChatGPT
    is_term, label = check_terminal_signal("[STATUS: COMMITTED]\n[BRANCH: ai-agent/test]\nPR_URL: https://github.com/o/r/pull/1", "chatgpt")
    assert is_term is True
    assert label == "COMMITTED"

    # ChatGPT with PR URL fallback
    is_term, label = check_terminal_signal("Created branch ai-agent/feature and PR https://github.com/thanhtupppp/repo/pull/8 with commit 9d7e03b", "chatgpt")
    assert is_term is True
    assert label == "COMMITTED"

    # Non-terminal or streaming
    is_term, label = check_terminal_signal("Thinking about the architecture...", "perplexity")
    assert is_term is False

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
    assert mock_page.evaluate.called or mock_page.keyboard.insert_text.called or mock_page.fill.called

@pytest.mark.asyncio
async def test_wait_for_completion_terminal_tag_immediate():
    """Verify that when terminal tag is present, it finishes on text stability without waiting for timeout, even if stop button is visible."""
    config = AppConfig(timeout_seconds=10, text_stability_seconds=0.5)
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose", "stop_button": "button.stop"},
        chatgpt={"last_response": "div.assistant", "stop_button": "button.stop"}
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    
    mock_page.evaluate = AsyncMock(return_value={
        "text": "[STATUS: COMMITTED]\nPR: https://github.com/o/r/pull/1\nSHA: 1234567",
        "hasStop": True,
        "hasAction": False,
        "isTool": False
    })

    result = await detector.wait_for_completion(mock_page, "chatgpt")
    assert "[STATUS: COMMITTED]" in result
