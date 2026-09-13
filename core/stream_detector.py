import asyncio
import time
import re
from typing import Optional, Callable, Tuple
from playwright.async_api import Page
from core.config_loader import AppConfig, SelectorsConfig

def check_terminal_signal(text: str, agent_type: str) -> Tuple[bool, str]:
    """
    Checks if text contains a terminal protocol tag or completed action:
    Returns (is_terminal, status_label)
    """
    if not text or len(text.strip()) < 10:
        return False, ""
        
    if agent_type == "perplexity":
        if "[STATUS: READY_FOR_DEV]" in text or re.search(r"\[STATUS\s*:\s*READY_FOR_DEV\]", text, re.I):
            return True, "READY_FOR_DEV"
        if "[STATUS: NEEDS_REVISION]" in text or re.search(r"\[STATUS\s*:\s*NEEDS_REVISION\]", text, re.I):
            return True, "NEEDS_REVISION"
        if "[STATUS: COMPLETED]" in text or re.search(r"\[STATUS\s*:\s*COMPLETED\]", text, re.I):
            return True, "COMPLETED"
        if "[STATUS: ERROR]" in text or re.search(r"\[STATUS\s*:\s*ERROR\]", text, re.I):
            return True, "ERROR"
    else:  # chatgpt
        if "[STATUS: COMMITTED]" in text or re.search(r"\[STATUS\s*:\s*COMMITTED\]", text, re.I):
            return True, "COMMITTED"
        if "[STATUS: ERROR]" in text or re.search(r"\[STATUS\s*:\s*ERROR\]", text, re.I):
            return True, "ERROR"
        # Heuristic fallback: GitHub PR URL present along with branch or commit sha
        if re.search(r"https://github\.com/[^\s]+/pull/\d+", text) and (
            re.search(r"\b[0-9a-f]{7,40}\b", text, re.I) or "ai-agent/" in text or "[BRANCH" in text
        ):
            return True, "COMMITTED"

    return False, ""

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

        el = None
        if hasattr(page, "wait_for_selector"):
            try:
                el = await page.wait_for_selector(s_input, state="visible", timeout=15000)
            except Exception:
                el = await page.query_selector(s_input)
        elif hasattr(page, "query_selector"):
            el = await page.query_selector(s_input)

        if el:
            if hasattr(el, "click"):
                try:
                    await el.click(force=True, timeout=5000)
                except Exception:
                    pass
            if hasattr(el, "focus"):
                try:
                    await el.focus()
                except Exception:
                    pass
            await asyncio.sleep(0.3)

            # Try keyboard.insert_text first (works for Lexical / ProseMirror contenteditable and textarea)
            if hasattr(page, "keyboard") and hasattr(page.keyboard, "insert_text"):
                await page.keyboard.insert_text(text)
            elif hasattr(el, "fill"):
                await el.fill(text)
            elif hasattr(page, "fill"):
                await page.fill(s_input, text)
        elif hasattr(page, "fill"):
            await page.fill(s_input, text)

        await asyncio.sleep(0.6)

        # Try clicking send button
        submitted = False
        if hasattr(page, "query_selector") and s_send:
            try:
                btn = await page.query_selector(s_send)
                if btn and await btn.is_visible():
                    await btn.click(force=True, timeout=5000)
                    submitted = True
            except Exception:
                pass

        # Fallback: Press Enter to submit
        if not submitted and hasattr(page, "keyboard"):
            await page.keyboard.press("Enter")

    async def wait_for_completion(self, page: Page, agent_type: str, on_progress: Optional[Callable[[str], None]] = None) -> str:
        s_cfg = self.selectors.perplexity if agent_type == "perplexity" else self.selectors.chatgpt
        s_stop = s_cfg.get("stop_button")
        s_resp = s_cfg.get("last_response")
        s_tool = s_cfg.get("tool_running_indicator")
        s_action = s_cfg.get("action_buttons")

        start_time = time.time()
        timeout = self.config.timeout_seconds
        stability_duration = self.config.text_stability_seconds

        await asyncio.sleep(2.0)

        last_text = ""
        stable_start: Optional[float] = None
        last_progress_time = start_time
        detected_terminal_tag = False
        terminal_status_name = ""

        while time.time() - start_time < timeout:
            now = time.time()
            elapsed = int(now - start_time)

            # 1. Fetch current response text
            current_text = ""
            if hasattr(page, "query_selector_all") and s_resp:
                try:
                    elements = await page.query_selector_all(s_resp)
                    if elements:
                        current_text = await elements[-1].inner_text()
                except Exception:
                    pass

            # 2. Check if terminal protocol tag is present in current text
            is_terminal, status_label = check_terminal_signal(current_text, agent_type)
            if is_terminal and not detected_terminal_tag:
                detected_terminal_tag = True
                terminal_status_name = status_label
                if on_progress:
                    on_progress(f"Đã phát hiện tín hiệu hoàn tất [{status_label}]. Đang kiểm tra ổn định dữ liệu...")

            # 3. Check DOM signals (Action buttons like copy button, Stop button, Tool running)
            has_action_buttons = False
            if s_action and hasattr(page, "query_selector_all"):
                try:
                    act_btns = await page.query_selector_all(s_action)
                    for b in act_btns:
                        if await b.is_visible():
                            has_action_buttons = True
                            break
                except Exception:
                    pass

            stop_visible = False
            if s_stop and hasattr(page, "is_visible"):
                try:
                    stop_visible = await page.is_visible(s_stop)
                except Exception:
                    pass

            is_tool_running = False
            if s_tool and hasattr(page, "is_visible"):
                try:
                    is_tool_running = await page.is_visible(s_tool)
                except Exception:
                    pass

            # 4. Progress logging every 5 seconds
            if on_progress and (now - last_progress_time >= 5.0):
                last_progress_time = now
                if is_tool_running:
                    on_progress(f"AI đang thực thi công cụ (Tool Calling)... ({elapsed}s)")
                elif current_text and len(current_text) > len(last_text):
                    on_progress(f"Đang nhận dữ liệu trực tiếp ({len(current_text)} ký tự)... ({elapsed}s)")
                elif detected_terminal_tag:
                    on_progress(f"Đang chốt kết quả sau tag [{terminal_status_name}]... ({elapsed}s)")
                else:
                    on_progress(f"Đang chờ {agent_type.capitalize()} phản hồi... ({elapsed}s / {timeout}s)")

            # 5. Stability & Completion Verification
            # Text changed? Reset stability
            if len(current_text) != len(last_text) or current_text != last_text:
                last_text = current_text
                stable_start = None
            elif current_text and current_text == last_text:
                # Text has stopped changing
                if stable_start is None:
                    stable_start = now
                else:
                    stable_duration = now - stable_start

                    # CASE A: Terminal tag is present AND text has stabilized for stability_duration
                    # (Even if stop button lingers as a ghost, terminal tag proves generation ended!)
                    if detected_terminal_tag and stable_duration >= stability_duration:
                        if on_progress:
                            on_progress(f"Hoàn thành chính xác qua Thẻ Giao Thức [{terminal_status_name}] ({elapsed}s)")
                        return current_text

                    # CASE B: Turn action buttons (Copy / Feedback) are visible AND text is stable
                    if has_action_buttons and not is_tool_running and stable_duration >= stability_duration:
                        if on_progress:
                            on_progress(f"Hoàn thành chính xác qua DOM Action Buttons ({elapsed}s)")
                        return current_text

                    # CASE C: No stop button, no tool running, text stable
                    if not stop_visible and not is_tool_running and stable_duration >= stability_duration:
                        if on_progress:
                            on_progress(f"Hoàn thành phản hồi (Stop button unmounted, text ổn định {elapsed}s)")
                        return current_text

            await asyncio.sleep(0.8)

        raise TimeoutError(f"{agent_type.capitalize()} response timed out after {timeout} seconds")
