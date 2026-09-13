import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from core.config_loader import SelectorsConfig
from core.tag_protocol import AgentStatus, parse_agent_output


_REDACTED = "[REDACTED]"
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "cookie",
    "session",
    "authorization",
    "auth",
)


class TaskCheckpoint(BaseModel):
    repo: str = ""
    branch: str = "main"
    goal: str = ""
    loop_count: int = 0
    max_loops: int = 5
    auto_mode: bool = True
    last_successful_agent: str = ""  # "perplexity" | "chatgpt"
    next_target_agent: str = "perplexity"  # "perplexity" | "chatgpt"
    feature_branch: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    last_prompt: str = ""
    last_raw_response: str = ""
    next_prompt_payload: str = ""
    status_label: str = ""
    error_message: str = ""
    timestamp: float = Field(default_factory=time.time)


def _is_secret_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SECRET_KEY_PARTS)


def redact_secrets(value: Any, key: Optional[str] = None) -> Any:
    """Recursively remove credential-like values before checkpoint persistence."""
    if key is not None and _is_secret_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {
            item_key: redact_secrets(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    return value


def _secure_permissions(path: Path) -> None:
    """Best-effort owner-only permissions; Windows may ignore POSIX modes."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def save_checkpoint(checkpoint: TaskCheckpoint, path: str = "storage/checkpoint.json") -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = redact_secrets(checkpoint.model_dump())

    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temp_path = Path(temp_name)
    try:
        _secure_permissions(temp_path)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        _secure_permissions(temp_path)
        os.replace(temp_path, destination)
        _secure_permissions(destination)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def load_checkpoint(path: str = "storage/checkpoint.json") -> Optional[TaskCheckpoint]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TaskCheckpoint(**data)
    except Exception:
        return None


def clear_checkpoint(path: str = "storage/checkpoint.json") -> None:
    p = Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


def has_active_checkpoint(path: str = "storage/checkpoint.json") -> bool:
    cp = load_checkpoint(path)
    return cp is not None and bool(cp.repo)


async def reconcile_from_tabs(
    p_tab: Any,
    c_tab: Any,
    repo: str,
    branch: str,
    goal: str,
    selectors: SelectorsConfig,
    max_loops: int = 5,
    auto_mode: bool = True,
) -> TaskCheckpoint:
    """
    Inspects existing browser tabs (Perplexity & ChatGPT), analyzes their current messages,
    and automatically reconstructs an accurate TaskCheckpoint to resume directly without restarting.
    """
    p_text = ""
    s_p_resp = selectors.perplexity.get("last_response")
    if p_tab and hasattr(p_tab, "query_selector_all") and s_p_resp:
        try:
            p_els = await p_tab.query_selector_all(s_p_resp)
            if p_els:
                p_text = await p_els[-1].inner_text()
        except Exception:
            pass

    c_text = ""
    s_c_resp = selectors.chatgpt.get("last_response")
    if c_tab and hasattr(c_tab, "query_selector_all") and s_c_resp:
        try:
            c_els = await c_tab.query_selector_all(s_c_resp)
            if c_els:
                c_text = await c_els[-1].inner_text()
        except Exception:
            pass

    p_res = parse_agent_output(p_text, source="perplexity") if p_text else None
    c_res = parse_agent_output(c_text, source="chatgpt") if c_text else None

    try:
        p_lead_template = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
    except Exception:
        p_lead_template = ""
    try:
        c_dev_template = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")
    except Exception:
        c_dev_template = ""

    if c_res and c_res.status == AgentStatus.COMMITTED:
        pl = c_res.payload
        feat_branch = getattr(pl, "branch", "")
        commit_sha = getattr(pl, "commit_sha", "")
        pr_url = getattr(pl, "pr_url", "")

        if p_res and p_res.status == AgentStatus.COMPLETED:
            return TaskCheckpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=1,
                max_loops=max_loops,
                auto_mode=auto_mode,
                last_successful_agent="perplexity",
                next_target_agent="none",
                feature_branch=feat_branch,
                commit_sha=commit_sha,
                pr_url=pr_url,
                last_raw_response=p_text,
                status_label="COMPLETED",
            )
        if p_res and p_res.status == AgentStatus.NEEDS_REVISION:
            next_payload = (
                f"[BÁO CÁO SỰ CỐ / YÊU CẦU SỬA ĐỔI TỪ LEAD]:\n{p_text}\n"
                f"Hãy chỉnh sửa mã nguồn và commit cập nhật lên nhánh {feat_branch}."
            )
            return TaskCheckpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=2,
                max_loops=max_loops,
                auto_mode=auto_mode,
                last_successful_agent="perplexity",
                next_target_agent="chatgpt",
                feature_branch=feat_branch,
                commit_sha=commit_sha,
                pr_url=pr_url,
                last_raw_response=p_text,
                next_prompt_payload=next_payload,
                status_label="NEEDS_REVISION",
            )

        next_payload = (
            f"[KẾT QUẢ PULL REQUEST TỪ DEV]:\n{c_text}\n"
            "Hãy nghiệm thu mã nguồn này và xuất [STATUS: COMPLETED] nếu đạt chuẩn "
            "hoặc [STATUS: NEEDS_REVISION] nếu cần sửa."
        )
        return TaskCheckpoint(
            repo=repo,
            branch=branch,
            goal=goal,
            loop_count=1,
            max_loops=max_loops,
            auto_mode=auto_mode,
            last_successful_agent="chatgpt",
            next_target_agent="perplexity",
            feature_branch=feat_branch,
            commit_sha=commit_sha,
            pr_url=pr_url,
            last_raw_response=c_text,
            next_prompt_payload=next_payload,
            status_label="COMMITTED_AWAITING_REVIEW",
        )

    if p_res and p_res.status == AgentStatus.READY_FOR_DEV:
        chatgpt_prompt = f"{c_dev_template}\n\n[TASK_SPEC FROM TECH LEAD]:\n{p_text}\n\n[TARGET REPO]: {repo}"
        return TaskCheckpoint(
            repo=repo,
            branch=branch,
            goal=goal,
            loop_count=1,
            max_loops=max_loops,
            auto_mode=auto_mode,
            last_successful_agent="perplexity",
            next_target_agent="chatgpt",
            last_raw_response=p_text,
            next_prompt_payload=chatgpt_prompt,
            status_label="READY_FOR_DEV",
        )

    first_prompt = (
        f"{p_lead_template}\n\n[MỤC TIÊU BÀI TOÁN]:\nRepository: {repo}\n"
        f"Branch: {branch}\nYêu cầu: {goal}"
    )
    return TaskCheckpoint(
        repo=repo,
        branch=branch,
        goal=goal,
        loop_count=0,
        max_loops=max_loops,
        auto_mode=auto_mode,
        last_successful_agent="",
        next_target_agent="perplexity",
        next_prompt_payload=first_prompt,
        status_label="IDLE",
    )
