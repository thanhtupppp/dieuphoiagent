import asyncio
import sys
from pathlib import Path

# Ensure UTF-8 output
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
    
    if p_tab:
        print("=== Detailed Perplexity Input Inspection ===")
        ce_list = await p_tab.query_selector_all("[contenteditable='true']")
        for i, ce in enumerate(ce_list):
            attrs = await ce.evaluate("""el => {
                const attrs = {};
                for (let a of el.attributes) {
                    attrs[a.name] = a.value;
                }
                return {
                    tagName: el.tagName,
                    id: el.id,
                    className: el.className,
                    attributes: attrs,
                    innerHTML: el.innerHTML
                };
            }""")
            print(f"ContentEditable #{i}:")
            print("  Tag:", attrs['tagName'])
            print("  Class:", attrs['className'])
            print("  Attrs:", attrs['attributes'])

        print("\n=== Submit/Send Buttons on Perplexity ===")
        btns = await p_tab.query_selector_all("button")
        for b in btns:
            info = await b.evaluate("""btn => {
                return {
                    ariaLabel: btn.getAttribute('aria-label') || '',
                    className: btn.className,
                    disabled: btn.disabled,
                    visible: btn.offsetParent !== null,
                    html: btn.outerHTML.slice(0, 150)
                };
            }""")
            if any(k in info['ariaLabel'].lower() for k in ['submit', 'send', 'ask', 'search']) or 'arrow' in info['html'].lower():
                print("  Candidate submit button:", info)

    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
