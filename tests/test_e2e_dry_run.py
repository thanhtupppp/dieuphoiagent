import pytest
import asyncio
from unittest.mock import AsyncMock
from core.orchestrator_fsm import OrchestratorFSM, FSMState
from core.config_loader import AppConfig, SelectorsConfig

@pytest.mark.asyncio
async def test_fsm_e2e_dry_run_completion():
    config = AppConfig(default_max_loops=3)
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "t", "send_button": "b", "last_response": "div"},
        chatgpt={"prompt_textarea": "t", "send_button": "b", "last_response": "div"}
    )
    fsm = OrchestratorFSM(config, selectors)
    
    # Mock CDP connection
    fsm.connector.connect = AsyncMock(return_value=True)
    fsm.connector.find_tabs = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    
    # Mock Perplexity returns [STATUS: COMPLETED] on first iteration
    fsm.detector.send_prompt = AsyncMock()
    fsm.detector.wait_for_completion = AsyncMock(return_value="""
    [STATUS: COMPLETED]
    [SUMMARY]: Toàn bộ yêu cầu kỹ thuật đã được nghiệm thu hoàn chỉnh!
    """)
    
    await fsm.start_task("test/repo", "main", "Fix issue", max_loops=3, auto_mode=True)
    await asyncio.sleep(0.5)
    
    assert fsm.state == FSMState.TASK_FINISHED
    assert len(fsm.session_events) > 0
