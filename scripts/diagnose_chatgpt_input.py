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
        print("=== Inspecting ChatGPT Prompt Elements ===")
        all_candidates = await c_tab.query_selector_all("#prompt-textarea, div[contenteditable='true'], textarea, [data-placeholder]")
        for i, el in enumerate(all_candidates):
            data = await el.evaluate("""node => {
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                return {
                    tagName: node.tagName,
                    id: node.id,
                    className: node.className,
                    contenteditable: node.getAttribute('contenteditable'),
                    visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
                    rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity
                };
            }""")
            print(f"Candidate #{i}:", data)

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
