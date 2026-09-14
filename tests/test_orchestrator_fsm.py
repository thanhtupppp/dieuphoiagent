import asyncio
from unittest.mock import AsyncMock

import pytest

from core.config_loader import AppConfig, SelectorsConfig
from core.orchestrator_fsm import FSMState, OrchestratorFSM
from core.providers.base import AgentProvider, AgentRequest, AgentResponse, AgentRole, ProviderKind


class DummyProvider(AgentProvider):
    kind = ProviderKind.LOCAL

    def __init__(self) -> None:
        self.send_mock = AsyncMock()
        self.health_mock = AsyncMock(return_value=True)
        self.close_mock = AsyncMock()

    async def send(self, request: AgentRequest) -> AgentResponse:
        return await self.send_mock(request)

    async def health_check(self) -> bool:
        return await self.health_mock()

    async def close(self) -> None:
        await self.close_mock()


def test_fsm_initial_state():
    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))
    assert fsm.state == FSMState.IDLE
    assert fsm.loop_count == 0


def test_fsm_stop_and_abort():
    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))
    fsm.state = FSMState.PERPLEXITY_WAITING
    fsm.stop()
    assert fsm.state == FSMState.IDLE
    fsm.state = FSMState.CHATGPT_WAITING
    fsm.abort()
    assert fsm.state == FSMState.ABORTED


@pytest.mark.asyncio
async def test_fsm_ensure_cdp_delegates_to_provider_healthy():
    provider = DummyProvider()
    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    assert await fsm.ensure_cdp() is True
    assert fsm.state == FSMState.IDLE
    provider.health_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_fsm_ensure_cdp_handles_unhealthy_provider():
    provider = DummyProvider()
    provider.health_mock.return_value = False
    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    assert await fsm.ensure_cdp() is False
    assert fsm.state == FSMState.CDP_ERROR


@pytest.mark.asyncio
async def test_fsm_ensure_cdp_handles_provider_exception():
    provider = DummyProvider()
    provider.health_mock.side_effect = RuntimeError("Connection timeout")
    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    assert await fsm.ensure_cdp() is False
    assert fsm.state == FSMState.CDP_ERROR


@pytest.mark.asyncio
async def test_fsm_runs_task_via_provider():
    provider = DummyProvider()
    provider.send_mock.return_value = AgentResponse(
        content="""
        [STATUS: COMPLETED]
        [SUMMARY]: Everything looks perfect and meets all acceptance criteria!
        """,
    )
    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )

    await fsm.start_task("test/repo", "main", "Fix issue", max_loops=3, auto_mode=True)
    await asyncio.sleep(0.3)

    assert fsm.state == FSMState.TASK_FINISHED
    provider.send_mock.assert_awaited_once()
    sent_request = provider.send_mock.call_args[0][0]
    assert sent_request.role == AgentRole.TECH_LEAD
    assert "test/repo" in sent_request.user_prompt


@pytest.mark.asyncio
async def test_fsm_two_turn_loop_with_provider():
    provider = DummyProvider()
    perplexity_turn_1 = AgentResponse(
        content="""
        [STATUS: READY_FOR_DEV]
        [SPEC]: Implement greeting endpoint.
        """,
    )
    chatgpt_turn_1 = AgentResponse(
        content="""
        [STATUS: COMMITTED]
        [BRANCH: feat/greeting]
        [COMMIT_SHA: 8a1f4b2]
        [PR_URL: https://github.com/test/repo/pull/12]
        """,
    )
    perplexity_turn_2 = AgentResponse(
        content="""
        [STATUS: COMPLETED]
        [SUMMARY]: PR 12 reviewed and approved.
        """,
    )
    provider.send_mock.side_effect = [
        perplexity_turn_1,
        chatgpt_turn_1,
        perplexity_turn_2,
    ]

    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )

    await fsm.start_task("test/repo", "main", "Build feature", max_loops=3, auto_mode=True)
    await asyncio.sleep(0.5)

    assert fsm.state == FSMState.TASK_FINISHED
    assert fsm.feature_branch == "feat/greeting"
    assert fsm.commit_sha == "8a1f4b2"
    assert fsm.pr_url == "https://github.com/test/repo/pull/12"
    assert provider.send_mock.await_count == 3

    calls = provider.send_mock.call_args_list
    assert calls[0][0][0].role == AgentRole.TECH_LEAD
    assert calls[1][0][0].role == AgentRole.CORE_DEV
    assert calls[2][0][0].role == AgentRole.TECH_LEAD


