from __future__ import annotations
"""
model_scout.py — 자율 모델 탐색 에이전트

이미지 VLM 분석 결과를 받아:
  1. 검색 쿼리를 스스로 생성
  2. arXiv + HuggingFace + DuckDuckGo에서 최적 모델 탐색
  3. LLM이 후보 중 최적 모델을 선택 + 이유 설명
  4. _ensure_model()로 자동 다운로드

사용 예:
    scout = ModelScout()
    result = scout.scout(vlm_analysis)
    # result = {
    #   "model": "hf_hub:google/efficientnet-b4",
    #   "model_type": "timm",
    #   "reason": "MVTec AD 벤치마크 SOTA, 표면 결함 탐지에 최적화",
    #   "source": "arxiv:2312.07177",
    #   "ready": True
    # }
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ── Ollama API ──────────────────────────────────────────────────────────────
OLLAMA_API = "http://localhost:11434/api/chat"

# ── 태스크-모델 타입 매핑 (잘못된 모델 선택 강제 차단) ──────────────────────
# object_detection 태스크에 segmentation 모델을 선택하는 LLM 오류 방지
TASK_MODEL_TYPE: dict[str, dict] = {
    "object_detection": {
        "allowed":  ["yolo", "detr", "rcnn", "retinanet", "fasterrcnn"],
        "forbidden": ["deeplabv3", "sam", "mask2former", "segmentation"],
        "fallback":  "yolov8n",
        "fallback_type": "yolo",
        "hint": "바운딩 박스를 생성하는 detection 모델만 선택해. segmentation/classification 모델은 절대 금지.",
    },
    "anomaly_detection": {
        "allowed":  ["ccifps", "efficientad", "patchcore"],
        "forbidden": ["deeplabv3", "sam", "mask2former", "wide_resnet50", "resnet50",
                      "efficientnet", "vit", "convnext", "yolo", "detr"],
        "fallback":  "ccifps",
        "fallback_type": "ccifps",
        "hint": "표면 결함/이상 탐지에는 PatchCore/CCIFPS/EfficientAD만 사용. wide_resnet50은 분류 모델이므로 절대 금지.",
    },
    "segmentation": {
        "allowed":  ["deeplabv3", "sam", "mask2former", "fcn"],
        "forbidden": ["yolo"],
        "fallback":  "deeplabv3_resnet50",
        "fallback_type": "torchvision",
        "hint": "픽셀 단위 세그멘테이션 모델을 선택해.",
    },
    "classification": {
        "allowed":  ["resnet", "efficientnet", "vit", "swin", "convnext"],
        "forbidden": ["deeplabv3", "sam", "yolo"],
        "fallback":  "resnet50",
        "fallback_type": "torchvision",
        "hint": "이미지 분류 모델을 선택해.",
    },
}


def _call_llm(prompt: str, model: str = "deepseek-r1:8b", timeout: int = 60) -> str:
    """LLM 호출 공통 함수."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_API, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["message"]["content"].strip()
    except Exception as e:
        print(f"  ❌ [Scout] LLM 호출 오류: {e}")
        return ""


# ── arXiv 검색 ──────────────────────────────────────────────────────────────
def _search_arxiv(query: str, max_results: int = 5) -> list:
    """arXiv API로 논문 검색. [{title, id, abstract, url}, ...]"""
    encoded = urllib.parse.quote(query)
    url = (
        f"http://export.arxiv.org/api/query"
        f"?search_query=all:{encoded}"
        f"&start=0&max_results={max_results}"
        f"&sortBy=relevance&sortOrder=descending"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            xml = r.read().decode("utf-8")
    except Exception as e:
        print(f"  ⚠️ [Scout] arXiv 검색 실패: {e}")
        return []

    results = []
    entries = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)
    for entry in entries:
        title_m   = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        id_m      = re.search(r"<id>(.*?)</id>", entry, re.DOTALL)
        abstract_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        if title_m and id_m:
            arxiv_id = id_m.group(1).strip().split("/")[-1]
            results.append({
                "source": "arxiv",
                "title": title_m.group(1).strip().replace("\n", " "),
                "id": arxiv_id,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "abstract": (abstract_m.group(1).strip().replace("\n", " ")[:300]
                             if abstract_m else ""),
            })
    print(f"  📄 [Scout] arXiv 결과: {len(results)}편")
    return results


