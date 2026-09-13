from .base import AgentProvider, AgentRequest, AgentResponse, ProviderKind


class ApiProvider(AgentProvider):
    """API provider seam; implementation is introduced in B6."""

    kind = ProviderKind.API

    async def send(self, request: AgentRequest) -> AgentResponse:
        raise NotImplementedError("ApiProvider is implemented in B6")

    async def health_check(self) -> bool:
        raise NotImplementedError("ApiProvider is implemented in B6")

    async def close(self) -> None:
        return None
