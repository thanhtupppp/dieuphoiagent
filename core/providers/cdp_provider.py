from core.config_loader import AppConfig, SelectorsConfig
from .base import AgentProvider, AgentRequest, AgentResponse, ProviderKind


class CdpProvider(AgentProvider):
    """CDP provider seam; implementation is introduced in B5."""

    kind = ProviderKind.CDP

    def __init__(self, config: AppConfig, selectors: SelectorsConfig | None = None):
        self.config = config
        self.selectors = selectors

    async def send(self, request: AgentRequest) -> AgentResponse:
        raise NotImplementedError("CdpProvider is implemented in B5")

    async def health_check(self) -> bool:
        raise NotImplementedError("CdpProvider is implemented in B5")

    async def close(self) -> None:
        return None
