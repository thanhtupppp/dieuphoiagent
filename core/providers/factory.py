from typing import Optional

from core.config_loader import AppConfig, SelectorsConfig, load_config, load_selectors
from core.providers.base import AgentProvider, ProviderKind


def build_provider(
    kind: ProviderKind,
    config: Optional[AppConfig] = None,
    selectors: Optional[SelectorsConfig] = None,
) -> AgentProvider:
    cfg = config or load_config()
    sel = selectors or load_selectors()
    if kind == ProviderKind.CDP:
        from core.providers.cdp_provider import CdpProvider

        return CdpProvider(cfg, sel)
    if kind == ProviderKind.API:
        from core.providers.api_provider import ApiProvider

        return ApiProvider()
    raise ValueError(f"Unknown provider kind: {kind}")

