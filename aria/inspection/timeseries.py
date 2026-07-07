"""시계열 척추(경량) — OEE/품질/가용성/tact 등을 SQLite에 append + 다운샘플 조회.

24h 드리프트·리플레이의 토대. 인메모리 링버퍼 대신 영속 저장 → 재시작 후 추세 복원.
(운영 규모에선 Timescale/Influx로 교체 — 인터페이스(record/recent) 동일 유지.)
절대 예외를 밖으로 던지지 않음(텔레메트리 실패가 파이프라인 차단 금지).
"""
from __future__ import annotations
import os
import sqlite3
import threading
import time

from aria.core.database import DB_PATH

TS_PATH = os.path.join(os.path.dirname(DB_PATH), "metrics_ts.db")
_lock = threading.Lock()
_conn = None


def _c():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(TS_PATH, check_same_thread=False)
        _conn.execute("""CREATE TABLE IF NOT EXISTS metrics_ts (
            ts REAL, lane INTEGER, category TEXT,
            oee REAL, quality REAL, availability REAL,
            tact REAL, infer_p95 REAL, drop_count INTEGER,
            n_ok INTEGER, n_ng INTEGER, n_skipped INTEGER)""")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics_ts(ts)")
        # T1-C C0: 자산 건전성 선행지표(온도·진동·p95·drop). 라인 품질(metrics_ts)과 별개.
        # sim: 1=온도/진동은 트윈 프록시(실센서 미연결), 0=실측. 정직성 태깅.
        _conn.execute("""CREATE TABLE IF NOT EXISTS asset_health_ts (
            ts REAL, lane INTEGER, asset_id TEXT,
            temp_c REAL, vib_rms_mm_s REAL, infer_p95_ms REAL,
            drop_rate REAL, current_a REAL, sim INTEGER)""")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_health_ts ON asset_health_ts(asset_id, ts)")
        # T1-C C3: PdM 융합 가설/승인/결과 로깅(평가·MLOps·향후 run-to-failure 라벨).
        _conn.execute("""CREATE TABLE IF NOT EXISTS pdm_episode (
            ts REAL, asset_id TEXT, health_index REAL, rul_est REAL,
            corroborated INTEGER, confidence REAL, leading TEXT, note TEXT)""")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_pdm_episode ON pdm_episode(ts)")
        _conn.commit()
    return _conn


def record(snap: dict, lane: int = 0, category: str | None = None, ts: float | None = None) -> None:
    """스냅샷 1건 저장(다운샘플은 호출측에서 ~2s 간격 권장)."""
    try:
        with _lock:
            c = _c()
            c.execute(
                "INSERT INTO metrics_ts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ts or time.time(), lane, category,
                 snap.get("oee"), snap.get("quality"), snap.get("availability"),
                 snap.get("tact_time_ms"), snap.get("infer_latency_p95_ms"), snap.get("drop_count"),
                 snap.get("n_ok"), snap.get("n_ng"), snap.get("n_skipped")))
            c.commit()
    except Exception:
        pass


