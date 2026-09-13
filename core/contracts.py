from typing import List, Optional

from pydantic import BaseModel, Field


class FileChange(BaseModel):
    path: str
    action: str = Field(description="Action to perform: create | update | delete")
    content: Optional[str] = None
    diff: Optional[str] = None


class TaskResult(BaseModel):
    summary: str
    files: List[FileChange] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    branch: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    status: Optional[str] = None


class ReviewVerdict(BaseModel):
    approved: bool
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    summary: str = ""


class DevTaskSpec(BaseModel):
    version: str = "1.0"
    task: str
    affected_files: List[str] = Field(default_factory=list)
    instructions: str = ""
