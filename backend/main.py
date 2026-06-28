"""
backend/main.py — ARIA 백엔드 진입점 (Vercel / uvicorn 호환 래퍼)

이 파일은 루트의 app.py FastAPI 인스턴스를 그대로 재노출합니다.
uvicorn backend.main:app 또는 python backend/main.py 로 실행 가능.

실행 예:
    # 루트 디렉토리에서
    uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
    # 또는
    python backend/main.py
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가 (루트의 app.py, agent_orchestrator.py 등 import 가능)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 루트 app.py의 FastAPI 인스턴스를 그대로 사용
from app import app  # noqa: F401  — re-export

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=[ROOT_DIR],
    )
