from core.config_loader import load_config
from core.providers.base import AgentProvider, ProviderKind


def build_provider(kind: ProviderKind) -> AgentProvider:
    if kind == ProviderKind.CDP:
        from core.providers.cdp_provider import CdpProvider

        return CdpProvider(load_config())
    if kind == ProviderKind.API:
        from core.providers.api_provider import ApiProvider

        return ApiProvider()
    raise ValueError(f"Unknown provider kind: {kind}")
