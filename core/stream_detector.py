import asyncio
import time
from typing import Optional, Callable
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

        start_time = time.time()
        timeout = self.config.timeout_seconds
        stability_duration = self.config.text_stability_seconds

        await asyncio.sleep(2.0)

        last_text = ""
        stable_start: Optional[float] = None
        last_progress_time = start_time

        while time.time() - start_time < timeout:
            now = time.time()
            elapsed = now - start_time
            if on_progress and (now - last_progress_time >= 25.0):
                last_progress_time = now
                on_progress(f"Đang đợi {agent_type.capitalize()} xử lý và chạy Tool... (đã đợi {int(elapsed)}s / {timeout}s)")
            # 1. Stop button check
            if s_stop and hasattr(page, "is_visible"):
                try:
                    stop_visible = await page.is_visible(s_stop)
                    if stop_visible:
                        stable_start = None
                        await asyncio.sleep(1.0)
                        continue
                except Exception:
                    pass

            # 2. Tool calling indicator check (ChatGPT)
            if s_tool and hasattr(page, "is_visible"):
                try:
                    tool_visible = await page.is_visible(s_tool)
                    if tool_visible:
                        stable_start = None
                        await asyncio.sleep(1.5)
                        continue
                except Exception:
                    pass

            # 3. Text stability check
            current_text = last_text
            if hasattr(page, "query_selector_all") and s_resp:
                try:
                    elements = await page.query_selector_all(s_resp)
                    if elements:
                        current_text = await elements[-1].inner_text()
                except Exception:
                    pass

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
