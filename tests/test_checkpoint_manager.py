from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.checkpoint_manager import (
    CheckpointStore,
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


def test_checkpoint_redact_secrets():
    from core.checkpoint_manager import redact_secrets, _REDACTED

    sample = {
        "repo": "owner/repo",
        "api_key": "secret_123",
        "nested": {
            "session_token": "token_abc",
            "safe_field": "hello",
        },
        "items": [{"password": "pwd"}, "clean_str"],
        "coords": ("regular_tuple",),
    }
    redacted = redact_secrets(sample)
    assert redacted["api_key"] == _REDACTED
    assert redacted["nested"]["session_token"] == _REDACTED
    assert redacted["nested"]["safe_field"] == "hello"
    assert redacted["items"][0]["password"] == _REDACTED
    assert redacted["coords"] == ["regular_tuple"]


def test_checkpoint_redact_secrets_inside_string():
    from core.checkpoint_manager import redact_secrets, _REDACTED

    payload = {
        "last_raw_response": (
            "Response received.\n"
            "Authorization: Bearer abc123def456\n"
            "api_key=secret-key-value\n"
            "Direct token: sk-abcdef12345678901234\n"
            "GitHub: ghp_1234567890123456789012345678901234"
        ),
        "token_count": 100,
        "session_count": 2,
        "tokenizer": "cl100k_base",
        "api_key_enabled": True,
        "password_policy": "strict",
    }
    result = redact_secrets(payload)
    raw = result["last_raw_response"]
    assert "abc123def456" not in raw
    assert "secret-key-value" not in raw
    assert "sk-abcdef12345678901234" not in raw
    assert "ghp_1234567890123456789012345678901234" not in raw
    assert _REDACTED in raw

    # Ensure non-secret keys are preserved without alteration
    assert result["token_count"] == 100
    assert result["session_count"] == 2
    assert result["tokenizer"] == "cl100k_base"
    assert result["api_key_enabled"] is True
    assert result["password_policy"] == "strict"


def test_checkpoint_load_corrupted_json(tmp_path):
    bad_file = tmp_path / "corrupted_checkpoint.json"
    bad_file.write_text("{broken json: 123", encoding="utf-8")

    result = load_checkpoint(str(bad_file))
    assert result is None


def test_checkpoint_loop_validation():
    # loop_count > max_loops should fail validation
    with pytest.raises(ValueError):
        TaskCheckpoint(loop_count=6, max_loops=5)

    # max_loops < 1 should fail validation
    with pytest.raises(ValueError):
        TaskCheckpoint(loop_count=0, max_loops=0)


@pytest.mark.asyncio
async def test_reconcile_from_tabs_ignores_trailing_loading_node():
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose"},
        chatgpt={"last_response": "div.assistant"},
    )
    mock_p_tab = AsyncMock()
    valid_el = AsyncMock()
    valid_el.inner_text = AsyncMock(return_value="[STATUS: READY_FOR_DEV]\n[TASK]: Build feature")
    loading_el = AsyncMock()
    loading_el.inner_text = AsyncMock(return_value="Thinking... [Citation 1]")

    # Trailing element is loading/citation without protocol status
    mock_p_tab.query_selector_all = AsyncMock(return_value=[valid_el, loading_el])

    mock_c_tab = AsyncMock()
    mock_c_tab.query_selector_all = AsyncMock(return_value=[])

    cp = await reconcile_from_tabs(
        p_tab=mock_p_tab,
        c_tab=mock_c_tab,
        repo="owner/repo",
        branch="main",
        goal="Test feature",
        selectors=selectors,
        current_loop_count=3,
    )
    # Should successfully parse the valid preceding element and preserve loop count
    assert cp.status_label == "READY_FOR_DEV"
    assert cp.loop_count == 3
    assert cp.last_successful_agent == "perplexity"
    assert cp.next_target_agent == "chatgpt"


@pytest.mark.asyncio
async def test_checkpoint_normalizes_invalid_loop_state():
    selectors = SelectorsConfig(perplexity={}, chatgpt={})
    mock_p_tab = AsyncMock()
    mock_p_tab.query_selector_all = AsyncMock(return_value=[])
    mock_c_tab = AsyncMock()
    mock_c_tab.query_selector_all = AsyncMock(return_value=[])

    cp = await reconcile_from_tabs(
        p_tab=mock_p_tab,
        c_tab=mock_c_tab,
        repo="owner/repo",
        branch="main",
        goal="Test feature",
        selectors=selectors,
        max_loops=5,
        current_loop_count=10,
    )
    assert cp.loop_count <= cp.max_loops
    assert cp.max_loops == 5


