import asyncio
import time
import re
from dataclasses import dataclass
from typing import Optional, Callable, Tuple, Any
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


@dataclass
class TabBaseline:
    response_count: int = 0
    last_text: str = ""


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

    async def get_baseline_state(self, page: Page, agent_type: str) -> TabBaseline:
        """Capture the response count and last response text before submitting a new turn."""
        s_cfg = self.selectors.perplexity if agent_type == "perplexity" else self.selectors.chatgpt
        s_resp = s_cfg.get("last_response")

        if not s_resp:
            return TabBaseline(response_count=0, last_text="")

        if hasattr(page, "evaluate"):
            try:
                res = await page.evaluate("""(selector) => {
                    const els = document.querySelectorAll(selector);
                    const count = els.length;
                    const lastText = count > 0 ? (els[count - 1].innerText || '').trim() : '';
                    return { count, lastText };
                }""", s_resp)
                if isinstance(res, dict):
                    return TabBaseline(
                        response_count=int(res.get("count", 0)),
                        last_text=str(res.get("lastText", "")),
                    )
            except Exception:
                pass

        if hasattr(page, "query_selector_all"):
            try:
                els = await page.query_selector_all(s_resp)
                count = len(els)
                last_text = ""
                if count > 0:
                    raw = els[-1].inner_text()
                    last_text = (await raw if asyncio.iscoroutine(raw) else raw).strip()
                return TabBaseline(response_count=count, last_text=last_text)
            except Exception:
                pass

        return TabBaseline(response_count=0, last_text="")

    async def _get_dom_state(
        self,
        page: Page,
        s_resp: Optional[str],
        s_stop: Optional[str],
        s_action: Optional[str],
        s_tool: Optional[str],
    ) -> dict[str, Any]:
        """Query the DOM once to collect response text, counts, and interactive control states."""
        dom_state: dict[str, Any] = {}
        if hasattr(page, "evaluate"):
            try:
                dom_state = await page.evaluate("""(cfg) => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
                    };

                    let text = '';
                    let count = 0;
                    if (cfg.resp) {
                        const respEls = document.querySelectorAll(cfg.resp);
                        count = respEls.length;
                        if (count > 0) {
                            const last = respEls[count - 1];
                            text = last.innerText || '';
                        }
                    }
                    
                    let hasStop = false;
                    if (cfg.stop) {
                        const stopEls = document.querySelectorAll(cfg.stop);
                        for (let i = 0; i < stopEls.length; i++) {
                            if (isVisible(stopEls[i])) {
                                hasStop = true;
                                break;
                            }
                        }
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
                        const toolEls = document.querySelectorAll(cfg.tool);
                        for (let i = 0; i < toolEls.length; i++) {
                            if (isVisible(toolEls[i])) {
                                isTool = true;
                                break;
                            }
                        }
                    }

                    return { text, count, hasStop, hasAction, isTool };
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
                    dom_state["count"] = len(elements)
                    if elements:
                        raw_t = elements[-1].inner_text()
                        dom_state["text"] = await raw_t if asyncio.iscoroutine(raw_t) else raw_t
                    if s_stop and hasattr(page, "is_visible"):
                        raw_vis = page.is_visible(s_stop)
                        dom_state["hasStop"] = await raw_vis if asyncio.iscoroutine(raw_vis) else raw_vis
                    if s_tool and hasattr(page, "is_visible"):
                        raw_tool = page.is_visible(s_tool)
                        dom_state["isTool"] = await raw_tool if asyncio.iscoroutine(raw_tool) else raw_tool
                    if s_action and hasattr(page, "is_visible"):
                        raw_act = page.is_visible(s_action)
                        dom_state["hasAction"] = await raw_act if asyncio.iscoroutine(raw_act) else raw_act
                except Exception:
                    pass

        return dom_state

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
            await asyncio.sleep(0.1)

            # Clear draft text if any
            if hasattr(page, "evaluate"):
                try:
                    await page.evaluate("""(selector) => {
                        const target = document.querySelector(selector);
                        if (!target) return;
                        if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
                            target.value = '';
                        } else if (target.isContentEditable) {
                            target.innerText = '';
                            target.innerHTML = '';
                        }
                        target.dispatchEvent(new Event('input', { bubbles: true }));
                    }""", s_input)
                except Exception:
                    pass

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
                            if ((target.innerText || target.textContent || target.value || '').trim().length > 0) {
                                target.dispatchEvent(new Event('input', { bubbles: true }));
                                return true;
                            }
                        } catch (e) {}

                        try {
                            if (document.execCommand('insertText', false, content)) {
                                target.dispatchEvent(new Event('input', { bubbles: true }));
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

        # Wait up to 3 seconds for send button to be enabled (vital for large payloads with attachment tiles)
        submitted = False
        for _ in range(6):
            await asyncio.sleep(0.5)
            if hasattr(page, "query_selector") and s_send:
                try:
                    btn = await page.query_selector(s_send)
                    if btn:
                        is_vis = True
                        if hasattr(btn, "is_visible"):
                            vis_val = btn.is_visible()
                            is_vis = bool(await vis_val if asyncio.iscoroutine(vis_val) else vis_val)
                        if is_vis:
                            is_disabled = False
                            if hasattr(btn, "is_disabled") and callable(btn.is_disabled):
                                try:
                                    dis_val = btn.is_disabled()
                                    dis_res = await dis_val if asyncio.iscoroutine(dis_val) else dis_val
                                    if isinstance(dis_res, bool):
                                        is_disabled = dis_res
                                except Exception:
                                    pass
                            if not is_disabled and hasattr(btn, "click"):
                                await btn.click(force=True, timeout=5000)
                                submitted = True
                                break
                except Exception:
                    pass

            if not submitted and hasattr(page, "evaluate") and s_send:
                try:
                    clicked = await page.evaluate("""(selector) => {
                        const btn = document.querySelector(selector);
                        if (btn && !btn.disabled) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }""", s_send)
                    if clicked:
                        submitted = True
                        break
                except Exception:
                    pass

        if not submitted and hasattr(page, "keyboard"):
            await page.keyboard.press("Enter")

    async def wait_for_completion(
        self,
        page: Page,
        agent_type: str,
        baseline: Optional[TabBaseline] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> str:
        s_cfg = self.selectors.perplexity if agent_type == "perplexity" else self.selectors.chatgpt
        s_stop = s_cfg.get("stop_button")
        s_resp = s_cfg.get("last_response")
        s_tool = s_cfg.get("tool_running_indicator")
        s_action = s_cfg.get("action_buttons")
        s_send = s_cfg.get("send_button")

        start_time = time.time()
        timeout = self.config.timeout_seconds
        stability_duration = self.config.text_stability_seconds

        dom_quiet_event = asyncio.Event()
        observer_active = await self._setup_observer(page, lambda: dom_quiet_event.set())
        if observer_active and on_progress:
            on_progress("Đã kích hoạt MutationObserver giám sát sự kiện DOM.")

        # --- PHASE 1: Wait for generation to start (if baseline is provided) ---
        generation_started = baseline is None
        phase1_start = time.time()
        phase1_timeout = 30.0
        retriggered_enter = False

        while not generation_started and (time.time() - phase1_start < phase1_timeout):
            await asyncio.sleep(0.5)
            now = time.time()
            elapsed_p1 = int(now - phase1_start)

            state = await self._get_dom_state(page, s_resp, s_stop, s_action, s_tool)
            current_text = state.get("text", "").strip()
            stop_visible = state.get("hasStop", False)
            is_tool = state.get("isTool", False)
            resp_count = state.get("count", 0)

            if stop_visible or is_tool:
                generation_started = True
            elif baseline and resp_count > baseline.response_count:
                generation_started = True
            elif baseline and current_text and (current_text != baseline.last_text.strip()):
                generation_started = True

            if generation_started:
                if on_progress:
                    on_progress(f"{agent_type.capitalize()} đã bắt đầu sinh phản hồi...")
                break

            if not retriggered_enter and (now - phase1_start >= 5.0):
                retriggered_enter = True
                if on_progress:
                    on_progress(f"Chưa thấy phản hồi, thử gửi lại lệnh vào {agent_type.capitalize()}...")
                if hasattr(page, "evaluate") and s_send:
                    try:
                        await page.evaluate("""(sel) => {
                            const b = document.querySelector(sel);
                            if (b && !b.disabled) b.click();
                        }""", s_send)
                    except Exception:
                        pass
                if hasattr(page, "keyboard"):
                    try:
                        await page.keyboard.press("Enter")
                    except Exception:
                        pass

            if on_progress and int(now - phase1_start) > 0 and int(now - phase1_start) % 4 == 0:
                on_progress(f"Đang chờ {agent_type.capitalize()} tiếp nhận yêu cầu... ({elapsed_p1}s)")

        if not generation_started:
            raise TimeoutError(f"{agent_type.capitalize()} chưa bắt đầu phản hồi sau {int(phase1_timeout)}s.")

        # --- PHASE 2: Wait for generation to complete ---
        last_text = ""
        stable_start: Optional[float] = None
        last_progress_time = time.time()
        detected_terminal_tag = False
        terminal_status_name = ""

        while time.time() - start_time < timeout:
            now = time.time()
            elapsed = int(now - start_time)

            dom_state = await self._get_dom_state(page, s_resp, s_stop, s_action, s_tool)
            current_text = dom_state.get("text", "")
            stop_visible = dom_state.get("hasStop", False)
            has_action_buttons = dom_state.get("hasAction", False)
            is_tool_running = dom_state.get("isTool", False)
            resp_count = dom_state.get("count", 0)

            # Prevent false immediate completion on stale baseline content
            is_new_content = True
            if baseline is not None:
                if resp_count <= baseline.response_count and current_text.strip() == baseline.last_text.strip():
                    is_new_content = False

            if is_new_content and current_text:
                is_terminal, status_label = check_terminal_signal(current_text, agent_type)
                if is_terminal and not detected_terminal_tag:
                    detected_terminal_tag = True
                    terminal_status_name = status_label
                    if on_progress:
                        on_progress(f"Đã phát hiện tín hiệu hoàn tất [{status_label}]. Đang thẩm định tín hiệu kết thúc...")
            else:
                is_terminal, status_label = False, ""

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

            sig_dom_quiet = (
                dom_quiet_event.is_set()
                or (stable_start is not None and (now - stable_start) >= stability_duration)
            )
            sig_button_ready = bool(
                not is_tool_running and ((not stop_visible and current_text != "") or has_action_buttons)
            )
            sig_protocol = is_terminal

            signals_met = sum([sig_dom_quiet, sig_button_ready, sig_protocol])

            if signals_met >= 2 and current_text and is_new_content:
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
