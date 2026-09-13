import pytest
from core.orchestrator_fsm import OrchestratorFSM, FSMState
from core.config_loader import AppConfig, SelectorsConfig

def test_fsm_initial_state():
    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))
    assert fsm.state == FSMState.IDLE
    assert fsm.loop_count == 0

def test_fsm_stop_and_abort():
    fsm = OrchestratorFSM(AppConfig(), SelectorsConfig(perplexity={}, chatgpt={}))
    fsm.state = FSMState.PERPLEXITY_WAITING
    fsm.stop()
    assert fsm.state == FSMState.IDLE
    
    fsm.state = FSMState.CHATGPT_WAITING
    fsm.abort()
    assert fsm.state == FSMState.ABORTED
