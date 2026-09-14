import asyncio
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

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
    re.compile(r"(?i)(\bbearer\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token)"
        r"\s*[:=]\s*)[^\s,;&?#]+"
    ),
    re.compile(
        r"(?i)((?:cookie|set-cookie)\s*[:=]\s*)"
        r"(?=[^\r\n]*(?:session|token|auth|sid))"
        r"[^\r\n]+"
    ),
)

_SECRET_STANDALONE_PATTERNS = (
    re.compile(
        r"(?i)\beyJ[A-Za-z0-9_-]{10,}\."
        r"[A-Za-z0-9_-]{10,}\."
        r"[A-Za-z0-9_-]{10,}\b"
    ),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bghp_[A-Za-z0-9]{30,}"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)\bxoxb-[A-Za-z0-9-]+"),
    re.compile(r"(?i)\bxoxp-[A-Za-z0-9-]+"),
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

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temp_path = Path(temp_name)
    fd_owned = True
    try:
        _secure_permissions(temp_path)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            fd_owned = False
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        _secure_permissions(temp_path)
        os.replace(temp_path, destination)
        _secure_permissions(destination)
        if os.name != "nt":
            try:
                dir_fd = os.open(str(destination.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
    finally:
        if fd_owned:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temp_path.unlink(missing_ok=True)
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
        logger.error("Checkpoint JSON bị hỏng: %s", p)
        return None
    except ValidationError:
        logger.error("Checkpoint không hợp lệ: %s", p)
        return None
    except Exception as exc:
        logger.error("Không thể đọc checkpoint: %s (%s)", p, type(exc).__name__)
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


def _normalize_loop_count(current_loop_count: int, max_loops: int) -> tuple[int, int]:
    """Ensures loop_count and max_loops are strictly within valid bounds."""
    normalized_max_loops = max(1, max_loops)
    normalized_current = max(0, current_loop_count)
    return min(normalized_current, normalized_max_loops), normalized_max_loops


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
        logger.debug(
            "Không thể đọc response từ tab source=%s selector=%s",
            source,
            selector,
            exc_info=True,
        )
    return "", None


def _checkpoint(
    *,
    repo: str,
    branch: str,
    goal: str,
    loop_count: int,
    max_loops: int,
    auto_mode: bool,
    last_successful_agent: LastAgentName,
    next_target_agent: AgentName,
    status_label: str,
    feature_branch: str = "",
    commit_sha: str = "",
    pr_url: str = "",
    last_prompt: str = "",
    last_raw_response: str = "",
    next_prompt_payload: str = "",
    error_message: str = "",
) -> TaskCheckpoint:
    return TaskCheckpoint(
        repo=repo,
        branch=branch,
        goal=goal,
        loop_count=loop_count,
        max_loops=max_loops,
        auto_mode=auto_mode,
        last_successful_agent=last_successful_agent,
        next_target_agent=next_target_agent,
        feature_branch=feature_branch,
        commit_sha=commit_sha,
        pr_url=pr_url,
        last_prompt=last_prompt,
        last_raw_response=last_raw_response,
        next_prompt_payload=next_prompt_payload,
        status_label=status_label,
        error_message=error_message,
    )


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
    safe_loop_count, safe_max_loops = _normalize_loop_count(
        current_loop_count,
        max_loops,
    )
    completed_loops = safe_loop_count

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

    # Check if ChatGPT has valid committed evidence
    has_commit_evidence = False
    feat_branch = ""
    commit_sha = ""
    pr_url = ""
    if c_res and c_res.status == AgentStatus.COMMITTED:
        pl = c_res.payload
        feat_branch = getattr(pl, "branch", "") or c_res.tags.get("BRANCH", "")
        commit_sha = getattr(pl, "commit_sha", "") or c_res.tags.get("COMMIT_SHA", "")
        pr_url = getattr(pl, "pr_url", "") or c_res.tags.get("PR_URL", "")
        payload_repo = getattr(pl, "repo", "") or c_res.tags.get("REPO", "")
        if not payload_repo and pr_url and "github.com/" in pr_url:
            parts = pr_url.split("github.com/")[-1].split("/")
            if len(parts) >= 2:
                payload_repo = f"{parts[0]}/{parts[1]}"
        has_commit_evidence = bool(feat_branch or commit_sha or pr_url)
        if payload_repo and repo and payload_repo.strip().lower() != repo.strip().lower():
            has_commit_evidence = False

    if c_res and c_res.status == AgentStatus.COMMITTED and has_commit_evidence:
        if p_res and p_res.status == AgentStatus.COMPLETED:
            return _checkpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=completed_loops,
                max_loops=safe_max_loops,
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
            if completed_loops >= safe_max_loops:
                return _checkpoint(
                    repo=repo,
                    branch=branch,
                    goal=goal,
                    loop_count=safe_max_loops,
                    max_loops=safe_max_loops,
                    auto_mode=auto_mode,
                    last_successful_agent="perplexity",
                    next_target_agent="none",
                    feature_branch=feat_branch,
                    commit_sha=commit_sha,
                    pr_url=pr_url,
                    last_raw_response=p_text,
                    next_prompt_payload="",
                    status_label="MAX_LOOPS_REACHED",
                )

            next_loop_count = min(safe_max_loops, completed_loops + 1)
            next_payload = (
                f"[BÁO CÁO SỰ CỐ / YÊU CẦU SỬA ĐỔI TỪ LEAD]:\n{p_text}\n"
                f"Hãy chỉnh sửa mã nguồn và commit cập nhật lên nhánh {feat_branch}."
            )
            return _checkpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=next_loop_count,
                max_loops=safe_max_loops,
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

        if completed_loops >= safe_max_loops:
            return _checkpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=safe_max_loops,
                max_loops=safe_max_loops,
                auto_mode=auto_mode,
                last_successful_agent="chatgpt",
                next_target_agent="none",
                feature_branch=feat_branch,
                commit_sha=commit_sha,
                pr_url=pr_url,
                last_raw_response=c_text,
                next_prompt_payload="",
                status_label="MAX_LOOPS_REACHED",
            )

        next_payload = (
            f"[KẾT QUẢ PULL REQUEST TỪ DEV]:\n{c_text}\n"
            "Hãy nghiệm thu mã nguồn này và xuất [STATUS: COMPLETED] nếu đạt chuẩn "
            "hoặc [STATUS: NEEDS_REVISION] nếu cần sửa."
        )
        return _checkpoint(
            repo=repo,
            branch=branch,
            goal=goal,
            loop_count=completed_loops,
            max_loops=safe_max_loops,
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
        if completed_loops >= safe_max_loops:
            return _checkpoint(
                repo=repo,
                branch=branch,
                goal=goal,
                loop_count=safe_max_loops,
                max_loops=safe_max_loops,
                auto_mode=auto_mode,
                last_successful_agent="perplexity",
                next_target_agent="none",
                last_raw_response=p_text,
                next_prompt_payload="",
                status_label="MAX_LOOPS_REACHED",
            )

        chatgpt_prompt = f"{c_dev_template}\n\n[TASK_SPEC FROM TECH LEAD]:\n{p_text}\n\n[TARGET REPO]: {repo}"
        return _checkpoint(
            repo=repo,
            branch=branch,
            goal=goal,
            loop_count=completed_loops,
            max_loops=safe_max_loops,
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
    return _checkpoint(
        repo=repo,
        branch=branch,
        goal=goal,
        loop_count=0,
        max_loops=safe_max_loops,
        auto_mode=auto_mode,
        last_successful_agent="",
        next_target_agent="perplexity",
        next_prompt_payload=first_prompt,
        status_label="IDLE",
    )


class CheckpointStore:
    """Coroutine-safe checkpoint manager using asyncio.Lock to avoid lost updates."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def save(
        self,
        checkpoint: TaskCheckpoint,
        path: str = "storage/checkpoint.json",
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(save_checkpoint, checkpoint, path)

    async def load(
        self,
        path: str = "storage/checkpoint.json",
    ) -> Optional[TaskCheckpoint]:
        async with self._lock:
            return await asyncio.to_thread(load_checkpoint, path)

    async def clear(
        self,
        path: str = "storage/checkpoint.json",
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(clear_checkpoint, path)

