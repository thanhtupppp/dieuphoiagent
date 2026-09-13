import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config_loader import load_config, load_selectors
from core.cdp_connector import CDPConnector

async def main():
    config = load_config(str(ROOT_DIR / "config" / "config.yaml"))
    selectors = load_selectors(str(ROOT_DIR / "config" / "selectors.json"))
    connector = CDPConnector(config, selectors)
    ok = await connector.connect()
    if not ok:
        print("Could not connect to CDP")
        return

    p_tab, c_tab = await connector.find_tabs()
    print("=== Perplexity Tab ===")
    if p_tab:
        print("URL:", p_tab.url)
        print("Title:", await p_tab.title())
        # Check textareas / inputs
        textareas = await p_tab.query_selector_all("textarea")
        print(f"Found {len(textareas)} <textarea> elements")
        for i, t in enumerate(textareas):
            ph = await t.get_attribute("placeholder")
            vis = await t.is_visible()
            print(f"  textarea[{i}]: placeholder={ph!r}, is_visible={vis}")
            
        # Check contenteditable
        contenteditables = await p_tab.query_selector_all("[contenteditable='true']")
        print(f"Found {len(contenteditables)} contenteditable elements")
        for i, ce in enumerate(contenteditables):
            print(f"  contenteditable[{i}]: tag={await ce.evaluate('el => el.tagName')}, visible={await ce.is_visible()}")

        # Check buttons
        buttons = await p_tab.query_selector_all("button")
        print(f"Found {len(buttons)} <button> elements")
        for b in buttons[:15]:
            aria = await b.get_attribute("aria-label")
            txt = (await b.inner_text()).strip().replace('\n', ' ')
            if aria or txt:
                print(f"  btn: aria-label={aria!r}, text={txt!r}")

    print("\n=== ChatGPT Tab ===")
    if c_tab:
        print("URL:", c_tab.url)
        print("Title:", await c_tab.title())
        textareas = await c_tab.query_selector_all("#prompt-textarea, textarea, [contenteditable='true']")
        print(f"Found {len(textareas)} prompt inputs on ChatGPT")
        for i, t in enumerate(textareas):
            tag = await t.evaluate("el => el.tagName")
            print(f"  input[{i}]: tag={tag}, id={await t.get_attribute('id')}, visible={await t.is_visible()}")

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
