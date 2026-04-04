"""Tests for multi-session management in WorkspaceManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from aqualib.config import DirectorySettings, Settings
from aqualib.workspace.manager import WorkspaceManager


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceManager:
    dirs = DirectorySettings(base=tmp_path).resolve()
    settings = Settings(directories=dirs)
    ws = WorkspaceManager(settings)
    ws.create_project(name="Test Project")
    return ws


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_creates_directory_structure(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="my-session")
        slug = meta["slug"]
        session_dir = workspace.session_dir(slug)

        assert session_dir.is_dir()
        assert (session_dir / "session.json").exists()
        assert (session_dir / "memory").is_dir()
        assert (session_dir / "results").is_dir()
        assert (session_dir / "vendor_traces").is_dir()

    def test_returns_correct_metadata(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="Protein Study")
        assert "slug" in meta
        assert "session_id" in meta
        assert meta["session_id"].startswith("aqualib-")
        assert meta["name"] == "Protein Study"
        assert meta["task_count"] == 0
        assert meta["status"] == "active"

    def test_sets_active_session(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="alpha")
        project = workspace.load_project()
        assert project is not None
        assert project["active_session"] == meta["slug"]

    def test_multiple_sessions(self, workspace: WorkspaceManager):
        meta_a = workspace.create_session(name="session-alpha")
        meta_b = workspace.create_session(name="session-beta")
        assert meta_a["slug"] != meta_b["slug"]

    def test_slug_uses_name(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="align conserved")
        assert "align" in meta["slug"]

    def test_creates_session_without_name(self, workspace: WorkspaceManager):
        meta = workspace.create_session()
        assert meta["slug"]  # has some slug
        assert meta["name"]  # has some name


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_empty_when_no_sessions(self, workspace: WorkspaceManager):
        assert workspace.list_sessions() == []

    def test_returns_all_sessions(self, workspace: WorkspaceManager):
        workspace.create_session(name="alpha")
        workspace.create_session(name="beta")
        workspace.create_session(name="gamma")
        sessions = workspace.list_sessions()
        assert len(sessions) == 3

    def test_sorted_by_updated_at_descending(self, workspace: WorkspaceManager):
        import time

        workspace.create_session(name="first")
        time.sleep(0.01)
        workspace.create_session(name="second")
        time.sleep(0.01)
        workspace.create_session(name="third")

        sessions = workspace.list_sessions()
        # Most recently updated first
        timestamps = [s["updated_at"] for s in sessions]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# load_session / find_session_by_prefix
# ---------------------------------------------------------------------------


class TestLoadAndFind:
    def test_load_existing_session(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="my-test")
        loaded = workspace.load_session(meta["slug"])
        assert loaded is not None
        assert loaded["slug"] == meta["slug"]

    def test_load_nonexistent_session_returns_none(self, workspace: WorkspaceManager):
        assert workspace.load_session("nonexistent-slug") is None

    def test_find_by_exact_prefix(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="align-conserved")
        slug = meta["slug"]
        # Find using first 5 chars of slug
        found = workspace.find_session_by_prefix(slug[:5])
        assert found is not None
        assert found["slug"] == slug

    def test_find_by_full_slug(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test-session")
        found = workspace.find_session_by_prefix(meta["slug"])
        assert found is not None
        assert found["slug"] == meta["slug"]

    def test_find_returns_none_for_no_match(self, workspace: WorkspaceManager):
        workspace.create_session(name="alpha")
        found = workspace.find_session_by_prefix("zzzzz")
        assert found is None

    def test_find_returns_most_recent_match(self, workspace: WorkspaceManager):
        import time

        # Create two sessions with the same prefix "test-"
        workspace.create_session(name="test-alpha")
        time.sleep(0.01)
        workspace.create_session(name="test-beta")

        # Both start with "test-"
        found = workspace.find_session_by_prefix("test-")
        assert found is not None
        # Should return the most recently updated one
        assert "test-beta" in found["name"]


# ---------------------------------------------------------------------------
# get_active_session
# ---------------------------------------------------------------------------


class TestGetActiveSession:
    def test_returns_none_when_no_sessions(self, workspace: WorkspaceManager):
        assert workspace.get_active_session() is None

    def test_returns_active_session(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="my-active")
        active = workspace.get_active_session()
        assert active is not None
        assert active["slug"] == meta["slug"]

    def test_returns_most_recently_created(self, workspace: WorkspaceManager):
        workspace.create_session(name="first")
        second = workspace.create_session(name="second")
        active = workspace.get_active_session()
        assert active is not None
        assert active["slug"] == second["slug"]

    def test_returns_none_when_project_missing(self, tmp_path: Path):
        # Workspace without a project
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        assert ws.get_active_session() is None


# ---------------------------------------------------------------------------
# session_dir / session_results_dir / session_vendor_traces_dir
# ---------------------------------------------------------------------------


class TestSessionDirs:
    def test_session_dir_path(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        expected = workspace.dirs.base / "sessions" / slug
        assert workspace.session_dir(slug) == expected

    def test_session_results_dir_created(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        results_dir = workspace.session_results_dir(meta["slug"])
        assert results_dir.is_dir()

    def test_session_vendor_traces_dir_created(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        traces_dir = workspace.session_vendor_traces_dir(meta["slug"])
        assert traces_dir.is_dir()


# ---------------------------------------------------------------------------
# update_session_after_task
# ---------------------------------------------------------------------------


class TestUpdateSessionAfterTask:
    def test_increments_task_count(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        workspace.update_session_after_task(slug, "align sequences", ["done"])
        updated = workspace.load_session(slug)
        assert updated is not None
        assert updated["task_count"] == 1

    def test_updates_summary(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        workspace.update_session_after_task(slug, "align sequences", ["done"])
        updated = workspace.load_session(slug)
        assert updated is not None
        assert "align sequences" in updated["summary"]

    def test_updates_project_task_count(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        workspace.update_session_after_task(slug, "test query", [])
        project = workspace.load_project()
        assert project is not None
        assert project["task_count"] >= 1

    def test_appends_to_context_log(self, workspace: WorkspaceManager):
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        workspace.update_session_after_task(slug, "my query", [])
        entries = workspace.load_context_log()
        assert any(e.get("query") == "my query" for e in entries)

    def test_skills_used_written_to_context_log(self, workspace: WorkspaceManager):
        """Bug 5: skills_used parameter should be written to context_log."""
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        workspace.update_session_after_task(
            slug, "align sequences", ["done"],
            skills_used=["vendor_seq_align", "vendor_drug_check"],
        )
        entries = workspace.load_context_log()
        task_entry = next(e for e in entries if e.get("query") == "align sequences")
        assert task_entry["skills_used"] == ["vendor_seq_align", "vendor_drug_check"]

    def test_skills_used_defaults_to_empty_list(self, workspace: WorkspaceManager):
        """Bug 5: when skills_used is not provided, defaults to empty list."""
        meta = workspace.create_session(name="test")
        slug = meta["slug"]
        workspace.update_session_after_task(slug, "test query", [])
        entries = workspace.load_context_log()
        task_entry = next(e for e in entries if e.get("query") == "test query")
        assert task_entry["skills_used"] == []


# ---------------------------------------------------------------------------
# Backward compatibility: old project without sessions/ directory
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_list_sessions_empty_for_old_project(self, tmp_path: Path):
        """Old projects without sessions/ directory should not crash."""
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        ws.create_project(name="old-project")
        # No sessions/ directory created
        assert not (tmp_path / "sessions").exists()
        assert ws.list_sessions() == []

    def test_get_active_session_returns_none_for_old_project(self, tmp_path: Path):
        """Old projects without active_session should return None."""
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        ws.create_project(name="old-project")
        assert ws.get_active_session() is None

    def test_first_run_creates_session(self, tmp_path: Path):
        """First run on an old project auto-creates a session."""
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        ws.create_project(name="old-project")

        # Simulate first run creating a session
        meta = ws.create_session()
        assert ws.get_active_session() is not None
        assert ws.get_active_session()["slug"] == meta["slug"]


# ---------------------------------------------------------------------------
# Bug 4: save_sdk_vendor_trace writes to session-level directory
# ---------------------------------------------------------------------------


class TestVendorTraceSessionDir:
    def test_writes_to_global_dir_without_session_slug(self, workspace: WorkspaceManager):
        """Without session_slug, only writes to global vendor_traces/."""
        trace_path = workspace.save_sdk_vendor_trace(
            "seq_align", {"returncode": 0, "stdout": "ok", "stderr": ""}
        )
        assert trace_path.exists()
        assert "vendor_traces" in str(trace_path)

    def test_writes_to_both_dirs_with_session_slug(self, workspace: WorkspaceManager):
        """With session_slug, writes to both global and session-level vendor_traces/."""
        meta = workspace.create_session(name="test")
        slug = meta["slug"]

        trace_path = workspace.save_sdk_vendor_trace(
            "seq_align",
            {"returncode": 0, "stdout": "ok", "stderr": ""},
            session_slug=slug,
        )
        # Global trace exists
        assert trace_path.exists()

        # Session-level trace also exists
        session_traces = workspace.session_vendor_traces_dir(slug)
        session_trace_files = list(session_traces.iterdir())
        assert len(session_trace_files) == 1
        assert session_trace_files[0].name == trace_path.name

    def test_session_trace_has_same_content(self, workspace: WorkspaceManager):
        """Session-level trace should have the same content as global trace."""
        import json

        meta = workspace.create_session(name="test")
        slug = meta["slug"]

        trace_path = workspace.save_sdk_vendor_trace(
            "drug_check",
            {"returncode": 0, "stdout": "result", "stderr": ""},
            session_slug=slug,
        )
        global_data = json.loads(trace_path.read_text())

        session_traces = workspace.session_vendor_traces_dir(slug)
        session_trace_path = session_traces / trace_path.name
        session_data = json.loads(session_trace_path.read_text())

        assert global_data["skill_name"] == session_data["skill_name"]
        assert global_data["stdout"] == session_data["stdout"]


# ---------------------------------------------------------------------------
# Bug 6: run command exits when project is not initialised
# ---------------------------------------------------------------------------


class TestRunExitsWithoutProject:
    def test_run_exits_when_no_project(self, tmp_path: Path):
        """aqualib run should exit with code 1 when no project.json exists."""
        from typer.testing import CliRunner

        from aqualib.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["run", "test query", "--base-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "No project found" in result.output


# ---------------------------------------------------------------------------
# Bug 3: status command shows session information
# ---------------------------------------------------------------------------


class TestStatusShowsSessions:
    def test_status_displays_session_info(self, workspace: WorkspaceManager, tmp_path: Path):
        """status command should show session count and active session."""
        from typer.testing import CliRunner

        from aqualib.cli import app

        # Create sessions
        workspace.create_session(name="alpha")
        workspace.create_session(name="beta")

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Sessions:" in result.output
        assert "2 total" in result.output

    def test_status_shows_no_sessions_section_when_none(self, tmp_path: Path):
        """When no sessions exist, Sessions line should not appear."""
        from typer.testing import CliRunner

        from aqualib.cli import app

        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        ws.create_project(name="Empty Project")

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Sessions:" not in result.output
