from pathlib import Path
import pytest
from pydantic import ValidationError

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
        "DIEUPHOI_CONNECT_TIMEOUT_MS",
        "DIEUPHOI_NAVIGATION_TIMEOUT_MS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config("config/config.yaml")
    assert isinstance(config, AppConfig)
    assert config.cdp_port == 9222
    assert config.max_loops == 5
    assert config.timeout_seconds == 600
    assert config.text_stability_seconds == 2.5
    assert config.connect_timeout_ms == 10_000
    assert config.navigation_timeout_ms == 30_000


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
    monkeypatch.setenv("DIEUPHOI_CONNECT_TIMEOUT_MS", " 15000 ")
    monkeypatch.setenv("DIEUPHOI_NAVIGATION_TIMEOUT_MS", " 45000 ")

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
    assert config.connect_timeout_ms == 15_000
    assert config.navigation_timeout_ms == 45_000


def test_load_config_rejects_invalid_integer_override(monkeypatch):
    monkeypatch.setenv("DIEUPHOI_CDP_PORT", "not-an-int")

    try:
        load_config("config/config.yaml")
    except ValueError as exc:
        assert "DIEUPHOI_CDP_PORT" in str(exc)
    else:
        raise AssertionError("invalid integer override must raise ValueError")


def test_load_config_rejects_empty_numeric_override(monkeypatch):
    monkeypatch.setenv("DIEUPHOI_CDP_PORT", "   ")
    with pytest.raises(ValueError, match="Invalid value for environment variable DIEUPHOI_CDP_PORT"):
        load_config("config/config.yaml")


def test_load_selectors():
    selectors = load_selectors("config/selectors.json")
    assert isinstance(selectors, SelectorsConfig)
    assert "input_textarea" in selectors.perplexity
    assert "send_button" in selectors.perplexity
    assert "prompt_textarea" in selectors.chatgpt
    assert "stop_button" in selectors.chatgpt


def test_alias_is_normalized():
    config = AppConfig(default_max_loops=7)
    assert config.max_loops == 7


def test_field_name_is_supported():
    config = AppConfig(max_loops=8)
    assert config.max_loops == 8


def test_app_config_populate_by_name():
    cfg1 = AppConfig(max_loops=10)
    assert cfg1.max_loops == 10

    cfg2 = AppConfig(default_max_loops=10)
    assert cfg2.max_loops == 10


def test_app_config_extra_forbid():
    with pytest.raises(ValidationError):
        AppConfig(unexpected_field="disallowed")

    with pytest.raises(ValidationError):
        SelectorsConfig(perplexity={}, chatgpt={}, extra_service={})


def test_cdp_url_and_port_validation():
    # Valid: matching ports
    cfg = AppConfig(cdp_url="http://remote.host:9555", cdp_port=9555)
    assert cfg.cdp_port == 9555

    # Invalid: url without port is rejected
    with pytest.raises(ValidationError, match="cdp_url phải chỉ rõ port"):
        AppConfig(cdp_url="http://remote.host", cdp_port=9222)

    # Invalid: mismatched ports
    with pytest.raises(ValidationError, match="cdp_url và cdp_port không đồng nhất"):
        AppConfig(cdp_url="http://localhost:9333", cdp_port=9222)

    # Invalid: credentials in url
    with pytest.raises(ValidationError, match="cdp_url không được chứa username/password"):
        AppConfig(cdp_url="http://user:password@localhost:9222")

    # Invalid: bad scheme
    with pytest.raises(ValidationError, match="cdp_url phải dùng http hoặc https"):
        AppConfig(cdp_url="ws://localhost:9222")

    # Invalid: missing hostname
    with pytest.raises(ValidationError, match="cdp_url phải có hostname"):
        AppConfig(cdp_url="http://:9222")


def test_app_config_range_constraints():
    with pytest.raises(ValidationError):
        AppConfig(cdp_port=0)

    with pytest.raises(ValidationError):
        AppConfig(cdp_port=70000)

    with pytest.raises(ValidationError):
        AppConfig(max_loops=0)

    with pytest.raises(ValidationError):
        AppConfig(timeout_seconds=0)

    with pytest.raises(ValidationError):
        AppConfig(text_stability_seconds=0.0)

    with pytest.raises(ValidationError):
        AppConfig(text_stability_seconds=-1.0)

    with pytest.raises(ValidationError):
        AppConfig(reconnect_attempts=0)

    with pytest.raises(ValidationError):
        AppConfig(reconnect_delay_seconds=-0.5)

    with pytest.raises(ValidationError):
        AppConfig(connect_timeout_ms=0)

    with pytest.raises(ValidationError):
        AppConfig(navigation_timeout_ms=0)


