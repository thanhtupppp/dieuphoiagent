"""
ApiProvider — CHỈ DÙNG CHO CI/CD VÀ FALLBACK.
Production chạy 100% trên CdpProvider (Chrome CDP miễn phí).
Không cần cấu hình API key để chạy hệ thống.
"""

import os
import time
from typing import Any, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .base import AgentProvider, AgentRequest, AgentResponse, AgentRole, ProviderKind

ROLE_MODEL: dict[AgentRole, str] = {
    AgentRole.TECH_LEAD: "sonar-pro",  # Perplexity API
    AgentRole.CORE_DEV: "gpt-4o",  # OpenAI API
}


class ApiProvider(AgentProvider):
    """API-based provider executing requests directly against OpenAI / Perplexity models."""

    kind = ProviderKind.API

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        client: Optional[AsyncOpenAI] = None,
    ) -> None:
        if client is not None:
            self._client = client
            return

        resolved_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("PERPLEXITY_API_KEY")
        )
        if not resolved_key:
            raise RuntimeError(
                "OPENAI_API_KEY or PERPLEXITY_API_KEY required for ApiProvider"
            )

        resolved_base_url = base_url or os.environ.get("LLM_BASE_URL")
        kwargs: dict[str, Any] = {"api_key": resolved_key}
        if resolved_base_url:
            kwargs["base_url"] = resolved_base_url

        self._client = AsyncOpenAI(**kwargs)

    async def send(self, request: AgentRequest) -> AgentResponse:
        if request.role not in ROLE_MODEL:
            raise ValueError(f"Unsupported agent role: {request.role}")

        model = ROLE_MODEL[request.role]
        if request.on_progress:
            request.on_progress(f"Gửi yêu cầu tới mô hình {model} qua API...")

        messages: list[ChatCompletionMessageParam] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        start = time.perf_counter()
        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=request.timeout_s,
        )
        elapsed = time.perf_counter() - start

        content = ""
        if resp.choices and resp.choices[0].message:
            content = resp.choices[0].message.content or ""

        if request.on_progress:
            request.on_progress(f"Nhận phản hồi từ mô hình {model} ({elapsed:.2f}s).")

        return AgentResponse(
            content=content,
            elapsed_s=elapsed,
        )

    async def health_check(self) -> bool:
        return bool(
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("PERPLEXITY_API_KEY")
            or getattr(self._client, "api_key", None)
        )

    async def close(self) -> None:
        await self._client.close()

