import json
import os
from typing import Dict

import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    cdp_url: str = "http://localhost:9222"
    cdp_port: int = 9222
    max_loops: int = Field(default=5, alias="default_max_loops")
    timeout_seconds: int = 600
    text_stability_seconds: float = 2.0
    reconnect_attempts: int = 3
    reconnect_delay_seconds: float = 2.0
    browser_path: str = ""
    dedicated_profile_dir: str = "browser_profile"


class SelectorsConfig(BaseModel):
    perplexity: Dict[str, str]
    chatgpt: Dict[str, str]


_ENV_OVERRIDES = {
    "DIEUPHOI_CDP_URL": ("cdp_url", str),
    "DIEUPHOI_CDP_PORT": ("cdp_port", int),
    "DIEUPHOI_MAX_LOOPS": ("default_max_loops", int),
    "DIEUPHOI_TIMEOUT_SECONDS": ("timeout_seconds", int),
    "DIEUPHOI_TEXT_STABILITY_SECONDS": ("text_stability_seconds", float),
    "DIEUPHOI_RECONNECT_ATTEMPTS": ("reconnect_attempts", int),
    "DIEUPHOI_RECONNECT_DELAY_SECONDS": ("reconnect_delay_seconds", float),
    "DIEUPHOI_BROWSER_PATH": ("browser_path", str),
    "DIEUPHOI_DEDICATED_PROFILE_DIR": ("dedicated_profile_dir", str),
}


def _apply_env_overrides(data: object) -> dict:
    values = dict(data) if isinstance(data, dict) else {}
    for env_name, (config_key, value_type) in _ENV_OVERRIDES.items():
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        if value_type is str:
            values[config_key] = raw_value
        else:
            try:
                values[config_key] = value_type(raw_value)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid value for environment variable {env_name}: {raw_value!r}"
                ) from exc
    return values


def load_config(path: str = "config/config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig(**_apply_env_overrides(data))


def load_selectors(path: str = "config/selectors.json") -> SelectorsConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SelectorsConfig(**data)
