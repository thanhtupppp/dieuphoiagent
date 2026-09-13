import json
import re
from enum import Enum
from typing import Dict, Optional, Union

from pydantic import BaseModel, Field

from core.contracts import DevTaskSpec, ReviewVerdict, TaskResult

JSON_BLOCK = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)


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
    TaskResult,
    ReviewVerdict,
    DevTaskSpec,
]


class TagParseResult(BaseModel):
    status: AgentStatus
    source: str
    raw_text: str
    payload: Optional[Payload] = None
    tags: Dict[str, str] = Field(default_factory=dict)


def parse_result(text: str) -> Optional[TaskResult]:
    """Parse TaskResult from a JSON fenced block."""
    m = JSON_BLOCK.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1).strip())
        return TaskResult.model_validate(data)
    except Exception:
        return None


def parse_review_verdict(text: str) -> Optional[ReviewVerdict]:
    """Parse ReviewVerdict from a JSON fenced block."""
    m = JSON_BLOCK.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1).strip())
        return ReviewVerdict.model_validate(data)
    except Exception:
        return None



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
    m = JSON_BLOCK.search(text)
    if m:
        try:
            raw_json = json.loads(m.group(1).strip())
            if isinstance(raw_json, dict):
                if "approved" in raw_json:
                    verdict = ReviewVerdict.model_validate(raw_json)
                    st = AgentStatus.COMPLETED if verdict.approved else AgentStatus.NEEDS_REVISION
                    summary = verdict.summary or (", ".join(verdict.issues) if verdict.issues else "Review complete")
                    return TagParseResult(
                        status=st,
                        source=source,
                        raw_text=text,
                        payload=verdict,
                        tags={"STATUS": st.value, "SUMMARY": summary},
                    )

                status_raw = str(raw_json.get("status", "")).upper()
                if status_raw:
                    try:
                        st = AgentStatus(status_raw)
                    except ValueError:
                        st = AgentStatus.UNKNOWN

                    if st == AgentStatus.COMPLETED:
                        return TagParseResult(
                            status=st,
                            source=source,
                            raw_text=text,
                            payload=CompletionPayload(summary=str(raw_json.get("summary", text))),
                            tags={"STATUS": st.value, "SUMMARY": str(raw_json.get("summary", text))},
                        )

                    if st in (AgentStatus.COMMITTED, AgentStatus.READY_FOR_DEV, AgentStatus.NEEDS_REVISION, AgentStatus.UNKNOWN):
                        task_res = TaskResult.model_validate(raw_json)
                        eff_status = st if st != AgentStatus.UNKNOWN else AgentStatus.COMMITTED
                        return TagParseResult(
                            status=eff_status,
                            source=source,
                            raw_text=text,
                            payload=task_res,
                            tags={
                                "STATUS": eff_status.value,
                                "BRANCH": task_res.branch,
                                "COMMIT_SHA": task_res.commit_sha,
                                "PR_URL": task_res.pr_url,
                                "SUMMARY": task_res.summary,
                            },
                        )

                if "summary" in raw_json and (
                    "files" in raw_json
                    or "questions" in raw_json
                    or "pr_url" in raw_json
                    or "commit_sha" in raw_json
                ):
                    task_res = TaskResult.model_validate(raw_json)
                    eff_status = (
                        AgentStatus.COMMITTED
                        if (task_res.commit_sha or task_res.pr_url or task_res.files)
                        else AgentStatus.READY_FOR_DEV
                    )
                    return TagParseResult(
                        status=eff_status,
                        source=source,
                        raw_text=text,
                        payload=task_res,
                        tags={
                            "STATUS": eff_status.value,
                            "BRANCH": task_res.branch,
                            "COMMIT_SHA": task_res.commit_sha,
                            "PR_URL": task_res.pr_url,
                            "SUMMARY": task_res.summary,
                        },
                    )
        except Exception:
            pass

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
