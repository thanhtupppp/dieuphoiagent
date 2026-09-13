import pytest
from unittest.mock import AsyncMock

from core.config_loader import AppConfig, SelectorsConfig
from core.stream_detector import StreamDetector, check_terminal_signal, OBSERVER_JS


def test_check_terminal_signal_tags():
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

    is_term, label = check_terminal_signal("Something failed.\n[STATUS: ERROR]", "perplexity")
    assert is_term is True
    assert label == "ERROR"

    # ChatGPT
    is_term, label = check_terminal_signal(
        "[STATUS: COMMITTED]\n[BRANCH: ai-agent/test]\nPR_URL: https://github.com/o/r/pull/1",
        "chatgpt",
    )
    assert is_term is True
    assert label == "COMMITTED"

    is_term, label = check_terminal_signal("Critical failure.\n[STATUS: ERROR]", "chatgpt")
    assert is_term is True
    assert label == "ERROR"

    is_term, label = check_terminal_signal(
        "Created branch ai-agent/feature and PR https://github.com/thanhtupppp/repo/pull/8 with commit 9d7e03b",
        "chatgpt",
    )
    assert is_term is True
    assert label == "COMMITTED"

    # Non-terminal or streaming
    is_term, label = check_terminal_signal("Thinking about the architecture...", "perplexity")
    assert is_term is False
    assert label == ""

    # Short string
    is_term, label = check_terminal_signal("hi", "perplexity")
    assert is_term is False


def test_check_terminal_signal_json_blocks():
    # JSON completed
    json_text = '```json\n{\n  "status": "completed",\n  "approved": true\n}\n```'
    is_term, label = check_terminal_signal(json_text, "perplexity")
    assert is_term is True
    assert label == "COMPLETED"

    # JSON ready_for_dev
    json_text = '```json\n{\n  "status": "ready_for_dev",\n  "tasks": []\n}\n```'
    is_term, label = check_terminal_signal(json_text, "perplexity")
    assert is_term is True
    assert label == "READY_FOR_DEV"

    # JSON needs_revision
    json_text = '```json\n{\n  "status": "needs_revision",\n  "approved": false\n}\n```'
    is_term, label = check_terminal_signal(json_text, "perplexity")
    assert is_term is True
    assert label == "NEEDS_REVISION"

    # JSON committed
    json_text = '```json\n{\n  "status": "committed",\n  "pr_url": "https://github.com/o/r/pull/2"\n}\n```'
    is_term, label = check_terminal_signal(json_text, "chatgpt")
    assert is_term is True
    assert label == "COMMITTED"

    # JSON error
    json_text = '```json\n{\n  "status": "error",\n  "error": "Failed to compile"\n}\n```'
    is_term, label = check_terminal_signal(json_text, "chatgpt")
    assert is_term is True
    assert label == "ERROR"

    # JSON other content
    json_text = '```json\n{\n  "step": 1,\n  "data": "processing"\n}\n```'
    is_term, label = check_terminal_signal(json_text, "perplexity")
    assert is_term is False


@pytest.mark.asyncio
async def test_stream_detector_send_prompt_perplexity():
    config = AppConfig()
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "textarea", "send_button": "button.submit"},
        chatgpt={"prompt_textarea": "#prompt-textarea", "send_button": "button.send"},
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=True)
    mock_btn = AsyncMock()
    mock_btn.is_visible = AsyncMock(return_value=True)
    mock_page.query_selector = AsyncMock(return_value=mock_btn)

    await detector.send_prompt(mock_page, "Hello World", agent_type="perplexity")
    assert mock_page.evaluate.called
    assert mock_btn.click.called


