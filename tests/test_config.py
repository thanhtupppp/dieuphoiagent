from core.config_loader import AppConfig, SelectorsConfig, load_config, load_selectors


def test_load_config_defaults():
    config = load_config("config/config.yaml")
    assert isinstance(config, AppConfig)
    assert config.cdp_port == 9222
    assert config.max_loops == 5
    assert config.timeout_seconds == 600
    assert config.text_stability_seconds == 2.5


def test_load_selectors():
    selectors = load_selectors("config/selectors.json")
    assert isinstance(selectors, SelectorsConfig)
    assert "input_textarea" in selectors.perplexity
    assert "send_button" in selectors.perplexity
    assert "prompt_textarea" in selectors.chatgpt
    assert "stop_button" in selectors.chatgpt
