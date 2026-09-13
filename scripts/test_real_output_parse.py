import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.tag_protocol import parse_agent_output, AgentStatus

real_sample = """
[STATUS: COMMITTED]
[BRANCH: ai-agent/production-observability-readiness]
[COMMIT_SHA: 9d7e03b]
PR_URL: https://github.com/thanhtupppp/nguyencuufacepython/pull/8

[SUMMARY_CHANGES]: Đã nâng cấp lớp observability/readiness và runtime contract: thêm request correlation X-Request-ID, error envelope an
"""

res = parse_agent_output(real_sample, source="chatgpt")
print("Status:", res.status)
print("Payload:", res.payload)
print("Tags:", res.tags)
if res.payload:
    print("Branch:", res.payload.branch)
    print("Commit SHA:", res.payload.commit_sha)
    print("PR URL:", res.payload.pr_url)
