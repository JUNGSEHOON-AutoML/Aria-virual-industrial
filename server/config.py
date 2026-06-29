"""서버 설정 — 경로·포트·CORS. 8080 탈피 → API :8200, 프론트 dev :5173."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent     # 레포 루트
API_HOST = "0.0.0.0"
API_PORT = 8200

DATA_ROOT = ROOT / "data"
BANKS_DIR = ROOT / "banks"
MODELS_DIR = ROOT / "models"
UPLOAD_DIR = ROOT / "uploads"
OUTPUT_DIR = ROOT / "outputs"
DIST_DIR = ROOT / "frontend" / "dist"

IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp")

# 프론트 dev 서버(Vite :5173)에서의 CORS 허용
CORS_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8200", "http://127.0.0.1:8200",
]

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
