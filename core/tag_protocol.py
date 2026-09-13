import re
from enum import Enum
from typing import Dict, Optional, Union

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


Payload = Union[
    TaskSpecPayload,
    RevisionPayload,
    CompletionPayload,
    CommitReportPayload,
    ErrorReportPayload,
]


class TagParseResult(BaseModel):
    status: AgentStatus
    source: str
    raw_text: str
    payload: Optional[Payload] = None
    tags: Dict[str, str] = Field(default_factory=dict)


def _extract_tags(text: str) -> Dict[str, str]:
    tags: Dict[str, str] = {}

    inside_pattern = re.compile(r"\[([A-Z0-9_]+)\s*:\s*([^\]\n]+)\]")
    for key, value in inside_pattern.findall(text):
        tags[key.strip().upper()] = value.strip()

    outside_pattern = re.compile(
        r"\[([A-Z0-9_]+)\]\s*:\s*([\s\S]*?)(?=\n\s*\[|\Z)"
    )
    for key, value in outside_pattern.findall(text):
        clean_key = key.strip().upper()
        clean_value = re.sub(r"\n\s*```.*$", "", value.strip()).strip()
        tags[clean_key] = clean_value

    for key, value in tags.items():
        if value.endswith("```"):
            tags[key] = value[:-3].strip()

    return tags


def parse_agent_output(text: str, source: str) -> TagParseResult:
    tags = _extract_tags(text)
    raw_status = tags.get("STATUS", "").upper()

    try:
        status = AgentStatus(raw_status)
    except ValueError:
        status = AgentStatus.UNKNOWN

    if source == "chatgpt" and status == AgentStatus.UNKNOWN:
        pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", text)
        sha_match = re.search(r"\b([0-9a-f]{7,40})\b", text, re.IGNORECASE)
        branch_match = re.search(r"\b(ai-agent/[a-zA-Z0-9_\-]+)\b", text)
        if pr_match or sha_match:
            status = AgentStatus.COMMITTED
            committed_payload = CommitReportPayload(
                branch=branch_match.group(1) if branch_match else "",
                commit_sha=sha_match.group(1) if sha_match else "",
                pr_url=pr_match.group(0) if pr_match else "",
                summary_changes=text[:200],
            )
            return TagParseResult(
                status=status,
                source=source,
                raw_text=text,
                payload=committed_payload,
                tags=tags,
            )

    payload: Optional[Payload] = None
    if status == AgentStatus.READY_FOR_DEV:
        payload = TaskSpecPayload(
            version=tags.get("SPEC_VERSION", "1.0"),
            task=tags.get("TASK", ""),
            affected_files=tags.get("AFFECTED_FILES", ""),
            instructions=tags.get("INSTRUCTIONS", ""),
        )
    elif status == AgentStatus.NEEDS_REVISION:
        payload = RevisionPayload(
            version=tags.get("SPEC_VERSION", "1.0"),
            branch=tags.get("BRANCH", ""),
            pr_url=tags.get("PR_URL", ""),
            revision_notes=tags.get("REVISION_NOTES", ""),
            instructions=tags.get("INSTRUCTIONS", ""),
        )
    elif status == AgentStatus.COMPLETED:
        payload = CompletionPayload(summary=tags.get("SUMMARY", text))
    elif status == AgentStatus.COMMITTED:
        pr_url = tags.get("PR_URL", "")
        if not pr_url:
            pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", text)
            if pr_match:
                pr_url = pr_match.group(0)

        payload = CommitReportPayload(
            branch=tags.get("BRANCH", ""),
            commit_sha=tags.get("COMMIT_SHA", ""),
            pr_url=pr_url,
            summary_changes=tags.get("SUMMARY_CHANGES", ""),
        )
    elif status == AgentStatus.ERROR:
        payload = ErrorReportPayload(
            branch=tags.get("BRANCH", ""),
            error_details=tags.get("ERROR_DETAILS", text),
            attempt_count=int(tags.get("ATTEMPT_COUNT", "1")),
        )

    return TagParseResult(
        status=status,
        source=source,
        raw_text=text,
        payload=payload,
        tags=tags,
    )
