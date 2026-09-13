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
        AppConfig(default_max_loops=3),
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
        AppConfig(default_max_loops=3),
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


