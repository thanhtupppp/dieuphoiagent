import pytest
from pydantic import ValidationError

from core.contracts import DevTaskSpec, FileChange, ReviewVerdict, TaskResult
from core.tag_protocol import (
    AgentStatus,
    parse_agent_output,
    parse_result,
    parse_review_verdict,
)


def test_file_change_model():
    fc = FileChange(path="core/test.py", action="create", content="print('hello')", diff=None)
    assert fc.path == "core/test.py"
    assert fc.action == "create"
    assert fc.content == "print('hello')"


def test_file_change_action_literal():
    with pytest.raises(ValidationError):
        FileChange.model_validate({"path": "x.py", "action": "rename", "content": "foo"})

    with pytest.raises(ValidationError):
        FileChange.model_validate({"path": "x.py", "action": "CREATEE", "content": "foo"})


def test_file_change_path_validation():
    # Valid relative paths
    fc = FileChange(path="core/auth.py", action="create", content="# code")
    assert fc.path == "core/auth.py"

    # Backslashes normalized to forward slashes
    fc_bs = FileChange(path="core\\nested\\file.py", action="create", content="# code")
    assert fc_bs.path == "core/nested/file.py"

    # Whitespace stripped
    fc_ws = FileChange(path="  core/app.py  ", action="create", content="# code")
    assert fc_ws.path == "core/app.py"

    # Reject empty or whitespace-only path
    with pytest.raises(ValidationError):
        FileChange.model_validate({"path": "   ", "action": "create", "content": "# code"})

    # Reject absolute POSIX paths
    with pytest.raises(ValidationError, match="path phải là relative path an toàn"):
        FileChange.model_validate({"path": "/etc/passwd", "action": "create", "content": "# code"})

    # Reject directory traversal
    with pytest.raises(ValidationError, match="path phải là relative path an toàn"):
        FileChange.model_validate({"path": "../../.env", "action": "create", "content": "# code"})

    with pytest.raises(ValidationError, match="path phải là relative path an toàn"):
        FileChange.model_validate({"path": "core/../../secret.txt", "action": "create", "content": "# code"})

    # Reject Windows drive paths
    with pytest.raises(ValidationError, match="path phải là relative path an toàn"):
        FileChange.model_validate({"path": r"C:\project\file.py", "action": "create", "content": "# code"})

    with pytest.raises(ValidationError, match="path phải là relative path an toàn"):
        FileChange.model_validate({"path": "C:/project/file.py", "action": "create", "content": "# code"})


def test_file_change_payload_invariants():
    # create requires content
    with pytest.raises(ValidationError, match="action='create' yêu cầu content"):
        FileChange.model_validate({"path": "new.py", "action": "create", "content": None})

    # create with empty string is allowed (e.g. empty __init__.py)
    fc_empty = FileChange(path="__init__.py", action="create", content="")
    assert fc_empty.content == ""

    # update requires content or diff
    with pytest.raises(ValidationError, match="action='update' yêu cầu content hoặc diff"):
        FileChange.model_validate({"path": "up.py", "action": "update", "content": None, "diff": None})

    fc_up_content = FileChange(path="up.py", action="update", content="new_content")
    assert fc_up_content.content == "new_content"

    fc_up_diff = FileChange(path="up.py", action="update", diff="@@ -1 +1 @@")
    assert fc_up_diff.diff == "@@ -1 +1 @@"

    # delete must not have content or diff
    with pytest.raises(ValidationError, match="action='delete' không được có content/diff"):
        FileChange.model_validate({"path": "del.py", "action": "delete", "content": "not allowed"})

    with pytest.raises(ValidationError, match="action='delete' không được có content/diff"):
        FileChange.model_validate({"path": "del.py", "action": "delete", "diff": "@@ -1 +0,0 @@"})

    fc_del = FileChange(path="del.py", action="delete")
    assert fc_del.content is None
    assert fc_del.diff is None


def test_task_result_model():
    tr = TaskResult(
        summary="Updated auth flow",
        files=[FileChange(path="core/auth.py", action="update", diff="@@ -1,3 +1,4 @@")],
        questions=["Do we need MFA?"],
        branch="feat/auth",
        commit_sha="abcdef1",
        pr_url="https://github.com/test/repo/pull/5",
    )
    assert tr.summary == "Updated auth flow"
    assert len(tr.files) == 1
    assert tr.files[0].path == "core/auth.py"
    assert tr.branch == "feat/auth"
    assert tr.commit_sha == "abcdef1"
    assert tr.pr_url == "https://github.com/test/repo/pull/5"


