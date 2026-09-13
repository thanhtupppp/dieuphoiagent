import json

from core.session_history import (
    format_timestamp,
    get_recent_sessions,
    load_session_details,
)


def test_format_timestamp():
    ts_str = format_timestamp(1700000000)
    assert "2023" in ts_str or "2024" in ts_str
    assert format_timestamp(float("nan")) == "N/A"


def test_get_recent_sessions_empty_dir(tmp_path):
    assert get_recent_sessions(storage_dir=str(tmp_path / "non_existent")) == []


def test_get_recent_sessions_and_load_details(tmp_path):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    session_data_1 = {
        "status": "COMPLETED",
        "repo": "owner/repo1",
        "branch": "main",
        "goal": "Fix bug",
        "loops": 3,
        "feature_branch": "ai-agent/fix",
        "commit_sha": "abc1234",
        "pr_url": "https://github.com/owner/repo1/pull/1",
        "events": [{"source": "system", "message": "Done"}],
    }
    session_data_2 = {
        "status": "HALTED",
        "repo": "owner/repo2",
        "branch": "dev",
        "goal": "Add feature",
        "loops": 5,
        "events": [],
    }

    # Write files with timestamp prefix
    f1 = session_dir / "1789000000_owner_repo1.json"
    f2 = session_dir / "1789000100_owner_repo2.json"
    f1.write_text(json.dumps(session_data_1), encoding="utf-8")
    f2.write_text(json.dumps(session_data_2), encoding="utf-8")

    # Invalid file to test resilience
    (session_dir / "corrupted.json").write_text("invalid json", encoding="utf-8")

    sessions = get_recent_sessions(storage_dir=str(session_dir))
    assert len(sessions) == 2
    # Should be sorted newest first (1789000100 first)
    assert sessions[0]["repo"] == "owner/repo2"
    assert sessions[0]["status"] == "HALTED"
    assert sessions[1]["repo"] == "owner/repo1"
    assert sessions[1]["status"] == "COMPLETED"
    assert sessions[1]["pr_url"] == "https://github.com/owner/repo1/pull/1"

    # Load details
    det = load_session_details(f1.name, storage_dir=str(session_dir))
    assert det is not None
    assert det["repo"] == "owner/repo1"
    assert len(det["events"]) == 1

    # Load non-existent
    assert load_session_details("non_existent.json", storage_dir=str(session_dir)) is None


def test_session_history_edge_cases(tmp_path):
    session_dir = tmp_path / "sessions_edge"
    session_dir.mkdir()

    # Non-dict json file (list)
    (session_dir / "1789000200_list.json").write_text("[1, 2, 3]", encoding="utf-8")
    # File without numeric prefix
    (session_dir / "custom_session.json").write_text(
        json.dumps({"repo": "owner/custom", "loops": 1}), encoding="utf-8"
    )

    sessions = get_recent_sessions(storage_dir=str(session_dir))
    assert len(sessions) == 1
    assert sessions[0]["repo"] == "owner/custom"

    # load_session_details with non-dict json file
    assert load_session_details("1789000200_list.json", storage_dir=str(session_dir)) is None

