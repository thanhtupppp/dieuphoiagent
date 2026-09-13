import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.checkpoint_manager import TaskCheckpoint
from core.config_loader import AppConfig, SelectorsConfig
from core.orchestrator_fsm import FSMState, OrchestratorFSM


@pytest.mark.asyncio
async def test_fsm_error_triggers_recovery_required(tmp_path):
    config = AppConfig(default_max_loops=3)
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "t", "send_button": "b", "last_response": "div"},
        chatgpt={"prompt_textarea": "t", "send_button": "b", "last_response": "div"},
    )
    fsm = OrchestratorFSM(config, selectors)
    fsm.connector.connect = AsyncMock(return_value=True)
    fsm.connector.find_tabs = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    fsm.detector.send_prompt = AsyncMock()
    fsm.detector.wait_for_completion = AsyncMock(side_effect=TimeoutError("Perplexity timeout"))
    with patch("core.orchestrator_fsm.save_checkpoint") as mock_save:
        await fsm.start_task("test/repo", "main", "Fix issue", max_loops=3, auto_mode=True)
        await asyncio.sleep(0.5)
        assert fsm.state == FSMState.RECOVERY_REQUIRED
        assert mock_save.called
        saved_cp = mock_save.call_args[0][0]
        assert saved_cp.status_label == "RECOVERY_REQUIRED"
        assert "Perplexity timeout" in saved_cp.error_message


@pytest.mark.asyncio
async def test_fsm_resume_from_checkpoint(tmp_path):
    config = AppConfig(default_max_loops=3)
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "t", "send_button": "b", "last_response": "div"},
        chatgpt={"prompt_textarea": "t", "send_button": "b", "last_response": "div"},
    )
    fsm = OrchestratorFSM(config, selectors)
    fsm.connector.connect = AsyncMock(return_value=True)
    fsm.connector.find_tabs = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    fsm.detector.send_prompt = AsyncMock()
    fsm.detector.wait_for_completion = AsyncMock(return_value="""
    [STATUS: COMPLETED]
    [SUMMARY]: All done!
    """)
    mock_cp = TaskCheckpoint(
        repo="owner/repo",
        branch="main",
        goal="Test feature",
        loop_count=1,
        max_loops=3,
        auto_mode=True,
        last_successful_agent="chatgpt",
        next_target_agent="perplexity",
        feature_branch="ai-agent/feature-x",
        commit_sha="9d7e03b",
        pr_url="https://github.com/owner/repo/pull/8",
        next_prompt_payload="[KẾT QUẢ PULL REQUEST TỪ DEV]: Please review",
        status_label="COMMITTED_AWAITING_REVIEW",
    )
    await fsm.resume_from_checkpoint(mock_cp)
    await asyncio.sleep(0.5)
    assert fsm.state == FSMState.TASK_FINISHED
    assert fsm.current_repo == "owner/repo"
    assert fsm.pr_url == "https://github.com/owner/repo/pull/8"