@pytest.mark.asyncio
async def test_fsm_close_delegates_to_provider():
    provider = DummyProvider()
    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    await fsm.close()
    provider.close_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_fsm_circuit_breaker_reset_on_retry_step():
    provider = DummyProvider()
    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    fsm.circuit_breaker.failures = 4
    await fsm.retry_step()
    assert fsm.circuit_breaker.failures == 0


@pytest.mark.asyncio
async def test_start_task_concurrent_call_rejected():
    provider = DummyProvider()
    # Mock send that waits indefinitely until cancelled
    async def slow_send(req):
        await asyncio.sleep(10)
        return AgentResponse(content="[STATUS: COMPLETED]")

    provider.send_mock.side_effect = slow_send
    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    await fsm.start_task("test/repo", "main", "Task 1", max_loops=3)
    assert fsm._task_is_active()

    # Calling start_task again while running must raise RuntimeError
    with pytest.raises(RuntimeError, match="Một workflow khác đang chạy"):
        await fsm.start_task("test/repo", "main", "Task 2", max_loops=3)

    fsm.stop()
    await asyncio.sleep(0.05)
    assert not fsm._task_is_active()


@pytest.mark.asyncio
async def test_start_task_invalid_max_loops_and_timeout():
    fsm = OrchestratorFSM(
        AppConfig(timeout_seconds=600),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=DummyProvider(),
    )

    with pytest.raises(ValueError, match="max_loops phải lớn hơn hoặc bằng 1"):
        await fsm.start_task("repo", "main", "goal", max_loops=0)

    with pytest.raises(ValueError, match="timeout_seconds phải lớn hơn 0"):
        await fsm.start_task("repo", "main", "goal", max_loops=2, timeout_seconds=0)

    # Valid timeout_seconds should not mutate AppConfig
    original_config_timeout = fsm.config.timeout_seconds
    await fsm.start_task("repo", "main", "goal", max_loops=2, timeout_seconds=120)
    assert fsm.timeout_seconds == 120
    assert fsm.config.timeout_seconds == original_config_timeout
    fsm.stop()


@pytest.mark.asyncio
async def test_fsm_stop_cancels_running_task():
    provider = DummyProvider()
    provider.send_mock.side_effect = lambda req: asyncio.sleep(5)
    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    await fsm.start_task("test/repo", "main", "Task", max_loops=3)
    task = fsm._run_task
    assert task is not None
    assert not task.done()

    fsm.stop()
    assert fsm.state == FSMState.IDLE
    assert not fsm.is_running
    assert fsm.approval_event.is_set()
    await asyncio.sleep(0.05)
    assert task.done()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_fsm_abort_cancels_running_task():
    provider = DummyProvider()
    provider.send_mock.side_effect = lambda req: asyncio.sleep(5)
    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    await fsm.start_task("test/repo", "main", "Task", max_loops=3)
    task = fsm._run_task
    assert task is not None

    fsm.abort()
    assert fsm.state == FSMState.ABORTED
    assert not fsm.is_running
    assert fsm.approval_event.is_set()
    await asyncio.sleep(0.05)
    assert task.done()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_fsm_task_exception_handled_and_logged():
    from unittest.mock import patch

    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=DummyProvider(),
    )
    with patch("core.orchestrator_fsm.run_fsm", side_effect=RuntimeError("Uncaught fatal crash")):
        await fsm.start_task("test/repo", "main", "Task", max_loops=3)
        await asyncio.sleep(0.1)

    assert not fsm.is_running
    assert fsm.state == FSMState.CDP_ERROR
    assert any("FSM task thất bại: RuntimeError: Uncaught fatal crash" in e["message"] for e in fsm.session_events)


