import json
import time
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel, Field
from core.tag_protocol import parse_agent_output, AgentStatus
from core.config_loader import SelectorsConfig

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

def save_checkpoint(checkpoint: TaskCheckpoint, path: str = "storage/checkpoint.json") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(checkpoint.model_dump(), f, ensure_ascii=False, indent=2)

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
    auto_mode: bool = True
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

    # Load prompt templates
    try:
        p_lead_template = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
    except Exception:
        p_lead_template = ""
    try:
        c_dev_template = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")
    except Exception:
        c_dev_template = ""

    # Infer state
    # Case 1: ChatGPT has COMMITTED and opened a PR
    if c_res and c_res.status == AgentStatus.COMMITTED:
        pl = c_res.payload
        feat_branch = getattr(pl, "branch", "")
        commit_sha = getattr(pl, "commit_sha", "")
        pr_url = getattr(pl, "pr_url", "")

        # Check if Perplexity already reviewed this PR
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
                status_label="COMPLETED"
            )
        elif p_res and p_res.status == AgentStatus.NEEDS_REVISION:
            # Perplexity requested revision -> Next is ChatGPT
            next_payload = f"[BÁO CÁO SỰ CỐ / YÊU CẦU SỬA ĐỔI TỪ LEAD]:\n{p_text}\nHãy chỉnh sửa mã nguồn và commit cập nhật lên nhánh {feat_branch}."
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
                status_label="NEEDS_REVISION"
            )
        else:
            # Perplexity has not reviewed this PR yet -> Next is Perplexity review
            next_payload = f"[KẾT QUẢ PULL REQUEST TỪ DEV]:\n{c_text}\nHãy nghiệm thu mã nguồn này và xuất [STATUS: COMPLETED] nếu đạt chuẩn hoặc [STATUS: NEEDS_REVISION] nếu cần sửa."
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
                status_label="COMMITTED_AWAITING_REVIEW"
            )

    # Case 2: Perplexity has generated READY_FOR_DEV, but ChatGPT hasn't committed yet
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
            status_label="READY_FOR_DEV"
        )

    # Default fallback: start from beginning with Perplexity
    first_prompt = f"{p_lead_template}\n\n[MỤC TIÊU BÀI TOÁN]:\nRepository: {repo}\nBranch: {branch}\nYêu cầu: {goal}"
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
        status_label="IDLE"
    )
