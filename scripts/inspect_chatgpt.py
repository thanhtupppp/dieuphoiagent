import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config_loader import load_config, load_selectors
from core.cdp_connector import CDPConnector

async def main():
    config = load_config(str(ROOT_DIR / "config" / "config.yaml"))
    selectors = load_selectors(str(ROOT_DIR / "config" / "selectors.json"))
    connector = CDPConnector(config, selectors)
    await connector.connect()
    p_tab, c_tab = await connector.find_tabs()
    
    if c_tab:
        print("=== Detailed ChatGPT Inspection ===")
        print("URL:", c_tab.url)
        inputs = await c_tab.query_selector_all("#prompt-textarea, [contenteditable='true'], textarea")
        for i, inp in enumerate(inputs):
            info = await inp.evaluate("""el => ({
                tag: el.tagName,
                id: el.id,
                role: el.getAttribute('role'),
                contenteditable: el.getAttribute('contenteditable'),
                visible: el.offsetParent !== null,
                classes: el.className
            })""")
            print(f"ChatGPT Input #{i}:", info)

        btns = await c_tab.query_selector_all("button")
        for b in btns:
            info = await b.evaluate("""btn => ({
                testid: btn.getAttribute('data-testid'),
                aria: btn.getAttribute('aria-label'),
                classes: btn.className,
                visible: btn.offsetParent !== null
            })""")
            if info['testid'] or info['aria'] in ['Send prompt', 'Submit']:
                print("ChatGPT Button:", info)

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
