from pathlib import Path

import pytest

from aria.mcp.servers import filesystem_mcp as fs


def test_sandbox_roots_resolve_from_project_not_mcp_package():
    root = Path(__file__).resolve().parents[1]
    assert fs.BASE_DIR == root
    assert fs.SANDBOX_ROOTS == [
        root / name for name in ('uploads', 'outputs', 'downloads', 'logs', 'scratch', 'data')
    ]
    for name in ('uploads', 'outputs'):
        assert fs._safe_path(str(root / name / 'root-regression.txt')) == root / name / 'root-regression.txt'
    # data may be an external symlink: the configured root is still project/data.
    assert fs.SANDBOX_ROOTS[-1] == root / 'data'
    assert fs._safe_path('server/app.py') == root / 'server/app.py'
    with pytest.raises(PermissionError):
        fs._safe_path('/tmp/aria-outside-project.txt')