@pytest.mark.asyncio
async def test_stream_detector_send_prompt_chatgpt_fallback():
    config = AppConfig()
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "textarea", "send_button": "button.submit"},
        chatgpt={"prompt_textarea": "#prompt-textarea", "send_button": "button.send"},
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    # Evaluate fails or returns False
    mock_page.evaluate = AsyncMock(side_effect=Exception("Paste failed"))
    mock_page.keyboard = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    await detector.send_prompt(mock_page, "Test prompt", agent_type="chatgpt")
    assert mock_page.keyboard.insert_text.called
    assert mock_page.keyboard.press.called


@pytest.mark.asyncio
async def test_setup_observer_and_dispatch():
    config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    detector = StreamDetector(config, selectors)

    mock_page = AsyncMock()
    registered_fn = None

    async def fake_expose(name, fn):
        nonlocal registered_fn
        if name == "__dpaStable":
            registered_fn = fn

    mock_page.expose_function = AsyncMock(side_effect=fake_expose)
    mock_page.evaluate = AsyncMock(return_value=None)

    called = False

    def on_stable_turn1():
        nonlocal called
        called = True

    active = await detector._setup_observer(mock_page, on_stable_turn1)
    assert active is True
    mock_page.evaluate.assert_called_with(OBSERVER_JS)
    assert registered_fn is not None

    # Trigger the browser binding
    registered_fn()
    assert called is True

    # Turn 2 on same page: expose_function raises error because already registered
    mock_page.expose_function.side_effect = Exception("Function already registered")
    called_turn2 = False

    def on_stable_turn2():
        nonlocal called_turn2
        called_turn2 = True

    active2 = await detector._setup_observer(mock_page, on_stable_turn2)
    assert active2 is True

    # Triggering the binding now must call the Turn 2 callback, not Turn 1
    registered_fn()
    assert called_turn2 is True


@pytest.mark.asyncio
async def test_setup_observer_graceful_failures():
    config = AppConfig()
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    detector = StreamDetector(config, selectors)

    # Bare object without evaluate or expose_function
    bare_page = object()
    active = await detector._setup_observer(bare_page, lambda: None)  # type: ignore
    assert active is False

    # Page whose evaluate throws
    mock_page = AsyncMock()
    mock_page.evaluate.side_effect = Exception("Evaluation disabled")
    active = await detector._setup_observer(mock_page, lambda: None)
    assert active is False


@pytest.mark.asyncio
async def test_wait_for_completion_button_ready_and_protocol_immediate():
    """Signal 2 (button ready) + Signal 3 (protocol signal) should complete on first cycle."""
    config = AppConfig(timeout_seconds=10, text_stability_seconds=2.0)
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose", "stop_button": "button.stop"},
        chatgpt={"last_response": "div.assistant", "stop_button": "button.stop"},
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value={
        "text": "Task finished.\n[STATUS: COMPLETED]",
        "hasStop": False,  # Button ready!
        "hasAction": True,
        "isTool": False,
    })
    progress_messages = []
    result = await detector.wait_for_completion(
        mock_page,
        "perplexity",
        on_progress=lambda m: progress_messages.append(m),
    )
    assert "[STATUS: COMPLETED]" in result
    assert any("Protocol [COMPLETED]" in m for m in progress_messages)


@pytest.mark.asyncio
async def test_wait_for_completion_dom_quiet_and_button_ready():
    """Signal 1 (DOM quiet from stability) + Signal 2 (Button ready) finishes without protocol."""
    config = AppConfig(timeout_seconds=5, text_stability_seconds=0.2)
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose", "stop_button": "button.stop"},
        chatgpt={"last_response": "div.assistant", "stop_button": "button.stop"},
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value={
        "text": "This is a regular explanation without any special status tags.",
        "hasStop": False,
        "hasAction": False,
        "isTool": False,
    })
    result = await detector.wait_for_completion(mock_page, "perplexity")
    assert "regular explanation" in result


