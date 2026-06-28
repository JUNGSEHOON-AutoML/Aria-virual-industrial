###############################################################################
# Dockerfile — ARIA (Anomaly Reasoning Intelligence Agent)
#
# backend 서비스와 ml_worker 서비스가 동일한 이미지를 공유합니다.
# 실행 시 ENTRYPOINT를 docker-compose.yml에서 오버라이드하여 역할을 구분합니다.
#
#   backend  → uvicorn app:app (REST API + WebSocket + 대시보드)
#   ml_worker → python -m agents.ml_worker (이미지 분석 워커, 필요 시 활성화)
###############################################################################

# ── 1단계: Python 런타임 ──────────────────────────────────────────────────
FROM python:3.10-slim-bullseye AS base

# 시스템 의존성 설치 (OpenCV, PyTorch CPU/GPU 공통)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 2단계: Python 패키지 설치 ─────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── 3단계: 소스 복사 ──────────────────────────────────────────────────────
# 대용량 바이너리(models, datasets, npy)는 볼륨으로 마운트되므로 제외
COPY . .

# ── 4단계: 경량화 (불필요 파일 제거) ─────────────────────────────────────
RUN rm -rf \
        .git \
        __pycache__ \
        _deprecated \
        "*.npy" \
    && find . -name "*.pyc" -delete

# ── 5단계: 기본 환경 변수 (docker-compose에서 오버라이드 가능) ─────────────
# 모델/데이터 경로는 볼륨 마운트로 /app/... 로 주입됩니다.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_BASE_PATH=/app/models \
    DATASET_BASE_PATH=/app/datasets \
    CHECKPOINT_BASE_PATH=/app/checkpoints \
    MEMORY_BANK_PATH=/app/memory_bank.npy \
    CMDIAD_DIR=/app \
    OUTPUT_DIR=/app/outputs

# 결과 이미지 출력 디렉토리 생성
RUN mkdir -p /app/outputs /app/uploads

EXPOSE 8080

# 기본 실행: backend (docker-compose에서 ml_worker는 command를 오버라이드)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
