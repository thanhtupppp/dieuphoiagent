import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
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
        print("=== Testing Selectors on ChatGPT ===")
        sel_list = [
            "div[data-message-author-role='assistant']:last-of-type",
            "div[data-message-author-role='assistant']",
            "article:has(div[data-message-author-role='assistant'])",
            "button[data-testid='stop-button']",
            "button[data-testid='send-button']"
        ]
        for s in sel_list:
            nodes = await c_tab.query_selector_all(s)
            print(f"Selector '{s}': count={len(nodes)}")
            if nodes and "assistant" in s:
                txt = await nodes[-1].inner_text()
                print(f"   -> Text length={len(txt)}, contains [STATUS]: {'[STATUS' in txt}")

    if p_tab:
        print("\n=== Testing Selectors on Perplexity ===")
        p_sel_list = [
            "div[data-testid='answer-content']",
            "div.prose",
            "div.default",
            "button:has-text('Stop')"
        ]
        for s in p_sel_list:
            nodes = await p_tab.query_selector_all(s)
            print(f"Perplexity selector '{s}': count={len(nodes)}")
            if nodes:
                txt = await nodes[-1].inner_text()
                print(f"   -> Text length={len(txt)}, contains [STATUS]: {'[STATUS' in txt}")

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