def test_load_config_fails_fast_on_non_mapping_yaml(tmp_path: Path):
    bad_yaml = tmp_path / "bad_config.yaml"
    bad_yaml.write_text("- item1\n- item2", encoding="utf-8")

    with pytest.raises(ValueError, match="Config root phải là mapping/object"):
        load_config(str(bad_yaml))


def test_load_selectors_fails_fast_on_non_object_json(tmp_path: Path):
    bad_json = tmp_path / "bad_selectors.json"
    bad_json.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(ValueError, match="Selectors root phải là object"):
        load_selectors(str(bad_json))


def test_yaml_alias_and_field_name_conflict(tmp_path: Path):
    conflict_yaml = tmp_path / "conflict.yaml"
    conflict_yaml.write_text(
        "max_loops: 7\ndefault_max_loops: 5\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="Không được đồng thời dùng 'max_loops' và 'default_max_loops'",
    ):
        load_config(str(conflict_yaml))


def test_alias_conflict_is_rejected(tmp_path: Path):
    conflict_yaml = tmp_path / "conflict.yaml"
    conflict_yaml.write_text(
        "max_loops: 5\ndefault_max_loops: 7\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="Không được đồng thời dùng 'max_loops' và 'default_max_loops'",
    ):
        load_config(str(conflict_yaml))


def test_alias_conflict_not_masked_by_environment(tmp_path: Path, monkeypatch):
    conflict_yaml = tmp_path / "conflict.yaml"
    conflict_yaml.write_text(
        "max_loops: 5\ndefault_max_loops: 7\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DIEUPHOI_MAX_LOOPS", "10")
    with pytest.raises(
        ValueError,
        match="Không được đồng thời dùng 'max_loops' và 'default_max_loops'",
    ):
        load_config(str(conflict_yaml))


def test_environment_max_loops_overrides_yaml(tmp_path: Path, monkeypatch):
    conf_file = tmp_path / "custom.yaml"
    conf_file.write_text("default_max_loops: 5\n", encoding="utf-8")

    monkeypatch.setenv("DIEUPHOI_MAX_LOOPS", "9")
    config = load_config(str(conf_file))
    assert config.max_loops == 9


def test_environment_overrides_yaml(monkeypatch, tmp_path: Path):
    conf_file = tmp_path / "custom.yaml"
    conf_file.write_text("default_max_loops: 5\n", encoding="utf-8")

    monkeypatch.setenv("DIEUPHOI_MAX_LOOPS", "9")
    config = load_config(str(conf_file))
    assert config.max_loops == 9


def test_yaml_with_canonical_max_loops(tmp_path: Path):
    conf_file = tmp_path / "canonical.yaml"
    conf_file.write_text("max_loops: 8\n", encoding="utf-8")

    config = load_config(str(conf_file))
    assert config.max_loops == 8


def test_invalid_cdp_port_in_url():
    with pytest.raises(ValidationError, match="cdp_url chứa port không hợp lệ"):
        AppConfig(cdp_url="http://localhost:nope")


def test_invalid_cdp_port_is_rejected():
    with pytest.raises(ValidationError, match="cdp_url chứa port không hợp lệ"):
        AppConfig(cdp_url="http://localhost:not-a-port")


def test_cdp_url_with_credentials_is_rejected():
    with pytest.raises(ValidationError, match="cdp_url không được chứa username/password"):
        AppConfig(cdp_url="http://user:password@localhost:9222")


def test_cdp_url_without_port_is_rejected():
    with pytest.raises(ValidationError, match="cdp_url phải chỉ rõ port"):
        AppConfig(cdp_url="http://localhost", cdp_port=9222)


def test_environment_override_catches_type_error(monkeypatch):
    import core.config_loader

    def bad_converter(v: str) -> int:
        raise TypeError("Simulated converter TypeError")

    monkeypatch.setitem(
        core.config_loader._ENV_OVERRIDES,
        "DIEUPHOI_TEST_CUSTOM",
        ("custom_key", bad_converter),
    )
    monkeypatch.setenv("DIEUPHOI_TEST_CUSTOM", "bad_value")
    with pytest.raises(
        ValueError,
        match="Invalid value for environment variable DIEUPHOI_TEST_CUSTOM",
    ):
        core.config_loader._apply_env_overrides({})
