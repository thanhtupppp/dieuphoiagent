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
        print("Focusing ChatGPT prompt textarea (#prompt-textarea)...")
        inp = await c_tab.query_selector("#prompt-textarea, div[contenteditable='true']")
        if inp:
            await inp.click()
            await inp.focus()
            print("Focused ChatGPT input!")
            
            # Test insert text
            await c_tab.keyboard.insert_text("Testing ChatGPT input")
            print("Inserted text via keyboard.insert_text")
            
            await asyncio.sleep(1)
            send_btn = await c_tab.query_selector("button[data-testid='send-button']")
            if send_btn:
                vis = await send_btn.is_visible()
                print("Found ChatGPT send-button, visible:", vis)
                
            # Clear text
            await c_tab.keyboard.press("Control+A")
            await c_tab.keyboard.press("Backspace")
            print("Cleared test text.")

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
