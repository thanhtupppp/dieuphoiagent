import re
from pathlib import PurePosixPath
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def normalize_relative_path(value: str) -> str:
    """Normalize and validate that a path is a safe relative file path.

    Rejects empty paths, NUL bytes, Windows drive letters, absolute paths,
    directory traversal ('..'), and root/current directory references ('.').
    """
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("path không được rỗng")
    if "\x00" in normalized:
        raise ValueError("path không được chứa NUL byte")
    if re.match(r"^[a-zA-Z]:", normalized):
        raise ValueError("path phải là relative path an toàn")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path phải là relative path an toàn")
    if normalized in {".", "./"}:
        raise ValueError("path phải trỏ tới file cụ thể")
    return normalized


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )


FileAction = Literal["create", "update", "delete"]
AgentResultStatus = Literal[
    "READY_FOR_DEV",
    "COMMITTED",
    "COMPLETED",
    "NEEDS_REVISION",
    "UNKNOWN",
]


class FileChange(ProtocolModel):
    path: str = Field(min_length=1, max_length=500)
    action: FileAction
    content: Optional[str] = None
    diff: Optional[str] = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return normalize_relative_path(value)

    @model_validator(mode="after")
    def validate_payload(self) -> "FileChange":
        if self.action == "create" and self.content is None:
            raise ValueError("action='create' yêu cầu content")
        if self.action == "update" and self.content is None and self.diff is None:
            raise ValueError("action='update' yêu cầu content hoặc diff")
        if self.action == "delete" and (self.content is not None or self.diff is not None):
            raise ValueError("action='delete' không được có content/diff")
        return self


class TaskResult(ProtocolModel):
    summary: str = Field(min_length=1, max_length=20_000)
    files: list[FileChange] = Field(default_factory=list, max_length=500)
    questions: list[str] = Field(default_factory=list, max_length=100)
    branch: str = Field(default="", max_length=255)
    commit_sha: str = Field(default="", max_length=64)
    pr_url: str = Field(default="", max_length=2_000)
    status: Optional[AgentResultStatus] = None

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, value: str) -> str:
        if value and not re.fullmatch(r"[0-9a-fA-F]{7,64}", value):
            raise ValueError("commit_sha không hợp lệ")
        return value

    @field_validator("pr_url")
    @classmethod
    def validate_pr_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("pr_url phải dùng http hoặc https")
        if parsed.hostname != "github.com":
            raise ValueError("pr_url phải trỏ tới github.com")
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[2] != "pull":
            raise ValueError("pr_url không phải URL pull request hợp lệ")
        return value

    @model_validator(mode="after")
    def validate_commit_fields(self) -> "TaskResult":
        if self.status == "COMMITTED":
            if not self.branch:
                raise ValueError("COMMITTED yêu cầu branch")
            if not self.commit_sha and not self.pr_url:
                raise ValueError("COMMITTED yêu cầu commit_sha hoặc pr_url")
        return self


class ReviewVerdict(ProtocolModel):
    """Structured review verdict returned by Tech Lead.

    Contract semantics:
    - `issues`: Blocking issues that prevent approval. Required when approved=False,
      forbidden when approved=True.
    - `suggestions`: Non-blocking suggestions/improvements. Allowed regardless of
      approval status.
    """
    approved: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=20_000)

    @model_validator(mode="after")
    def validate_verdict(self) -> "ReviewVerdict":
        if not self.approved and not self.issues:
            raise ValueError("Review không approved phải có ít nhất một issue")
        if self.approved and self.issues:
            raise ValueError("Review approved không nên còn issue")
        return self


class DevTaskSpec(ProtocolModel):
    version: Literal["1.0"] = "1.0"
    task: str = Field(min_length=1, max_length=50_000)
    affected_files: list[str] = Field(default_factory=list, max_length=500)
    instructions: str = Field(default="", max_length=100_000)

    @field_validator("affected_files")
    @classmethod
    def validate_affected_files(cls, values: list[str]) -> list[str]:
        normalized = [normalize_relative_path(value) for value in values]
        return list(dict.fromkeys(normalized))