def test_task_result_committed_invariants():
    # COMMITTED without branch -> fails
    with pytest.raises(ValidationError, match="COMMITTED yêu cầu branch"):
        TaskResult.model_validate({
            "summary": "Done",
            "status": "COMMITTED",
            "branch": "",
            "commit_sha": "abcdef1",
        })

    # COMMITTED with branch, but without commit_sha and pr_url -> fails
    with pytest.raises(ValidationError, match="COMMITTED yêu cầu commit_sha hoặc pr_url"):
        TaskResult.model_validate({
            "summary": "Done",
            "status": "COMMITTED",
            "branch": "feat/xyz",
            "commit_sha": "",
            "pr_url": "",
        })

    # COMMITTED with branch and commit_sha -> valid
    tr1 = TaskResult.model_validate({
        "summary": "Done",
        "status": "COMMITTED",
        "branch": "feat/xyz",
        "commit_sha": "abcdef12345",
    })
    assert tr1.status == "COMMITTED"
    assert tr1.branch == "feat/xyz"

    # COMMITTED with branch and pr_url -> valid
    tr2 = TaskResult.model_validate({
        "summary": "Done",
        "status": "COMMITTED",
        "branch": "feat/xyz",
        "pr_url": "https://github.com/org/repo/pull/1",
    })
    assert tr2.status == "COMMITTED"

    # Non-COMMITTED status does not require branch or commit_sha
    tr3 = TaskResult.model_validate({
        "summary": "Work in progress",
        "status": "READY_FOR_DEV",
    })
    assert tr3.status == "READY_FOR_DEV"


def test_task_result_commit_sha_format():
    # Valid 7-char sha
    tr = TaskResult(summary="Test", commit_sha="abcdef1")
    assert tr.commit_sha == "abcdef1"

    # Valid 40-char sha
    tr40 = TaskResult(summary="Test", commit_sha="a" * 40)
    assert tr40.commit_sha == "a" * 40

    # Invalid sha: too short (less than 7 chars)
    with pytest.raises(ValidationError, match="commit_sha không hợp lệ"):
        TaskResult.model_validate({"summary": "Test", "commit_sha": "abc123"})

    # Invalid sha: non-hex characters
    with pytest.raises(ValidationError, match="commit_sha không hợp lệ"):
        TaskResult.model_validate({"summary": "Test", "commit_sha": "zzzzzzz"})


def test_task_result_extra_forbid_and_whitespace():
    # Extra field is forbidden
    with pytest.raises(ValidationError):
        TaskResult.model_validate({"summary": "Test", "unknown_field": "val"})

    # Whitespace is stripped
    tr = TaskResult(summary="  Test with spaces  ", branch="  feat/branch  ")
    assert tr.summary == "Test with spaces"
    assert tr.branch == "feat/branch"


def test_task_result_validate_assignment():
    tr = TaskResult(summary="Test", branch="feat/ok")
    # Mutating to an invalid commit_sha triggers validation_assignment
    with pytest.raises(ValidationError):
        tr.commit_sha = "invalid!"


def test_review_verdict_model():
    rv = ReviewVerdict(
        approved=True,
        issues=[],
        suggestions=["Add type hint on return"],
        summary="LGTM",
    )
    assert rv.approved is True
    assert len(rv.suggestions) == 1
    assert rv.summary == "LGTM"


def test_review_verdict_invariants():
    # Not approved must have at least one issue
    with pytest.raises(ValidationError, match="Review không approved phải có ít nhất một issue"):
        ReviewVerdict.model_validate({
            "approved": False,
            "issues": [],
            "summary": "Failed",
        })

    # Approved must not have issues
    with pytest.raises(ValidationError, match="Review approved không nên còn issue"):
        ReviewVerdict.model_validate({
            "approved": True,
            "issues": ["Unresolved critical bug"],
            "summary": "Approved anyway",
        })

    # Valid rejected
    rv_rej = ReviewVerdict(approved=False, issues=["Missing tests"])
    assert rv_rej.approved is False
    assert rv_rej.issues == ["Missing tests"]

    # Valid approved
    rv_app = ReviewVerdict(approved=True, issues=[])
    assert rv_app.approved is True


def test_dev_task_spec_model():
    spec = DevTaskSpec(
        task="Refactor database layer",
        affected_files=["core/db.py"],
        instructions="Use connection pooling",
    )
    assert spec.version == "1.0"
    assert spec.task == "Refactor database layer"
    assert spec.affected_files == ["core/db.py"]


