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
    p_tab, _ = await connector.find_tabs()

    if p_tab:
        print("Focusing Perplexity input (#ask-input)...")
        ce = await p_tab.query_selector("#ask-input, div[contenteditable='true']")
        if ce:
            await ce.click()
            await ce.focus()
            print("Focused successfully!")
            
            # Let's test inserting text
            test_msg = "Hello testing from orchestrator"
            # Try insert_text
            await p_tab.keyboard.insert_text(test_msg)
            print("Inserted text via keyboard.insert_text")
            
            await asyncio.sleep(1)
            # Now let's see which buttons exist or if submit button is visible
            btns = await p_tab.query_selector_all("button")
            for b in btns:
                aria = await b.get_attribute("aria-label") or ""
                testid = await b.get_attribute("data-testid") or ""
                vis = await b.is_visible()
                if vis and any(k in aria.lower() for k in ["submit", "send", "ask", "arrow"]):
                    print(f"Visible submit candidate: aria={aria!r}, testid={testid!r}")

            # Let's clear the text so we don't pollute the prompt
            await p_tab.keyboard.press("Control+A")
            await p_tab.keyboard.press("Backspace")
            print("Cleared test text.")

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
