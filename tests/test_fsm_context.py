from core.fsm.context import FSMState, RunContext


def test_run_context_defaults():
    ctx = RunContext()
    assert ctx.current_turn == "perplexity"
    assert ctx.loop_count == 0
    assert ctx.max_loops == 5
    assert ctx.auto_mode is True
    assert ctx.is_running is True
    assert ctx.state == FSMState.IDLE
    assert ctx.logs == []


def test_run_context_set_state_callback():
    changes = []
    ctx = RunContext(on_state_change=lambda s: changes.append(s))
    ctx.set_state(FSMState.PERPLEXITY_SENDING)
    assert ctx.state == FSMState.PERPLEXITY_SENDING
    assert changes == [FSMState.PERPLEXITY_SENDING]


def test_run_context_log():
    logged = []
    ctx = RunContext(on_log=lambda src, msg: logged.append((src, msg)))
    ctx.log("system", "Test message")
    assert len(ctx.logs) == 1
    assert ctx.logs[0]["source"] == "system"
    assert ctx.logs[0]["message"] == "Test message"
    assert logged == [("system", "Test message")]
