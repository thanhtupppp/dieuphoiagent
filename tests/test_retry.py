import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.fsm.context import FSMState, RunContext
from core.fsm.machine import run_fsm
from core.fsm.retry import (
    CircuitBreaker,
    CircuitBreakerTrippedError,
    ErrorType,
    FatalError,
    FormatError,
    OrchestratorError,
    TransientError,
    classify_error,
    with_retry,
)
from core.fsm.states import StateHandler
from core.providers.base import AgentProvider


def test_error_types_and_custom_exceptions():
    assert ErrorType.TRANSIENT == "transient"
    assert ErrorType.FORMAT == "format"
    assert ErrorType.FATAL == "fatal"

    assert issubclass(TransientError, OrchestratorError)
    assert issubclass(FormatError, OrchestratorError)
    assert issubclass(FatalError, OrchestratorError)
    assert issubclass(CircuitBreakerTrippedError, FatalError)

    assert TransientError().error_type == ErrorType.TRANSIENT
    assert FormatError().error_type == ErrorType.FORMAT
    assert FatalError().error_type == ErrorType.FATAL
    assert CircuitBreakerTrippedError().error_type == ErrorType.FATAL


def test_classify_error_custom_exceptions():
    assert classify_error(TransientError("test")) == ErrorType.TRANSIENT
    assert classify_error(FormatError("test")) == ErrorType.FORMAT
    assert classify_error(FatalError("test")) == ErrorType.FATAL
    assert classify_error(CircuitBreakerTrippedError("test")) == ErrorType.FATAL


def test_classify_error_fatal_keywords():
    assert classify_error(RuntimeError("Unauthorized access to endpoint")) == ErrorType.FATAL
    assert classify_error(ValueError("Authentication failed: invalid token")) == ErrorType.FATAL
    assert classify_error(Exception("403 Forbidden")) == ErrorType.FATAL
    assert classify_error(Exception("Login required to view tab")) == ErrorType.FATAL
    assert classify_error(Exception("Invalid API key provided")) == ErrorType.FATAL
    assert classify_error(Exception("Selector '#prompt-textarea' not found in DOM")) == ErrorType.FATAL


def test_classify_error_transient_exceptions():
    assert classify_error(TimeoutError("Connection timed out")) == ErrorType.TRANSIENT
    assert classify_error(ConnectionError("Connection lost")) == ErrorType.TRANSIENT
    assert classify_error(OSError("Pipe broken")) == ErrorType.TRANSIENT
    assert classify_error(Exception("Target closed")) == ErrorType.TRANSIENT
    assert classify_error(Exception("Page closed unexpectedly")) == ErrorType.TRANSIENT
    assert classify_error(Exception("Browser has been closed")) == ErrorType.TRANSIENT
    assert classify_error(Exception("net::ERR_CONNECTION_RESET")) == ErrorType.TRANSIENT
    assert classify_error(Exception("Connection reset by peer")) == ErrorType.TRANSIENT


def test_classify_error_format_exceptions():
    try:
        json.loads("{invalid json")
    except Exception as e:
        assert classify_error(e) == ErrorType.FORMAT

    assert classify_error(ValueError("Contract schema validation failed")) == ErrorType.FORMAT
    assert classify_error(TypeError("JSON decode error in output format")) == ErrorType.FORMAT


def test_classify_error_fallback_fatal():
    assert classify_error(KeyError("missing_key")) == ErrorType.FATAL
    assert classify_error(RuntimeError("unexpected state encountered")) == ErrorType.FATAL


