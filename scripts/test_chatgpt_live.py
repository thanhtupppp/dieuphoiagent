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
        print(f"Waiting for visible selector: {selector}")
        el = await c_tab.wait_for_selector(selector, state="visible", timeout=10000)
        print("Found visible element:", el)
        
        # Click with force=True and focus
        await el.click(force=True)
        await el.focus()
        print("Clicked and focused successfully!")
        
        # Type sample
        await c_tab.keyboard.insert_text("Testing ChatGPT input live")
        print("Typed text via keyboard.insert_text!")
        
        await asyncio.sleep(1)
        # Clear
        await c_tab.keyboard.press("Control+A")
        await c_tab.keyboard.press("Backspace")
        print("Cleared text successfully!")

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