@pytest.mark.asyncio
async def test_fsm_close_cancels_and_awaits_running_task():
    provider = DummyProvider()
    provider.send_mock.side_effect = lambda req: asyncio.sleep(5)
    fsm = OrchestratorFSM(
        AppConfig(max_loops=3),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )
    await fsm.start_task("test/repo", "main", "Task", max_loops=3)
    task = fsm._run_task
    assert task is not None

    await fsm.close()
    assert task.done()
    assert task.cancelled()
    provider.close_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_terminal_checkpoint_does_not_start_agent():
    from core.checkpoint_manager import TaskCheckpoint

    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=DummyProvider(),
    )

    # Completed terminal checkpoint
    cp_done = TaskCheckpoint(
        repo="test/repo",
        branch="main",
        status_label="COMPLETED",
        next_target_agent="none",
    )
    await fsm.resume_from_checkpoint(cp_done)
    assert fsm.state == FSMState.TASK_FINISHED
    assert not fsm.is_running
    assert fsm._run_task is None

    # Max loops halted terminal checkpoint
    cp_halted = TaskCheckpoint(
        repo="test/repo",
        branch="main",
        status_label="MAX_LOOPS_REACHED",
        next_target_agent="none",
    )
    await fsm.resume_from_checkpoint(cp_halted)
    assert fsm.state == FSMState.MAX_LOOPS_HALTED
    assert not fsm.is_running
    assert fsm._run_task is None


@pytest.mark.asyncio
async def test_resume_preserves_loop_count_semantics():
    from core.checkpoint_manager import TaskCheckpoint

    provider = DummyProvider()
    fsm = OrchestratorFSM(
        AppConfig(),
        SelectorsConfig(perplexity={}, chatgpt={}),
        provider=provider,
    )

    # When resuming chatgpt with loop_count=4, it should NOT subtract 1
    cp = TaskCheckpoint(
        repo="test/repo",
        branch="main",
        loop_count=4,
        max_loops=5,
        status_label="NEEDS_REVISION",
        next_target_agent="chatgpt",
        next_prompt_payload="Fix bug",
    )
    await fsm.resume_from_checkpoint(cp)
    assert fsm.loop_count == 4
    fsm.stop()


@pytest.mark.asyncio
async def test_callbacks_isolated_from_exceptions():
    from core.fsm.context import RunContext
    from core.fsm.states import ApprovalHandler

    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))

    def bad_state_callback(state):
        raise RuntimeError("UI state error")

    def bad_log_callback(src, msg):
        raise RuntimeError("UI log error")

    def bad_approval_callback(agent, p_res):
        raise RuntimeError("UI approval modal error")

    fsm.on_state_change = bad_state_callback
    fsm.on_log = bad_log_callback

    # Neither should raise an exception out of set_state or log
    fsm.set_state(FSMState.PERPLEXITY_WAITING)
    assert fsm.state == FSMState.PERPLEXITY_WAITING

    fsm.log("system", "Test log message")
    assert len(fsm.session_events) >= 1

    # Test on_approval_required callback isolation in ApprovalHandler
    ctx = RunContext(
        on_approval_required=bad_approval_callback,
        last_raw_response="[STATUS: NEEDS_REVISION]",
        is_running=False,  # to exit wait immediately once event is set
    )
    handler = ApprovalHandler()

    async def trigger_approval():
        await asyncio.sleep(0.01)
        ctx.approval_event.set()

    asyncio.create_task(trigger_approval())
    res = await handler.handle(ctx, DummyProvider())
    assert res == "done"
    assert any("Callback on_approval_required bị lỗi" in log_entry["message"] for log_entry in ctx.logs)



