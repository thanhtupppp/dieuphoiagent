import asyncio
import logging
from typing import Optional, Tuple
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from core.config_loader import AppConfig, SelectorsConfig

logger = logging.getLogger(__name__)


class CDPConnector:
    def __init__(
        self,
        config: AppConfig,
        selectors: SelectorsConfig,
    ) -> None:
        self.config = config
        self.selectors = selectors
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.perplexity_tab: Optional[Page] = None
        self.chatgpt_tab: Optional[Page] = None
        self.is_connected = False
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        if not (self.is_connected and self.browser):
            return False
        try:
            return self.browser.is_connected()
        except Exception:
            return False

    async def connect(self) -> bool:
        async with self._lock:
            if self.connected:
                return True

            await self._disconnect()
            try:
                self.playwright = await async_playwright().start()
                timeout = getattr(self.config, "connect_timeout_ms", 10_000)
                self.browser = await self.playwright.chromium.connect_over_cdp(
                    self.config.cdp_url,
                    timeout=timeout,
                )
                if not self.browser.contexts:
                    raise RuntimeError("CDP connected nhưng không có browser context")

                self.is_connected = True
                self.browser.on("disconnected", self._handle_browser_disconnected)
                logger.info("Connected to browser via CDP at %s", self.config.cdp_url)
                return True
            except Exception:
                logger.exception("Không thể kết nối CDP: %s", self.config.cdp_url)
                await self._disconnect()
                return False

    async def find_tabs(self) -> Tuple[Optional[Page], Optional[Page]]:
        if not self.connected or not self.browser:
            logger.warning("CDP chưa kết nối")
            return None, None

        if not self.browser.contexts:
            logger.warning("CDP không có browser context")
            return None, None

        context = self.browser.contexts[0]
        pages = [
            page for page in context.pages
            if not self._is_page_closed(page)
        ]
        p_match = self.selectors.perplexity.get("url_match", "perplexity.ai")
        c_match = self.selectors.chatgpt.get("url_match", "chatgpt.com")

        self.perplexity_tab = self._find_page(pages, p_match)
        self.chatgpt_tab = self._find_page(pages, c_match)

        if self.perplexity_tab is None:
            self.perplexity_tab = await self._open_page(context, "https://www.perplexity.ai")
        if self.chatgpt_tab is None:
            self.chatgpt_tab = await self._open_page(context, "https://chatgpt.com")

        return self.perplexity_tab, self.chatgpt_tab

    async def reconnect(self) -> bool:
        attempts = max(1, getattr(self.config, "reconnect_attempts", 3))
        delay = getattr(self.config, "reconnect_delay_seconds", 2.0)

        for attempt in range(1, attempts + 1):
            if attempt > 1:
                await asyncio.sleep(delay)
            logger.info("Đang reconnect CDP, lần %d/%d", attempt, attempts)
            if await self.connect():
                p_tab, c_tab = await self.find_tabs()
                if p_tab or c_tab:
                    return True

        logger.error("Reconnect CDP thất bại sau %d lần", attempts)
        return False

    async def close(self) -> None:
        """Đóng Playwright connection tới browser CDP.

        Lưu ý: với remote browser, browser.close() sẽ giải phóng Playwright
        objects và ngắt kết nối khỏi browser server.
        """
        async with self._lock:
            await self._disconnect()

    async def _disconnect(self) -> None:
        self.is_connected = False
        self.perplexity_tab = None
        self.chatgpt_tab = None
        browser = self.browser
        playwright = self.playwright
        self.browser = None
        self.playwright = None

        if browser:
            try:
                if browser.is_connected():
                    await browser.close()
            except Exception:
                logger.exception("Lỗi khi đóng kết nối browser CDP")

        if playwright:
            try:
                await playwright.stop()
            except Exception:
                logger.exception("Lỗi khi stop Playwright")

    @staticmethod
    def _is_page_closed(page: Page) -> bool:
        try:
            return page.is_closed()
        except Exception:
            return True

    @staticmethod
    def _find_page(pages: list[Page], url_match: str) -> Optional[Page]:
        match = url_match.lower()
        aliases = {match}
        if "chatgpt" in match or "openai" in match:
            aliases.update({"chatgpt.com", "chat.openai.com"})
        for page in pages:
            try:
                url = page.url.lower()
                if any(alias in url for alias in aliases):
                    return page
            except Exception:
                continue
        return None

    async def _open_page(self, context: BrowserContext, url: str) -> Optional[Page]:
        page: Optional[Page] = None
        timeout = getattr(self.config, "navigation_timeout_ms", 30_000)
        try:
            page = await context.new_page()
            if page is not None:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout,
                )
                return page
        except PlaywrightTimeoutError:
            logger.warning("Timeout khi mở trang: %s", url)
        except Exception:
            logger.exception("Không thể mở trang: %s", url)

        if page and not self._is_page_closed(page):
            try:
                await page.close()
            except Exception:
                logger.debug("Không thể đóng page lỗi: %s", url, exc_info=True)
        return None

    def _handle_browser_disconnected(self, browser: Optional[Browser] = None) -> None:
        if browser is not None and self.browser is not None and browser is not self.browser:
            logger.debug("Bỏ qua disconnected event từ instance browser cũ")
            return
        self.is_connected = False
        self.perplexity_tab = None
        self.chatgpt_tab = None
        logger.warning("Browser CDP đã bị ngắt kết nối")
