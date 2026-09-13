
from core.config_loader import load_config, load_selectors
from core.orchestrator_fsm import OrchestratorFSM
from core.providers.base import ProviderKind
from core.providers.factory import build_provider
from ui.app import build_ui


def test_app_components_instantiation():
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    fsm = OrchestratorFSM(config, selectors)
    assert fsm is not None
    assert fsm.state.value == "IDLE"
    assert fsm.circuit_breaker is not None
    assert fsm.circuit_breaker.failures == 0


def test_build_ui_initialization():
    fsm = build_ui()
    assert fsm is not None
    assert fsm.state.value == "IDLE"
    assert fsm.provider.kind == ProviderKind.CDP
    assert fsm.circuit_breaker.failures == 0
    assert fsm.on_log is not None


def test_provider_switching_logic(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")

    cdp_p = build_provider(ProviderKind.CDP, config, selectors)
    api_p = build_provider(ProviderKind.API, config, selectors)

    assert cdp_p.kind == ProviderKind.CDP
    assert api_p.kind == ProviderKind.API
