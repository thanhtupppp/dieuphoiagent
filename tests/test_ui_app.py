import pytest
from core.config_loader import load_config, load_selectors
from core.orchestrator_fsm import OrchestratorFSM

def test_app_components_instantiation():
    config = load_config("config/config.yaml")
    selectors = load_selectors("config/selectors.json")
    fsm = OrchestratorFSM(config, selectors)
    assert fsm is not None
    assert fsm.state.value == "IDLE"
