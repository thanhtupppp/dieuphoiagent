from pathlib import Path

def test_perplexity_prompt_contains_tags():
    content = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
    assert "[SPEC_VERSION: 1.0]" in content
    assert "[TASK]:" in content
    assert "[AFFECTED_FILES]:" in content
    assert "[INSTRUCTIONS]:" in content
    assert "[STATUS: READY_FOR_DEV]" in content
    assert "[STATUS: NEEDS_REVISION]" in content
    assert "[STATUS: COMPLETED]" in content

def test_chatgpt_prompt_contains_tags():
    content = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")
    assert "[STATUS: COMMITTED]" in content
    assert "[STATUS: ERROR]" in content
    assert "[BRANCH:" in content
    assert "[COMMIT_SHA:" in content
    assert "[PR_URL:" in content
    assert "ai-agent/" in content
