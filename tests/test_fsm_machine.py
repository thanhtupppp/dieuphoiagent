import json
from pathlib import Path
import pytest

from core.checkpoint_manager import load_checkpoint
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