def recent(minutes: int = 60, max_points: int = 200) -> list:
    """최근 N분 시계열(다운샘플). 재시작 후에도 저장분에서 복원."""
    try:
        with _lock:
            c = _c()
            since = time.time() - minutes * 60
            rows = c.execute(
                "SELECT ts, oee, quality, availability, drop_count FROM metrics_ts "
                "WHERE ts>=? ORDER BY ts", (since,)).fetchall()
        if len(rows) > max_points:
            step = -(-len(rows) // max_points)   # ceil → 결과 ≤ max_points 보장
            rows = rows[::step]
        return [{"ts": r[0], "oee": r[1], "quality": r[2], "availability": r[3], "drop": r[4]} for r in rows]
    except Exception:
        return []


# ── T1-C C0: 자산 건전성 시계열(선행 지표) — 동일 record/recent 계약 ──
def record_health(row: dict, ts: float | None = None) -> None:
    """자산 건전성 1건 저장. row: {lane, asset_id, temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate, current_a?, sim?}"""
    try:
        with _lock:
            c = _c()
            c.execute(
                "INSERT INTO asset_health_ts VALUES (?,?,?,?,?,?,?,?,?)",
                (ts or time.time(), row.get("lane", 0), row.get("asset_id"),
                 row.get("temp_c"), row.get("vib_rms_mm_s"), row.get("infer_p95_ms"),
                 row.get("drop_rate"), row.get("current_a"), int(row.get("sim", 1))))
            c.commit()
    except Exception:
        pass


def recent_health(asset_id: str | None = None, minutes: int = 60, max_points: int = 300) -> list:
    """최근 N분 자산 건전성(다운샘플). asset_id 지정 시 해당 자산만. 재시작 후 복원."""
    try:
        with _lock:
            c = _c()
            since = time.time() - minutes * 60
            if asset_id is not None:
                rows = c.execute(
                    "SELECT ts, lane, asset_id, temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate, current_a, sim "
                    "FROM asset_health_ts WHERE asset_id=? AND ts>=? ORDER BY ts",
                    (asset_id, since)).fetchall()
            else:
                rows = c.execute(
                    "SELECT ts, lane, asset_id, temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate, current_a, sim "
                    "FROM asset_health_ts WHERE ts>=? ORDER BY ts", (since,)).fetchall()
        if len(rows) > max_points:
            step = -(-len(rows) // max_points)
            rows = rows[::step]
        return [{"ts": r[0], "lane": r[1], "asset_id": r[2], "temp_c": r[3],
                 "vib_rms_mm_s": r[4], "infer_p95_ms": r[5], "drop_rate": r[6],
                 "current_a": r[7], "sim": r[8]} for r in rows]
    except Exception:
        return []


def record_episode(ep: dict, ts: float | None = None) -> None:
    """PdM 에피소드 1건 저장(가설/승인/결과)."""
    try:
        with _lock:
            c = _c()
            c.execute(
                "INSERT INTO pdm_episode VALUES (?,?,?,?,?,?,?,?)",
                (ts or time.time(), ep.get("asset"), ep.get("health_index"),
                 (ep.get("rul") or {}).get("est_hours"),
                 int(bool(ep.get("corroborated"))), ep.get("confidence"),
                 ",".join(ep.get("leading_signals") or []), ep.get("note")))
            c.commit()
    except Exception:
        pass


def recent_episodes(minutes: int = 1440, max_points: int = 200) -> list:
    try:
        with _lock:
            c = _c()
            since = time.time() - minutes * 60
            rows = c.execute(
                "SELECT ts, asset_id, health_index, rul_est, corroborated, confidence, leading, note "
                "FROM pdm_episode WHERE ts>=? ORDER BY ts DESC LIMIT ?",
                (since, max_points)).fetchall()
        return [{"ts": r[0], "asset": r[1], "health_index": r[2], "rul_est": r[3],
                 "corroborated": bool(r[4]), "confidence": r[5], "leading": r[6], "note": r[7]}
                for r in rows]
    except Exception:
        return []


def last_health_ts_per_asset(minutes: int = 60) -> dict:
    """자산별 마지막 신호 시각(wallclock) → {asset_id: ts}.
    S3b-3 Layer-2 stale: producer는 연결됐는데 개별 자산 신호가 늦을 때 사용."""
    try:
        with _lock:
            c = _c()
            since = time.time() - minutes * 60
            rows = c.execute(
                "SELECT asset_id, MAX(ts) FROM asset_health_ts "
                "WHERE ts>=? AND asset_id IS NOT NULL GROUP BY asset_id",
                (since,)).fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def health_assets(minutes: int = 60) -> list:
    """최근 창에서 신호가 있는 자산 id 목록(융합 서비스가 순회용)."""
    try:
        with _lock:
            c = _c()
            since = time.time() - minutes * 60
            rows = c.execute(
                "SELECT DISTINCT asset_id FROM asset_health_ts WHERE ts>=? AND asset_id IS NOT NULL",
                (since,)).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
