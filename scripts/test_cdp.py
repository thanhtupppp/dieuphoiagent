import asyncio
import sys
from pathlib import Path

# Add project root to sys.path so 'core' can be imported when running script directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config_loader import load_config, load_selectors
from core.cdp_connector import CDPConnector

async def main():
    print("Testing CDP Connection to http://localhost:9222...")
    config = load_config(str(ROOT_DIR / "config" / "config.yaml"))
    selectors = load_selectors(str(ROOT_DIR / "config" / "selectors.json"))
    connector = CDPConnector(config, selectors)
    
    ok = await connector.connect()
    if not ok:
        print("[-] FAILED: Could not connect to port 9222. Ensure launch_comet.bat has been run.")
        return
    print("[+] SUCCESS: Connected to Chromium via CDP!")
    p_tab, c_tab = await connector.find_tabs()
    print(f"[+] Perplexity Tab: {p_tab.url if p_tab else 'Not Found'}")
    print(f"[+] ChatGPT Tab: {c_tab.url if c_tab else 'Not Found'}")
    await connector.close()

if __name__ == "__main__":
    asyncio.run(main())
