"""
database.py — SQLAlchemy-free SQLite shim.
동일한 인터페이스를 유지하면서 sqlalchemy 의존성 없이 동작합니다.
"""
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "argus_core.db")


# ─── 경량 ORM 대체 ─────────────────────────────────────────────────────────────

class _Row:
    """dict-like 결과 행"""
    def __init__(self, **kw): self.__dict__.update(kw)
    def __getattr__(self, k): return None


class _Session:
    def __init__(self, conn):
        self._conn = conn

    def add(self, obj):
        if isinstance(obj, AnalysisHistory):
            self._conn.execute(
                "INSERT INTO analysis_history "
                "(timestamp, image_path, domain_type, score, defect_probability, heatmap_url) "
                "VALUES (?,?,?,?,?,?)",
                (
                    obj.timestamp.isoformat() if hasattr(obj.timestamp, "isoformat") else str(datetime.now()),
                    obj.image_path or "", obj.domain_type or "",
                    float(obj.score or 0), float(obj.defect_probability or 0),
                    obj.heatmap_url or ""
                )
            )
        elif isinstance(obj, AgentMemory):
            self._conn.execute(
                "INSERT INTO agent_memory (session_id, role, content, timestamp) VALUES (?,?,?,?)",
                (
                    obj.session_id or "default", obj.role or "agent",
                    obj.content or "",
                    obj.timestamp.isoformat() if hasattr(obj.timestamp, "isoformat") else str(datetime.now()),
                )
            )

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        pass  # 연결은 SessionLocal이 관리

    def query(self, model):
        return _Query(self._conn, model)


class _Query:
    def __init__(self, conn, model):
        self._conn  = conn
        self._model = model
        self._filters = []
        self._order   = None
        self._limit_n = None

    def filter(self, *args): return self  # simplification

    def order_by(self, *args):
        self._order = "DESC"
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def first(self):
        self._limit_n = 1
        res = self.all()
        return res[0] if res else None

    def all(self):
        table = self._model.__tablename__
        q = f"SELECT * FROM {table}"
        if self._order:
            q += " ORDER BY timestamp DESC"
        if self._limit_n:
            q += f" LIMIT {self._limit_n}"
        rows = []
        try:
            cur = self._conn.execute(q)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                obj = self._model.__new__(self._model)
                for c, v in zip(cols, r):
                    setattr(obj, c, v)
                # timestamp 문자열 → datetime (필요 시)
                if hasattr(obj, "timestamp") and isinstance(obj.timestamp, str):
                    try:
                        obj.timestamp = datetime.fromisoformat(obj.timestamp)
                    except Exception:
                        obj.timestamp = datetime.now()
                rows.append(obj)
        except Exception:
            pass
        return rows


def SessionLocal():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return _Session(conn)


# ─── 모델 클래스 (속성 컨테이너) ───────────────────────────────────────────────

class _DescProxy:
    """order_by(Model.col.desc()) 패턴을 허용하는 더미 프록시"""
    def desc(self): return self
    def asc(self):  return self


class AnalysisHistory:
    __tablename__ = "analysis_history"
    # class-level column proxies (for order_by(AnalysisHistory.timestamp.desc()))
    timestamp          = _DescProxy()
    id                 = _DescProxy()

    def __init__(self, image_path="", domain_type="", score=0.0,
                 defect_probability=0.0, heatmap_url=""):
        self.id = None
        self.timestamp = datetime.now()
        self.image_path = image_path
        self.domain_type = domain_type
        self.score = score
        self.defect_probability = defect_probability
        self.heatmap_url = heatmap_url


class AgentMemory:
    __tablename__ = "agent_memory"
    timestamp  = _DescProxy()
    id         = _DescProxy()

    def __init__(self, session_id="default", role="agent", content=""):
        self.id = None
        self.session_id = session_id
        self.role = role
        self.content = content
        self.timestamp = datetime.now()


class LearningState:
    __tablename__ = "learning_state"
    timestamp  = _DescProxy()
    id         = _DescProxy()

    def __init__(self):
        self.id = None
        self.last_analysis_id = 0
        self.last_memory_id = 0
        self.updated_at = datetime.now()



# ─── 테이블 초기화 ─────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            image_path TEXT NOT NULL,
            domain_type TEXT NOT NULL,
            score REAL NOT NULL,
            defect_probability REAL NOT NULL,
            heatmap_url TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT 'default',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_analysis_id INTEGER DEFAULT 0,
            last_memory_id INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] SQLite 테이블 초기화 완료 (sqlalchemy-free shim)")
