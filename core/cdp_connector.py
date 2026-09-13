import asyncio
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page, Playwright
from core.config_loader import AppConfig, SelectorsConfig

class CDPConnector:
    def __init__(self, config: AppConfig, selectors: SelectorsConfig):
        self.config = config
        self.selectors = selectors
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.perplexity_tab: Optional[Page] = None
        self.chatgpt_tab: Optional[Page] = None
        self.is_connected: bool = False

    async def connect(self) -> bool:
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(self.config.cdp_url)
            self.is_connected = True
            return True
        except Exception:
            self.is_connected = False
            return False

    async def find_tabs(self) -> Tuple[Optional[Page], Optional[Page]]:
        if not self.browser or not self.browser.contexts:
            return None, None
        
        context = self.browser.contexts[0]
        pages = context.pages
        p_match = self.selectors.perplexity.get("url_match", "perplexity.ai")
        c_match = self.selectors.chatgpt.get("url_match", "chatgpt.com")

        self.perplexity_tab = None
        self.chatgpt_tab = None

        for p in pages:
            url = getattr(p, "url", "")
            if p_match in url:
                self.perplexity_tab = p
            elif c_match in url or "chat.openai.com" in url:
                self.chatgpt_tab = p

        # If not open, open new pages automatically
        if not self.perplexity_tab and hasattr(context, "new_page"):
            self.perplexity_tab = await context.new_page()
            await self.perplexity_tab.goto("https://www.perplexity.ai")
        if not self.chatgpt_tab and hasattr(context, "new_page"):
            self.chatgpt_tab = await context.new_page()
            await self.chatgpt_tab.goto("https://chatgpt.com")

        return self.perplexity_tab, self.chatgpt_tab

    async def reconnect(self) -> bool:
        for _ in range(1, self.config.reconnect_attempts + 1):
            await asyncio.sleep(self.config.reconnect_delay_seconds)
            try:
                await self.close()
                ok = await self.connect()
                if ok:
                    await self.find_tabs()
                    return True
            except Exception:
                pass
        return False

    async def close(self):
        self.is_connected = False
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
