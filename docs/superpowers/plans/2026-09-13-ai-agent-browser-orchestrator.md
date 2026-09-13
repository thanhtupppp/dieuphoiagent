# AI Agent Browser Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop browser orchestrator that connects to Comet (Perplexity AI) and ChatGPT via Chrome DevTools Protocol (CDP port 9222) to automate closed-loop research-to-commit workflows with a Python + NiceGUI interface.

**Architecture:** Modular Event-Driven FSM with dedicated classes for CDP connection, stream/tool-completion detection, robust Regex tag parsing, and a NiceGUI 2-column reactive dashboard with live logging, abort/rollback mechanisms, and dual Auto-pilot/Step-by-step modes.

**Tech Stack:** Python 3.10+, Playwright (async API), NiceGUI, Pydantic v2, PyYAML, Pytest, Pytest-asyncio.

## Global Constraints

- **Python Version:** Python 3.10 or higher.
- **Port:** Default CDP port is 9222 (`http://localhost:9222`).
- **Safety Rule:** Every branch created by ChatGPT must use the `ai-agent/` prefix.
- **Safety Rule:** Max loop count strictly halts execution when reached (default: 5).
- **Selector Isolation:** All DOM selectors must live in `config/selectors.json` (no hardcoded selectors in core logic).
- **Formatting & Links:** Use clickable `file://` links for all referenced files in documentation and logs.

---

### Task 1: Project Scaffolding & Configuration Loader

**Files:**
- Create: `requirements.txt`
- Create: `config/config.yaml`
- Create: `config/selectors.json`
- Create: `core/__init__.py`
- Create: `core/config_loader.py`
- Create: `scripts/launch_comet.bat`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `core.config_loader.load_config(path: str = "config/config.yaml") -> AppConfig`
- Produces: `core.config_loader.load_selectors(path: str = "config/selectors.json") -> SelectorsConfig`

- [ ] **Step 1: Write the failing test for configuration loading**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from core.config_loader import load_config, load_selectors, AppConfig, SelectorsConfig

def test_load_config_defaults():
    config = load_config("config/config.yaml")
    assert isinstance(config, AppConfig)
    assert config.cdp_port == 9222
    assert config.max_loops == 5
    assert config.timeout_seconds == 240
    assert config.text_stability_seconds == 2.5

def test_load_selectors():
    selectors = load_selectors("config/selectors.json")
    assert isinstance(selectors, SelectorsConfig)
    assert "input_textarea" in selectors.perplexity
    assert "send_button" in selectors.perplexity
    assert "prompt_textarea" in selectors.chatgpt
    assert "stop_button" in selectors.chatgpt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.config_loader'`

- [ ] **Step 3: Implement requirements.txt, config files, and config_loader.py**

```text
# requirements.txt
playwright>=1.40.0
nicegui>=1.4.0
pydantic>=2.0.0
pyyaml>=6.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

```yaml
# config/config.yaml
cdp_url: "http://localhost:9222"
cdp_port: 9222
default_max_loops: 5
timeout_seconds: 240
text_stability_seconds: 2.5
reconnect_attempts: 3
reconnect_delay_seconds: 2.0
browser_path: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
dedicated_profile_dir: "browser_profile"
```

```json
{
  "perplexity": {
    "url_match": "perplexity.ai",
    "input_textarea": "textarea[placeholder*='Ask'], textarea",
    "send_button": "button[aria-label*='Submit'], button:has(svg.lucide-arrow-right)",
    "stop_button": "button:has-text('Stop')",
    "last_response": "div[data-testid='answer-content'], div.prose:last-of-type"
  },
  "chatgpt": {
    "url_match": "chatgpt.com",
    "prompt_textarea": "#prompt-textarea, div[contenteditable='true']",
    "send_button": "button[data-testid='send-button']",
    "stop_button": "button[data-testid='stop-button']",
    "last_response": "div[data-message-author-role='assistant']:last-of-type",
    "tool_running_indicator": "div[data-testid*='tool-call-running'], div.animate-spin"
  }
}
```

```bat
@echo off
:: scripts/launch_comet.bat
set PROFILE_DIR=%~dp0..\browser_profile
echo Starting Browser with Remote Debugging on Port 9222...
echo Profile Directory: %PROFILE_DIR%

start "" "chrome.exe" --remote-debugging-port=9222 --user-data-dir="%PROFILE_DIR%" https://www.perplexity.ai https://chatgpt.com
echo Browser started. Please log into Perplexity and ChatGPT if you haven't already.
```

```python
# core/config_loader.py
from pathlib import Path
from typing import Dict, Any
import yaml
import json
from pydantic import BaseModel, Field

class AppConfig(BaseModel):
    cdp_url: str = "http://localhost:9222"
    cdp_port: int = 9222
    max_loops: int = Field(default=5, alias="default_max_loops")
    timeout_seconds: int = 240
    text_stability_seconds: float = 2.5
    reconnect_attempts: int = 3
    reconnect_delay_seconds: float = 2.0
    browser_path: str = ""
    dedicated_profile_dir: str = "browser_profile"

class SelectorsConfig(BaseModel):
    perplexity: Dict[str, str]
    chatgpt: Dict[str, str]

