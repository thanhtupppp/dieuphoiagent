import asyncio
import time
import re
from typing import Optional, Callable, Tuple
from playwright.async_api import Page
from core.config_loader import AppConfig, SelectorsConfig

OBSERVER_JS = """
(() => {
  if (window.__dpaObserver) return;
  let timer = null;
  const notify = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (typeof window.__dpaStable === 'function') {
        window.__dpaStable();
      }
    }, 2500);
  };
  window.__dpaObserver = new MutationObserver(notify);
  window.__dpaObserver.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
})();
"""


def check_terminal_signal(text: str, agent_type: str) -> Tuple[bool, str]:
    """
    Checks if text contains a terminal protocol tag, JSON block, or completed action:
    Returns (is_terminal, status_label)
    """
    if not text or len(text.strip()) < 10:
        return False, ""

    # Check for structured JSON fenced block first
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        content = json_match.group(1).lower()
        if "completed" in content or '"approved": true' in content or '"approved":true' in content:
            return True, "COMPLETED"
        if "ready_for_dev" in content:
            return True, "READY_FOR_DEV"
        if "needs_revision" in content or '"approved": false' in content or '"approved":false' in content:
            return True, "NEEDS_REVISION"
        if "committed" in content or "pr_url" in content or "commit_sha" in content:
            return True, "COMMITTED"
        if "error" in content:
            return True, "ERROR"

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
        self._page_callbacks: dict[int, Callable[[], None]] = {}

    def _dispatch_stable(self, page_id: int) -> None:
        cb = self._page_callbacks.get(page_id)
        if cb:
            cb()

    async def _setup_observer(self, page: Page, on_stable: Callable[[], None]) -> bool:
        """Register CDP / browser binding and inject MutationObserver once."""
        page_id = id(page)
        self._page_callbacks[page_id] = on_stable

        if hasattr(page, "expose_function"):
            try:
                await page.expose_function("__dpaStable", lambda: self._dispatch_stable(page_id))
            except Exception:
                pass

        if hasattr(page, "evaluate"):
            try:
                await page.evaluate(OBSERVER_JS)
                return True
            except Exception:
                return False
        return False

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
            await asyncio.sleep(0.2)

            inserted = False
            if hasattr(page, "evaluate"):
                try:
                    inserted = await page.evaluate("""({selector, content}) => {
                        const target = document.querySelector(selector);
                        if (!target) return false;
                        target.focus();
                        try {
                            const dt = new DataTransfer();
                            dt.setData('text/plain', content);
                            const ev = new ClipboardEvent('paste', {
                                clipboardData: dt,
                                bubbles: true,
                                cancelable: true
                            });
                            target.dispatchEvent(ev);
                            if ((target.innerText || target.textContent || '').trim().length > 0) {
                                return true;
                            }
                        } catch (e) {}

                        try {
                            if (document.execCommand('insertText', false, content)) {
                                return true;
                            }
                        } catch (e) {}
                        return false;
                    }""", {"selector": s_input, "content": text})
                except Exception:
                    inserted = False

            if not inserted:
                if hasattr(page, "keyboard") and hasattr(page.keyboard, "insert_text"):
                    await page.keyboard.insert_text(text)
                elif hasattr(el, "fill"):
                    await el.fill(text)
                elif hasattr(page, "fill"):
                    await page.fill(s_input, text)
        elif hasattr(page, "fill"):
            await page.fill(s_input, text)

        await asyncio.sleep(0.5)

        submitted = False
        if hasattr(page, "query_selector") and s_send:
            try:
                btn = await page.query_selector(s_send)
                if btn and await btn.is_visible():
                    await btn.click(force=True, timeout=5000)
                    submitted = True
            except Exception:
                pass

        if not submitted and hasattr(page, "keyboard"):
            await page.keyboard.press("Enter")

    async def wait_for_completion(
        self,
        page: Page,
        agent_type: str,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> str:
        s_cfg = self.selectors.perplexity if agent_type == "perplexity" else self.selectors.chatgpt
        s_stop = s_cfg.get("stop_button")
        s_resp = s_cfg.get("last_response")
        s_tool = s_cfg.get("tool_running_indicator")
        s_action = s_cfg.get("action_buttons")

        start_time = time.time()
        timeout = self.config.timeout_seconds
        stability_duration = self.config.text_stability_seconds

        dom_quiet_event = asyncio.Event()
        observer_active = await self._setup_observer(page, lambda: dom_quiet_event.set())
        if observer_active and on_progress:
            on_progress("Đã kích hoạt MutationObserver giám sát sự kiện DOM.")

        await asyncio.sleep(1.0)

        last_text = ""
        stable_start: Optional[float] = None
        last_progress_time = start_time
        detected_terminal_tag = False
        terminal_status_name = ""

        while time.time() - start_time < timeout:
            now = time.time()
            elapsed = int(now - start_time)

            dom_state = {}
            if hasattr(page, "evaluate"):
                try:
                    dom_state = await page.evaluate("""(cfg) => {
                        const isVisible = (el) => {
                            if (!el) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none' && s.visibility !== 'hidden' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
                        };

                        let text = '';
                        if (cfg.resp) {
                            const respEls = document.querySelectorAll(cfg.resp);
                            if (respEls.length > 0) {
                                const last = respEls[respEls.length - 1];
                                text = last.innerText || '';
                            }
                        }
                        
                        let hasStop = false;
                        if (cfg.stop) {
                            const stopEl = document.querySelector(cfg.stop);
                            hasStop = isVisible(stopEl);
                        }
                        
                        let hasAction = false;
                        if (cfg.action) {
                            const actEls = document.querySelectorAll(cfg.action);
                            for (let i = 0; i < actEls.length; i++) {
                                if (isVisible(actEls[i])) {
                                    hasAction = true;
                                    break;
                                }
                            }
                        }
                        
                        let isTool = false;
                        if (cfg.tool) {
                            const toolEl = document.querySelector(cfg.tool);
                            isTool = isVisible(toolEl);
                        }

                        return { text, hasStop, hasAction, isTool };
                    }""", {
                        "resp": s_resp,
                        "stop": s_stop,
                        "action": s_action,
                        "tool": s_tool
                    })
                except Exception:
                    pass

            if not isinstance(dom_state, dict) or not dom_state:
                dom_state = {}
                if hasattr(page, "query_selector_all") and s_resp:
                    try:
                        elements = await page.query_selector_all(s_resp)
                        if elements:
                            raw_t = elements[-1].inner_text()
                            dom_state["text"] = await raw_t if asyncio.iscoroutine(raw_t) else raw_t
                        if s_stop and hasattr(page, "is_visible"):
                            raw_vis = page.is_visible(s_stop)
                            dom_state["hasStop"] = await raw_vis if asyncio.iscoroutine(raw_vis) else raw_vis
                        if s_tool and hasattr(page, "is_visible"):
                            raw_tool = page.is_visible(s_tool)
                            dom_state["isTool"] = await raw_tool if asyncio.iscoroutine(raw_tool) else raw_tool
                    except Exception:
                        pass

            current_text = dom_state.get("text", "")
            stop_visible = dom_state.get("hasStop", False)
            has_action_buttons = dom_state.get("hasAction", False)
            is_tool_running = dom_state.get("isTool", False)

            is_terminal, status_label = check_terminal_signal(current_text, agent_type)
            if is_terminal and not detected_terminal_tag:
                detected_terminal_tag = True
                terminal_status_name = status_label
                if on_progress:
                    on_progress(f"Đã phát hiện tín hiệu hoàn tất [{status_label}]. Đang thẩm định tín hiệu kết thúc...")

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

            if len(current_text) != len(last_text) or current_text != last_text:
                last_text = current_text
                stable_start = None
                dom_quiet_event.clear()
            elif current_text and current_text == last_text:
                if stable_start is None:
                    stable_start = now

            sig_dom_quiet = bool(
                dom_quiet_event.is_set()
                or (stable_start is not None and (now - stable_start) >= stability_duration)
            )
            sig_button_ready = bool(
                not is_tool_running and ((not stop_visible and current_text != "") or has_action_buttons)
            )
            sig_protocol = bool(is_terminal)

            signals_met = sum([sig_dom_quiet, sig_button_ready, sig_protocol])

            if signals_met >= 2 and current_text:
                if on_progress:
                    sig_desc = []
                    if sig_dom_quiet:
                        sig_desc.append("DOM Quiet")
                    if sig_button_ready:
                        sig_desc.append("Button Ready")
                    if sig_protocol:
                        sig_desc.append(f"Protocol [{status_label}]")
                    on_progress(f"Hoàn tất phản hồi ({'+'.join(sig_desc)}) ({elapsed}s)")
                return current_text

            await asyncio.sleep(1.0)

        raise TimeoutError(f"{agent_type.capitalize()} response timed out after {timeout} seconds")

