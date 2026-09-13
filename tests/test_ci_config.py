from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_exists_and_is_valid_yaml() -> None:
    data = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(data, dict)
    assert data["name"] == "CI"
    assert "on" in data
    assert set(data["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert data["on"]["push"]["branches"] == ["master"]


def test_ci_workflow_has_required_quality_gates() -> None:
    data = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    jobs = data["jobs"]
    assert set(jobs) >= {
        "package",
        "format",
        "lint",
        "typecheck",
        "test",
        "pre-commit",
        "secret-scan",
    }

    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    for command in (
        "uv sync --locked",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy core ui",
        "uv run pytest",
        "uv run pre-commit run --all-files",
    ):
        assert command in workflow_text


def test_live_browser_tests_are_excluded_by_default() -> None:
    pytest_config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "addopts = \"-m 'not live'\"" in pytest_config
