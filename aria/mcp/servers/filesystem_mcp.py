"""
filesystem_mcp.py — 파일 시스템 접근 FastMCP 서버

노출 도구:
  1. read_file       — 파일 내용 읽기
  2. write_file      — 파일 쓰기/생성
  3. list_directory  — 디렉토리 목록
  4. search_files    — 파일/디렉토리 검색

FastMCP SDK 기반: stdout 오염 없는 안전한 stdio transport
"""

import os
import sys
import glob
from pathlib import Path

# FastMCP import (mcp>=1.0.0)
from mcp.server.fastmcp import FastMCP

# ── 샌드박스 루트 (프로젝트 디렉토리로 제한) ──────────────────
BASE_DIR = Path(__file__).parent.parent.resolve()
SANDBOX_ROOTS = [
    BASE_DIR / "uploads",
    BASE_DIR / "outputs",
    BASE_DIR / "downloads",
    BASE_DIR / "logs",
    BASE_DIR / "scratch",
    BASE_DIR / "data",
]

mcp = FastMCP("filesystem-mcp")


def _safe_path(path_str: str) -> Path:
    """경로를 정규화하고 BASE_DIR 범위 내인지 검증."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = BASE_DIR / p
    p = p.resolve()
    # 샌드박스 루트 중 하나의 하위이거나 BASE_DIR 하위면 허용
    if not str(p).startswith(str(BASE_DIR)):
        raise PermissionError(f"접근 거부: '{p}'는 허용된 경로 밖입니다.")
    return p


@mcp.tool()
async def read_file(path: str, encoding: str = "utf-8", max_bytes: int = 1_000_000) -> dict:
    """
    파일 내용을 읽어 반환합니다.

    Args:
        path: 파일 경로 (절대 또는 프로젝트 루트 기준 상대경로)
        encoding: 텍스트 인코딩 (기본: utf-8)
        max_bytes: 최대 읽기 바이트 (기본 1MB)
    """
    try:
        p = _safe_path(path)
        if not p.exists():
            return {"success": False, "error": f"파일이 존재하지 않습니다: {path}"}
        if not p.is_file():
            return {"success": False, "error": f"경로가 파일이 아닙니다: {path}"}

        size = p.stat().st_size
        # 바이너리 파일 감지
        try:
            content = p.read_text(encoding=encoding)[:max_bytes]
        except UnicodeDecodeError:
            return {
                "success": True,
                "path": str(p),
                "size_bytes": size,
                "is_binary": True,
                "content": f"(바이너리 파일 — {size:,} bytes)",
            }

        return {
            "success": True,
            "path": str(p),
            "size_bytes": size,
            "truncated": size > max_bytes,
            "content": content,
        }
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"읽기 오류: {e}"}


@mcp.tool()
async def write_file(path: str, content: str, encoding: str = "utf-8", append: bool = False) -> dict:
    """
    파일에 내용을 씁니다 (없으면 생성).

    Args:
        path: 파일 경로
        content: 저장할 문자열 내용
        encoding: 텍스트 인코딩 (기본: utf-8)
        append: True이면 기존 내용에 추가, False이면 덮어씀
    """
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding=encoding) as f:
            f.write(content)
        return {
            "success": True,
            "path": str(p),
            "bytes_written": len(content.encode(encoding)),
            "mode": "append" if append else "overwrite",
        }
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"쓰기 오류: {e}"}


@mcp.tool()
async def list_directory(path: str = ".", show_hidden: bool = False) -> dict:
    """
    디렉토리 내 파일 및 하위 디렉토리를 나열합니다.

    Args:
        path: 대상 디렉토리 경로 (기본: 프로젝트 루트)
        show_hidden: 숨김 파일 포함 여부
    """
    try:
        p = _safe_path(path)
        if not p.exists():
            return {"success": False, "error": f"디렉토리가 존재하지 않습니다: {path}"}
        if not p.is_dir():
            return {"success": False, "error": f"경로가 디렉토리가 아닙니다: {path}"}

        entries = []
        for item in sorted(p.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size_bytes": stat.st_size if item.is_file() else None,
                "modified": stat.st_mtime,
            })

        return {
            "success": True,
            "path": str(p),
            "count": len(entries),
            "entries": entries,
        }
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"디렉토리 조회 오류: {e}"}


@mcp.tool()
async def search_files(path: str = ".", pattern: str = "*", recursive: bool = True, max_results: int = 50) -> dict:
    """
    지정된 패턴으로 파일을 검색합니다.

    Args:
        path: 검색 시작 디렉토리
        pattern: glob 패턴 (예: '*.jpg', '**/*.png')
        recursive: 하위 디렉토리 포함 여부
        max_results: 최대 결과 수
    """
    try:
        p = _safe_path(path)
        if not p.is_dir():
            return {"success": False, "error": f"디렉토리가 아닙니다: {path}"}

        if recursive and "**" not in pattern:
            pattern = f"**/{pattern}"

        matches = []
        for m in p.glob(pattern):
            if len(matches) >= max_results:
                break
            try:
                stat = m.stat()
                matches.append({
                    "path": str(m),
                    "name": m.name,
                    "type": "dir" if m.is_dir() else "file",
                    "size_bytes": stat.st_size if m.is_file() else None,
                })
            except Exception:
                continue

        return {
            "success": True,
            "search_path": str(p),
            "pattern": pattern,
            "count": len(matches),
            "truncated": len(matches) >= max_results,
            "results": matches,
        }
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"검색 오류: {e}"}


if __name__ == "__main__":
    sys.stderr.write("[filesystem-mcp] FastMCP 서버 시작\n")
    mcp.run()
