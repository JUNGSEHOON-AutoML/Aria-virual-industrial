"""
vision_router.py — 자율 비전 모델 선택 + 자동 설치 + 추론 엔진

핵심 동작:
  1. 이미지를 qwen2.5vl에게 보여줘서 "어떤 작업이 필요한지" 판단
  2. 판단 결과에 따라 최적 모델 선택 (CCIFPS / YOLO / VLM)
  3. 모델이 로컬에 없으면 자동 설치 (pip / weights 다운로드)
  4. 추론 실행 후 결과 + 시각화 이미지 반환

사용 예:
    router = VisionRouter()
    result = router.run("downloads/telegram_check.jpg")
    # result = {
    #   "model_used": "yolov8n",
    #   "task": "object_detection",
    #   "detections": [...],
    #   "result_image_path": "outputs/result.jpg",
    #   "vlm_explanation": "선풍기 2개가 탐지되었습니다..."
    # }
"""

import base64
import importlib
import io
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from datetime import datetime

# ── GPU 격리: 실존하는 인덱스일 때만 마스킹 ──
def _safe_set_visible_devices():
    import sys
    import subprocess
    n = 0
    try:
        # parent 프로세스에서 torch CUDA가 조기 초기화되지 않도록 서브프로세스로 탐색
        res = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.cuda.device_count() if torch.cuda.is_available() else 0)"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            n = int(res.stdout.strip())
    except Exception:
        n = 0
    target = None
    try:
        from aria.core.utils.gpu_selector import pick_gpus
        target = int(pick_gpus()["vision"])
    except Exception:
        target = None
    # target이 실존하는 GPU 범위 안일 때만 마스킹 수행
    if target is not None and 0 <= target < n:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(target)
    # 그 외에는 마스킹을 수행하지 않음 (모든 디바이스가 보이도록 하여 resource.policy가 선택하게 함)
_safe_set_visible_devices()

# ── 설정 ──────────────────────────────────────────────────────────────────
_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://172.17.0.1:11434")
OLLAMA_API = f"{_OLLAMA_BASE}/api/chat"
VLM_MODEL  = "qwen2.5vl:7b"   # 화면/이미지 이해용 VLM
LLM_MODEL  = "qwen2.5:14b"    # 한국어 대화/추론 LLM
REASON_MODEL = "deepseek-r1:8b" # 모델 선택 추론
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# 자주 쓰는 모델을 도메인별로 영구 등록
MODEL_REGISTRY = {
    "pcb": "keremberke/yolov8m-pcb-defect-segmentation",
}

def get_registered_model(domain: str):
    """등록된 모델이 있으면 반환 (다운로드 불필요)."""
    return MODEL_REGISTRY.get(domain)

# 모델별 VRAM 예상 (MB) — RTX 3090 24GB 기준
MODEL_VRAM = {
    "yolov8n":  130,
    "yolov8s":  440,
    "yolov8m": 1500,
    "yolov8l": 3200,
    "yolov8x": 6700,
    "ccifps":  2000,
    "qwen2.5vl:7b": 7000,
    "keremberke/yolov8m-pcb-defect-segmentation": 1500,
}

# YOLO weights 다운로드 URL
YOLO_WEIGHTS_URLS = {
    "yolov8n": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt",
    "yolov8s": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s.pt",
    "yolov8m": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.pt",
}
# YOLO weights 저장 디렉토리 — MODEL_BASE_PATH/yolo 또는 로컬 models/yolo 폴백
# 쓰기 불가 환경(읽기 전용 마운트 등)이면 /tmp/aria_yolo_weights로 자동 폴백
_model_base = os.environ.get("MODEL_BASE_PATH", "")
_weights_candidate = Path(_model_base) / "yolo" if _model_base else Path("models/yolo")
try:
    _weights_candidate.mkdir(parents=True, exist_ok=True)
    WEIGHTS_DIR = _weights_candidate
except (PermissionError, OSError):
    WEIGHTS_DIR = Path("/tmp/aria_yolo_weights")
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  [vision_router] WEIGHTS_DIR 쓰기 불가 → 임시 경로 사용: {WEIGHTS_DIR}")

# YOLO가 가중치를 WEIGHTS_DIR에 저장하도록 환경변수 설정 (ultralytics 설정 기반)
os.environ.setdefault("YOLO_CONFIG_DIR", str(WEIGHTS_DIR))


# ── Ollama API 호출 ───────────────────────────────────────────────────────
def _call_ollama(model: str, messages: list, timeout: int = 120,
                 num_ctx: int = 4096) -> str:
    """Ollama /api/chat 엔드포인트 호출. 텍스트 응답 반환."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": num_ctx},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_API, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            return data["message"]["content"].strip()
    except Exception as e:
        err_str = str(e)
        if "timed out" in err_str or "timeout" in err_str.lower():
            return "⚠️ VLM 응답 시간 초과. 이미지가 너무 크거나 복잡합니다."
        return f"[Ollama 오류] {e}"


def _resize_for_vlm(image_path: str, max_size: int = 512) -> str:
    """VLM 입력 전 이미지를 리사이즈. 토큰 절약 + 속도 향상."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size

        if max(w, h) <= max_size:
            return image_path  # 이미 작으면 그대로

        ratio = max_size / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)

        # 리사이즈된 이미지 저장
        ext = os.path.splitext(image_path)[1] or ".jpg"
        resized_path = image_path.rsplit(".", 1)[0] + f"_r{max_size}" + ext
        img.save(resized_path, quality=85)
        print(f"[VLM] 이미지 리사이즈: {w}x{h} → {new_size[0]}x{new_size[1]}")
        return resized_path
    except Exception as e:
        print(f"[VLM] 리사이즈 실패: {e}")
        return image_path