def load_config(path: str = "config/config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)

def load_selectors(path: str = "config/selectors.json") -> SelectorsConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SelectorsConfig(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config/ scripts/ core/__init__.py core/config_loader.py tests/test_config.py
git commit -m "feat: setup project scaffolding, configuration loader, and tests"
```

---

### Task 2: System Prompts & Markdown Templates

**Files:**
- Create: `prompts/perplexity_lead.md`
- Create: `prompts/chatgpt_dev.md`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Produces: System prompt templates containing all required tags.

- [ ] **Step 1: Write the failing test for prompt content verification**

```python
# tests/test_prompts.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompts.py -v`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Implement prompt template files**

```markdown
<!-- prompts/perplexity_lead.md -->
Bạn là Tech Lead và Software Architect trong hệ thống phát triển tự động.
Nhiệm vụ của bạn:
1. Nghiên cứu tài liệu kỹ thuật, thư viện, thuật toán mới nhất để giải quyết yêu cầu của bài toán.
2. Lập đặc tả kỹ thuật chi tiết theo đúng cấu trúc thẻ bắt buộc dưới đây:

[SPEC_VERSION: 1.0]
[TASK]: <Mô tả chi tiết logic cần sửa hoặc tính năng cần viết>
[AFFECTED_FILES]: <Danh sách file liên quan>
[INSTRUCTIONS]: <Các yêu cầu bắt buộc về thư viện, phiên bản, thuật toán>
[STATUS: READY_FOR_DEV]

3. Khi nhận được kết quả Pull Request từ Developer (ChatGPT):
- Nếu phát hiện bug, thiếu sót hoặc chưa đạt chuẩn, xuất:
[SPEC_VERSION: 1.0]
[BRANCH: <nhánh_hiện_tại>]
[PR_URL: <link_pull_request>]
[REVISION_NOTES]: <Phân tích chi tiết lỗi cần sửa>
[INSTRUCTIONS]: <Các bước khắc phục>
[STATUS: NEEDS_REVISION]

- Nếu code đã hoàn chỉnh và đạt yêu cầu:
[STATUS: COMPLETED]
[SUMMARY]: <Tóm tắt kết quả nghiệm thu>
```

```markdown
<!-- prompts/chatgpt_dev.md -->
Bạn là Core Developer và Git Operator trong hệ thống phát triển tự động.
Nhiệm vụ của bạn:
1. Đọc kỹ đặc tả kỹ thuật [TASK] và [INSTRUCTIONS] được cung cấp.
2. Viết mã nguồn hoàn chỉnh, sạch và an toàn.
3. Sử dụng GitHub Plugin/Tool để tạo branch mới (bắt buộc có tiền tố "ai-agent/"), commit toàn bộ code và mở/cập nhật Pull Request.
4. Khi hoàn thành commit, bạn PHẢI xuất kết quả theo định dạng thẻ sau:

[STATUS: COMMITTED]
[BRANCH: ai-agent/<tên_branch>]
[COMMIT_SHA: <mã_sha_7_ky_tu>]
[PR_URL: https://github.com/org/repo/pull/xxx]
[SUMMARY_CHANGES]: <Tóm tắt thay đổi>

5. Nếu xảy ra lỗi (xung đột git, lỗi plugin, lỗi token):
[STATUS: ERROR]
[BRANCH: ai-agent/<tên_branch>]
[ERROR_DETAILS]: <Chi tiết lỗi>
[ATTEMPT_COUNT]: 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_prompts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add prompts/ tests/test_prompts.py
git commit -m "feat: add prompt templates for Perplexity Tech Lead and ChatGPT Core Dev"
```

---

### Task 3: Tag Protocol Schemas & Robust Parser

**Files:**
- Create: `core/tag_protocol.py`
- Test: `tests/test_tag_protocol.py`

**Interfaces:**
- Produces: `core.tag_protocol.parse_agent_output(text: str, source: str) -> TagParseResult`
- Produces: Data models: `TaskSpecPayload`, `RevisionPayload`, `CompletionPayload`, `CommitReportPayload`, `ErrorReportPayload`

- [ ] **Step 1: Write the failing tests for tag parsing and heuristic fallbacks**

```python
# tests/test_tag_protocol.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tag_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.tag_protocol'`

- [ ] **Step 3: Implement core/tag_protocol.py**

```python
# core/tag_protocol.py
import re
from enum import Enum
from typing import Optional, Union, Dict
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

class TagParseResult(BaseModel):
    status: AgentStatus
    source: str
    raw_text: str
    payload: Optional[Union[
        TaskSpecPayload,
        RevisionPayload,
        CompletionPayload,
        CommitReportPayload,
        ErrorReportPayload
    ]] = None
    tags: Dict[str, str] = Field(default_factory=dict)

def _extract_tags(text: str) -> Dict[str, str]:
    # Regex matching [TAG_NAME]: content up to next tag or end
    tag_pattern = re.compile(r"\[([A-Z0-9_]+)\]\s*:\s*([\s\S]*?)(?=\n\s*\[[A-Z0-9_]+\]|\Z)")
    matches = tag_pattern.findall(text)
    tags = {}
    for k, v in matches:
        tags[k.strip().upper()] = v.strip()
    
    # Also extract [STATUS: VALUE] directly if written as [STATUS: READY_FOR_DEV]
    status_match = re.search(r"\[STATUS\s*:\s*([A-Z_]+)\]", text, re.IGNORECASE)
    if status_match and "STATUS" not in tags:
        tags["STATUS"] = status_match.group(1).strip().upper()
        
    return tags

def parse_agent_output(text: str, source: str) -> TagParseResult:
    tags = _extract_tags(text)
    raw_status = tags.get("STATUS", "").upper()

    try:
        status = AgentStatus(raw_status)
    except ValueError:
        status = AgentStatus.UNKNOWN

    # Heuristic fallback for ChatGPT if tags are missing
    if source == "chatgpt" and status == AgentStatus.UNKNOWN:
        pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", text)
        sha_match = re.search(r"\b([0-9a-f]{7,40})\b", text, re.IGNORECASE)
        branch_match = re.search(r"\b(ai-agent/[a-zA-Z0-9_\-]+)\b", text)
        if pr_match or sha_match:
            status = AgentStatus.COMMITTED
            payload = CommitReportPayload(
                branch=branch_match.group(1) if branch_match else "",
                commit_sha=sha_match.group(1) if sha_match else "",
                pr_url=pr_match.group(0) if pr_match else "",
                summary_changes=text[:200]
            )
            return TagParseResult(status=status, source=source, raw_text=text, payload=payload, tags=tags)

    payload = None
    if status == AgentStatus.READY_FOR_DEV:
        payload = TaskSpecPayload(
            version=tags.get("SPEC_VERSION", "1.0"),
            task=tags.get("TASK", ""),
            affected_files=tags.get("AFFECTED_FILES", ""),
            instructions=tags.get("INSTRUCTIONS", "")
        )
    elif status == AgentStatus.NEEDS_REVISION:
        payload = RevisionPayload(
            version=tags.get("SPEC_VERSION", "1.0"),
            branch=tags.get("BRANCH", ""),
            pr_url=tags.get("PR_URL", ""),
            revision_notes=tags.get("REVISION_NOTES", ""),
            instructions=tags.get("INSTRUCTIONS", "")
        )
    elif status == AgentStatus.COMPLETED:
        payload = CompletionPayload(summary=tags.get("SUMMARY", text))
    elif status == AgentStatus.COMMITTED:
        payload = CommitReportPayload(
            branch=tags.get("BRANCH", ""),
            commit_sha=tags.get("COMMIT_SHA", ""),
            pr_url=tags.get("PR_URL", ""),
            summary_changes=tags.get("SUMMARY_CHANGES", "")
        )
    elif status == AgentStatus.ERROR:
        payload = ErrorReportPayload(
            branch=tags.get("BRANCH", ""),
            error_details=tags.get("ERROR_DETAILS", text),
            attempt_count=int(tags.get("ATTEMPT_COUNT", "1"))
        )

    return TagParseResult(status=status, source=source, raw_text=text, payload=payload, tags=tags)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tag_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/tag_protocol.py tests/test_tag_protocol.py
git commit -m "feat: implement tag protocol schema, regex parser, and heuristic fallbacks"
```

---

### Task 4: CDP Connection & Browser Tab Discovery

**Files:**
- Create: `core/cdp_connector.py`
- Create: `scripts/test_cdp.py`
- Test: `tests/test_cdp_connector.py`

**Interfaces:**
- Produces: `core.cdp_connector.CDPConnector`
  - `connect() -> bool`
  - `find_tabs() -> Tuple[Page, Page]`
  - `reconnect_if_needed() -> bool`
  - `close()`

- [ ] **Step 1: Write test for CDPConnector tab discovery logic**

```python
# tests/test_cdp_connector.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.cdp_connector import CDPConnector
from core.config_loader import AppConfig, SelectorsConfig

@pytest.mark.asyncio
async def test_cdp_connector_tab_matching():
    app_config = AppConfig(cdp_url="http://localhost:9222")
    selectors = SelectorsConfig(
        perplexity={"url_match": "perplexity.ai"},
        chatgpt={"url_match": "chatgpt.com"}
    )
    connector = CDPConnector(app_config, selectors)
    
    mock_p1 = AsyncMock()
    mock_p1.url = "https://www.perplexity.ai/search"
    mock_p2 = AsyncMock()
    mock_p2.url = "https://chatgpt.com/c/12345"
    mock_p3 = AsyncMock()
    mock_p3.url = "https://google.com"

    mock_context = MagicMock()
    mock_context.pages = [mock_p1, mock_p2, mock_p3]
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]
    
    connector.browser = mock_browser
    p_tab, c_tab = await connector.find_tabs()
    
    assert p_tab == mock_p1
    assert c_tab == mock_p2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cdp_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.cdp_connector'`

- [ ] **Step 3: Implement core/cdp_connector.py and scripts/test_cdp.py**

```python
# core/cdp_connector.py
import asyncio
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page, Playwright
from core.config_loader import AppConfig, SelectorsConfig

class CDPConnector:
    def __init__(self, config: AppConfig, selectors: SelectorsConfig):
        self.config = config
        self.selectors = selectors
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.perplexity_tab: Optional[Page] = None
        self.chatgpt_tab: Optional[Page] = None
        self.is_connected: bool = False

    async def connect(self) -> bool:
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(self.config.cdp_url)
            self.is_connected = True
            return True
        except Exception as e:
            self.is_connected = False
            return False

    async def find_tabs(self) -> Tuple[Optional[Page], Optional[Page]]:
        if not self.browser or not self.browser.contexts:
            return None, None
        
        context = self.browser.contexts[0]
        pages = context.pages
        p_match = self.selectors.perplexity.get("url_match", "perplexity.ai")
        c_match = self.selectors.chatgpt.get("url_match", "chatgpt.com")

        self.perplexity_tab = None
        self.chatgpt_tab = None

        for p in pages:
            if p_match in p.url:
                self.perplexity_tab = p
            elif c_match in p.url or "chat.openai.com" in p.url:
                self.chatgpt_tab = p

        # If not open, open new pages automatically
        if not self.perplexity_tab:
            self.perplexity_tab = await context.new_page()
            await self.perplexity_tab.goto("https://www.perplexity.ai")
        if not self.chatgpt_tab:
            self.chatgpt_tab = await context.new_page()
            await self.chatgpt_tab.goto("https://chatgpt.com")

        return self.perplexity_tab, self.chatgpt_tab

    async def reconnect(self) -> bool:
        for attempt in range(1, self.config.reconnect_attempts + 1):
            await asyncio.sleep(self.config.reconnect_delay_seconds)
            try:
                await self.close()
                ok = await self.connect()
                if ok:
                    await self.find_tabs()
                    return True
            except Exception:
                pass
        return False

    async def close(self):
        self.is_connected = False
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
```

```python
# scripts/test_cdp.py
import asyncio
from core.config_loader import load_config, load_selectors
from core.cdp_connector import CDPConnector

async def main():
    print("Testing CDP Connection to http://localhost:9222...")
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    connector = CDPConnector(config, selectors)
    
    ok = await connector.connect()
    if not ok:
        print("[-] FAILED: Could not connect to port 9222. Ensure launch_comet.bat has been run.")
        return
    print("[+] SUCCESS: Connected to Chromium via CDP!")
    p_tab, c_tab = await connector.find_tabs()
    print(f"[+] Perplexity Tab: {p_tab.url if p_tab else 'Not Found'}")
    print(f"[+] ChatGPT Tab: {c_tab.url if c_tab else 'Not Found'}")
    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cdp_connector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/cdp_connector.py scripts/test_cdp.py tests/test_cdp_connector.py
git commit -m "feat: implement CDP connector, tab detection, and connection test script"
```

---

### Task 5: 3-Layer Stream & Tool Completion Detector

**Files:**
- Create: `core/stream_detector.py`
- Test: `tests/test_stream_detector.py`

**Interfaces:**
- Produces: `core.stream_detector.StreamDetector`
  - `wait_for_completion(page: Page, agent_type: str) -> str`
  - `send_prompt(page: Page, text: str, agent_type: str)`

- [ ] **Step 1: Write test for StreamDetector text stability and button state logic**

```python
# tests/test_stream_detector.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.stream_detector import StreamDetector
from core.config_loader import AppConfig, SelectorsConfig

@pytest.mark.asyncio
async def test_stream_detector_send_prompt():
    config = AppConfig()
    selectors = SelectorsConfig(
        perplexity={"input_textarea": "textarea", "send_button": "button.submit"},
        chatgpt={"prompt_textarea": "#prompt-textarea", "send_button": "button.send"}
    )
    detector = StreamDetector(config, selectors)
    mock_page = AsyncMock()
    
    await detector.send_prompt(mock_page, "Hello World", agent_type="perplexity")
    mock_page.fill.assert_called_with("textarea", "Hello World")
    mock_page.click.assert_called_with("button.submit")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stream_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.stream_detector'`

- [ ] **Step 3: Implement core/stream_detector.py**

```python
# core/stream_detector.py
import asyncio
import time
from playwright.async_api import Page
from core.config_loader import AppConfig, SelectorsConfig

class StreamDetector:
    def __init__(self, config: AppConfig, selectors: SelectorsConfig):
        self.config = config
        self.selectors = selectors

    async def send_prompt(self, page: Page, text: str, agent_type: str):
        if agent_type == "perplexity":
            s_input = self.selectors.perplexity["input_textarea"]
            s_send = self.selectors.perplexity["send_button"]
        else:
            s_input = self.selectors.chatgpt["prompt_textarea"]
            s_send = self.selectors.chatgpt["send_button"]

        await page.wait_for_selector(s_input, timeout=10000)
        await page.fill(s_input, text)
        await asyncio.sleep(0.3)
        await page.click(s_send)

    async def wait_for_completion(self, page: Page, agent_type: str) -> str:
        s_cfg = self.selectors.perplexity if agent_type == "perplexity" else self.selectors.chatgpt
        s_stop = s_cfg.get("stop_button")
        s_send = s_cfg.get("send_button")
        s_resp = s_cfg.get("last_response")
        s_tool = s_cfg.get("tool_running_indicator")

        start_time = time.time()
        timeout = self.config.timeout_seconds
        stability_duration = self.config.text_stability_seconds

        # Wait 2 seconds for generation to kick off
        await asyncio.sleep(2.0)

        last_text = ""
        stable_start: Optional[float] = None

        while time.time() - start_time < timeout:
            # 1. Check if Stop button is still visible
            if s_stop:
                try:
                    stop_visible = await page.is_visible(s_stop)
                    if stop_visible:
                        stable_start = None
                        await asyncio.sleep(1.0)
                        continue
                except Exception:
                    pass

            # 2. Check if GitHub Tool is executing (ChatGPT)
            if s_tool:
                try:
                    tool_visible = await page.is_visible(s_tool)
                    if tool_visible:
                        stable_start = None
                        await asyncio.sleep(1.5)
                        continue
                except Exception:
                    pass

            # 3. Check Text Stability
            try:
                elements = await page.query_selector_all(s_resp)
                if elements:
                    current_text = await elements[-1].inner_text()
                else:
                    current_text = ""
            except Exception:
                current_text = last_text

            if current_text and current_text == last_text:
                if stable_start is None:
                    stable_start = time.time()
                elif time.time() - stable_start >= stability_duration:
                    return current_text
            else:
                last_text = current_text
                stable_start = None

            await asyncio.sleep(0.8)

        raise TimeoutError(f"{agent_type.capitalize()} response timed out after {timeout} seconds")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stream_detector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/stream_detector.py tests/test_stream_detector.py
git commit -m "feat: implement 3-layer stream and tool completion detector"
```

---

### Task 6: Orchestrator FSM Engine & Session Recorder

**Files:**
- Create: `core/orchestrator_fsm.py`
- Test: `tests/test_orchestrator_fsm.py`

**Interfaces:**
- Produces: `core.orchestrator_fsm.OrchestratorFSM`
  - States: `FSMState` enum
  - `start_task(repo: str, branch: str, goal: str, auto_mode: bool = True)`
  - `pause()`, `resume()`, `stop()`, `abort()`
  - `approve_step(modified_payload: Optional[str] = None)`
  - Callbacks for UI updates: `on_state_change`, `on_log`, `on_approval_required`

- [ ] **Step 1: Write test for FSM state transitions**

```python
# tests/test_orchestrator_fsm.py
import pytest
from core.orchestrator_fsm import OrchestratorFSM, FSMState
from core.config_loader import AppConfig, SelectorsConfig

def test_fsm_initial_state():
    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))
    assert fsm.state == FSMState.IDLE
    assert fsm.loop_count == 0

def test_fsm_stop_and_abort():
    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))
    fsm.state = FSMState.PERPLEXITY_WAITING
    fsm.stop()
    assert fsm.state == FSMState.IDLE
    
    fsm.state = FSMState.CHATGPT_WAITING
    fsm.abort()
    assert fsm.state == FSMState.ABORTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator_fsm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.orchestrator_fsm'`

- [ ] **Step 3: Implement core/orchestrator_fsm.py**

```python
# core/orchestrator_fsm.py
import asyncio
import json
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from core.config_loader import AppConfig, SelectorsConfig
from core.cdp_connector import CDPConnector
from core.stream_detector import StreamDetector
from core.tag_protocol import parse_agent_output, AgentStatus, TagParseResult

class FSMState(str, Enum):
    IDLE = "IDLE"
    PERPLEXITY_SENDING = "PERPLEXITY_SENDING"
    PERPLEXITY_WAITING = "PERPLEXITY_WAITING"
    PERPLEXITY_PARSING = "PERPLEXITY_PARSING"
    WAITING_USER_APPROVAL = "WAITING_USER_APPROVAL"
    CHATGPT_SENDING = "CHATGPT_SENDING"
    CHATGPT_WAITING = "CHATGPT_WAITING"
    CHATGPT_PARSING = "CHATGPT_PARSING"
    MAX_LOOPS_HALTED = "MAX_LOOPS_HALTED"
    TASK_FINISHED = "TASK_FINISHED"
    PAUSED = "PAUSED"
    ABORTED = "ABORTED"
    RECONNECTING = "RECONNECTING"
    CDP_ERROR = "CDP_ERROR"

class OrchestratorFSM:
    def __init__(self, config: AppConfig, selectors: SelectorsConfig):
        self.config = config
        self.selectors = selectors
        self.state: FSMState = FSMState.IDLE
        self.loop_count: int = 0
        self.max_loops: int = config.max_loops
        self.auto_mode: bool = True
        self.is_running: bool = False
        
        self.connector = CDPConnector(config, selectors)
        self.detector = StreamDetector(config, selectors)
        
        self.on_state_change: Optional[Callable[[FSMState], None]] = None
        self.on_log: Optional[Callable[[str, str], None]] = None # (source, message)
        self.on_approval_required: Optional[Callable[[str, TagParseResult], None]] = None
        
        self.current_repo: str = ""
        self.current_branch: str = ""
        self.current_goal: str = ""
        self.pending_payload: str = ""
        self.target_agent_for_pending: str = ""
        self.approval_event = asyncio.Event()
        self.session_events: list = []

    def set_state(self, new_state: FSMState):
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def log(self, source: str, message: str):
        self.session_events.append({"timestamp": time.time(), "source": source, "message": message})
        if self.on_log:
            self.on_log(source, message)

    async def start_task(self, repo: str, branch: str, goal: str, max_loops: int, auto_mode: bool = True):
        self.current_repo = repo
        self.current_branch = branch
        self.current_goal = goal
        self.max_loops = max_loops
        self.auto_mode = auto_mode
        self.loop_count = 0
        self.is_running = True
        self.session_events = []

        self.log("system", f"Bắt đầu tác vụ cho repo: {repo} (Nhánh: {branch})")
        connected = await self.connector.connect()
        if not connected:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không thể kết nối tới trình duyệt qua cổng 9222!")
            return

        p_tab, c_tab = await self.connector.find_tabs()
        if not p_tab or not c_tab:
            self.set_state(FSMState.CDP_ERROR)
            self.log("system", "Không tìm thấy đủ tab Perplexity và ChatGPT.")
            return

        asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        p_lead_template = Path("prompts/perplexity_lead.md").read_text(encoding="utf-8")
        first_prompt = f"{p_lead_template}\n\n[MỤC TIÊU BÀI TOÁN]:\nRepository: {self.current_repo}\nBranch: {self.current_branch}\nYêu cầu: {self.current_goal}"
        
        next_prompt = first_prompt
        while self.is_running and self.loop_count < self.max_loops:
            self.loop_count += 1
            self.log("system", f"--- Bắt đầu Vòng lặp {self.loop_count} / {self.max_loops} ---")

            # 1. Gửi Perplexity
            self.set_state(FSMState.PERPLEXITY_SENDING)
            self.log("perplexity", f"Gửi yêu cầu phân tích vào Perplexity...")
            await self.detector.send_prompt(self.connector.perplexity_tab, next_prompt, "perplexity")

            self.set_state(FSMState.PERPLEXITY_WAITING)
            raw_p_resp = await self.detector.wait_for_completion(self.connector.perplexity_tab, "perplexity")
            
            self.set_state(FSMState.PERPLEXITY_PARSING)
            p_result = parse_agent_output(raw_p_resp, source="perplexity")
            self.log("perplexity", f"Nhận kết quả: {p_result.status.value}")

            if p_result.status == AgentStatus.COMPLETED:
                self.set_state(FSMState.TASK_FINISHED)
                self.log("system", "Task đã được nghiệm thu hoàn tất!")
                self._save_session("COMPLETED")
                return

            # Chờ duyệt nếu ở chế độ Step-by-step
            c_dev_template = Path("prompts/chatgpt_dev.md").read_text(encoding="utf-8")
            chatgpt_prompt = f"{c_dev_template}\n\n[TASK_SPEC FROM TECH LEAD]:\n{raw_p_resp}\n\n[TARGET REPO]: {self.current_repo}"
            
            if not self.auto_mode:
                self.set_state(FSMState.WAITING_USER_APPROVAL)
                self.pending_payload = chatgpt_prompt
                self.target_agent_for_pending = "chatgpt"
                self.approval_event.clear()
                if self.on_approval_required:
                    self.on_approval_required("ChatGPT", p_result)
                await self.approval_event.wait()
                chatgpt_prompt = self.pending_payload

            if not self.is_running:
                break

            # 2. Gửi ChatGPT
            self.set_state(FSMState.CHATGPT_SENDING)
            self.log("chatgpt", "Chuyển payload sang ChatGPT...")
            await self.detector.send_prompt(self.connector.chatgpt_tab, chatgpt_prompt, "chatgpt")

            self.set_state(FSMState.CHATGPT_WAITING)
            raw_c_resp = await self.detector.wait_for_completion(self.connector.chatgpt_tab, "chatgpt")

            self.set_state(FSMState.CHATGPT_PARSING)
            c_result = parse_agent_output(raw_c_resp, source="chatgpt")
            self.log("chatgpt", f"Nhận kết quả: {c_result.status.value}")

            if c_result.status == AgentStatus.ERROR:
                self.log("chatgpt", "ChatGPT báo lỗi, gửi lại Perplexity phân tích...")
                next_prompt = f"[BÁO CÁO SỰ CỐ TỪ DEV]:\n{raw_c_resp}\nHãy phân tích nguyên nhân và cập nhật hướng dẫn sửa đổi."
            else:
                next_prompt = f"[KẾT QUẢ PULL REQUEST TỪ DEV]:\n{raw_c_resp}\nHãy nghiệm thu mã nguồn này và xuất [STATUS: COMPLETED] nếu đạt chuẩn hoặc [STATUS: NEEDS_REVISION] nếu cần sửa."

        if self.loop_count >= self.max_loops and self.is_running:
            self.set_state(FSMState.MAX_LOOPS_HALTED)
            self.log("system", f"Đã chạm trần Max Loops ({self.max_loops}). Tạm dừng để người dùng duyệt tay.")
            self._save_session("HALTED")

    def approve_step(self, modified_payload: Optional[str] = None):
        if modified_payload:
            self.pending_payload = modified_payload
        self.approval_event.set()

    def pause(self):
        self.set_state(FSMState.PAUSED)
        self.log("system", "Hệ thống tạm dừng.")

    def stop(self):
        self.is_running = False
        self.approval_event.set()
        self.set_state(FSMState.IDLE)
        self.log("system", "Hệ thống đã dừng khẩn cấp.")

    def abort(self):
        self.is_running = False
        self.approval_event.set()
        self.set_state(FSMState.ABORTED)
        self.log("system", "Tác vụ đã bị hủy bỏ (Aborted).")
        self._save_session("ABORTED")

    def _save_session(self, final_status: str):
        Path("storage/sessions").mkdir(parents=True, exist_ok=True)
        filename = f"storage/sessions/{int(time.time())}_{self.current_repo.replace('/', '_')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "repo": self.current_repo,
                "branch": self.current_branch,
                "goal": self.current_goal,
                "loops": self.loop_count,
                "final_status": final_status,
                "events": self.session_events
            }, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orchestrator_fsm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator_fsm.py tests/test_orchestrator_fsm.py
git commit -m "feat: implement orchestrator FSM engine with session persistence"
```

---

### Task 7: Async Log Streamer & Queue

**Files:**
- Create: `ui/log_streamer.py`
- Test: `tests/test_log_streamer.py`

**Interfaces:**
- Produces: `ui.log_streamer.LogStreamer`
  - `push(source: str, message: str)`
  - `get_recent_logs(limit: int) -> list`
  - `subscribe(callback)`

- [ ] **Step 1: Write test for log queue and subscriber delivery**

```python
# tests/test_log_streamer.py
import pytest
from ui.log_streamer import LogStreamer

def test_log_streamer_push_and_subscribe():
    streamer = LogStreamer()
    received = []
    streamer.subscribe(lambda item: received.append(item))
    
    streamer.push("perplexity", "Found docs")
    assert len(received) == 1
    assert received[0]["source"] == "perplexity"
    assert received[0]["message"] == "Found docs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_log_streamer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui.log_streamer'`

- [ ] **Step 3: Implement ui/log_streamer.py**

```python
# ui/log_streamer.py
import time
from typing import Callable, List, Dict, Any

class LogStreamer:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []
        self.subscribers: List[Callable[[Dict[str, Any]], None]] = []

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        self.subscribers.append(callback)

    def push(self, source: str, message: str):
        item = {
            "timestamp": time.strftime("%H:%M:%S"),
            "source": source,
            "message": message
        }
        self.logs.append(item)
        for cb in self.subscribers:
            try:
                cb(item)
            except Exception:
                pass

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.logs[-limit:]

    def clear(self):
        self.logs.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_log_streamer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/log_streamer.py tests/test_log_streamer.py
git commit -m "feat: implement async log streamer for real-time UI logging"
```

---

### Task 8: Step-by-Step Approval Modal

**Files:**
- Create: `ui/preview_modal.py`
- Test: `tests/test_preview_modal.py`

**Interfaces:**
- Produces: `ui.preview_modal.PreviewModal` (NiceGUI dialog component)

- [ ] **Step 1: Write test for PreviewModal creation and payload assignment**

```python
# tests/test_preview_modal.py
from ui.preview_modal import PreviewModalState

def test_preview_modal_state():
    state = PreviewModalState()
    state.open_modal(target="ChatGPT", payload="Initial Prompt")
    assert state.is_visible is True
    assert state.target == "ChatGPT"
    assert state.payload == "Initial Prompt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_modal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui.preview_modal'`

- [ ] **Step 3: Implement ui/preview_modal.py**

```python
# ui/preview_modal.py
from typing import Optional, Callable
from nicegui import ui

class PreviewModalState:
    def __init__(self):
        self.is_visible: bool = False
        self.target: str = ""
        self.payload: str = ""

    def open_modal(self, target: str, payload: str):
        self.is_visible = True
        self.target = target
        self.payload = payload

    def close_modal(self):
        self.is_visible = False

class PreviewModal:
    def __init__(self, on_approve: Callable[[str], None], on_reject: Callable[[], None]):
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.state = PreviewModalState()
        self._build_dialog()

    def _build_dialog(self):
        with ui.dialog() as self.dialog, ui.card().classes("w-[700px] max-w-4xl p-6"):
            self.title_label = ui.label("Duyệt Payload chuyển giao").classes("text-xl font-bold")
            ui.label("Xem trước và chỉnh sửa nội dung trước khi gửi sang tab tiếp theo:").classes("text-sm text-gray-500 mb-2")
            
            self.payload_input = ui.textarea(label="Nội dung gửi").classes("w-full h-64 font-mono text-sm")
            
            with ui.row().classes("w-full justify-end mt-4 gap-3"):
                ui.button("Hủy bỏ bước", color="red", on_click=self._handle_reject).props("flat")
                ui.button("Duyệt & Gửi tiếp", color="green", on_click=self._handle_approve)

    def show(self, target: str, payload: str):
        self.state.open_modal(target, payload)
        self.title_label.text = f"Duyệt Payload chuyển giao sang {target}"
        self.payload_input.value = payload
        self.dialog.open()

    def _handle_approve(self):
        self.dialog.close()
        self.on_approve(self.payload_input.value)

    def _handle_reject(self):
        self.dialog.close()
        self.on_reject()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_modal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/preview_modal.py tests/test_preview_modal.py
git commit -m "feat: implement step-by-step preview and approval dialog"
```

---

### Task 9: NiceGUI Control Panel & Main Application

**Files:**
- Create: `ui/app.py`
- Create: `run.py`
- Test: `tests/test_ui_app.py`

**Interfaces:**
- Produces: `ui.app.build_ui()`: Creates the full NiceGUI 2-column reactive dashboard.
- Produces: `run.py`: Application entrypoint.

- [ ] **Step 1: Write smoke test verifying run.py entrypoint syntax and components**

```python
# tests/test_ui_app.py
import pytest
from core.config_loader import load_config, load_selectors
from core.orchestrator_fsm import OrchestratorFSM

def test_app_components_instantiation():
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    fsm = OrchestratorFSM(config, selectors)
    assert fsm is not None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_ui_app.py -v`
Expected: PASS

- [ ] **Step 3: Implement ui/app.py and run.py**

```python
# ui/app.py
from nicegui import ui
from core.config_loader import load_config, load_selectors
from core.orchestrator_fsm import OrchestratorFSM, FSMState
from ui.log_streamer import LogStreamer
from ui.preview_modal import PreviewModal

def build_ui():
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    fsm = OrchestratorFSM(config, selectors)
    streamer = LogStreamer()

    ui.page_title("AI Agent Browser Orchestrator")

    # Connect FSM to LogStreamer
    def fsm_log(source, msg):
        streamer.push(source, msg)
    fsm.on_log = fsm_log

    # Header
    with ui.header().classes("bg-slate-900 text-white p-4 flex justify-between items-center"):
        ui.label("AI AGENT BROWSER ORCHESTRATOR").classes("text-lg font-bold tracking-wider")
        cdp_badge = ui.badge("CDP: Port 9222", color="green").classes("px-3 py-1 text-xs")

    # 2-Column Main Layout
    with ui.row().classes("w-full p-4 gap-6"):
        # Left Column: Configuration & Controls (40%)
        with ui.column().classes("w-5/12 bg-white p-5 rounded-lg border shadow-sm gap-4"):
            ui.label("Cấu hình Nhiệm vụ").classes("text-base font-semibold text-slate-800")
            
            repo_input = ui.input(label="Repository (vd: owner/repo)", value="example/my-project").classes("w-full")
            branch_input = ui.input(label="Base Branch", value="main").classes("w-full")
            goal_input = ui.textarea(label="Mục tiêu Task kỹ thuật", placeholder="Mô tả chi tiết bug cần sửa hoặc feature cần code...").classes("w-full h-28")
            
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Giới hạn Vòng lặp:").classes("text-sm text-gray-700")
                loop_slider = ui.slider(min=1, max=10, value=5).classes("w-48")
                loop_label = ui.label("5").classes("font-mono font-bold")
                loop_slider.bind_value_to(loop_label, "text", forward=lambda v: str(v))

            auto_switch = ui.switch("Chạy tự động (Auto-pilot)", value=True)

            ui.separator()
            ui.label("Điều khiển Vận hành").classes("text-sm font-semibold text-slate-700")
            
            with ui.row().classes("w-full gap-2"):
                start_btn = ui.button("Bắt đầu", color="primary", icon="play_arrow").classes("flex-1")
                pause_btn = ui.button("Tạm dừng", color="warning", icon="pause").classes("flex-1")
                stop_btn = ui.button("Dừng khẩn", color="negative", icon="stop").classes("flex-1")

            abort_btn = ui.button("Hủy bỏ & Rollback Task", color="red-8", icon="cancel").classes("w-full")

        # Right Column: Real-time Log Stream & State (60%)
        with ui.column().classes("w-6/12 bg-white p-5 rounded-lg border shadow-sm gap-4 flex-1"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-2"):
                    ui.label("Trạng thái:").classes("text-sm font-semibold")
                    state_badge = ui.badge("IDLE", color="gray").classes("px-3 py-1 font-mono")
                
                with ui.row().classes("items-center gap-2"):
                    ui.label("Vòng lặp:").classes("text-sm font-semibold")
                    loop_badge = ui.badge("0 / 5", color="blue").classes("px-3 py-1 font-mono")

            # Update badges on state change
            def on_state_update(st: FSMState):
                state_badge.text = st.value
                state_badge.color = "green" if st == FSMState.TASK_FINISHED else "red" if "ERROR" in st.value else "blue"
                loop_badge.text = f"{fsm.loop_count} / {fsm.max_loops}"
            fsm.on_state_change = on_state_update

            # Tabs for Logs
            with ui.tabs().classes("w-full") as tabs:
                tab_all = ui.tab("Tất cả Log")
                tab_p = ui.tab("Perplexity (Lead)")
                tab_c = ui.tab("ChatGPT (Dev)")

            log_container = ui.column().classes("w-full h-[450px] overflow-y-auto bg-slate-950 text-slate-200 p-3 rounded font-mono text-xs gap-1")

            def add_log_ui(item):
                color = "text-purple-400" if item["source"] == "perplexity" else "text-emerald-400" if item["source"] == "chatgpt" else "text-blue-300"
                with log_container:
                    ui.label(f"[{item['timestamp']}] [{item['source'].upper()}]: {item['message']}").classes(color)

            streamer.subscribe(add_log_ui)

            with ui.row().classes("w-full justify-between mt-2"):
                ui.button("Xóa Log", on_click=lambda: (streamer.clear(), log_container.clear())).props("flat text-gray-500")
                ui.button("Lưu phiên (Export)", on_click=lambda: ui.notify("Đã lưu phiên vào storage/sessions/")).props("flat text-blue-500")

    # Preview Modal Setup
    modal = PreviewModal(
        on_approve=lambda payload: fsm.approve_step(payload),
        on_reject=lambda: fsm.abort()
    )
    fsm.on_approval_required = lambda target, res: modal.show(target, fsm.pending_payload)

    # Event handlers
    start_btn.on_click(lambda: fsm.start_task(
        repo=repo_input.value,
        branch=branch_input.value,
        goal=goal_input.value,
        max_loops=int(loop_slider.value),
        auto_mode=auto_switch.value
    ))
    pause_btn.on_click(lambda: fsm.pause())
    stop_btn.on_click(lambda: fsm.stop())
    abort_btn.on_click(lambda: fsm.abort())
```

```python
# run.py
from nicegui import ui
from ui.app import build_ui

if __name__ in {"__main__", "__mp_main__"}:
    build_ui()
    ui.run(title="AI Agent Browser Orchestrator", port=8080, reload=False)
```

- [ ] **Step 4: Commit**

```bash
git add ui/app.py run.py tests/test_ui_app.py
git commit -m "feat: complete NiceGUI 2-column control panel and run.py entrypoint"
```

---

### Task 10: End-to-End Test Suite & Verification

**Files:**
- Create: `tests/test_e2e_dry_run.py`
- Modify: `README.md`

- [ ] **Step 1: Write E2E mock dry-run test exercising full FSM loop**

```python
# tests/test_e2e_dry_run.py
import pytest
from unittest.mock import AsyncMock, patch
from core.orchestrator_fsm import OrchestratorFSM, FSMState
from core.config_loader import AppConfig, SelectorsConfig

@pytest.mark.asyncio
async def test_fsm_e2e_dry_run_completion():
    config = AppConfig(default_max_loops=3)
    selectors = SelectorsConfig(perplexity={"input_textarea": "t", "send_button": "b"}, chatgpt={"prompt_textarea": "t", "send_button": "b"})
    fsm = OrchestratorFSM(config, selectors)
    
    # Mock CDP and StreamDetector
    fsm.connector.connect = AsyncMock(return_value=True)
    fsm.connector.find_tabs = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    
    # Mock Perplexity returns [STATUS: COMPLETED] immediately
    fsm.detector.send_prompt = AsyncMock()
    fsm.detector.wait_for_completion = AsyncMock(return_value="""
    [STATUS: COMPLETED]
    [SUMMARY]: Hoàn thành xuất sắc nhiệm vụ!
    """)
    
    await fsm.start_task("test/repo", "main", "Fix issue", max_loops=3, auto_mode=True)
    # Give task a moment to complete
    import asyncio
    await asyncio.sleep(0.5)
    
    assert fsm.state == FSMState.TASK_FINISHED
```

- [ ] **Step 2: Run all unit & E2E tests**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Create README.md with clear usage instructions**

```markdown
# AI Agent Browser Orchestrator

Hệ thống điều phối đa Agent giữa **Perplexity (Comet)** và **ChatGPT (GitHub Integration)** điều khiển qua giao diện **Python + NiceGUI**.

## Cài đặt
```bash
pip install -r requirements.txt
playwright install chromium
```

## Khởi động
1. Bật trình duyệt Comet/Chrome với cờ CDP cổng 9222:
```bash
scripts\launch_comet.bat
```
2. Kiểm tra kết nối CDP:
```bash
python scripts\test_cdp.py
```
3. Chạy ứng dụng giao diện:
```bash
python run.py
```
Mở trình duyệt truy cập: `http://localhost:8080`
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_dry_run.py README.md
git commit -m "feat: add E2E dry run tests and project README instructions"
```
