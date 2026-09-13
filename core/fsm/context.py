import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from core.tag_protocol import TagParseResult


class FSMState(str, Enum):
    IDLE = "IDLE"
    PERPLEXITY_SENDING = "PERPLEXITY_SENDING"
    PERPLEXITY_WAITING = "PERPLEXITY_WAITING"
    PERPLEXITY_PARSING = "PERPLEXITY_PARSING"
    WAITING_USER_APPROVAL = "WAITING_USER_APPROVAL"
    CHATGPT_SENDING = "CHATGPT_SENDING"
    CHATGPT_WAITING = "CHATGPT_WAITING"
    CHATGPT_PARSING = "CHATGPT_PARSING"
    MAX_LOOPS_HALTED = "MAX_LOOPS_HALTED"
    TASK_FINISHED = "TASK_FINISHED"
    PAUSED = "PAUSED"
    ABORTED = "ABORTED"
    RECONNECTING = "RECONNECTING"
    CDP_ERROR = "CDP_ERROR"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECONCILING = "RECONCILING"


@dataclass
class RunContext:
    current_turn: str = "perplexity"  # "perplexity" | "chatgpt" | "approval" | "done"
    loop_count: int = 0
    max_loops: int = 5
    auto_mode: bool = True
    is_running: bool = True
    state: FSMState = FSMState.IDLE

    # Task specification
    current_repo: str = ""
    current_branch: str = ""
    current_goal: str = ""

    # Artifact tracking
    feature_branch: str = ""
    commit_sha: str = ""
    pr_url: str = ""

    # Payload & prompt tracking
    next_prompt: str = ""
    pending_payload: str = ""
    target_agent_for_pending: str = ""
    last_attempted_agent: str = ""
    last_attempted_payload: str = ""
    last_raw_response: str = ""
    last_error: Optional[str] = None

    # Callbacks & Events
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    on_state_change: Optional[Callable[[FSMState], None]] = None
    on_log: Optional[Callable[[str, str], None]] = None
    on_approval_required: Optional[Callable[[str, TagParseResult], None]] = None
    logs: list[dict[str, Any]] = field(default_factory=list)

    def set_state(self, new_state: FSMState) -> None:
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def log(self, source: str, message: str) -> None:
        self.logs.append({"timestamp": time.time(), "source": source, "message": message})
        if self.on_log:
            self.on_log(source, message)
