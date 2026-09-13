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
        print("=== Inspecting ChatGPT Tab Current State ===")
        # Check stop button
        stop_btn = await c_tab.query_selector("button[data-testid='stop-button']")
        print("Stop button visible:", await stop_btn.is_visible() if stop_btn else False)

        # Check send button
        send_btn = await c_tab.query_selector("button[data-testid='send-button']")
        print("Send button visible:", await send_btn.is_visible() if send_btn else False)

        # Check assistant responses
        assistant_nodes = await c_tab.query_selector_all("div[data-message-author-role='assistant']")
        print(f"Found {len(assistant_nodes)} div[data-message-author-role='assistant'] nodes")
        
        # Also check articles / prose / other message containers
        articles = await c_tab.query_selector_all("article")
        print(f"Found {len(articles)} <article> nodes")

        if assistant_nodes:
            last_msg = assistant_nodes[-1]
            txt = await last_msg.inner_text()
            print("=== Last Assistant Message (First 300 chars) ===")
            print(txt[:300])
            print("... Total length:", len(txt))
        elif articles:
            last_art = articles[-1]
            txt = await last_art.inner_text()
            print("=== Last Article (First 300 chars) ===")
            print(txt[:300])
            print("... Total length:", len(txt))

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
