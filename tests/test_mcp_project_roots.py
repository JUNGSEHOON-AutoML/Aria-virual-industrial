"""The three MCP tools must resolve resources from the repository after moving packages."""
from pathlib import Path
import sqlite3
import subprocess

import pytest

from aria.mcp.servers import database_mcp as database
from aria.mcp.servers import huggingface_mcp as huggingface
from aria.mcp.servers import shell_exec_mcp as shell

ROOT = Path(__file__).resolve().parents[1]


def test_database_uses_project_database_and_read_only_connections(tmp_path, monkeypatch):
    assert database.BASE_DIR == ROOT
    assert database.DB_PATH == ROOT / 'argus_core.db'
    path = tmp_path / 'fixture.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE probe (value INTEGER)')
        conn.execute('INSERT INTO probe VALUES (7)')
    monkeypatch.setattr(database, 'DB_PATH', path)
    with database._get_conn() as conn:
        assert conn.execute('SELECT value FROM probe').fetchone()[0] == 7
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            conn.execute('INSERT INTO probe VALUES (8)')


def test_huggingface_cache_uses_project_downloads():
    assert huggingface.BASE_DIR == ROOT
    assert huggingface.HF_CACHE_DIR == ROOT / 'downloads' / 'huggingface'


def test_shell_default_cwd_is_project_and_external_cwd_is_denied(monkeypatch, tmp_path):
    assert Path(shell.PROJECT_ROOT) == ROOT
    calls = []
    def run(*args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout='ok', stderr='')
    monkeypatch.setattr(shell.subprocess, 'run', run)
    shell.tool_run_command({'command': 'ls'})
    assert len(calls) == 1 and Path(calls[0]['cwd']) == ROOT
    shell.tool_run_command({'command': 'ls', 'cwd': str(tmp_path)})
    assert len(calls) == 1