def test_circuit_breaker_flow():
    cb = CircuitBreaker(max_failures=3)
    assert cb.failures == 0
    assert not cb.is_tripped

    cb.record_failure()
    assert cb.failures == 1
    assert not cb.is_tripped

    cb.record_failure()
    assert cb.failures == 2
    assert not cb.is_tripped

    with pytest.raises(CircuitBreakerTrippedError, match="lỗi liên tiếp vượt ngưỡng"):
        cb.record_failure()

    assert cb.failures == 3
    assert cb.is_tripped

    cb.reset()
    assert cb.failures == 0
    assert not cb.is_tripped

    cb.record_failure()
    assert cb.failures == 1
    cb.record_success()
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_with_retry_immediate_success():
    mock_fn = AsyncMock(return_value="hello world")
    result = await with_retry(mock_fn, attempts=3, base=1.0)
    assert result == "hello world"
    assert mock_fn.await_count == 1


@pytest.mark.asyncio
async def test_with_retry_transient_recovery():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("Temporarily disconnected")
        return "recovered"

    retry_logs = []

    def on_retry(att, max_att, wait, exc):
        retry_logs.append((att, max_att, wait, str(exc)))

    result = await with_retry(flaky, attempts=3, base=0.01, on_retry=on_retry)
    assert result == "recovered"
    assert calls == 3
    assert len(retry_logs) == 2


@pytest.mark.asyncio
async def test_with_retry_format_recovery():
    calls = 0
    format_retry_logs = []

    async def bad_format_then_good():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FormatError("Missing JSON markdown block")
        return "parsed successfully"

    def on_retry(att, max_att, wait, exc):
        format_retry_logs.append((att, max_att, wait, str(exc)))

    result = await with_retry(
        bad_format_then_good,
        attempts=3,
        base=0.01,
        max_format_attempts=2,
        on_retry=on_retry,
    )
    assert result == "parsed successfully"
    assert calls == 2
    assert len(format_retry_logs) == 1

    with pytest.raises(RuntimeError, match="Retry loop exhausted without result"):
        await with_retry(bad_format_then_good, attempts=0)


@pytest.mark.asyncio
async def test_with_retry_format_exhausted():
    calls = 0

    async def bad_format_always():
        nonlocal calls
        calls += 1
        raise FormatError("Bad schema syntax")

    with pytest.raises(FormatError, match="Bad schema syntax"):
        await with_retry(bad_format_always, attempts=3, base=0.01, max_format_attempts=2)

    assert calls == 2


@pytest.mark.asyncio
async def test_with_retry_fatal_no_retry():
    calls = 0

    async def fail_fatal():
        nonlocal calls
        calls += 1
        raise FatalError("Selector #invalid changed")

    with pytest.raises(FatalError, match="Selector #invalid changed"):
        await with_retry(fail_fatal, attempts=5, base=0.01)

    assert calls == 1


@pytest.mark.asyncio
async def test_with_retry_exhaustion():
    calls = 0

    async def always_timeout():
        nonlocal calls
        calls += 1
        raise TimeoutError("Still timed out")

    with pytest.raises(TimeoutError, match="Still timed out"):
        await with_retry(always_timeout, attempts=3, base=0.01)

    assert calls == 3


@pytest.mark.asyncio
async def test_fsm_circuit_breaker_tripping():
    class FailingTransientHandler(StateHandler):
        async def handle(self, context: RunContext, provider: AgentProvider) -> str:
            raise TransientError("Browser target closed")

    ctx = RunContext(
        current_turn="fail_state",
        current_repo="owner/repo",
        current_branch="main",
        current_goal="test CB",
    )
    cb = CircuitBreaker(max_failures=3)
    provider = MagicMock(spec=AgentProvider)
    transitions = {"fail_state": FailingTransientHandler()}

    # Run FSM with failing handler
    await run_fsm(ctx, provider, transitions=transitions, circuit_breaker=cb)

    assert ctx.state == FSMState.RECOVERY_REQUIRED
    assert ctx.is_running is False
    assert cb.is_tripped is False  # 1 failure so far
    assert cb.failures == 1

    # Record 2 more failures to trip the circuit breaker
    cb.record_failure()
    assert cb.failures == 2

    # Third failure trips
    with pytest.raises(CircuitBreakerTrippedError):
        cb.record_failure()

    assert cb.is_tripped is True