@pytest.mark.asyncio
async def test_wait_for_completion_observer_signal_and_sticky_stop():
    """Signal 1 (Observer event) + Signal 3 (Protocol) finishes even if stop button is stuck."""
    config = AppConfig(timeout_seconds=5, text_stability_seconds=10.0)
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose", "stop_button": "button.stop"},
        chatgpt={"last_response": "div.assistant", "stop_button": "button.stop"},
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()

    # Capture observer callback
    observer_callback = None

    async def fake_expose(name, fn):
        nonlocal observer_callback
        if name == "__dpaStable":
            observer_callback = fn

    mock_page.expose_function = AsyncMock(side_effect=fake_expose)

    call_count = 0

    async def fake_evaluate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # When evaluating dom_state (call >= 2, because call 1 is OBSERVER_JS)
        if call_count > 1:
            if observer_callback:
                observer_callback()  # simulate browser observer quiet event
            return {
                "text": "[STATUS: COMMITTED]\nSHA: a1b2c3d",
                "hasStop": True,  # Stop button stuck visible
                "hasAction": False,
                "isTool": False,
            }
        return None

    mock_page.evaluate = AsyncMock(side_effect=fake_evaluate)

    result = await detector.wait_for_completion(mock_page, "chatgpt")
    assert "[STATUS: COMMITTED]" in result


@pytest.mark.asyncio
async def test_wait_for_completion_tool_running_blocks_completion():
    """Tool running prevents Signal 2 (button ready) from triggering completion."""
    config = AppConfig(timeout_seconds=6, text_stability_seconds=0.1)
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose", "stop_button": "button.stop"},
        chatgpt={"last_response": "div.assistant", "stop_button": "button.stop"},
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()

    cycle = 0

    async def fake_evaluate(*args, **kwargs):
        nonlocal cycle
        cycle += 1
        if cycle == 1:
            return None  # OBSERVER_JS
        elif cycle <= 2:
            # Tool running: hasStop=False, but isTool=True
            return {
                "text": "Executing Python tool...",
                "hasStop": False,
                "hasAction": False,
                "isTool": True,
            }
        else:
            # Tool finished and output completed
            return {
                "text": "Execution done.\n[STATUS: COMPLETED]",
                "hasStop": False,
                "hasAction": True,
                "isTool": False,
            }

    mock_page.evaluate = AsyncMock(side_effect=fake_evaluate)
    result = await detector.wait_for_completion(mock_page, "chatgpt")
    assert "[STATUS: COMPLETED]" in result


@pytest.mark.asyncio
async def test_wait_for_completion_timeout():
    config = AppConfig(timeout_seconds=1, text_stability_seconds=2.0)
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()

    # Continually changing text with stop visible
    step = 0

    async def fake_evaluate(*args, **kwargs):
        nonlocal step
        step += 1
        return {
            "text": f"Generating stream chunk {step}...",
            "hasStop": True,
            "hasAction": False,
            "isTool": False,
        }

    mock_page.evaluate = AsyncMock(side_effect=fake_evaluate)
    with pytest.raises(TimeoutError):
        await detector.wait_for_completion(mock_page, "chatgpt")


@pytest.mark.live
@pytest.mark.asyncio
async def test_stream_detector_live_observer_injection():
    """Verify MutationObserver injection and binding on a live Chrome tab."""
    from core.cdp_connector import CDPConnector
    from core.config_loader import load_config, load_selectors

    config = load_config()
    selectors = load_selectors()
    connector = CDPConnector(config, selectors)
    detector = StreamDetector(config, selectors)

    connected = await connector.connect()
    if not connected:
        pytest.skip("Chrome CDP not reachable at port 9222")

    p_tab, c_tab = await connector.find_tabs()
    target_tab = p_tab or c_tab
    if not target_tab:
        pytest.skip("No suitable live tab found")

    event_triggered = False

    def on_stable():
        nonlocal event_triggered
        event_triggered = True

    active = await detector._setup_observer(target_tab, on_stable)
    assert active is True

    # Verify that window.__dpaObserver is defined in the live DOM
    has_observer = await target_tab.evaluate("() => window.__dpaObserver !== undefined")
    assert has_observer is True
