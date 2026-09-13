from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class AgentRole(str, Enum):
    TECH_LEAD = "tech_lead"
    CORE_DEV = "core_dev"


class ProviderKind(str, Enum):
    CDP = "cdp"
    API = "api"
    LOCAL = "local"


@dataclass
class AgentRequest:
    role: AgentRole
    system_prompt: str
    user_prompt: str
    timeout_s: int = 600
    on_progress: Callable[[str], None] | None = None


@dataclass
class AgentResponse:
    content: str
    raw_html: str | None = None
    source_url: str | None = None
    elapsed_s: float = 0.0


class AgentProvider(ABC):
    kind: ProviderKind

    @abstractmethod
    async def send(self, request: AgentRequest) -> AgentResponse:
        """Send a prompt and return the completed response."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Check whether the provider is ready for requests."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release provider-owned resources."""
        raise NotImplementedError
