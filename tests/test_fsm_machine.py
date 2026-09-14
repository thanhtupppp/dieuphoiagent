import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest

from core.checkpoint_manager import clear_checkpoint, load_checkpoint, reconcile_from_tabs
from core.config_loader import SelectorsConfig
from core.fsm.context import FSMState, RunContext
from core.fsm.machine import run_fsm, save_session_record
from core.fsm.states import StateHandler
from core.providers.base import AgentProvider, AgentRequest, AgentResponse, ProviderKind


class DummyTestProvider(AgentProvider):
    kind = ProviderKind.LOCAL

    async def send(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(content="OK")

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class ImmediateDoneHandler(StateHandler):
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        context.set_state(FSMState.TASK_FINISHED)
        return "done"


class LoopingHandler(StateHandler):
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        context.loop_count += 1
        return "perplexity"


class FailingHandler(StateHandler):
    async def handle(self, context: RunContext, provider: AgentProvider) -> str:
        raise RuntimeError("Intentional state failure")


@pytest.mark.asyncio
async def test_run_fsm_completes_successfully():
    ctx = RunContext(current_repo="test/repo", current_turn="test_state")
    provider = DummyTestProvider()
    transitions = {"test_state": ImmediateDoneHandler()}

    await run_fsm(ctx, provider, transitions=transitions)
    assert ctx.state == FSMState.TASK_FINISHED


@pytest.mark.asyncio
async def test_run_fsm_halts_on_max_loops():
    ctx = RunContext(
        current_repo="test/repo",
        current_turn="perplexity",
        max_loops=2,
        loop_count=0,
    )
    provider = DummyTestProvider()
    transitions = {"perplexity": LoopingHandler()}

    await run_fsm(ctx, provider, transitions=transitions)
    assert ctx.state == FSMState.MAX_LOOPS_HALTED
    assert ctx.loop_count == 2

    cp = load_checkpoint()
    assert cp is not None
    assert cp.status_label == "MAX_LOOPS_REACHED"
    assert cp.next_target_agent == "none"
    assert cp.loop_count <= cp.max_loops


@pytest.mark.asyncio
async def test_run_fsm_handles_exception_with_recovery():
    ctx = RunContext(current_repo="test/repo", current_turn="failing_state")
    provider = DummyTestProvider()
    transitions = {"failing_state": FailingHandler()}

    await run_fsm(ctx, provider, transitions=transitions)
    assert ctx.state == FSMState.RECOVERY_REQUIRED
    assert ctx.is_running is False
    assert ctx.last_error == "Intentional state failure"

    cp = load_checkpoint()
    assert cp is not None
    assert cp.status_label == "RECOVERY_REQUIRED"
    assert cp.error_message == "Intentional state failure"
    assert cp.loop_count <= cp.max_loops
    assert cp.next_target_agent in {"perplexity", "chatgpt", "none"}


def test_save_session_record(tmp_path):
    ctx = RunContext(
        current_repo="owner/myrepo",
        current_branch="main",
        current_goal="Build app",
        loop_count=3,
        feature_branch="ai-agent/feature",
        commit_sha="abcdef1",
        pr_url="https://github.com/owner/myrepo/pull/1",
    )
    ctx.log("system", "Test log message")
    filepath = save_session_record(ctx, "COMPLETED")

    assert Path(filepath).exists()
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["status"] == "COMPLETED"
    assert data["repo"] == "owner/myrepo"
    assert data["loops"] == 3
    assert len(data["events"]) == 1


@pytest.mark.asyncio
async def test_run_fsm_unknown_state_handler():
    ctx = RunContext(current_repo="test/repo", current_turn="missing_state")
    provider = DummyTestProvider()
    transitions = {"other_state": ImmediateDoneHandler()}

    await run_fsm(ctx, provider, transitions=transitions)
    assert ctx.state == FSMState.RECOVERY_REQUIRED
    assert "Unknown state handler for: missing_state" in ctx.last_error


@pytest.mark.asyncio
async def test_fsm_orchestration_happy_path_transitions_and_invariants():
    """Verify happy path IDLE -> READY_FOR_DEV -> COMMITTED -> COMPLETED with invariants."""
    clear_checkpoint()
    captured_checkpoints = []

    p_lead_resp = AgentResponse(
        content=(
            "[STATUS: READY_FOR_DEV]\n"
            "[SPEC]: Implement auth token refresh endpoint.\n"
            "[TARGET REPO]: owner/my-repo"
        )
    )
    c_dev_resp = AgentResponse(
        content=(
            "[STATUS: COMMITTED]\n"
            "[BRANCH: feat/auth-refresh]\n"
            "[COMMIT_SHA: 7a8b9c0]\n"
            "[PR_URL: https://github.com/owner/my-repo/pull/15]"
        )
    )
    p_review_resp = AgentResponse(
        content=(
            "[STATUS: COMPLETED]\n"
            "[SUMMARY]: PR #15 verified and approved for merge."
        )
    )

    class SequenceProvider(AgentProvider):
        kind = ProviderKind.LOCAL

        def __init__(self) -> None:
            self.calls = []
            self.responses = [p_lead_resp, c_dev_resp, p_review_resp]

        async def send(self, request: AgentRequest) -> AgentResponse:
            self.calls.append(request)
            return self.responses.pop(0)

        async def health_check(self) -> bool:
            return True

        async def close(self) -> None:
            pass

    provider = SequenceProvider()
    ctx = RunContext(
        current_repo="owner/my-repo",
        current_branch="main",
        current_goal="Add auth token refresh",
        loop_count=0,
        max_loops=3,
        auto_mode=True,
        save_checkpoint_fn=lambda cp: captured_checkpoints.append(cp),
    )

    await run_fsm(ctx, provider)

    assert ctx.state == FSMState.TASK_FINISHED
    assert ctx.feature_branch == "feat/auth-refresh"
    assert ctx.commit_sha == "7a8b9c0"
    assert ctx.pr_url == "https://github.com/owner/my-repo/pull/15"
    assert len(provider.calls) == 3

    assert len(captured_checkpoints) == 2

    for cp in captured_checkpoints:
        assert cp.loop_count <= cp.max_loops
        assert cp.next_target_agent in {"perplexity", "chatgpt", "none"}

    cp1 = captured_checkpoints[0]
    assert cp1.status_label == "READY_FOR_DEV"
    assert cp1.last_successful_agent == "perplexity"
    assert cp1.next_target_agent == "chatgpt"
    assert cp1.loop_count == 1
    assert cp1.max_loops == 3

    cp2 = captured_checkpoints[1]
    assert cp2.status_label == "COMMITTED"
    assert cp2.last_successful_agent == "chatgpt"
    assert cp2.next_target_agent == "perplexity"
    assert cp2.feature_branch == "feat/auth-refresh"
    assert cp2.commit_sha == "7a8b9c0"
    assert cp2.pr_url == "https://github.com/owner/my-repo/pull/15"
    assert cp2.loop_count == 1
    assert cp2.max_loops == 3


@pytest.mark.asyncio
async def test_fsm_orchestration_revision_loop_to_max_loops_invariants():
    """Verify revision cycle: READY_FOR_DEV -> COMMITTED -> NEEDS_REVISION -> COMMITTED -> MAX_LOOPS_HALTED."""
    clear_checkpoint()
    captured_checkpoints = []

    p_turn1 = AgentResponse(
        content="[STATUS: READY_FOR_DEV]\n[SPEC]: Initial implementation."
    )
    c_turn1 = AgentResponse(
        content=(
            "[STATUS: COMMITTED]\n"
            "[BRANCH: feat/retry-flow]\n"
            "[COMMIT_SHA: 1111111]\n"
            "[PR_URL: https://github.com/owner/repo/pull/1]"
        )
    )
    p_turn2 = AgentResponse(
        content=(
            "[STATUS: NEEDS_REVISION]\n"
            "[ISSUES]: Missing validation for negative numbers."
        )
    )
    c_turn2 = AgentResponse(
        content=(
            "[STATUS: COMMITTED]\n"
            "[BRANCH: feat/retry-flow]\n"
            "[COMMIT_SHA: 2222222]\n"
            "[PR_URL: https://github.com/owner/repo/pull/1]"
        )
    )

    class RevisionSequenceProvider(AgentProvider):
        kind = ProviderKind.LOCAL

        def __init__(self) -> None:
            self.responses = [p_turn1, c_turn1, p_turn2, c_turn2]

        async def send(self, request: AgentRequest) -> AgentResponse:
            return self.responses.pop(0)

        async def health_check(self) -> bool:
            return True

        async def close(self) -> None:
            pass

    provider = RevisionSequenceProvider()
    ctx = RunContext(
        current_repo="owner/repo",
        current_branch="main",
        current_goal="Implement retry flow",
        loop_count=0,
        max_loops=2,
        auto_mode=True,
        save_checkpoint_fn=lambda cp: captured_checkpoints.append(cp),
    )

    await run_fsm(ctx, provider)

    assert ctx.state == FSMState.MAX_LOOPS_HALTED
    assert ctx.loop_count == 2
    assert ctx.max_loops == 2

    # Checkpoints captured: 2 from turn 1, 2 from turn 2, 1 on halt
    assert len(captured_checkpoints) == 5

    for cp in captured_checkpoints:
        assert cp.loop_count <= cp.max_loops
        assert cp.next_target_agent in {"perplexity", "chatgpt", "none"}

    final_cp = captured_checkpoints[-1]
    assert final_cp.status_label == "MAX_LOOPS_REACHED"
    assert final_cp.next_target_agent == "none"
    assert final_cp.loop_count == 2
    assert final_cp.max_loops == 2


@pytest.mark.asyncio
async def test_fsm_recovery_checkpoint_invariant_with_out_of_bounds_loops():
    """Verify recovery checkpoint normalizes out-of-bounds loop_count/max_loops without error."""
    captured_checkpoints = []
    ctx = RunContext(
        current_repo="test/repo",
        current_turn="failing_state",
        loop_count=99,
        max_loops=3,
        save_checkpoint_fn=lambda cp: captured_checkpoints.append(cp),
    )
    provider = DummyTestProvider()
    transitions = {"failing_state": FailingHandler()}

    await run_fsm(ctx, provider, transitions=transitions)

    assert ctx.state == FSMState.RECOVERY_REQUIRED
    assert len(captured_checkpoints) == 1
    cp = captured_checkpoints[0]
    assert cp.loop_count <= cp.max_loops
    assert cp.loop_count == 3
    assert cp.max_loops == 3
    assert cp.status_label == "RECOVERY_REQUIRED"
    assert cp.next_target_agent in {"perplexity", "chatgpt", "none"}


@pytest.mark.asyncio
async def test_reconcile_from_tabs_all_state_invariants():
    """Verify reconcile_from_tabs preserves loop bounds and valid next agent across all states."""
    selectors = SelectorsConfig(
        perplexity={"last_response": "div.p-resp"},
        chatgpt={"last_response": "div.c-resp"},
    )

    def make_mock_tab(text: str):
        tab = AsyncMock()
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value=text)
        tab.query_selector_all = AsyncMock(return_value=[el] if text else [])
        return tab

    # 1. IDLE (empty tabs)
    p_tab_idle = make_mock_tab("")
    c_tab_idle = make_mock_tab("")
    cp_idle = await reconcile_from_tabs(
        p_tab=p_tab_idle,
        c_tab=c_tab_idle,
        repo="owner/repo",
        branch="main",
        goal="Task goal",
        selectors=selectors,
        max_loops=5,
        current_loop_count=0,
    )
    assert cp_idle.status_label == "IDLE"
    assert cp_idle.loop_count <= cp_idle.max_loops
    assert cp_idle.next_target_agent in {"perplexity", "chatgpt", "none"}
    assert cp_idle.next_target_agent == "perplexity"

    # 2. READY_FOR_DEV
    p_tab_rfd = make_mock_tab("[STATUS: READY_FOR_DEV]\n[SPEC]: Do feature")
    c_tab_rfd = make_mock_tab("")
    cp_rfd = await reconcile_from_tabs(
        p_tab=p_tab_rfd,
        c_tab=c_tab_rfd,
        repo="owner/repo",
        branch="main",
        goal="Task goal",
        selectors=selectors,
        max_loops=5,
        current_loop_count=1,
    )
    assert cp_rfd.status_label == "READY_FOR_DEV"
    assert cp_rfd.loop_count <= cp_rfd.max_loops
    assert cp_rfd.next_target_agent in {"perplexity", "chatgpt", "none"}
    assert cp_rfd.next_target_agent == "chatgpt"

    # 3. COMMITTED_AWAITING_REVIEW
    c_text_committed = (
        "[STATUS: COMMITTED]\n"
        "[BRANCH: feat/test]\n"
        "[COMMIT_SHA: 1234567]\n"
        "[PR_URL: https://github.com/owner/repo/pull/1]"
    )
    p_tab_empty = make_mock_tab("")
    c_tab_committed = make_mock_tab(c_text_committed)
    cp_comm = await reconcile_from_tabs(
        p_tab=p_tab_empty,
        c_tab=c_tab_committed,
        repo="owner/repo",
        branch="main",
        goal="Task goal",
        selectors=selectors,
        max_loops=5,
        current_loop_count=1,
    )
    assert cp_comm.status_label == "COMMITTED_AWAITING_REVIEW"
    assert cp_comm.loop_count <= cp_comm.max_loops
    assert cp_comm.next_target_agent in {"perplexity", "chatgpt", "none"}
    assert cp_comm.next_target_agent == "perplexity"

    # 4. NEEDS_REVISION before limit (completed=1, max=3 -> next_loop=2)
    p_tab_rev = make_mock_tab("[STATUS: NEEDS_REVISION]\n[FEEDBACK]: Fix test")
    cp_rev = await reconcile_from_tabs(
        p_tab=p_tab_rev,
        c_tab=c_tab_committed,
        repo="owner/repo",
        branch="main",
        goal="Task goal",
        selectors=selectors,
        max_loops=3,
        current_loop_count=1,
    )
    assert cp_rev.status_label == "NEEDS_REVISION"
    assert cp_rev.loop_count == 2
    assert cp_rev.loop_count <= cp_rev.max_loops
    assert cp_rev.next_target_agent in {"perplexity", "chatgpt", "none"}
    assert cp_rev.next_target_agent == "chatgpt"

    # 5. NEEDS_REVISION at limit (completed=3, max=3 -> MAX_LOOPS_REACHED)
    cp_rev_limit = await reconcile_from_tabs(
        p_tab=p_tab_rev,
        c_tab=c_tab_committed,
        repo="owner/repo",
        branch="main",
        goal="Task goal",
        selectors=selectors,
        max_loops=3,
        current_loop_count=3,
    )
    assert cp_rev_limit.status_label == "MAX_LOOPS_REACHED"
    assert cp_rev_limit.loop_count == 3
    assert cp_rev_limit.loop_count <= cp_rev_limit.max_loops
    assert cp_rev_limit.next_target_agent in {"perplexity", "chatgpt", "none"}
    assert cp_rev_limit.next_target_agent == "none"

    # 6. COMPLETED
    p_tab_comp = make_mock_tab("[STATUS: COMPLETED]\n[SUMMARY]: All good")
    cp_comp = await reconcile_from_tabs(
        p_tab=p_tab_comp,
        c_tab=c_tab_committed,
        repo="owner/repo",
        branch="main",
        goal="Task goal",
        selectors=selectors,
        max_loops=5,
        current_loop_count=2,
    )
    assert cp_comp.status_label == "COMPLETED"
    assert cp_comp.loop_count <= cp_comp.max_loops
    assert cp_comp.next_target_agent in {"perplexity", "chatgpt", "none"}
    assert cp_comp.next_target_agent == "none"

