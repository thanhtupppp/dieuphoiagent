import re
from pathlib import PurePosixPath
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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
        normalized = value.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("path không được rỗng")
        if re.match(r"^[a-zA-Z]:", normalized):
            raise ValueError("path phải là relative path an toàn")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("path phải là relative path an toàn")
        return normalized

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
    files: list[FileChange] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
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

    @model_validator(mode="after")
    def validate_commit_fields(self) -> "TaskResult":
        if self.status == "COMMITTED":
            if not self.branch:
                raise ValueError("COMMITTED yêu cầu branch")
            if not self.commit_sha and not self.pr_url:
                raise ValueError("COMMITTED yêu cầu commit_sha hoặc pr_url")
        return self


class ReviewVerdict(ProtocolModel):
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
        normalized: list[str] = []
        for value in values:
            path_str = value.strip().replace("\\", "/")
            if not path_str:
                raise ValueError("affected_files không được chứa path rỗng")
            if re.match(r"^[a-zA-Z]:", path_str):
                raise ValueError(f"affected_files chứa path không an toàn: {value!r}")
            path = PurePosixPath(path_str)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"affected_files chứa path không an toàn: {value!r}")
            normalized.append(path_str)
        return list(dict.fromkeys(normalized))
