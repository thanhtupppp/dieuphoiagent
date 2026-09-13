from ui.preview_modal import PreviewModalState

def test_preview_modal_state():
    state = PreviewModalState()
    state.open_modal(target="ChatGPT", payload="Initial Prompt")
    assert state.is_visible is True
    assert state.target == "ChatGPT"
    assert state.payload == "Initial Prompt"
    state.close_modal()
    assert state.is_visible is False
