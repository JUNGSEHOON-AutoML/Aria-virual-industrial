"""
database_mcp.py — 검사 이력 SQLite FastMCP 서버

노출 도구:
  1. get_inspection_history  — 최근 N건 검사 이력 조회
  2. get_inspection_stats    — 기간별 통계 (정상/결함 건수, 평균 점수)
  3. search_inspections      — 조건부 검색 (날짜, 결과, 모델명)
  4. get_defect_heatmap_data — 결함 다발 위치 집계

DB 경로: argus_core.db (프로젝트 루트, SQLAlchemy로 기존 스키마 재사용)
FastMCP SDK 기반: stdout 오염 없는 안전한 stdio transport
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# FastMCP SDK
from mcp.server.fastmcp import FastMCP

# SQLite 직접 접근
import sqlite3

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "argus_core.db"

mcp = FastMCP("database-mcp")


def _get_conn() -> sqlite3.Connection:
    """Read-only 연결 반환."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"데이터베이스 파일 없음: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_list(rows) -> list[dict]:
    return [dict(row) for row in rows]


@mcp.tool()
async def get_inspection_history(limit: int = 20, offset: int = 0) -> dict:
    """
    최근 검사 이력을 조회합니다.

    Args:
        limit: 조회 건수 (최대 100)
        offset: 페이지 오프셋
    """
    limit = min(int(limit), 100)
    try:
        with _get_conn() as conn:
            cur = conn.execute(
                """
                SELECT id, filename, model_used, score, threshold, status,
                       defect_probability_percent, inference_time_ms,
                       defect_location_description, created_at
                FROM inspections
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = _rows_to_list(cur.fetchall())
            total = conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]

        return {
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "records": rows,
        }
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except sqlite3.OperationalError as e:
        # 테이블 없을 경우 (빈 DB)
        return {"success": False, "error": f"DB 조회 오류 (테이블 미생성?): {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_inspection_stats(days: int = 7) -> dict:
    """
    최근 N일간 검사 통계를 반환합니다.

    Args:
        days: 집계 기간 (기본 7일)
    """
    try:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        with _get_conn() as conn:
            # 전체 집계
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status IN ('anomaly','detected') THEN 1 ELSE 0 END) AS defect_count,
                    SUM(CASE WHEN status = 'normal' THEN 1 ELSE 0 END) AS normal_count,
                    ROUND(AVG(score), 3) AS avg_score,
                    ROUND(AVG(inference_time_ms), 1) AS avg_latency_ms,
                    MAX(score) AS max_score
                FROM inspections
                WHERE created_at >= ?
                """,
                (since,),
            ).fetchone()

            # 모델별 집계
            model_rows = conn.execute(
                """
                SELECT model_used, COUNT(*) AS count,
                       ROUND(AVG(score), 3) AS avg_score,
                       SUM(CASE WHEN status IN ('anomaly','detected') THEN 1 ELSE 0 END) AS defects
                FROM inspections
                WHERE created_at >= ?
                GROUP BY model_used
                ORDER BY count DESC
                """,
                (since,),
            ).fetchall()

        stats = dict(row)
        defect_rate = (
            round(stats["defect_count"] / stats["total"] * 100, 1)
            if stats["total"] else 0.0
        )

        return {
            "success": True,
            "period_days": days,
            "since": since,
            "summary": {**stats, "defect_rate_pct": defect_rate},
            "by_model": _rows_to_list(model_rows),
        }
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except sqlite3.OperationalError as e:
        return {"success": False, "error": f"DB 조회 오류: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def search_inspections(
    status: Optional[str] = None,
    model_used: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_score: Optional[float] = None,
    limit: int = 30,
) -> dict:
    """
    조건부 검사 이력 검색.

    Args:
        status: 'normal', 'anomaly', 'detected' 등
        model_used: 사용 모델명 (부분 일치)
        date_from: 시작 날짜 (ISO 형식: 2025-01-01)
        date_to: 종료 날짜
        min_score: 최소 이상 스코어
        limit: 최대 결과 수 (최대 100)
    """
    limit = min(int(limit), 100)
    clauses = []
    params = []

    if status:
        clauses.append("status = ?")
        params.append(status)
    if model_used:
        clauses.append("model_used LIKE ?")
        params.append(f"%{model_used}%")
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("created_at <= ?")
        params.append(date_to)
    if min_score is not None:
        clauses.append("score >= ?")
        params.append(min_score)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT id, filename, model_used, score, status,
               defect_probability_percent, inference_time_ms, created_at
        FROM inspections {where}
        ORDER BY created_at DESC LIMIT ?
    """
    params.append(limit)

    try:
        with _get_conn() as conn:
            rows = _rows_to_list(conn.execute(sql, params).fetchall())
        return {"success": True, "count": len(rows), "records": rows}
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_defect_heatmap_data(days: int = 30, limit: int = 200) -> dict:
    """
    결함이 감지된 검사 결과를 집계하여 히트맵 데이터를 반환합니다.

    Args:
        days: 집계 기간
        limit: 최대 레코드 수
    """
    try:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        with _get_conn() as conn:
            rows = _rows_to_list(conn.execute(
                """
                SELECT filename, score, defect_probability_percent,
                       defect_location_description, created_at
                FROM inspections
                WHERE status IN ('anomaly', 'detected')
                  AND created_at >= ?
                ORDER BY score DESC LIMIT ?
                """,
                (since, limit),
            ).fetchall())

        return {
            "success": True,
            "period_days": days,
            "defect_count": len(rows),
            "data": rows,
        }
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    sys.stderr.write("[database-mcp] FastMCP 서버 시작\n")
    mcp.run()