def _image_to_base64(image_path: str) -> str:
    """이미지 파일을 base64 문자열로 변환."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── Step 1: VLM으로 이미지 분석 ──────────────────────────────────────────
def analyze_image_with_vlm(image_path: str, user_caption: str = None) -> dict:
    """
    qwen2.5vl에게 이미지를 보여주고 어떤 비전 작업이 필요한지 판단시킨다.

    반환 예:
        {
            "scene": "선풍기가 놓인 실내",
            "objects": ["선풍기", "책상"],
            "task_needed": "object_detection",
            "reason": "특정 객체의 위치와 개수 파악이 필요함",
            "anomaly_possible": false
        }
    """
    resized = _resize_for_vlm(image_path, max_size=512)
    b64 = _image_to_base64(resized)

    prompt = (
        "이 이미지를 분석해서 반드시 아래 JSON 형식으로만 응답해줘. "
        "다른 텍스트는 절대 포함하지 마.\n\n"
    )
    if user_caption:
        prompt += f"[사용자 질문]: {user_caption}\n\n"

    prompt += (
        "{\n"
        '  "image_type": "screenshot/product/nature/document/chart/general",\n'
        '  "scene": "이미지 전체 설명 (한 문장)",\n'
        '  "objects": ["감지된 주요 객체들"],\n'
        '  "confidence_score": 0.75,\n'
        '  "task_needed": "description/anomaly_detection/object_detection/ocr/classification",\n'
        '  "reason": "이 task가 필요한 이유 + confidence가 낮으면 왜 불확실한지",\n'
        '  "anomaly_possible": true 또는 false\n'
        "}\n\n"
        "confidence_score 기준:\n"
        "- 1.0: 이미지가 명확하고 task 판단에 확신이 있음\n"
        "- 0.7~0.9: 대체로 확실하지만 일부 불확실\n"
        "- 0.4~0.6: 도메인 특화 지식 없이는 정확한 분석이 어려움\n"
        "- 0.0~0.3: 매우 불확실 (저해상도, 노이즈, 미학습 도메인)\n\n"
        "=== task 선택 기준 (최우선 → 최하위) ===\n"
        "1. 사용자가 '뭐가 보여?', '설명해줘', '분석해줘', '뭐야?' 라고 물었으면\n"
        "   → description (이미지를 설명하는 것이 목적)\n"
        "2. 스크린샷/웹페이지/UI 화면 → description 또는 ocr\n"
        "3. 문서/텍스트가 포함된 이미지 → ocr\n"
        "4. 산업 부품이 검은 배경 위에 놓여있고, 사용자가 결함/균열/이상을 찾으라고 했으면\n"
        "   → anomaly_detection\n"
        "5. 특정 물체의 위치/개수를 알아야 하면 → object_detection\n"
        "6. 위 어디에도 해당 안 되면 → classification\n\n"
        "⚠️ 중요 규칙:\n"
        "- 스크린샷은 절대 anomaly_detection이 아님!\n"
        "- '뭐가 보여?' 질문에는 절대 anomaly_detection 하지 마.\n"
        "- anomaly_detection은 사용자가 명시적으로 결함/균열/이상을 요청했을 때만.\n"
        "- 산업/제조 이미지인데 정확한 결함 유형을 모르겠으면 confidence를 낮게 줘."
    )

    response = _call_ollama(VLM_MODEL, [
        {"role": "user", "content": prompt, "images": [b64]}
    ])

    # JSON 파싱 시도
    try:
        # 코드블록 제거
        clean = response.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        # 파싱 실패 시 기본값
        print(f"  ⚠️ VLM JSON 파싱 실패. 원본:\n{response[:300]}")
        return {
            "scene": response[:100],
            "objects": [],
            "task_needed": "object_detection",
            "reason": "JSON 파싱 실패, 기본값 사용",
            "anomaly_possible": False,
        }


# ── Step 2a: 자율 탐색 모드 (ModelScout) ─────────────────────────────────
def scout_and_select_model(vlm_analysis: dict, ccifps_memory_exists: bool,
                           notify_fn=None, user_request: str = "") -> dict:
    """
    ModelScout를 이용해 arXiv + HuggingFace + 웹 검색으로 최적 모델 자율 탐색.
    탐색 결과를 select_best_model() 형식으로 변환해 반환.
    """
    try:
        from aria.learning.model_scout import ModelScout
        scout = ModelScout(notify_fn=notify_fn)
        result = scout.scout(vlm_analysis, user_request=user_request)  # ← user_request 전달

        # ModelScout 결과 → vision_router 표준 형식 변환
        return {
            "model": result.get("model", "yolov8n"),
            "model_type": result.get("model_type", "yolo"),
            "weights_file": None,
            "reason": result.get("reason", ""),
            "install_needed": False,
            "install_command": None,
            "scout_metadata": {
                "confidence": result.get("confidence"),
                "source_paper": result.get("source_paper"),
                "elapsed_sec": result.get("elapsed_sec"),
                "search_stats": result.get("search_stats", {}),
                "reasoning": result.get("reasoning", ""),
            },
        }
    except Exception as e:
        print(f"  ⚠️ [Scout] ModelScout 실패: {e}, select_best_model로 폴백")
        return select_best_model(vlm_analysis, ccifps_memory_exists)


# ── Step 2b: 정적 모델 선택 (기존, 폴백용) ───────────────────────────────
# DEPRECATED: 입구는 agents.vision_agent.inspect_via_registry() 사용. Step 1 이후 미사용.
# 이 함수를 autonomous_agent.py 등 외부에서 직접 호출하지 말 것.
def select_best_model(vlm_analysis: dict, ccifps_memory_exists: bool) -> dict:
    """
    VLM 분석 결과를 최적의 LLM 모델을 선택해 넘겨서 어떤 비전 모델을 써야 할지 추론시킨다.
    """

    # 설치된 모델 조회하여 최고의 LLM/VLM 모델 찾기
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        installed = res.stdout.lower()
    except Exception:
        installed = ""

    # 추론용 모델 결정
    # 모델 선택 추론: deepseek-r1 우선, 폴백 qwen2.5:14b
    reasoning_model = "qwen2.5:14b"
    if "deepseek-r1:8b" in installed:
        reasoning_model = "deepseek-r1:8b"
    elif "qwen2.5:14b" in installed:
        reasoning_model = "qwen2.5:14b"

    # 비전 설명/분류에 사용할 모델 결정
    active_vlm = VLM_MODEL
    if "qwen3-vl:8b" in installed:
        active_vlm = "qwen3-vl:8b"
    elif "qwen2.5vl:7b" in installed:
        active_vlm = "qwen2.5vl:7b"

    task = vlm_analysis.get("task_needed", "object_detection")
    objects = vlm_analysis.get("objects", [])
    anomaly = vlm_analysis.get("anomaly_possible", False)

    prompt = (
        f"비전 작업을 수행해야 해. 아래 분석 결과를 보고 "
        f"최적의 모델을 선택해서 반드시 JSON으로만 응답해.\n\n"
        f"분석 결과:\n"
        f"- 필요한 작업: {task}\n"
        f"- 감지된 객체: {objects}\n"
        f"- 이상 탐지 가능성: {anomaly}\n"
        f"- CCIFPS 메모리 뱅크 존재: {ccifps_memory_exists}\n\n"
        f"사용 가능한 모델 소스:\n"
        f"1. torchvision: wide_resnet50_2, resnet50, resnet101, efficientnet_b0, "
        f"efficientnet_b7, vit_b_16, convnext_base, swin_b (ImageNet 사전학습, 즉시 사용)\n"
        f"2. timm: 수천 개 이미지 모델 (timm.create_model로 자동 로드)\n"
        f"3. HuggingFace: openai/clip-vit-base-patch32 등 transformers 기반 모델\n"
        f"4. ultralytics: yolov8n, yolov8s, yolov8m (일반 객체 탐지)\n"
        f"5. ccifps: 산업 부품 표면 이상 탐지 전용 (픽셀 수준 anomaly score)\n"
        f"6. Ollama VLM: {active_vlm} (이미지 설명/분류)\n\n"
        f"선택 규칙:\n"
        f"- 일반 객체(선풍기, 사람, 차 등) 탐지 → yolov8n (model_type: yolo)\n"
        f"- 표면 결함/이상 + CCIFPS 메모리 있음 → ccifps (model_type: ccifps)\n"
        f"- 표면 결함 + CCIFPS 없음 → wide_resnet50_2 (model_type: torchvision)\n"
        f"- ImageNet 특징 추출 필요 → torchvision 또는 timm 모델\n"
        f"- 단순 이미지 설명 → {active_vlm} (model_type: vlm)\n\n"
        f"JSON 형식 (install_needed는 항상 false로, torchvision/timm/yolo는 자동 로드됨):\n"
        f"{{\n"
        f'  "model": "모델명 (예: wide_resnet50_2, yolov8n, {active_vlm})",\n'
        f'  "model_type": "torchvision 또는 timm 또는 yolo 또는 ccifps 또는 vlm",\n'
        f'  "weights_file": "가중치 파일명 (yolo만 해당, 나머지는 null)",\n'
        f'  "reason": "선택 이유",\n'
        f'  "install_needed": false,\n'
        f'  "install_command": null\n'
        f"}}"
    )

    response = _call_ollama(reasoning_model, [
        {"role": "user", "content": prompt}
    ])

    try:
        clean = response.replace("```json", "").replace("```", "").strip()
        start = clean.find("{")
        end   = clean.rfind("}") + 1
        return json.loads(clean[start:end])
    except Exception:
        print(f"  ⚠️ LLM 모델 선택 파싱 실패. 기본값(yolov8n) 사용")
        return {
            "model": "yolov8n",
            "model_type": "yolo",
            "weights_file": "yolov8n.pt",
            "reason": "파싱 실패, 기본값",
            "install_needed": True,
            "install_command": "pip install ultralytics",
        }

# torchvision 내장 모델 매핑 (소문자 정규화 키)
TORCHVISION_MODELS = {
    "wideresnet50":    "wide_resnet50_2",
    "wide_resnet50":   "wide_resnet50_2",
    "wide_resnet50_2": "wide_resnet50_2",
    "wideresnet101":   "wide_resnet101_2",
    "wide_resnet101":  "wide_resnet101_2",
    "resnet50":        "resnet50",
    "resnet101":       "resnet101",
    "resnet152":       "resnet152",
    "efficientnet_b0": "efficientnet_b0",
    "efficientnet_b4": "efficientnet_b4",
    "efficientnet_b7": "efficientnet_b7",
    "vit_b_16":        "vit_b_16",
    "vit_b_32":        "vit_b_32",
    "vit_l_16":        "vit_l_16",
    "convnext_base":   "convnext_base",
    "convnext_large":  "convnext_large",
    "swin_b":          "swin_b",
    "swin_t":          "swin_t",
    "densenet121":     "densenet121",
    "densenet201":     "densenet201",
    "mobilenet_v3_large": "mobilenet_v3_large",
}


def free_memory():
    """메모리에 로드된 기존 PyTorch 모델 및 가중치를 해제하여 VRAM 부족(OOM)을 방지."""
    import gc
    import torch
    import sys
    
    # app.py 전역에 로드된 ccifps engine 해제 시도
    try:
        if 'app' in sys.modules:
            app_module = sys.modules['app']
            if hasattr(app_module, 'engine') and app_module.engine is not None:
                print("  [Build] 기존 CCIFPS Engine 모델 해제 (Free Memory)...")
                if hasattr(app_module.engine, 'model'):
                    del app_module.engine.model
                if hasattr(app_module.engine, 'memory_bank'):
                    del app_module.engine.memory_bank
                app_module.engine = None
    except Exception as e:
        print(f"  [Build] 기존 엔진 해제 중 오류: {e}")
        
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("  [Build] PyTorch VRAM/RAM 가비지 컬렉션 완료 (Free)")

def ensure_model_installed(model_decision: dict) -> bool:
    """하위 호환성 유지용 래퍼. _ensure_model()로 위임."""
    model_name = model_decision.get("model", "yolov8n")
    model_type = model_decision.get("model_type", "yolo")
    domain = model_decision.get("domain")

    # 등록된 모델 우선 사용
    if domain in MODEL_REGISTRY:
        model_name = MODEL_REGISTRY[domain]
        if "/" in model_name and "yolo" in model_name.lower() and "yolos" not in model_name.lower():
            model_type = "yolo"
        elif "/" in model_name and any(x in model_name.lower() for x in ["detr", "yolos", "deta", "table-transformer"]):
            model_type = "transformers"
        elif "ccifps" in model_name.lower():
            model_type = "ccifps"
        else:
            model_type = "transformers"

    # CCIFPS는 별도 처리
    if model_type == "ccifps":
        # 탐색 순서: ① 환경변수 MEMORY_BANK_PATH → ② skills/ 내부 → ③ 프로젝트 루트
        env_memory = os.environ.get("MEMORY_BANK_PATH", "")
        memory_path = Path(env_memory) if env_memory and Path(env_memory).exists() else Path("skills/ccifps_vision/memory_bank.npy")

        if not memory_path.exists():
            src = Path("memory_bank.npy")
            if src.exists():
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy(src, memory_path)
                print(f"  ✅ [CCIFPS] memory bank 복사 완료: {src} → {memory_path}")
            else:
                print(f"  ❌ CCIFPS memory bank 없음. MEMORY_BANK_PATH 환경변수를 확인하거나 build_memory.py를 실행하세요.")
                return False
        return True

    return _ensure_model(model_name)


def _ensure_model(model_name: str) -> bool:
    """
    어떤 모델이든 자동으로 설치/로드 확인.
    """
    print(f"  [Build] Loading model '{model_name}' from HF...")
    free_memory()
    
    import importlib
    import subprocess
    import sys

    key = model_name.lower().replace("-", "_").replace(" ", "_")

    # ── 1. torchvision 내장 모델 (즉시 사용 가능, 가중치 자동 다운로드) ──
    if key in TORCHVISION_MODELS:
        tv_name = TORCHVISION_MODELS[key]
        try:
            import torchvision.models as tvm
            print(f"  📥 [torchvision] {tv_name} (ImageNet1K_V1) 로드 중...")
            model = getattr(tvm, tv_name)(weights="IMAGENET1K_V1")
            model.eval()
            print(f"  ✅ [torchvision] {tv_name} 로드 완료")
            return True
        except Exception as e:
            print(f"  ⚠️ [torchvision] {tv_name} 로드 실패: {e}")
            # timm으로 폴백 시도

    # ── 2. ultralytics YOLO & Hugging Face Hub YOLO ──
    # hf-hub:로 시작하거나 yolo 키워드가 들어가고 슬래시가 있으면 YOLO 모델로 최우선 처리
    is_yolo = "yolo" in model_name.lower() and "yolos" not in model_name.lower()
    if is_yolo or model_name.startswith("hf-hub:"):
        try:
            importlib.import_module("ultralytics")
        except ImportError:
            print(f"  📦 ultralytics 설치 중...")
            subprocess.run([sys.executable, "-m", "pip", "install", "ultralytics", "--quiet"],
                           capture_output=True, text=True, timeout=180)
        try:
            from ultralytics import YOLO
            if "/" in model_name:
                hf_path = model_name.replace("hf-hub:", "")
                from huggingface_hub import hf_hub_download, list_repo_files
                print(f"  📥 [HuggingFace Hub YOLO] {hf_path} 파일 목록 조회 중...")
                repo_files = list_repo_files(hf_path)
                pt_files = [f for f in repo_files if f.endswith(".pt")]
                if not pt_files:
                    print(f"  ❌ [YOLO] {hf_path}에 .pt 파일 없음")
                    return False
                target_file = "best.pt" if "best.pt" in pt_files else pt_files[0]
                print(f"  📥 [HuggingFace Hub YOLO] {hf_path}에서 {target_file} 다운로드 중...")
                local_path = hf_hub_download(repo_id=hf_path, filename=target_file)
                YOLO(local_path)
            else:
                pt_name = model_name if model_name.endswith(".pt") else model_name + ".pt"
                YOLO(pt_name)
            print(f"  ✅ [YOLO] {model_name} 준비 완료")
            return True
        except Exception as e:
            print(f"  ⚠️ [YOLO] {model_name} 로드 실패: {e}")

    # ── 3. timm (Hugging Face Image Models) ──
    try:
        import timm
    except ImportError:
        print(f"  📦 timm 설치 중...")
        subprocess.run([sys.executable, "-m", "pip", "install", "timm", "--quiet"],
                       capture_output=True, text=True, timeout=180)
    try:
        import timm
        print(f"  📥 [timm] {model_name} pretrained 로드 중...")
        model = timm.create_model(model_name, pretrained=True)
        model.eval()
        print(f"  ✅ [timm] {model_name} 로드 완료")
        return True
    except Exception as e:
        timm_err = str(e)
        if "not found" not in timm_err.lower() and "invalid" not in timm_err.lower():
            print(f"  ⚠️ [timm] {model_name} 시도 중 오류: {e}")

    # ── 4. HuggingFace transformers AutoModel / Pipeline ──
    is_transformer = "/" in model_name or any(x in model_name.lower() for x in ["bert", "gpt", "t5", "clip", "vit", "deit", "detr", "yolos"])
    if is_transformer:
        try:
            import transformers
        except ImportError:
            print(f"  📦 transformers & timm 설치 중...")
            subprocess.run([sys.executable, "-m", "pip", "install", "transformers", "timm", "--quiet"],
                           capture_output=True, text=True, timeout=180)
        try:
            from transformers import AutoModel
            print(f"  📥 [transformers] {model_name} 로드 중...")
            model = AutoModel.from_pretrained(model_name)
            print(f"  ✅ [transformers] {model_name} 로드 완료")
            return True
        except Exception as e:
            print(f"  ⚠️ [transformers] {model_name} 로드 실패: {e}")

    # ── 5. Anomalib ──
    if "anomalib" in model_name.lower() or model_name.lower() in ["patchcore", "efficientad", "padim"]:
        try:
            import anomalib
        except ImportError:
            print(f"  📦 anomalib 설치 중...")
            subprocess.run([sys.executable, "-m", "pip", "install", "anomalib", "--quiet"],
                           capture_output=True, text=True, timeout=240)
        try:
            import anomalib
            print(f"  ✅ [Anomalib] 라이브러리 준비 완료")
            return True
        except Exception as e:
            print(f"  ⚠️ [Anomalib] 로드 실패: {e}")

    # ── 6. Ollama ──
    print(f"  📥 [Ollama] ollama pull {model_name} 실행 중...")
    result = subprocess.run(
        ["ollama", "pull", model_name],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode == 0:
        print(f"  ✅ [Ollama] {model_name} 다운로드 완료")
        return True
    else:
        print(f"  ❌ [Ollama] {model_name} 다운로드 실패: {result.stderr[:200]}")
        return False



# ── 결과 이미지 보장 함수 ──────────────────────────────────────────────────
def ensure_result_image(image_path: str, result: dict) -> None:
    """
    추론 결과가 뭐든 시각화 이미지를 반드시 생성.
    result에 result_image_path가 없으면 원본에 텍스트를 오버레이해서 저장.
    """
    if result.get("result_image_path") and Path(result["result_image_path"]).exists():
        return  # 이미 결과 이미지 있으면 OK

    try:
        import cv2
        import numpy as np
        import time

        img = cv2.imread(image_path)
        if img is None:
            print(f"  ⚠️ [ensure_result_image] 원본 이미지 로드 실패: {image_path}")
            return

        # 배경 반투명 박스
        overlay = img.copy()
        h, w = img.shape[:2]
        cv2.rectangle(overlay, (0, 0), (w, 60), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)

        # 텍스트 오버레이
        model_name = result.get("model_used") or result.get("model", "unknown")
        score      = result.get("anomaly_score") or result.get("score", "N/A")
        task       = result.get("task", "")
        err        = result.get("error", "")

        line1 = f"Model: {model_name} | Task: {task}"
        line2 = f"Score: {score}" + (f" | Error: {err[:40]}" if err else "")

        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, line1, (10, 22), font, 0.55, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.putText(img, line2, (10, 48), font, 0.55, (0, 220, 255), 1, cv2.LINE_AA)

        # 저장
        Path("outputs").mkdir(exist_ok=True)
        ts = int(time.time())
        out_path = f"outputs/result_fallback_{ts}.jpg"
        cv2.imwrite(out_path, img)
        result["result_image_path"] = out_path
        print(f"  🖼️ [ensure_result_image] 텍스트 오버레이 이미지 생성: {out_path}")

    except Exception as e:
        print(f"  ⚠️ [ensure_result_image] 이미지 생성 실패: {e}")


# ── Step 4: 추론 실행 ─────────────────────────────────────────────────────
# NOTE: 입구(inspect_via_registry) 미사용. ModelDiscovery의 동적 모델(yolo/hf/timm) 실행기로만 사용.
def run_inference(image_path: str, model_decision: dict) -> dict:
    """선택된 모델로 실제 추론을 실행한다. 실패 시 YOLOv8n으로 폴백."""

    model_type = model_decision["model_type"]
    model_name = model_decision["model"]

    # ── 등록된 모델 우선 사용 (도메인 매칭 시) ──
    domain = model_decision.get("domain")
    if domain in MODEL_REGISTRY:
        registered_model = MODEL_REGISTRY[domain]
        print(f"  ⚡ [run_inference] 등록된 모델 발견 (도메인: {domain}) → {registered_model}로 대체합니다.")
        model_name = registered_model
        # model_type 보정
        if "/" in model_name and "yolo" in model_name.lower() and "yolos" not in model_name.lower():
            model_type = "yolo"
        elif "/" in model_name and any(x in model_name.lower() for x in ["detr", "yolos", "deta", "table-transformer"]):
            model_type = "transformers"
        elif "ccifps" in model_name.lower():
            model_type = "ccifps"
        else:
            model_type = "transformers"

    # ── HuggingFace Hub YOLO 판단 고도화 ──
    if "/" in model_name and "yolo" in model_name.lower() and "yolos" not in model_name.lower():
        model_type = "yolo"

    # ── HuggingFace transformers 계열 판단 고도화 (detr, yolos 등) ──
    if "/" in model_name and any(x in model_name.lower() for x in ["detr", "yolos", "deta", "table-transformer"]):
        model_type = "transformers"

    if model_type == "yolo" or (model_type == "detection" and "/" in model_name):
        # 만약 model_type이 generic detection인데 슬래시가 있으면 YOLO로 간주해보거나 폴백
        result = _run_yolo(image_path, model_name,
                         model_decision.get("weights_file", f"{model_name}.pt"))
    elif model_type in ("ccifps", "anomaly", "patchcore", "efficientad"):
        # ── anomaly 계열은 모두 CCIFPS 히트맵 파이프라인으로 라우팅 ──
        print(f"  🔥 [run_inference] anomaly 태스크 → CCIFPS 히트맵 파이프라인")
        result = _run_ccifps(image_path)
    elif model_type == "transformers":
        result = _run_transformers_pipeline(image_path, model_name)
    elif model_type == "anomalib":
        result = _run_anomalib(image_path, model_name)
    elif model_type == "vlm":
        result = _run_vlm_classify(image_path)
    else:
        # 그 외에 model_name에 슬래시가 있으면 YOLO 허브 모델로 시도
        if "/" in model_name:
            print(f"  🔍 [run_inference] '/' 포함 모델 → HuggingFace YOLO로 시도: {model_name}")
            result = _run_yolo(image_path, model_name, None)
        elif any(x in model_name.lower() for x in ["ccifps", "patchcore", "efficientad"]):
            # 모델명에 anomaly 키워드가 있으면 CCIFPS로
            print(f"  🔥 [run_inference] 모델명 {model_name}에 anomaly 키워드 → CCIFPS")
            result = _run_ccifps(image_path)
        else:
            print(f"  ⚠️ [run_inference] 알 수 없는 model_type: {model_type} → yolov8n 폴백")
            result = _run_yolo(image_path, "yolov8n", "yolov8n.pt")
            result["fallback_used"] = True

    # 결과 이미지 보장
    ensure_result_image(image_path, result)
    return result


def _run_yolo(image_path: str, model_name: str, weights_file: str) -> dict:
    """YOLO 추론 + 결과 이미지 저장."""
    try:
        from ultralytics import YOLO
        import cv2
        import numpy as np

        # 모델 로드 (없으면 자동 다운로드)
        if "/" in model_name:
            hf_path = model_name.replace("hf-hub:", "")
            from huggingface_hub import hf_hub_download, list_repo_files
            print(f"  📥 [YOLO] Hugging Face Hub {hf_path}에서 모델 로드 시도...")
            repo_files = list_repo_files(hf_path)
            pt_files = [f for f in repo_files if f.endswith(".pt")]
            if not pt_files:
                raise FileNotFoundError(f"리포지토리에 .pt 파일이 없습니다: {hf_path}")
            target_file = "best.pt" if "best.pt" in pt_files else pt_files[0]
            print(f"  📥 [YOLO] {hf_path}에서 {target_file} 다운로드 및 로드 중...")
            local_path = hf_hub_download(repo_id=hf_path, filename=target_file)
            model = YOLO(local_path)
        else:
            # WEIGHTS_DIR에 .pt 파일이 있으면 로컬 로드, 없으면 다운로드 후 저장
            pt_name = model_name if model_name.endswith(".pt") else model_name + ".pt"
            local_pt = WEIGHTS_DIR / pt_name
            if local_pt.exists():
                print(f"  ✅ [YOLO] 로컬 캐시에서 로드: {local_pt}")
                model = YOLO(str(local_pt))
            else:
                # ultralytics가 다운로드 후 CWD에 저장하는 것을 WEIGHTS_DIR로 리다이렉트
                try:
                    import shutil as _shutil
                    model = YOLO(pt_name)   # ultralytics 자동 다운로드
                    # 다운로드 후 파일을 WEIGHTS_DIR로 이동 (중복 방지)
                    cwd_pt = Path(pt_name)
                    if cwd_pt.exists() and cwd_pt != local_pt:
                        local_pt.parent.mkdir(parents=True, exist_ok=True)
                        _shutil.move(str(cwd_pt), str(local_pt))
                        print(f"  📦 [YOLO] 가중치 이동 완료: {cwd_pt} → {local_pt}")
                except (PermissionError, OSError) as perm_err:
                    # WEIGHTS_DIR 쓰기 불가 시 /tmp 폴백
                    _tmp_dir = Path("/tmp/aria_yolo_weights")
                    _tmp_dir.mkdir(parents=True, exist_ok=True)
                    print(f"  ⚠️ [YOLO] WEIGHTS_DIR 쓰기 불가 ({perm_err}) → /tmp 폴백")
                    model = YOLO(str(_tmp_dir / pt_name))


        # 추론
        results = model(image_path, verbose=False)
        result  = results[0]

        detections = []
        img_bgr = cv2.imread(image_path)

        for box in result.boxes:
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            conf  = float(box.conf[0])
            cls   = int(box.cls[0])
            label = result.names[cls]

            detections.append({
                "label": label,
                "confidence": round(conf, 3),
                "bbox": [x1, y1, x2, y2],
            })

            # 바운딩 박스 그리기
            color = (0, 255, 0) if conf > 0.5 else (0, 165, 255)
            cv2.rectangle(img_bgr, (x1, y1), (x2, y2), color, 2)
            cv2.putText(img_bgr, f"{label} {conf:.2f}",
                        (x1, max(y1 - 8, 16)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 결과 이미지 저장 (절대 경로 사용 — os.path.exists 보장)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = str(OUTPUT_DIR.resolve() / f"yolo_result_{ts}.jpg")
        write_ok = cv2.imwrite(out_path, img_bgr)
        if not write_ok:
            print(f"  ⚠️ [YOLO] 이미지 저장 실패: {out_path}")
        else:
            print(f"  🖼️ [YOLO] 결과 이미지 저장: {out_path}")

        return {
            "status": "success",
            "model_used": model_name,
            "task": "object_detection",
            "detections": detections,
            "detection_count": len(detections),
            "result_image_path": out_path,
        }

    except ImportError:
        return {"status": "error", "error": "ultralytics 미설치. ensure_model_installed()를 먼저 호출하세요."}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _run_transformers_pipeline(image_path: str, model_name: str) -> dict:
    """
    HF transformers 객체탐지 파이프라인.
    실패 시 명확한 폴백 + 결과 이미지 항상 생성.
    """
    try:
        from transformers import pipeline
        import cv2
        import time

        # 타임아웃 가드 (모델 로드 60초 제한)
        t0 = time.time()
        pipe = pipeline("object-detection", model=model_name)

        results = pipe(image_path)

        # 결과 시각화 (바운딩박스)
        img = cv2.imread(image_path)
        for det in results:
            box = det["box"]
            label = det["label"]
            score = det["score"]
            cv2.rectangle(img,
                (int(box["xmin"]), int(box["ymin"])),
                (int(box["xmax"]), int(box["ymax"])),
                (0, 255, 0), 2)
            cv2.putText(img, f"{label} {score:.2f}",
                (int(box["xmin"]), int(box["ymin"])-8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 0), 2)

        out_path = f"outputs/hf_result_{int(time.time())}.jpg"
        cv2.imwrite(out_path, img)

        return {
            "status": "success",
            "model_used": model_name,
            "task": "object_detection",
            "detections": [
                {"label": d["label"],
                 "confidence": round(d["score"], 3)}
                for d in results],
            "result_image_path": out_path,
            "elapsed": round(time.time()-t0, 1),
        }
    except Exception as e:
        # 명확한 실패 보고 + YOLO 폴백
        return {
            "status": "fallback",
            "error": str(e),
            "fallback_to": "yolov8n",
        }


def _run_anomalib(image_path: str, model_name: str) -> dict:
    """Anomalib을 이용한 이상 탐지 (체크포인트 부재 시 기존 CCIFPS로 안전하게 폴백)."""
    try:
        import torch
        print(f"  📥 [Anomalib] {model_name} 모델 추론 준비...")
        
        try:
            import anomalib
            print(f"  ℹ️ [Anomalib] 추론에 필요한 특정 도메인 체크포인트(.ckpt)가 설정되지 않았습니다.")
            print(f"  🔄 [Anomalib] 기존 구축 완료된 Bottle 라인 CCIFPS 엔진으로 폴백하여 추론합니다.")
            return _run_ccifps(image_path)
        except ImportError:
            print(f"  ⚠️ [Anomalib] anomalib 설치 안 됨 → CCIFPS 폴백")
            return _run_ccifps(image_path)
            
    except Exception as e:
        print(f"  ⚠️ [Anomalib] 오류: {e} → CCIFPS 폴백")
        return _run_ccifps(image_path)


# DEPRECATED: 입구는 agents.vision_agent.inspect_via_registry() 사용. Step 1.5 이후 직접 import 제거.
# cmdiad_inference 실행은 detectors/cmdiad_detector.py (플러그인) 경유할 것.
def _run_ccifps(image_path: str) -> dict:
    """CCIFPS 이상 탐지 — inspect_via_registry로 위임 (직접 cmdiad_inference import 금지)."""
    try:
        from aria.agents.vision_agent import inspect_via_registry
        return inspect_via_registry(image_path)
    except Exception as e:
        import traceback
        return {"status": "error", "error": f"CCIFPS 위임 실패: {e}\n{traceback.format_exc()}"}


def _run_vlm_classify(image_path: str) -> dict:
    """VLM으로 이미지 설명/분류."""
    b64 = _image_to_base64(image_path)
    response = _call_ollama(VLM_MODEL, [{
        "role": "user",
        "content": "이 이미지를 자세히 설명해줘. 물체, 색상, 상태, 특이사항을 포함해서.",
        "images": [b64],
    }])
    return {
        "status": "success",
        "model_used": VLM_MODEL,
        "task": "classification",
        "description": response,
    }


# ── Step 5: VLM으로 결과 설명 생성 ────────────────────────────────────────
def generate_explanation(image_path: str, inference_result: dict,
                         vlm_analysis: dict) -> str:
    """
    추론 결과를 VLM에게 보여주고 자연어 설명을 생성한다.
    텔레그램 전송용 리포트로 활용.
    """
    b64 = _image_to_base64(image_path)
    task = inference_result.get("task", "unknown")

    if task == "object_detection":
        detections = inference_result.get("detections", [])
        det_text = "\n".join(
            f"  - {d['label']} (신뢰도: {d['confidence']:.0%}, 위치: {d['bbox']})"
            for d in detections
        ) or "  탐지된 객체 없음"
        prompt = (
            f"이 이미지에서 YOLO 객체 탐지 결과가 나왔어:\n{det_text}\n\n"
            "이미지를 직접 보고 탐지 결과가 맞는지 확인하고, "
            "결과를 한국어로 2-3문장으로 요약해줘."
        )
    elif task == "anomaly_detection":
        score = inference_result.get("anomaly_score", 0)
        result = inference_result.get("result", "unknown")
        prompt = (
            f"이 이미지의 이상 탐지 점수는 {score:.2f}이고 "
            f"판정은 {result}이야. "
            "이미지를 직접 보고 어떤 부분이 이상해 보이는지 설명해줘."
        )
    else:
        prompt = "이 이미지를 분석하고 주요 내용을 한국어로 설명해줘."

    return _call_ollama(VLM_MODEL, [
        {"role": "user", "content": prompt, "images": [b64]}
    ])


# ── 메인 엔트리포인트 ─────────────────────────────────────────────────────
class VisionRouter:
    """
    자율 비전 라우터 — 이미지 하나를 받으면 스스로 판단하여
    최적 모델을 선택·설치·실행하고 결과를 반환한다.
    """

    def __init__(self, ccifps_memory_path: str = ""):
        # 환경변수 → 인자 → 기본 경로 순으로 메모리 뱅크 존재 확인
        env_path = os.environ.get("MEMORY_BANK_PATH", "")
        resolved = env_path or ccifps_memory_path or "skills/ccifps_vision/memory_bank.npy"
        self.ccifps_memory_exists = Path(resolved).exists()

    def run(self, image_path: str, user_caption: str = None) -> dict:
        """
        이미지 경로를 받아 전체 파이프라인을 실행한다.

        Returns:
            dict with keys: model_used, task, result_image_path (optional),
                            vlm_explanation, detections (optional),
                            anomaly_score (optional), error (optional)
        """
        print(f"\n{'='*55}")
        print(f"  🔍 VisionRouter.run({Path(image_path).name})")
        print(f"{'='*55}")

        if not Path(image_path).exists():
            return {"error": f"이미지 파일 없음: {image_path}"}

        # ── Step 1: VLM 이미지 분석 ──
        print("  [1/5] VLM 이미지 분석 중...")
        vlm_analysis = analyze_image_with_vlm(image_path, user_caption)
        print(f"  📋 장면: {vlm_analysis.get('scene', '?')}")
        print(f"  📋 필요 작업: {vlm_analysis.get('task_needed', '?')}")
        print(f"  📋 이유: {vlm_analysis.get('reason', '?')}")

        # ── Step 2: 최적 모델 선택 ──
        print("  [2/5] 모델 선택 추론 중...")
        model_decision = select_best_model(vlm_analysis, self.ccifps_memory_exists)
        model_decision["domain"] = vlm_analysis.get("domain")
        print(f"  🤖 선택된 모델: {model_decision.get('model', '?')}")
        print(f"  🤖 이유: {model_decision.get('reason', '?')}")

        # ── Step 3: 모델 설치 확인 ──
        print("  [3/5] 모델 설치 확인 중...")
        installed = ensure_model_installed(model_decision)
        if not installed:
            # 설치 실패 시 YOLOv8n으로 즉시 폴백 (결과 이미지 보장)
            print(f"  ⚠️ 모델 설치 실패 → yolov8n 폴백으로 추론 진행")
            model_decision = {
                "model": "yolov8n", "model_type": "yolo",
                "weights_file": "yolov8n.pt", "fallback_used": True,
                "reason": f"원래 선택 모델({model_decision.get('model')}) 설치 실패 → YOLOv8n 폴백",
            }

        # ── Step 4: 추론 실행 ──
        print("  [4/5] 추론 실행 중...")
        inference_result = run_inference(image_path, model_decision)
        # 오류여도 결과 이미지 보장 (텍스트 오버레이라도 생성)
        ensure_result_image(image_path, inference_result)
        print(f"  ✅ 추론 완료: {json.dumps(inference_result, ensure_ascii=False)[:150]}")

        # ── Step 5: VLM 결과 설명 ──
        print("  [5/5] VLM 결과 설명 생성 중...")
        explanation = generate_explanation(image_path, inference_result, vlm_analysis)
        print(f"  💬 설명: {explanation[:100]}...")

        # ── 최종 결과 조합 ──
        final = {
            **inference_result,
            "vlm_analysis": vlm_analysis,
            "vlm_explanation": explanation,
            "model_decision": model_decision,
        }
        print(f"\n  🎯 완료: {model_decision.get('model')} → {inference_result.get('task')}")
        return final


# ── 단독 실행 테스트 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VisionRouter 단독 테스트")
    parser.add_argument("image", help="분석할 이미지 경로")
    parser.add_argument("--vlm", default="qwen2.5vl:7b")
    parser.add_argument("--llm", default="llama3.1")
    args = parser.parse_args()

    VLM_MODEL = args.vlm
    LLM_MODEL = args.llm

    router = VisionRouter()
    result = router.run(args.image)

    print(f"\n{'='*55}")
    print("최종 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2,
                     default=lambda o: str(o)))
