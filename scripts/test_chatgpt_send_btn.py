import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.config_loader import load_config, load_selectors
from core.cdp_connector import CDPConnector

async def main():
    config = load_config(str(ROOT_DIR / "config" / "config.yaml"))
    selectors = load_selectors(str(ROOT_DIR / "config" / "selectors.json"))
    connector = CDPConnector(config, selectors)
    await connector.connect()
    _, c_tab = await connector.find_tabs()

    if c_tab:
        selector = "div#prompt-textarea, [contenteditable='true']:not([style*='display: none'])"
        el = await c_tab.wait_for_selector(selector, state="visible", timeout=10000)
        await el.click(force=True)
        await el.focus()
        await c_tab.keyboard.insert_text("Testing button visibility")
        await asyncio.sleep(0.5)

        send_btn = await c_tab.query_selector("button[data-testid='send-button']")
        if send_btn:
            data = await send_btn.evaluate("""btn => {
                const rect = btn.getBoundingClientRect();
                return {
                    disabled: btn.disabled,
                    visible: rect.width > 0 && rect.height > 0,
                    ariaLabel: btn.getAttribute('aria-label'),
                    testid: btn.getAttribute('data-testid')
                };
            }""")
            print("Send button state:", data)

        # Clear text
        await c_tab.keyboard.press("Control+A")
        await c_tab.keyboard.press("Backspace")
        print("Cleared text.")

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
