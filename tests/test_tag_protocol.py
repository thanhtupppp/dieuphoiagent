import pytest
from core.tag_protocol import (
    parse_agent_output,
    AgentStatus,
    TaskSpecPayload,
    RevisionPayload,
    CompletionPayload,
    CommitReportPayload,
    ErrorReportPayload
)

def test_parse_perplexity_ready_for_dev():
    sample = """
    Sau đây là phân tích của tôi:
    [SPEC_VERSION: 1.0]
    [TASK]: Sửa lỗi memory leak trong module cache
    [AFFECTED_FILES]: core/cache.py, tests/test_cache.py
    [INSTRUCTIONS]: Dùng WeakValueDictionary thay vì dict thông thường.
    [STATUS: READY_FOR_DEV]
    """
    res = parse_agent_output(sample, source="perplexity")
    assert res.status == AgentStatus.READY_FOR_DEV
    assert isinstance(res.payload, TaskSpecPayload)
    assert res.payload.task == "Sửa lỗi memory leak trong module cache"
    assert "core/cache.py" in res.payload.affected_files

def test_parse_perplexity_needs_revision():
    sample = """
    [SPEC_VERSION: 1.0]
    [BRANCH: ai-agent/fix-cache]
    [PR_URL: https://github.com/myorg/myrepo/pull/12]
    [REVISION_NOTES]: Vẫn còn lỗi concurrency khi truy cập đồng thời.
    [INSTRUCTIONS]: Thêm asyncio.Lock()
    [STATUS: NEEDS_REVISION]
    """
    res = parse_agent_output(sample, source="perplexity")
    assert res.status == AgentStatus.NEEDS_REVISION
    assert isinstance(res.payload, RevisionPayload)
    assert res.payload.branch == "ai-agent/fix-cache"

def test_parse_perplexity_completed():
    sample = """
    Tuyệt vời, code đã đạt chuẩn.
    [STATUS: COMPLETED]
    [SUMMARY]: Đã pass toàn bộ test case và không còn memory leak.
    """
    res = parse_agent_output(sample, source="perplexity")
    assert res.status == AgentStatus.COMPLETED
    assert isinstance(res.payload, CompletionPayload)

def test_parse_chatgpt_committed():
    sample = """
    ```text
    [STATUS: COMMITTED]
    [BRANCH: ai-agent/fix-cache]
    [COMMIT_SHA: a1b2c3d]
    [PR_URL: https://github.com/myorg/myrepo/pull/12]
    [SUMMARY_CHANGES]: Đã thay dict bằng WeakValueDictionary.
    ```
    """
    res = parse_agent_output(sample, source="chatgpt")
    assert res.status == AgentStatus.COMMITTED
    assert isinstance(res.payload, CommitReportPayload)
    assert res.payload.commit_sha == "a1b2c3d"

def test_parse_chatgpt_error():
    sample = """
    [STATUS: ERROR]
    [BRANCH: ai-agent/fix-cache]
    [ERROR_DETAILS]: GitHub Action timeout after 60s
    [ATTEMPT_COUNT]: 1
    """
    res = parse_agent_output(sample, source="chatgpt")
    assert res.status == AgentStatus.ERROR
    assert isinstance(res.payload, ErrorReportPayload)

def test_parse_chatgpt_fallback_heuristic():
    sample = """
    Tôi đã tạo commit thành công với sha 9f8a2bc và mở PR tại https://github.com/myorg/myrepo/pull/45 trên nhánh ai-agent/update-docs.
    """
    res = parse_agent_output(sample, source="chatgpt")
    assert res.status == AgentStatus.COMMITTED
    assert isinstance(res.payload, CommitReportPayload)
    assert res.payload.commit_sha == "9f8a2bc"
    assert res.payload.pr_url == "https://github.com/myorg/myrepo/pull/45"
