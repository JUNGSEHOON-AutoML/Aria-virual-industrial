import os

DATASET_DIR = os.environ.get("DATASET_BASE_PATH", "data/mvtec_ad")

MODELS = {
    # 텍스트 — GPU 0
    "chat":      "qwen2.5:14b",      # 한국어 대화 (9GB)
    "router":    "deepseek-r1:8b",   # 라우팅/추론 (6GB)
    "fast":      "qwen2.5:3b",       # 빠른 응답 (2GB)
    # 비전 — GPU 1
    "vision":    "qwen2.5vl:7b",     # 이미지 이해 (7GB)
    # 산업 이상탐지 — GPU 1
    "anomaly":   "ccifps",           # CMDIAD DINO (2GB)
}

def route_to_model(task_type):
    """작업에 맞는 모델 + GPU 배정."""
    routing = {
        "chat":              (MODELS["chat"], "gpu0"),
        "quick_reply":       (MODELS["fast"],  "gpu0"),
        "model_selection":   (MODELS["router"], "gpu0"),
        "image_description": (MODELS["vision"], "gpu1"),
        "anomaly_detection": (MODELS["anomaly"], "gpu1"),
    }
    return routing.get(task_type, (MODELS["fast"], "gpu0"))
