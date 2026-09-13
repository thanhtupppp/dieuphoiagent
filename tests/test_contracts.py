
from core.contracts import DevTaskSpec, FileChange, ReviewVerdict, TaskResult
from core.tag_protocol import parse_agent_output, parse_result, parse_review_verdict, AgentStatus


def test_file_change_model():
    fc = FileChange(path="core/test.py", action="create", content="print('hello')", diff=None)
    assert fc.path == "core/test.py"
    assert fc.action == "create"
    assert fc.content == "print('hello')"


def test_task_result_model():
    tr = TaskResult(
        summary="Updated auth flow",
        files=[FileChange(path="core/auth.py", action="update")],
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


def test_dev_task_spec_model():
    spec = DevTaskSpec(
        task="Refactor database layer",
        affected_files=["core/db.py"],
        instructions="Use connection pooling",
    )
    assert spec.version == "1.0"
    assert spec.task == "Refactor database layer"
    assert spec.affected_files == ["core/db.py"]


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
      "files": [{"path": "api.py", "action": "create"}]
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
