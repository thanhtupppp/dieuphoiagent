import json
import time
from pathlib import Path
from typing import Optional

from core.checkpoint_manager import TaskCheckpoint
from core.fsm.context import FSMState, RunContext
from core.fsm.states import (
    ApprovalHandler,
    ChatGptDevHandler,
    PerplexityLeadHandler,
    StateHandler,
)
from core.providers.base import AgentProvider

from core.fsm.retry import CircuitBreaker, ErrorType, classify_error

DEFAULT_TRANSITIONS: dict[str, StateHandler] = {
    "perplexity": PerplexityLeadHandler(),
    "chatgpt": ChatGptDevHandler(),
    "approval": ApprovalHandler(),
}


def save_session_record(context: RunContext, final_status: str) -> str:
    """Save execution telemetry session record to storage/sessions/."""
    Path("storage/sessions").mkdir(parents=True, exist_ok=True)
    filename = (
        f"storage/sessions/{int(time.time())}_"
        f"{context.current_repo.replace('/', '_')}.json"
    )
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            {
                "status": final_status,
                "repo": context.current_repo,
                "branch": context.current_branch,
                "goal": context.current_goal,
                "loops": context.loop_count,
                "feature_branch": context.feature_branch,
                "commit_sha": context.commit_sha,
                "pr_url": context.pr_url,
                "events": context.logs,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    return filename


async def run_fsm(
    context: RunContext,
    provider: AgentProvider,
    transitions: Optional[dict[str, StateHandler]] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> None:
    """Execute FSM loop transitioning across states according to the transition map."""
    table = transitions if transitions is not None else DEFAULT_TRANSITIONS
    breaker = circuit_breaker if circuit_breaker is not None else CircuitBreaker(max_failures=5)

    try:
        current_state = context.current_turn
        while context.is_running and current_state != "done":
            if current_state == "perplexity" and context.loop_count >= context.max_loops:
                context.set_state(FSMState.MAX_LOOPS_HALTED)
                context.log(
                    "system",
                    f"Đã chạm trần Max Loops ({context.max_loops}). Tạm dừng để người dùng duyệt tay.",
                )
                save_session_record(context, "HALTED")
                break

            handler = table.get(current_state)
            if not handler:
                raise ValueError(f"Unknown state handler for: {current_state}")

            try:
                current_state = await handler.handle(context, provider)
                context.current_turn = current_state
                breaker.record_success()
            except Exception as e:
                err_type = classify_error(e)
                if err_type == ErrorType.TRANSIENT:
                    breaker.record_failure()
                raise

            if current_state == "done" and context.state == FSMState.TASK_FINISHED:
                save_session_record(context, "COMPLETED")

        if (
            context.is_running
            and context.loop_count >= context.max_loops
            and context.state != FSMState.TASK_FINISHED
        ):
            context.set_state(FSMState.MAX_LOOPS_HALTED)
            context.log(
                "system",
                f"Đã chạm trần Max Loops ({context.max_loops}). Tạm dừng để người dùng duyệt tay.",
            )
            save_session_record(context, "HALTED")

    except Exception as e:
        err_msg = str(e) or type(e).__name__
        context.set_state(FSMState.RECOVERY_REQUIRED)
        context.is_running = False
        context.last_error = err_msg
        context.log(
            "system",
            f"Sự cố thực thi: {err_msg}. Đã lưu trạng thái phục hồi (Checkpoint).",
        )
        context.log(
            "system",
            "Hệ thống đang chờ lệnh cứu hộ: bạn có thể bấm 'Thử lại bước' "
            "(Retry) hoặc 'Tiếp tục từ Checkpoint' (Resume).",
        )
        context.save_checkpoint(
            TaskCheckpoint(
                repo=context.current_repo,
                branch=context.current_branch,
                goal=context.current_goal,
                loop_count=context.loop_count,
                max_loops=context.max_loops,
                auto_mode=context.auto_mode,
                last_successful_agent=context.last_attempted_agent,
                next_target_agent=context.last_attempted_agent or "perplexity",
                feature_branch=context.feature_branch,
                commit_sha=context.commit_sha,
                pr_url=context.pr_url,
                next_prompt_payload=context.last_attempted_payload,
                status_label="RECOVERY_REQUIRED",
                error_message=err_msg,
            )
        )
