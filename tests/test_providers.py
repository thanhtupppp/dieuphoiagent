from core.providers.base import AgentRequest, AgentResponse, AgentRole, ProviderKind
from core.providers.factory import build_provider


def test_agent_roles_are_stable():
    assert [role.value for role in AgentRole] == ["tech_lead", "core_dev"]


def test_provider_kinds_are_stable():
    assert [kind.value for kind in ProviderKind] == ["cdp", "api", "local"]


def test_agent_request_fields_and_defaults():
    request = AgentRequest(
        role=AgentRole.TECH_LEAD,
        system_prompt="system",
        user_prompt="user",
    )
    assert request.role is AgentRole.TECH_LEAD
    assert request.system_prompt == "system"
    assert request.user_prompt == "user"
    assert request.timeout_s == 600
    assert request.on_progress is None


def test_agent_response_fields_and_defaults():
    response = AgentResponse(content="result")
    assert response.content == "result"
    assert response.raw_html is None
    assert response.source_url is None
    assert response.elapsed_s == 0.0


def test_factory_builds_cdp_provider():
    provider = build_provider(ProviderKind.CDP)
    assert provider.kind is ProviderKind.CDP
    assert provider.__class__.__name__ == "CdpProvider"


def test_factory_builds_api_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    provider = build_provider(ProviderKind.API)
    assert provider.kind is ProviderKind.API
    assert provider.__class__.__name__ == "ApiProvider"



def test_factory_rejects_unsupported_provider():
    try:
        build_provider(ProviderKind.LOCAL)
    except ValueError as exc:
        assert "Unknown provider kind" in str(exc)
    else:
        raise AssertionError("LOCAL provider must not be available before implementation")
