import pytest
from unittest.mock import AsyncMock

from core.checkpoint_manager import (
    TaskCheckpoint,
    clear_checkpoint,
    has_active_checkpoint,
    load_checkpoint,
    reconcile_from_tabs,
    save_checkpoint,
)
from core.config_loader import SelectorsConfig


def test_checkpoint_save_and_load(tmp_path):
    cp_file = str(tmp_path / "checkpoint.json")
    cp = TaskCheckpoint(
        repo="owner/repo",
        branch="main",
        goal="Fix issue",
        loop_count=1,
        feature_branch="ai-agent/fix",
        commit_sha="abcdef1",
        pr_url="https://github.com/owner/repo/pull/1",
        next_target_agent="perplexity",
        status_label="COMMITTED_AWAITING_REVIEW",
    )
    save_checkpoint(cp, path=cp_file)
    assert has_active_checkpoint(path=cp_file) is True
    loaded = load_checkpoint(path=cp_file)
    assert loaded is not None
    assert loaded.repo == "owner/repo"
    assert loaded.feature_branch == "ai-agent/fix"
    assert loaded.pr_url == "https://github.com/owner/repo/pull/1"
    assert loaded.next_target_agent == "perplexity"
    clear_checkpoint(path=cp_file)
    assert has_active_checkpoint(path=cp_file) is False
    assert load_checkpoint(path=cp_file) is None


@pytest.mark.asyncio
async def test_reconcile_from_tabs_chatgpt_committed():
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose"},
        chatgpt={"last_response": "div.assistant"},
    )
    mock_p_tab = AsyncMock()
    mock_p_el = AsyncMock()
    mock_p_el.inner_text = AsyncMock(return_value="[STATUS: READY_FOR_DEV]\n[TASK]: Build feature")
    mock_p_tab.query_selector_all = AsyncMock(return_value=[mock_p_el])
    mock_c_tab = AsyncMock()
    mock_c_el = AsyncMock()
    mock_c_el.inner_text = AsyncMock(return_value="""
    [STATUS: COMMITTED]
    [BRANCH: ai-agent/feature-x]
    [COMMIT_SHA: 9d7e03b]
    PR_URL: https://github.com/owner/repo/pull/8
    """)
    mock_c_tab.query_selector_all = AsyncMock(return_value=[mock_c_el])
    cp = await reconcile_from_tabs(
        p_tab=mock_p_tab,
        c_tab=mock_c_tab,
        repo="owner/repo",
        branch="main",
        goal="Test feature",
        selectors=selectors,
    )
    assert cp.loop_count == 1
    assert cp.last_successful_agent == "chatgpt"
    assert cp.next_target_agent == "perplexity"
    assert cp.feature_branch == "ai-agent/feature-x"
    assert cp.commit_sha == "9d7e03b"
    assert cp.pr_url == "https://github.com/owner/repo/pull/8"
    assert "[KẾT QUẢ PULL REQUEST TỪ DEV]:" in cp.next_prompt_payload


@pytest.mark.asyncio
async def test_reconcile_from_tabs_perplexity_needs_revision():
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose"},
        chatgpt={"last_response": "div.assistant"},
    )
    mock_p_tab = AsyncMock()
    mock_p_el = AsyncMock()
    mock_p_el.inner_text = AsyncMock(return_value="[STATUS: NEEDS_REVISION]\nFix test ordering.")
    mock_p_tab.query_selector_all = AsyncMock(return_value=[mock_p_el])
    mock_c_tab = AsyncMock()
    mock_c_el = AsyncMock()
    mock_c_el.inner_text = AsyncMock(return_value="""
    [STATUS: COMMITTED]
    [BRANCH: ai-agent/feature-x]
    [COMMIT_SHA: 9d7e03b]
    PR_URL: https://github.com/owner/repo/pull/8
    """)
    mock_c_tab.query_selector_all = AsyncMock(return_value=[mock_c_el])
    cp = await reconcile_from_tabs(
        p_tab=mock_p_tab,
        c_tab=mock_c_tab,
        repo="owner/repo",
        branch="main",
        goal="Test feature",
        selectors=selectors,
    )
    assert cp.loop_count == 2
    assert cp.last_successful_agent == "perplexity"
    assert cp.next_target_agent == "chatgpt"
    assert cp.feature_branch == "ai-agent/feature-x"
    assert "YÊU CẦU SỬA ĐỔI TỪ LEAD" in cp.next_prompt_payload
