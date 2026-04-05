"""Tests for the ``aqualib chat`` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aqualib.cli import (
    _chat_print_help,
    _chat_print_history,
    _chat_print_session,
    _chat_print_skills,
    _chat_print_status,
)
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
# Slash-command helper tests
# ---------------------------------------------------------------------------


class TestSlashHelp:
    def test_prints_table(self, capsys: Any) -> None:
        _chat_print_help()
        # Rich writes to its own console, but we can assert no exception


class TestSlashStatus:
    def test_with_project(self, workspace: WorkspaceManager) -> None:
        _chat_print_status(workspace)

    def test_without_project(self, tmp_path: Path) -> None:
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        _chat_print_status(ws)


class TestSlashSkills:
    def test_no_skills(self, workspace: WorkspaceManager) -> None:
        def fake_scan(settings: Any, ws: Any) -> list:
            return []

        _chat_print_skills(workspace.settings, workspace, fake_scan)

    def test_with_skills(self, workspace: WorkspaceManager) -> None:
        mock_meta = MagicMock()
        mock_meta.name = "alignment"
        mock_meta.description = "Align sequences"
        mock_meta.tags = ["bio"]

        def fake_scan(settings: Any, ws: Any) -> list:
            return [mock_meta]

        _chat_print_skills(workspace.settings, workspace, fake_scan)


class TestSlashSession:
    def test_existing_session(self, workspace: WorkspaceManager) -> None:
        meta = workspace.create_session(name="test-sess")
        _chat_print_session(workspace, meta["slug"])

    def test_missing_session(self, workspace: WorkspaceManager) -> None:
        _chat_print_session(workspace, "nonexistent-slug")


class TestSlashHistory:
    def test_empty_history(self, workspace: WorkspaceManager) -> None:
        meta = workspace.create_session(name="hist-sess")
        _chat_print_history(workspace, meta["slug"])

    def test_with_entries(self, workspace: WorkspaceManager) -> None:
        meta = workspace.create_session(name="hist-sess")
        workspace.append_context_log({
            "session_slug": meta["slug"],
            "query": "Test query",
            "status": "approved",
            "timestamp": "2026-04-01T00:00:00Z",
        })
        _chat_print_history(workspace, meta["slug"])


# ---------------------------------------------------------------------------
# Chat command integration tests (mock SDK)
# ---------------------------------------------------------------------------


class TestChatCommandNoProject:
    def test_exits_when_no_project(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from aqualib.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["chat", "--base-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "aqualib init" in result.output


class TestChatCommandExitWords:
    """Verify that typing exit/quit terminates the loop."""

    @pytest.fixture()
    def _project_dir(self, tmp_path: Path) -> Path:
        """Create a minimal project so chat can start."""
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        ws.create_project(name="Chat Test")
        return tmp_path

    @pytest.mark.parametrize("word", ["exit", "quit", "/exit", "/quit"])
    def test_exit_word(self, word: str, _project_dir: Path) -> None:
        from typer.testing import CliRunner

        from aqualib.cli import app

        runner = CliRunner()

        fake_client = AsyncMock()
        fake_client.start = AsyncMock(return_value=MagicMock())
        fake_client.stop = AsyncMock()

        fake_session = MagicMock()
        fake_session.on = MagicMock()
        fake_session.send = AsyncMock()

        with (
            patch("aqualib.cli.console") as mock_console,
            patch("aqualib.sdk.client.AquaLibClient", return_value=fake_client),
            patch(
                "aqualib.sdk.session_manager.SessionManager.get_or_create_session",
                new_callable=AsyncMock,
                return_value=(fake_session, "test-slug-12345678"),
            ),
        ):
            # First call returns the exit word, then EOFError to be safe
            mock_console.input = MagicMock(side_effect=[word])

            result = runner.invoke(app, ["chat", "--base-dir", str(_project_dir)])
            # Should exit cleanly
            assert result.exit_code == 0


class TestChatSlashInLoop:
    """Verify /help in the loop doesn't crash."""

    @pytest.fixture()
    def _project_dir(self, tmp_path: Path) -> Path:
        dirs = DirectorySettings(base=tmp_path).resolve()
        settings = Settings(directories=dirs)
        ws = WorkspaceManager(settings)
        ws.create_project(name="Slash Test")
        return tmp_path

    def test_help_then_exit(self, _project_dir: Path) -> None:
        from typer.testing import CliRunner

        from aqualib.cli import app

        runner = CliRunner()

        fake_client = AsyncMock()
        fake_client.start = AsyncMock(return_value=MagicMock())
        fake_client.stop = AsyncMock()

        fake_session = MagicMock()
        fake_session.on = MagicMock()
        fake_session.send = AsyncMock()

        with (
            patch("aqualib.cli.console") as mock_console,
            patch("aqualib.sdk.client.AquaLibClient", return_value=fake_client),
            patch(
                "aqualib.sdk.session_manager.SessionManager.get_or_create_session",
                new_callable=AsyncMock,
                return_value=(fake_session, "test-slug-12345678"),
            ),
        ):
            mock_console.input = MagicMock(side_effect=["/help", "exit"])
            mock_console.print = MagicMock()

            result = runner.invoke(app, ["chat", "--base-dir", str(_project_dir)])
            assert result.exit_code == 0
