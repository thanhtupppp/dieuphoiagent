from core.config_loader import AppConfig, SelectorsConfig, load_config, load_selectors


def test_load_config_defaults(monkeypatch):
    for name in (
        "DIEUPHOI_CDP_URL",
        "DIEUPHOI_CDP_PORT",
        "DIEUPHOI_MAX_LOOPS",
        "DIEUPHOI_TIMEOUT_SECONDS",
        "DIEUPHOI_TEXT_STABILITY_SECONDS",
        "DIEUPHOI_RECONNECT_ATTEMPTS",
        "DIEUPHOI_RECONNECT_DELAY_SECONDS",
        "DIEUPHOI_BROWSER_PATH",
        "DIEUPHOI_DEDICATED_PROFILE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config("config/config.yaml")
    assert isinstance(config, AppConfig)
    assert config.cdp_port == 9222
    assert config.max_loops == 5
    assert config.timeout_seconds == 600
    assert config.text_stability_seconds == 2.5


def test_load_config_environment_overrides(monkeypatch):
    monkeypatch.setenv("DIEUPHOI_CDP_URL", "http://127.0.0.1:9333")
    monkeypatch.setenv("DIEUPHOI_CDP_PORT", "9333")
    monkeypatch.setenv("DIEUPHOI_MAX_LOOPS", "8")
    monkeypatch.setenv("DIEUPHOI_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("DIEUPHOI_TEXT_STABILITY_SECONDS", "3.5")
    monkeypatch.setenv("DIEUPHOI_RECONNECT_ATTEMPTS", "7")
    monkeypatch.setenv("DIEUPHOI_RECONNECT_DELAY_SECONDS", "4.5")
    monkeypatch.setenv("DIEUPHOI_BROWSER_PATH", r"C:\Chrome\chrome.exe")
    monkeypatch.setenv("DIEUPHOI_DEDICATED_PROFILE_DIR", r"C:\dpa-profile")

    config = load_config("config/config.yaml")
    assert config.cdp_url == "http://127.0.0.1:9333"
    assert config.cdp_port == 9333
    assert config.max_loops == 8
    assert config.timeout_seconds == 900
    assert config.text_stability_seconds == 3.5
    assert config.reconnect_attempts == 7
    assert config.reconnect_delay_seconds == 4.5
    assert config.browser_path == r"C:\Chrome\chrome.exe"
    assert config.dedicated_profile_dir == r"C:\dpa-profile"


def test_load_config_rejects_invalid_integer_override(monkeypatch):
    monkeypatch.setenv("DIEUPHOI_CDP_PORT", "not-an-int")

    try:
        load_config("config/config.yaml")
    except ValueError as exc:
        assert "DIEUPHOI_CDP_PORT" in str(exc)
    else:
        raise AssertionError("invalid integer override must raise ValueError")


def test_load_selectors():
    selectors = load_selectors("config/selectors.json")
    assert isinstance(selectors, SelectorsConfig)
    assert "input_textarea" in selectors.perplexity
    assert "send_button" in selectors.perplexity
    assert "prompt_textarea" in selectors.chatgpt
    assert "stop_button" in selectors.chatgpt