def test_redaction_does_not_match_token_metadata():
    from core.checkpoint_manager import redact_secrets

    payload = {
        "token_count": 128,
        "token_budget": 4096,
        "session_count": 2,
        "tokenizer": "cl100k_base",
    }
    result = redact_secrets(payload)
    assert result == payload


def test_redacts_bearer_and_extended_tokens():
    from core.checkpoint_manager import redact_secrets, _REDACTED

    value = (
        "Bearer abc-secret-token "
        "ghp_abcdefghijklmnopqrstuvwxyz123456 "
        "github_pat_11AAAAAAA0123456789_abcdefg "
        "xoxb-1234567890-abcdef "
        "xoxp-9876543210-fedcba"
    )
    result = redact_secrets(value)
    assert "abc-secret-token" not in result
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in result
    assert "github_pat_11AAAAAAA0123456789_abcdefg" not in result
    assert "xoxb-1234567890-abcdef" not in result
    assert "xoxp-9876543210-fedcba" not in result
    assert _REDACTED in result


@pytest.mark.asyncio
async def test_reconcile_from_tabs_max_loops_reached_on_revision():
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

    # Calling with current_loop_count=5 and max_loops=5
    cp = await reconcile_from_tabs(
        p_tab=mock_p_tab,
        c_tab=mock_c_tab,
        repo="owner/repo",
        branch="main",
        goal="Test feature",
        selectors=selectors,
        current_loop_count=5,
        max_loops=5,
    )
    assert cp.status_label == "MAX_LOOPS_REACHED"
    assert cp.loop_count == 5
    assert cp.next_target_agent == "none"
    assert cp.next_prompt_payload == ""


def test_loop_count_is_not_above_max_loops():
    with pytest.raises(ValidationError):
        TaskCheckpoint(
            loop_count=6,
            max_loops=5,
        )


def test_redacts_secrets_in_url_query():
    from core.checkpoint_manager import redact_secrets

    url = "https://example.com/oauth/callback?access_token=secret_tok_12345&scope=read#section"
    result = redact_secrets(url)
    assert "secret_tok_12345" not in result
    assert result == "https://example.com/oauth/callback?access_token=[REDACTED]&scope=read#section"


@pytest.mark.asyncio
async def test_reconcile_from_tabs_rejects_unrelated_repo_commit():
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.prose"},
        chatgpt={"last_response": "div.assistant"},
    )
    mock_p_tab = AsyncMock()
    mock_p_tab.query_selector_all = AsyncMock(return_value=[])

    mock_c_tab = AsyncMock()
    mock_c_el = AsyncMock()
    mock_c_el.inner_text = AsyncMock(return_value="""
    [STATUS: COMMITTED]
    [REPO: other-owner/completely-different-repo]
    [BRANCH: ai-agent/feature-x]
    [COMMIT_SHA: 9d7e03b]
    PR_URL: https://github.com/other-owner/completely-different-repo/pull/1
    """)
    mock_c_tab.query_selector_all = AsyncMock(return_value=[mock_c_el])

    cp = await reconcile_from_tabs(
        p_tab=mock_p_tab,
        c_tab=mock_c_tab,
        repo="my-org/my-project",
        branch="main",
        goal="Build feature",
        selectors=selectors,
    )
    # Because repo doesn't match, commit evidence is discarded and fallback to IDLE
    assert cp.status_label == "IDLE"
    assert cp.loop_count == 0
    assert cp.last_successful_agent == ""
    assert cp.next_target_agent == "perplexity"


@pytest.mark.asyncio
async def test_checkpoint_store_save_load_clear(tmp_path):
    store = CheckpointStore()
    cp_file = str(tmp_path / "store_test.json")
    cp = TaskCheckpoint(
        repo="my-org/my-project",
        branch="main",
        goal="Test store",
        loop_count=1,
        max_loops=5,
    )

    await store.save(cp, path=cp_file)
    loaded = await store.load(path=cp_file)
    assert loaded is not None
    assert loaded.repo == "my-org/my-project"
    assert loaded.loop_count == 1

    await store.clear(path=cp_file)
    assert await store.load(path=cp_file) is None

