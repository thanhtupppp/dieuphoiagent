import asyncio
import json
import logging
from enum import Enum
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    TRANSIENT = "transient"  # Network, timeout, temporary tab glitches -> retry
    FORMAT = "format"        # Output parsing or contract validation error -> format retry
    FATAL = "fatal"          # Authentication expired, selector break -> immediate halt


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    error_type: ErrorType = ErrorType.FATAL


class TransientError(OrchestratorError):
    """Temporary errors that can be resolved with retry and backoff."""
    error_type = ErrorType.TRANSIENT


class FormatError(OrchestratorError):
    """Model output parsing or schema validation failures."""
    error_type = ErrorType.FORMAT


class FatalError(OrchestratorError):
    """Unrecoverable errors requiring human intervention."""
    error_type = ErrorType.FATAL


class CircuitBreakerTrippedError(FatalError):
    """Raised when continuous transient failures trip the circuit breaker."""
    pass


def classify_error(exc: Exception) -> ErrorType:
    """Classify an exception into TRANSIENT, FORMAT, or FATAL."""
    if isinstance(exc, OrchestratorError):
        return exc.error_type

    msg = str(exc).lower()

    # Fatal conditions (auth, selectors, explicit permission errors)
    if any(k in msg for k in ["unauthorized", "authentication", "forbidden", "login", "invalid api key", "selector"]):
        return ErrorType.FATAL

    # Builtin transient network and OS errors
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return ErrorType.TRANSIENT

    # Network, disconnection, tab reload, or browser crashes
    if any(
        k in msg
        for k in [
            "timeout",
            "connection closed",
            "closed pipe",
            "disconnected",
            "reset by peer",
            "target closed",
            "page closed",
            "browser has been closed",
            "net::",
        ]
    ):
        return ErrorType.TRANSIENT

    # Format and parsing errors
    if isinstance(exc, json.JSONDecodeError):
        return ErrorType.FORMAT

    if isinstance(exc, (ValueError, TypeError)) and any(
        k in msg for k in ["json", "format", "contract", "schema", "parse", "unmarshal", "decode"]
    ):
        return ErrorType.FORMAT

    return ErrorType.FATAL


class CircuitBreaker:
    """Protects browser tabs and external APIs from runaway failure cascades."""

    def __init__(self, max_failures: int = 5):
        self.failures = 0
        self.max_failures = max_failures

    @property
    def is_tripped(self) -> bool:
        return self.failures >= self.max_failures

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.max_failures:
            raise CircuitBreakerTrippedError(
                f"Circuit breaker tripped: {self.failures} lỗi liên tiếp vượt ngưỡng an toàn ({self.max_failures})"
            )

    def record_success(self) -> None:
        self.failures = 0

    def reset(self) -> None:
        self.failures = 0


async def with_retry(
    coro_fn: Callable[[], Coroutine[Any, Any, T]],
    *,
    attempts: int = 3,
    base: float = 2.0,
    max_format_attempts: int = 2,
    on_retry: Optional[Callable[[int, int, float, Exception], None]] = None,
) -> T:
    """Execute an async function with exponential backoff for transient errors, and up to 2 format retries."""
    format_attempts = 0
    for i in range(attempts):
        try:
            return await coro_fn()
        except Exception as e:
            err_type = classify_error(e)
            if err_type == ErrorType.FATAL:
                raise

            if err_type == ErrorType.FORMAT:
                format_attempts += 1
                if format_attempts >= max_format_attempts or i == attempts - 1:
                    raise
                wait = 0.5
                logger.warning(
                    "Format retry %d/%d due to %s: %s",
                    format_attempts,
                    max_format_attempts,
                    type(e).__name__,
                    e,
                )
                if on_retry:
                    on_retry(i + 1, attempts, wait, e)
                await asyncio.sleep(wait)
                continue

            # Transient error
            if i == attempts - 1:
                raise

            wait = base ** i
            logger.warning(
                "Retry %d/%d after %.1fs due to %s: %s",
                i + 1,
                attempts,
                wait,
                type(e).__name__,
                e,
            )
            if on_retry:
                on_retry(i + 1, attempts, wait, e)
            await asyncio.sleep(wait)

    raise RuntimeError("Retry loop exhausted without result")