# ── HuggingFace 모델 검색 ───────────────────────────────────────────────────
def _search_huggingface(query: str, max_results: int = 8) -> list:
    """HuggingFace Hub API로 모델 검색. [{model_id, downloads, task, url}, ...]"""
    encoded = urllib.parse.quote(query)
    url = (
        f"https://huggingface.co/api/models"
        f"?search={encoded}&limit={max_results}&sort=downloads&direction=-1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ModelScout/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            models = json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️ [Scout] HuggingFace 검색 실패: {e}")
        return []

    results = []
    for m in models:
        model_id = m.get("modelId") or m.get("id", "")
        results.append({
            "source": "huggingface",
            "model_id": model_id,
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "tags": m.get("tags", [])[:6],
            "url": f"https://huggingface.co/{model_id}",
        })
    print(f"  🤗 [Scout] HuggingFace 결과: {len(results)}개 모델")
    return results


# ── DuckDuckGo 웹 검색 (무인증) ─────────────────────────────────────────────
def _search_web(query: str, max_results: int = 5) -> list:
    """DuckDuckGo Instant Answer API + HTML scrape로 웹 검색."""
    encoded = urllib.parse.quote(query + " best model 2024 site:paperswithcode.com OR site:arxiv.org")
    url = f"https://duckduckgo.com/html/?q={encoded}"
    try:
        req = urllib.request.Request(
            url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ⚠️ [Scout] 웹 검색 실패: {e}")
        return []

    # 제목과 스니펫 추출
    snippets = re.findall(
        r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL
    )[:max_results]
    titles = re.findall(
        r'<a class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL
    )[:max_results]

    results = []
    for t, s in zip(titles, snippets):
        clean_t = re.sub(r"<[^>]+>", "", t).strip()
        clean_s = re.sub(r"<[^>]+>", "", s).strip()
        results.append({"source": "web", "title": clean_t, "snippet": clean_s[:200]})

    print(f"  🌐 [Scout] 웹 검색 결과: {len(results)}건")
    return results


# ── LLM 검색 쿼리 생성 ─────────────────────────────────────────────────────
def _make_search_query(vlm_analysis: dict) -> str:
    """VLM 분석 결과로부터 최적 검색 쿼리를 LLM이 생성."""
    scene   = vlm_analysis.get("scene", "")
    objects = vlm_analysis.get("objects", [])
    task    = vlm_analysis.get("task_needed", "")
    reason  = vlm_analysis.get("reason", "")

    prompt = (
        f"이미지 분석 결과:\n"
        f"- 장면: {scene}\n"
        f"- 객체: {objects}\n"
        f"- 필요 작업: {task}\n"
        f"- 이유: {reason}\n\n"
        f"이 작업에 최적인 딥러닝 모델/백본을 찾기 위한 영어 검색 쿼리를 딱 한 줄로 만들어줘.\n"
        f"예: 'industrial surface defect detection backbone 2024'\n"
        f"쿼리만 출력해, 다른 텍스트 금지:"
    )
    result = _call_llm(prompt)
    # <think> 태그 제거 (deepseek-r1)
    result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()
    result = result.strip('"\'').strip()
    print(f"  🔍 [Scout] 검색 쿼리: {result}")
    return result or f"{task} {' '.join(objects[:2])} deep learning backbone 2024"


# ── LLM 최적 모델 선택 ─────────────────────────────────────────────────────
def _pick_best_model(
    arxiv_results: list,
    hf_results: list,
    web_results: list,
    vlm_analysis: dict,
    user_request: str = "",
) -> dict:
    """검색 결과를 LLM에 주고 최적 모델 선택."""

    # 컨텍스트 구성
    arxiv_text = "\n".join(
        f"- [{r['id']}] {r['title']}: {r['abstract'][:150]}"
        for r in arxiv_results[:4]
    ) or "없음"

    hf_text = "\n".join(
        f"- {r['model_id']} (다운로드: {r['downloads']:,}, 태그: {r['tags']})"
        for r in hf_results[:6]
    ) or "없음"

    web_text = "\n".join(
        f"- {r['title']}: {r['snippet']}"
        for r in web_results[:3]
    ) or "없음"

    scene   = vlm_analysis.get("scene", "")
    task    = vlm_analysis.get("task_needed", "object_detection")
    objects = vlm_analysis.get("objects", [])

    task_cfg  = TASK_MODEL_TYPE.get(task, TASK_MODEL_TYPE["object_detection"])
    forbidden = task_cfg["forbidden"]

    # ── 사용자 요청 감지 ──
    bbox_kws = ["바운딩", "bounding", "bbox", "객체 탐지", "객체를 탐지",
                "객체 인식", "객체를 인식", "detect", "detection",
                "바운딩박스", "그려줘"]
    anomaly_kws = ["결함", "이상", "anomaly", "스크래치", "균열",
                   "이상탐지", "defect", "crack", "부식", "표면",
                   "문제", "고장", "파손", "손상"]

    if user_request and any(k in user_request.lower() for k in bbox_kws):
        task = "object_detection"
    elif user_request and any(k in user_request.lower() for k in anomaly_kws):
        task = "anomaly_detection"
    # VLM 분석에서도 이상 탐지 키워드 감지
    scene_lower = scene.lower() if scene else ""
    if any(k in scene_lower for k in ["결함", "스크래치", "균열", "부식", "이상", "파손", "손상", "깨진", "부러진", "defect", "crack", "scratch", "damage"]):
        task = "anomaly_detection"

    prompt = f"""
이미지 VLM 분석 결과:
{json.dumps(vlm_analysis, ensure_ascii=False)[:400]}

사용자 요청: {user_request or task}

=== arXiv 검색 결과 ===
{arxiv_text}

=== HuggingFace 검색 결과 ===
{hf_text}

=== 웹 검색 결과 ===
{web_text}

=== 판단 기준 (반드시 준수) ===

[태스크 구분]
- 표면 결함/스크래치/부식/균열/파손/손상 탐지
  → task_type: "anomaly"
  → 적합 모델: PatchCore, EfficientAD, CCIFPS
  → 절대 금지: ResNet 분류, wide_resnet50_2, YOLO 일반 탐지, EfficientNet

- 특정 객체 위치/개수 탐지 (바운딩박스)
  → task_type: "detection"
  → 적합 모델: YOLOv8, RT-DETR, FCOS
  → 절대 금지: ResNet 분류, wide_resnet50_2

- 이미지 전체 설명/분류
  → task_type: "classification"
  → 적합 모델: ResNet, EfficientNet, VLM

[현재 이미지 판단]
VLM 분석에서 "결함", "스크래치", "균열", "부식", "이상", "표면",
"파손", "손상", "고장"이 언급되면 반드시 task_type="anomaly".
wide_resnet50_2는 ImageNet 분류 모델이므로 결함 탐지에 절대 사용 금지.
현재 태스크: {task}

4단계로 생각해서 최종 JSON으로 답해:
1. 이 이미지의 특성과 도메인은?
2. 이 작업에 어떤 모델 계열이 적합한가? (위 규칙 참조)
3. 검색 결과 중 실제로 이 도메인에 특화된 것은?
4. 최종 선택 — task_type이 anomaly면 반드시 ccifps/patchcore/efficientad 중 선택

{{"model": "모델명", "type": "anomaly/detection/classification",
  "reason": "선택 이유",
  "reasoning": "위 1~4단계 추론 과정",
  "confidence": "high/medium/low"}}
"""
    print(f"  💬 [Scout] 쿼리: task={task}, user_req={user_request[:50] if user_request else '(none)'}")

    response = _call_llm(prompt, timeout=90)
    
    # 1. <think> 태그 안의 추론 과정 추출 시도
    reasoning_match = re.search(r"<think>(.*?)</think>", response, flags=re.DOTALL)
    if reasoning_match:
        reasoning_content = reasoning_match.group(1).strip()
        clean_response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    else:
        # 2. <think> 태그가 없으면 JSON 이전의 모든 텍스트를 추론 과정으로 간주
        json_start = response.find("{")
        if json_start > 0:
            reasoning_content = response[:json_start].strip()
            clean_response = response[json_start:].strip()
        else:
            reasoning_content = ""
            clean_response = response.strip()

    try:
        start = clean_response.find("{")
        end   = clean_response.rfind("}") + 1
        raw = json.loads(clean_response[start:end])
        # 새 포맷(type) 또는 기존 포맷(model_type) 모두 지원
        decision = {
            "model":        raw.get("model", task_cfg["fallback"]),
            "model_type":   raw.get("type") or raw.get("model_type", task_cfg["fallback_type"]),
            "reason":       raw.get("reason", ""),
            "reasoning":    raw.get("reasoning") or reasoning_content,
            "source_paper": raw.get("source_paper"),
            "confidence":   raw.get("confidence", "medium"),
        }
    except Exception:
        print(f"  ⚠️ [Scout] 모델 선택 파싱 실패. 태스크 기본값 사용.")
        decision = {
            "model":        task_cfg["fallback"],
            "model_type":   task_cfg["fallback_type"],
            "reason":       f"파싱 실패 — {task} 태스크 기본 폴백",
            "reasoning":    reasoning_content,
            "source_paper": None,
            "confidence":   "low",
        }

    # ── 검증 1: anomaly 타입인데 ccifps/patchcore/efficientad 아니면 강제 ccifps ──
    chosen = decision.get("model", "").lower()
    chosen_type = decision.get("model_type", "").lower()
    if chosen_type == "anomaly" or task == "anomaly_detection":
        if not any(x in chosen for x in ["ccifps", "patchcore", "efficientad"]):
            print(f"  ⛔ [Scout] anomaly인데 {decision['model']} 선택 → 강제 ccifps")
            decision["model"]      = "ccifps"
            decision["model_type"] = "ccifps"
            decision["reason"]     = f"anomaly 태스크에 부적합({chosen}) → ccifps 강제 (히트맵 생성)"
            decision["confidence"] = "high"

    # ── 검증 2: detection 타입인데 yolo/detr/rcnn 계열이 아니면 강제 yolov8n ──
    chosen = decision.get("model", "").lower()
    chosen_type = decision.get("model_type", "").lower()
    if chosen_type == "detection" or task == "object_detection":
        if not any(x in chosen for x in ["yolo", "detr", "rcnn", "fcos", "retinanet", "yolos"]):
            print(f"  ⛔ [Scout] detection인데 {decision['model']} 선택 → 강제 yolov8n")
            decision["model"]      = "yolov8n"
            decision["model_type"] = "yolo"
            decision["reason"]     = f"detection 타입에 부적합한 모델({chosen}) 선택 차단 → yolov8n"
            decision["confidence"] = "high"

    # ── 검증 3: forbidden 모델 선택 시 강제 폴백 ──
    chosen = decision.get("model", "").lower()
    if any(bad in chosen for bad in forbidden):
        print(f"  ⛔ [Scout] 금지된 모델({decision['model']}) → 강제 폴백: {task_cfg['fallback']}")
        decision["model"]      = task_cfg["fallback"]
        decision["model_type"] = task_cfg["fallback_type"]
        decision["reason"]     = f"금지 모델({chosen}) 선택 차단 → {task} 기본 폴백"
        decision["confidence"] = "low"

    print(f"  ✅ [Scout] 최종 선택: {decision['model']} ({decision['model_type']})")
    return decision



# ── ModelScout 메인 클래스 ──────────────────────────────────────────────────
class ModelScout:
    """
    이미지 VLM 분석 결과를 받아 최적 모델을 자율 탐색·선택·다운로드.

    사용 예:
        scout = ModelScout(notify_fn=send_telegram_message)
        result = scout.scout(vlm_analysis)
    """

    def __init__(self, notify_fn=None):
        """
        notify_fn: 중간 상태를 전달할 콜백 (예: Telegram 전송 함수).
                   None이면 print만.
        """
        self.notify = notify_fn or (lambda msg: print(f"  📢 [Scout] {msg}"))

    def scout(self, vlm_analysis: dict, notify_fn=None, user_request: str = "") -> dict:
        """
        전체 탐색 파이프라인 실행.

        Args:
            vlm_analysis: VLM 이미지 분석 결과
            notify_fn: 로그 콜백
            user_request: 사용자 캐프션/요청 (바운딩박스 의도 감지 등)

        Returns:
            {model, model_type, reason, source_paper, confidence, ready, elapsed_sec}
        """
        t0 = time.time()
        if notify_fn:
            self.notify = notify_fn

        scene   = vlm_analysis.get("scene", "이미지")
        objects = vlm_analysis.get("objects", [])
        task    = vlm_analysis.get("task_needed", "object_detection")
        task_cfg = TASK_MODEL_TYPE.get(task, TASK_MODEL_TYPE["object_detection"])

        self.notify(
            f"🔍 자율 모델 탐색 시작\n"
            f"장면: {scene}\n"
            f"태스크: {task} → 허용: {task_cfg['allowed']}"
        )

        # 1. 검색 쿼리 생성
        query = _make_search_query(vlm_analysis)

        # 2. 병렬 검색 (순차 실행 — 서버 환경)
        self.notify("📡 arXiv · HuggingFace · 웹 동시 탐색 중...")
        arxiv_results = _search_arxiv(query)
        hf_results    = _search_huggingface(query)
        web_results   = _search_web(query)

        self.notify(f"📊 탐색 완료: 논문 {len(arxiv_results)}편, 모델 {len(hf_results)}개, 웹 {len(web_results)}건")

        # 3. LLM 최적 모델 선택 (태스크 제약 + 사용자 요청 포함)
        self.notify("🧠 LLM이 최적 모델 선택 중...")
        decision = _pick_best_model(arxiv_results, hf_results, web_results, vlm_analysis, user_request=user_request)

        model_name = decision.get("model", task_cfg["fallback"])
        model_type = decision.get("model_type", task_cfg["fallback_type"])
        reason     = decision.get("reason", "")
        paper      = decision.get("source_paper")

        self.notify(
            f"✅ 선택된 모델: {model_name}\n"
            f"이유: {reason[:150]}\n"
            + (f"근거 논문: arxiv.org/abs/{paper}" if paper else "")
        )

        # 4. 모델 로드 시도 — 10초 타임아웃, 실패 시 즉시 YOLOv8n 폴백
        self.notify(f"⬇️ {model_name} 로드 중...")
        from aria.perception.vision_router import _ensure_model
        import threading

        load_result = {"ready": False}

        def _load():
            load_result["ready"] = _ensure_model(model_name)

        t = threading.Thread(target=_load, daemon=True)
        t.start()
        t.join(timeout=10)  # 10초 타임아웃

        ready = load_result["ready"]

        if not ready:
            # 즉시 폴백 — YOLOv8n은 항상 작동
            fallback = task_cfg["fallback"]
            self.notify(
                f"⚠️ {model_name} 로드 실패. {fallback}으로 대체합니다."
            )
            print(f"  🔄 [Scout] 폴백: {model_name} → {fallback}")
            decision["model"]        = fallback
            decision["model_type"]   = task_cfg["fallback_type"]
            decision["fallback_used"] = True
            model_name = fallback
            ready = _ensure_model(fallback)  # 폴백도 로드 확인

        elapsed = round(time.time() - t0, 1)

        result = {
            **decision,
            "ready":       ready,
            "elapsed_sec": elapsed,
            "search_stats": {
                "arxiv":       len(arxiv_results),
                "huggingface": len(hf_results),
                "web":         len(web_results),
            },
        }

        status = "✅ 준비 완료" if ready else "❌ 로드 실패"
        self.notify(f"{status}: {model_name} ({elapsed}초)")
        return result

    def analyze_image_features(self, image_path: str) -> dict:
        """
        테스트 이미지의 feature를 추출하고 memory bank와의 거리를 구해
        PCA 2D 좌표 및 통계량(평균, 분산, 95% 신뢰 구간)을 반환.
        (Numpy 기반 연산)
        """
        import cv2
        import numpy as np
        import torch
        import torch.nn.functional as F
        import torchvision.models as models
        import torchvision.transforms as transforms
        from pathlib import Path
        import os
        
        # 1. 이미지 로드
        frame_bgr = cv2.imread(image_path)
        if frame_bgr is None:
            return {"error": f"이미지를 읽을 수 없습니다: {image_path}"}
            
        # 2. 엔진 초기화 (또는 로컬 CCIFPS 로직 수행)
        base_dir = Path(__file__).parent.resolve()
        memory_path = str(base_dir / "memory_bank_t95.npy")
        if not os.path.exists(memory_path):
            memory_path = str(base_dir / "memory_bank.npy")
            
        if not os.path.exists(memory_path):
            return {"error": f"Memory bank 파일이 없습니다: {memory_path}"}
            
        memory_bank = np.load(memory_path).astype(np.float32)
        
        device = torch.device("cpu")
        model = models.wide_resnet50_2(pretrained=True).to(device)
        model.eval()
        for p in model.parameters():
            p.requires_grad = False
            
        outputs = {}
        def hook(m, i, o):
            outputs[m._layer_name] = o
            
        # 훅 등록을 위해 레이어 이름 주입
        for layer_name in ("layer2", "layer3"):
            layer = dict(model.named_modules())[layer_name]
            layer._layer_name = layer_name
            layer.register_forward_hook(hook)
            
        transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img_tensor = transform(frame_rgb).unsqueeze(0).to(device)
        
        outputs.clear()
        with torch.no_grad():
            model(img_tensor)
            
        features_list = []
        ref_shape = None
        for layer_name in ("layer2", "layer3"):
            feat = outputs[layer_name]
            if ref_shape is None:
                ref_shape = (feat.shape[2], feat.shape[3])
            elif (feat.shape[2], feat.shape[3]) != ref_shape:
                feat = F.interpolate(feat, size=ref_shape, mode="bilinear", align_corners=False)
            feat = F.avg_pool2d(feat, kernel_size=3, stride=1, padding=1)
            features_list.append(feat)
            
        concat = torch.cat(features_list, dim=1)
        n_patches = concat.shape[2] * concat.shape[3]
        query = concat.permute(0, 2, 3, 1).reshape(n_patches, -1)
        query = query.cpu().numpy().astype(np.float32)
        
        # k-NN (k=1)
        q_sq = np.sum(query ** 2, axis=1, keepdims=True)
        m_sq = np.sum(memory_bank ** 2, axis=1)
        dists = q_sq + m_sq - 2 * (query @ memory_bank.T)
        dists = np.maximum(dists, 0)
        min_dists = np.min(dists, axis=1)
        
        anomaly_score = float(np.max(min_dists))
        mean_dist = float(np.mean(min_dists))
        var_dist = float(np.var(min_dists))
        ci_lower = float(np.percentile(min_dists, 2.5))
        ci_upper = float(np.percentile(min_dists, 97.5))
        
        # PCA 축소 (샘플링 100/200)
        np.random.seed(42)
        q_indices = np.random.choice(len(query), min(100, len(query)), replace=False)
        m_indices = np.random.choice(len(memory_bank), min(200, len(memory_bank)), replace=False)
        
        q_sample = query[q_indices]
        m_sample = memory_bank[m_indices]
        
        all_data = np.concatenate([m_sample, q_sample], axis=0)
        mean_vec = np.mean(all_data, axis=0)
        centered = all_data - mean_vec
        cov = np.cov(centered, rowvar=False)
        
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        idx = np.argsort(eigenvalues)[::-1]
        top_vectors = eigenvectors[:, idx[:2]]
        
        m_proj = (m_sample - mean_vec) @ top_vectors
        q_proj = (q_sample - mean_vec) @ top_vectors
        
        return {
            "stats": {
                "score": round(anomaly_score, 3),
                "mean": round(mean_dist, 3),
                "variance": round(var_dist, 3),
                "ci_lower": round(ci_lower, 3),
                "ci_upper": round(ci_upper, 3)
            },
            "pca_data": {
                "normal": m_proj.tolist(),
                "query": q_proj.tolist()
            }
        }


# ── 단독 실행 테스트 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 팬 블레이드 균열 탐지 시뮬레이션
    test_analysis = {
        "scene": "산업용 팬 블레이드 클로즈업, 표면에 균열 의심",
        "objects": ["fan blade", "metal surface", "crack"],
        "task_needed": "anomaly_detection",
        "reason": "금속 표면의 미세 균열 탐지가 필요",
        "anomaly_possible": True,
    }

    print("=" * 60)
    print("  ModelScout 단독 테스트")
    print("=" * 60)

    scout = ModelScout()
    result = scout.scout(test_analysis)

    print("\n최종 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
