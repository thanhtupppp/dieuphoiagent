import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from core.config_loader import SelectorsConfig
from core.tag_protocol import AgentStatus, parse_agent_output

logger = logging.getLogger(__name__)

_REDACTED = "[REDACTED]"

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "password",
    "passwd",
    "secret",
    "cookie",
    "session_cookie",
    "authorization",
    "auth_token",
}

_SECRET_SUFFIXES = (
    "_api_key",
    "_apikey",
    "_token",
    "_secret",
    "_password",
    "_passwd",
    "_cookie",
)

_SECRET_KEY_VALUE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token)"
        r"\s*[:=]\s*)[^\s,;]+"
    ),
    re.compile(r"(?i)((?:cookie|set-cookie)\s*[:=]\s*)[^\r\n]+"),
)

_SECRET_STANDALONE_PATTERNS = (
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bghp_[A-Za-z0-9]{30,}"),
)

AgentName = Literal["perplexity", "chatgpt", "none"]
LastAgentName = Literal["", "perplexity", "chatgpt"]


class TaskCheckpoint(BaseModel):
    repo: str = ""
    branch: str = "main"
    goal: str = ""
    loop_count: int = Field(default=0, ge=0)
    max_loops: int = Field(default=5, ge=1)
    auto_mode: bool = True
    last_successful_agent: LastAgentName = ""
    next_target_agent: AgentName = "perplexity"
    feature_branch: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    last_prompt: str = ""
    last_raw_response: str = ""
    next_prompt_payload: str = ""
    status_label: str = ""
    error_message: str = ""
    timestamp: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def validate_loop_bounds(self) -> "TaskCheckpoint":
        if self.loop_count > self.max_loops:
            raise ValueError("loop_count không được lớn hơn max_loops")
        return self


def _is_secret_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    return (
        normalized in _SECRET_KEYS
        or normalized.endswith(_SECRET_SUFFIXES)
        or normalized.startswith("authorization_")
    )


def _redact_string(value: str) -> str:
    result = value
    for pattern in _SECRET_KEY_VALUE_PATTERNS:
        result = pattern.sub(rf"\g<1>{_REDACTED}", result)
    for pattern in _SECRET_STANDALONE_PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


def redact_secrets(value: Any, key: Optional[str] = None) -> Any:
    """Recursively remove credential-like values and string secrets before checkpoint persistence."""
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
    if isinstance(value, str):
        return _redact_string(value)
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
        return TaskCheckpoint.model_validate(data)
    except json.JSONDecodeError:
        logger.exception("Checkpoint JSON bị hỏng: %s", p)
        return None
    except Exception:
        logger.exception("Không thể validate checkpoint: %s", p)
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


async def _read_last_parseable_response(
    tab: Any,
    selector: Optional[str],
    source: str,
) -> tuple[str, Optional[Any]]:
    """Reads elements backwards and returns the last element that produces valid parsed agent output."""
    if not tab or not hasattr(tab, "query_selector_all") or not selector:
        return "", None
    try:
        elements = await tab.query_selector_all(selector)
        for element in reversed(elements):
            try:
                text = (await element.inner_text()).strip()
            except Exception:
                continue
            if not text:
                continue
            parsed = parse_agent_output(text, source=source)
            if parsed is not None and parsed.status != AgentStatus.UNKNOWN:
                return text, parsed
    except Exception:
        pass
    return "", None


async def reconcile_from_tabs(
    p_tab: Any,
    c_tab: Any,
    repo: str,
    branch: str,
    goal: str,
    selectors: SelectorsConfig,
    max_loops: int = 5,
    auto_mode: bool = True,
    current_loop_count: int = 0,
) -> TaskCheckpoint:
    """
    Inspects existing browser tabs (Perplexity & ChatGPT), analyzes their current messages,
    and automatically reconstructs an accurate TaskCheckpoint to resume directly without restarting.
    """
    s_p_resp = selectors.perplexity.get("last_response")
    s_c_resp = selectors.chatgpt.get("last_response")

    p_text, p_res = await _read_last_parseable_response(p_tab, s_p_resp, source="perplexity")
    c_text, c_res = await _read_last_parseable_response(c_tab, s_c_resp, source="chatgpt")

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
                loop_count=max(1, current_loop_count),
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
            target_loop = max(2, current_loop_count + 1) if current_loop_count > 0 else 2
            return TaskCheckpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=min(max_loops, target_loop),
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
            loop_count=max(1, current_loop_count),
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
            loop_count=max(1, current_loop_count),
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