def test_dev_task_spec_validation():
    # Version must be "1.0"
    with pytest.raises(ValidationError):
        DevTaskSpec.model_validate({
            "version": "2.0",
            "task": "Do something",
        })

    # Task cannot be empty
    with pytest.raises(ValidationError):
        DevTaskSpec.model_validate({
            "task": "",
        })

    # Affected files validation: reject empty path
    with pytest.raises(ValidationError, match="affected_files không được chứa path rỗng"):
        DevTaskSpec.model_validate({
            "task": "Test",
            "affected_files": ["core/a.py", "  "],
        })

    # Affected files validation: reject traversal
    with pytest.raises(ValidationError, match="affected_files chứa path không an toàn"):
        DevTaskSpec.model_validate({
            "task": "Test",
            "affected_files": ["../secret.env"],
        })

    # Affected files validation: reject absolute path
    with pytest.raises(ValidationError, match="affected_files chứa path không an toàn"):
        DevTaskSpec.model_validate({
            "task": "Test",
            "affected_files": ["/etc/hosts"],
        })

    # Affected files validation: reject Windows drive letter
    with pytest.raises(ValidationError, match="affected_files chứa path không an toàn"):
        DevTaskSpec.model_validate({
            "task": "Test",
            "affected_files": [r"D:\project\file.py"],
        })

    # Deduplication and normalization
    spec = DevTaskSpec(
        task="Clean up modules",
        affected_files=["core\\auth.py", "core/db.py", "core/auth.py"],
    )
    assert spec.affected_files == ["core/auth.py", "core/db.py"]


def test_parse_result_valid_json():
    raw = """
    Here is my completed work:
    ```json
    {
      "summary": "Implemented feature X",
      "files": [
        {"path": "core/x.py", "action": "create", "content": "x = 1"}
      ],
      "questions": [],
      "branch": "feat/x",
      "commit_sha": "1234567",
      "pr_url": "https://github.com/org/repo/pull/1"
    }
    ```
    Please review!
    """
    res = parse_result(raw)
    assert res is not None
    assert res.summary == "Implemented feature X"
    assert len(res.files) == 1
    assert res.files[0].path == "core/x.py"
    assert res.commit_sha == "1234567"
    assert res.pr_url == "https://github.com/org/repo/pull/1"


def test_parse_result_missing_or_invalid():
    assert parse_result("No json block here") is None
    assert parse_result("```json\n{invalid json\n```") is None


def test_parse_review_verdict_valid():
    raw_approved = """
    Nghiệm thu mã nguồn:
    ```json
    {
      "approved": true,
      "issues": [],
      "suggestions": ["Optional: clean up comments"],
      "summary": "All tests passed cleanly."
    }
    ```
    """
    rv = parse_review_verdict(raw_approved)
    assert rv is not None
    assert rv.approved is True
    assert rv.summary == "All tests passed cleanly."

    raw_rejected = """
    ```json
    {
      "approved": false,
      "issues": ["Missing unit test", "Broken import"],
      "suggestions": ["Fix import on line 3"]
    }
    ```
    """
    rv_rej = parse_review_verdict(raw_rejected)
    assert rv_rej is not None
    assert rv_rej.approved is False
    assert len(rv_rej.issues) == 2


def test_parse_agent_output_with_json_review_approved():
    raw = """
    Kết quả đánh giá từ Tech Lead:
    ```json
    {
      "approved": true,
      "issues": [],
      "summary": "PR #10 đã đạt chuẩn chất lượng."
    }
    ```
    """
    res = parse_agent_output(raw, source="perplexity")
    assert res.status == AgentStatus.COMPLETED
    assert "PR #10" in res.tags.get("SUMMARY", "")


def test_parse_agent_output_with_json_review_rejected():
    raw = """
    ```json
    {
      "approved": false,
      "issues": ["Lỗi type hints", "Thiếu test coverage"],
      "summary": "Cần bổ sung test"
    }
    ```
    """
    res = parse_agent_output(raw, source="perplexity")
    assert res.status == AgentStatus.NEEDS_REVISION
    assert "Cần bổ sung test" in res.tags.get("SUMMARY", "")


def test_parse_agent_output_with_json_task_result():
    raw = """
    ChatGPT Dev đã tạo PR:
    ```json
    {
      "status": "COMMITTED",
      "summary": "Created endpoint",
      "branch": "ai-agent/endpoint",
      "commit_sha": "deadbeef",
      "pr_url": "https://github.com/org/repo/pull/99",
      "files": [{"path": "api.py", "action": "create", "content": "# api endpoint code"}]
    }
    ```
    """
    res = parse_agent_output(raw, source="chatgpt")
    assert res.status == AgentStatus.COMMITTED
    assert res.tags["BRANCH"] == "ai-agent/endpoint"
    assert res.tags["COMMIT_SHA"] == "deadbeef"
    assert res.tags["PR_URL"] == "https://github.com/org/repo/pull/99"
    assert isinstance(res.payload, TaskResult)
    assert res.payload.commit_sha == "deadbeef"
