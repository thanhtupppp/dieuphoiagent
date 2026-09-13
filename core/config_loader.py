from pathlib import Path
from typing import Dict, Any
import yaml
import json
from pydantic import BaseModel, Field

class AppConfig(BaseModel):
    cdp_url: str = "http://localhost:9222"
    cdp_port: int = 9222
    max_loops: int = Field(default=5, alias="default_max_loops")
    timeout_seconds: int = 240
    text_stability_seconds: float = 2.5
    reconnect_attempts: int = 3
    reconnect_delay_seconds: float = 2.0
    browser_path: str = ""
    dedicated_profile_dir: str = "browser_profile"

class SelectorsConfig(BaseModel):
    perplexity: Dict[str, str]
    chatgpt: Dict[str, str]

def load_config(path: str = "config/config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)

def load_selectors(path: str = "config/selectors.json") -> SelectorsConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SelectorsConfig(**data)
