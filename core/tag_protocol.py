import re
from enum import Enum
from typing import Optional, Union, Dict
from pydantic import BaseModel, Field

class AgentStatus(str, Enum):
    READY_FOR_DEV = "READY_FOR_DEV"
    NEEDS_REVISION = "NEEDS_REVISION"
    COMPLETED = "COMPLETED"
    COMMITTED = "COMMITTED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

class TaskSpecPayload(BaseModel):
    version: str = "1.0"
    task: str
    affected_files: str = ""
    instructions: str = ""

class RevisionPayload(BaseModel):
    version: str = "1.0"
    branch: str
    pr_url: str = ""
    revision_notes: str
    instructions: str = ""

class CompletionPayload(BaseModel):
    summary: str

class CommitReportPayload(BaseModel):
    branch: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    summary_changes: str = ""

class ErrorReportPayload(BaseModel):
    branch: str = ""
    error_details: str
    attempt_count: int = 1

class TagParseResult(BaseModel):
    status: AgentStatus
    source: str
    raw_text: str
    payload: Optional[Union[
        TaskSpecPayload,
        RevisionPayload,
        CompletionPayload,
        CommitReportPayload,
        ErrorReportPayload
    ]] = None
    tags: Dict[str, str] = Field(default_factory=dict)

def _extract_tags(text: str) -> Dict[str, str]:
    tags = {}
    
    # 1. Match [KEY: VALUE] (colon inside brackets, single-line)
    inside_pattern = re.compile(r"\[([A-Z0-9_]+)\s*:\s*([^\]\n]+)\]")
    for k, v in inside_pattern.findall(text):
        tags[k.strip().upper()] = v.strip()

    # 2. Match [KEY]: VALUE (colon outside brackets, can be multiline up to next [KEY] or end)
    outside_pattern = re.compile(r"\[([A-Z0-9_]+)\]\s*:\s*([\s\S]*?)(?=\n\s*\[|\Z)")
    for k, v in outside_pattern.findall(text):
        k_clean = k.strip().upper()
        v_clean = re.sub(r"\n\s*```.*$", "", v.strip()).strip()
        tags[k_clean] = v_clean

    # Clean markdown code blocks from values if present
    for k, v in tags.items():
        if v.endswith("```"):
            tags[k] = v[:-3].strip()

    return tags

def parse_agent_output(text: str, source: str) -> TagParseResult:
    tags = _extract_tags(text)
    raw_status = tags.get("STATUS", "").upper()

    try:
        status = AgentStatus(raw_status)
    except ValueError:
        status = AgentStatus.UNKNOWN

    # Heuristic fallback for ChatGPT if tags are missing
    if source == "chatgpt" and status == AgentStatus.UNKNOWN:
        pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", text)
        sha_match = re.search(r"\b([0-9a-f]{7,40})\b", text, re.IGNORECASE)
        branch_match = re.search(r"\b(ai-agent/[a-zA-Z0-9_\-]+)\b", text)
        if pr_match or sha_match:
            status = AgentStatus.COMMITTED
            payload = CommitReportPayload(
                branch=branch_match.group(1) if branch_match else "",
                commit_sha=sha_match.group(1) if sha_match else "",
                pr_url=pr_match.group(0) if pr_match else "",
                summary_changes=text[:200]
            )
            return TagParseResult(status=status, source=source, raw_text=text, payload=payload, tags=tags)

    payload = None
    if status == AgentStatus.READY_FOR_DEV:
        payload = TaskSpecPayload(
            version=tags.get("SPEC_VERSION", "1.0"),
            task=tags.get("TASK", ""),
            affected_files=tags.get("AFFECTED_FILES", ""),
            instructions=tags.get("INSTRUCTIONS", "")
        )
    elif status == AgentStatus.NEEDS_REVISION:
        payload = RevisionPayload(
            version=tags.get("SPEC_VERSION", "1.0"),
            branch=tags.get("BRANCH", ""),
            pr_url=tags.get("PR_URL", ""),
            revision_notes=tags.get("REVISION_NOTES", ""),
            instructions=tags.get("INSTRUCTIONS", "")
        )
    elif status == AgentStatus.COMPLETED:
        payload = CompletionPayload(summary=tags.get("SUMMARY", text))
    elif status == AgentStatus.COMMITTED:
        payload = CommitReportPayload(
            branch=tags.get("BRANCH", ""),
            commit_sha=tags.get("COMMIT_SHA", ""),
            pr_url=tags.get("PR_URL", ""),
            summary_changes=tags.get("SUMMARY_CHANGES", "")
        )
    elif status == AgentStatus.ERROR:
        payload = ErrorReportPayload(
            branch=tags.get("BRANCH", ""),
            error_details=tags.get("ERROR_DETAILS", text),
            attempt_count=int(tags.get("ATTEMPT_COUNT", "1"))
        )

    return TagParseResult(status=status, source=source, raw_text=text, payload=payload, tags=tags)
