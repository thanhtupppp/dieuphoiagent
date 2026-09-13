import time
from typing import Any

from playwright.async_api import Page

from core.cdp_connector import CDPConnector
from core.config_loader import AppConfig, SelectorsConfig, load_selectors
from core.stream_detector import StreamDetector
from .base import AgentProvider, AgentRequest, AgentResponse, AgentRole, ProviderKind


class CdpProvider(AgentProvider):
    """Provider implementation backed by the existing CDP connector and detector."""

    kind = ProviderKind.CDP

    def __init__(self, config: AppConfig, selectors: SelectorsConfig | None = None):
        self.config = config
        self.selectors = selectors if selectors is not None else load_selectors()
        self.connector = CDPConnector(config, self.selectors)
        self.detector = StreamDetector(config, self.selectors)
        self._tabs_ready = False

    async def _ensure_tabs(self) -> tuple[Page | None, Page | None]:
        if self._tabs_ready:
            return self.connector.perplexity_tab, self.connector.chatgpt_tab

        connected = await self.connector.connect()
        if not connected:
            raise RuntimeError("CDP connect failed")

        p_tab, c_tab = await self.connector.find_tabs()
        self.connector.perplexity_tab = p_tab
        self.connector.chatgpt_tab = c_tab
        self._tabs_ready = True
        return p_tab, c_tab

    async def send(self, request: AgentRequest) -> AgentResponse:
        p_tab, c_tab = await self._ensure_tabs()

        if request.role == AgentRole.TECH_LEAD:
            tab = p_tab
            site = "perplexity"
        elif request.role == AgentRole.CORE_DEV:
            tab = c_tab
            site = "chatgpt"
        else:
            raise ValueError(f"Unsupported agent role: {request.role}")

        if tab is None:
            raise RuntimeError(f"Tab {site} không sẵn sàng!")

        start = time.perf_counter()
        await self.detector.send_prompt(tab, request.user_prompt, site)
        raw_response = await self.detector.wait_for_completion(
            tab,
            site,
            on_progress=request.on_progress,
        )
        elapsed = time.perf_counter() - start

        return AgentResponse(
            content=raw_response,
            elapsed_s=elapsed,
        )

    async def health_check(self) -> bool:
        p_tab, c_tab = await self._ensure_tabs()
        return p_tab is not None and c_tab is not None

    async def close(self) -> None:
        # Keep the user-managed Chrome session alive; only invalidate cached tabs.
        self._tabs_ready = False
        self.connector.perplexity_tab = None
        self.connector.chatgpt_tab = None
