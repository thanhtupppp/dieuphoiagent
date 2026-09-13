import asyncio
import pytest
from unittest.mock import AsyncMock

from core.fsm.context import FSMState, RunContext
from core.fsm.states import ApprovalHandler, ChatGptDevHandler, PerplexityLeadHandler
from core.providers.base import AgentProvider, AgentRequest, AgentResponse, ProviderKind


class DummyTestProvider(AgentProvider):
    kind = ProviderKind.LOCAL

    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.send_mock = AsyncMock(return_value=AgentResponse(content=response_text))

    async def send(self, request: AgentRequest) -> AgentResponse:
        return await self.send_mock(request)

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_perplexity_handler_completed():
    handler = PerplexityLeadHandler()
    provider = DummyTestProvider(
        "[STATUS: COMPLETED]\n[SUMMARY]: All changes validated and approved!"
    )
    ctx = RunContext(current_repo="test/repo", current_branch="main", current_goal="Test goal")

    next_state = await handler.handle(ctx, provider)
    assert next_state == "done"
    assert ctx.state == FSMState.TASK_FINISHED
    assert ctx.loop_count == 1


@pytest.mark.asyncio
async def test_perplexity_handler_to_chatgpt_auto():
    handler = PerplexityLeadHandler()
    provider = DummyTestProvider(
        "[STATUS: READY_FOR_DEV]\nPlan: Implement feature A\nFiles: src/a.py"
    )
    ctx = RunContext(
        current_repo="test/repo",
        current_branch="main",
        current_goal="Test goal",
        auto_mode=True,
    )

    next_state = await handler.handle(ctx, provider)
    assert next_state == "chatgpt"
    assert "Implement feature A" in ctx.next_prompt


@pytest.mark.asyncio
async def test_perplexity_handler_to_approval_manual():
    handler = PerplexityLeadHandler()
    provider = DummyTestProvider(
        "[STATUS: READY_FOR_DEV]\nPlan: Review required before dev"
    )
    ctx = RunContext(
        current_repo="test/repo",
        current_branch="main",
        current_goal="Test goal",
        auto_mode=False,
    )

    next_state = await handler.handle(ctx, provider)
    assert next_state == "approval"
    assert "Review required before dev" in ctx.pending_payload


@pytest.mark.asyncio
async def test_approval_handler():
    handler = ApprovalHandler()
    provider = DummyTestProvider()
    approval_called = False

    def on_approval(agent_name, result):
        nonlocal approval_called
        approval_called = True

    ctx = RunContext(
        pending_payload="Original payload",
        last_raw_response="[STATUS: READY_FOR_DEV]\nTask spec",
        on_approval_required=on_approval,
    )

    async def approve_after_delay():
        await asyncio.sleep(0.05)
        ctx.pending_payload = "Modified payload by user"
        ctx.approval_event.set()

    asyncio.create_task(approve_after_delay())
    next_state = await handler.handle(ctx, provider)

    assert next_state == "chatgpt"
    assert ctx.next_prompt == "Modified payload by user"
    assert approval_called is True


@pytest.mark.asyncio
async def test_chatgpt_dev_handler_success():
    handler = ChatGptDevHandler()
    provider = DummyTestProvider(
        "```json\n"
        "{\n"
        '  "status": "committed",\n'
        '  "branch": "ai-agent/feature-x",\n'
        '  "commit_sha": "f1a2b3c",\n'
        '  "pr_url": "https://github.com/test/repo/pull/12"\n'
        "}\n"
        "```"
    )
    ctx = RunContext(current_repo="test/repo", next_prompt="Initial prompt")

    next_state = await handler.handle(ctx, provider)
    assert next_state == "perplexity"
    assert ctx.feature_branch == "ai-agent/feature-x"
    assert ctx.commit_sha == "f1a2b3c"
    assert ctx.pr_url == "https://github.com/test/repo/pull/12"
    assert "[KẾT QUẢ PULL REQUEST TỪ DEV]" in ctx.next_prompt


@pytest.mark.asyncio
async def test_chatgpt_dev_handler_error():
    handler = ChatGptDevHandler()
    provider = DummyTestProvider("[STATUS: ERROR]\nBuild failed: syntax error in main.py")
    ctx = RunContext(current_repo="test/repo", next_prompt="Initial prompt")

    next_state = await handler.handle(ctx, provider)
    assert next_state == "perplexity"
    assert "[BÁO CÁO SỰ CỐ TỪ DEV]" in ctx.next_prompt
