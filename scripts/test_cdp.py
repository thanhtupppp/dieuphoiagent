import asyncio
from core.config_loader import load_config, load_selectors
from core.cdp_connector import CDPConnector

async def main():
    print("Testing CDP Connection to http://localhost:9222...")
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
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
