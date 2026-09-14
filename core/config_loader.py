import json
import os
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppConfig(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    cdp_url: str = "http://localhost:9222"
    cdp_port: int = Field(default=9222, ge=1, le=65535)
    max_loops: int = Field(
        default=5,
        alias="default_max_loops",
        ge=1,
    )
    timeout_seconds: int = Field(default=600, ge=1)
    text_stability_seconds: float = Field(default=2.0, gt=0)
    reconnect_attempts: int = Field(default=3, ge=1)
    reconnect_delay_seconds: float = Field(default=2.0, ge=0)
    browser_path: str = ""
    dedicated_profile_dir: str = "browser_profile"
    connect_timeout_ms: int = Field(default=10_000, gt=0)
    navigation_timeout_ms: int = Field(default=30_000, gt=0)

    @model_validator(mode="after")
    def validate_cdp_url(self) -> "AppConfig":
        parsed = urlparse(self.cdp_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("cdp_url phải dùng http hoặc https")
        if not parsed.hostname:
            raise ValueError("cdp_url phải có hostname")
        if parsed.port is not None and parsed.port != self.cdp_port:
            raise ValueError("cdp_url và cdp_port không đồng nhất")
        return self


class SelectorsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    perplexity: dict[str, str]
    chatgpt: dict[str, str]


_ENV_OVERRIDES: dict[str, tuple[str, type]] = {
    "DIEUPHOI_CDP_URL": ("cdp_url", str),
    "DIEUPHOI_CDP_PORT": ("cdp_port", int),
    "DIEUPHOI_MAX_LOOPS": ("default_max_loops", int),
    "DIEUPHOI_TIMEOUT_SECONDS": ("timeout_seconds", int),
    "DIEUPHOI_TEXT_STABILITY_SECONDS": ("text_stability_seconds", float),
    "DIEUPHOI_RECONNECT_ATTEMPTS": ("reconnect_attempts", int),
    "DIEUPHOI_RECONNECT_DELAY_SECONDS": ("reconnect_delay_seconds", float),
    "DIEUPHOI_BROWSER_PATH": ("browser_path", str),
    "DIEUPHOI_DEDICATED_PROFILE_DIR": ("dedicated_profile_dir", str),
    "DIEUPHOI_CONNECT_TIMEOUT_MS": ("connect_timeout_ms", int),
    "DIEUPHOI_NAVIGATION_TIMEOUT_MS": ("navigation_timeout_ms", int),
}


def _apply_env_overrides(data: object) -> dict[str, Any]:
    values = dict(data) if isinstance(data, dict) else {}
    for env_name, (config_key, value_type) in _ENV_OVERRIDES.items():
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        normalized = raw_value.strip()
        if value_type is str:
            values[config_key] = normalized
            continue
        try:
            values[config_key] = value_type(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid value for environment variable {env_name}: {raw_value!r}"
            ) from exc
    if "default_max_loops" in values and "max_loops" in values:
        values.pop("max_loops", None)
    return values


def _load_yaml_mapping(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root phải là mapping/object: {path}")
    return data


def load_config(path: str = "config/config.yaml") -> AppConfig:
    data = _load_yaml_mapping(path)
    return AppConfig(**_apply_env_overrides(data))


def load_selectors(path: str = "config/selectors.json") -> SelectorsConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Selectors root phải là object: {path}")
    return SelectorsConfig.model_validate(data)
