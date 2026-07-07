"""
Harness Engineering Loop for ARGUS AI Agent.
Plan → Build → Verify → Fix 자율 검증 루프.

사용자 이미지에 대한 분석이 올바른지 스스로 검증하고,
실패 시 전략을 수정하여 재시도한다.
"""

import base64
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 설정 ─────────────────────────────────────────────────────────────────────
OLLAMA_API = "http://localhost:11434/api/chat"
REASONING_MODEL = "deepseek-r1:8b"    # Plan, Verify, Fix (깊은 추론)
from aria.core.config.models import MODELS
VLM_MODEL = MODELS["vision"]           # Build (빠른 시각 분석) — config/models.py 단일 출처
MAX_FIX_ATTEMPTS = 3


# ── Ollama 호출 헬퍼 ─────────────────────────────────────────────────────────
def _call_llm(model: str, prompt: str, timeout: int = 120) -> str:
    """텍스트 전용 LLM 호출."""
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
            data = json.loads(r.read())
            return data["message"]["content"].strip()
    except Exception as e:
        return f"[LLM 오류] {e}"


def _call_vlm(model: str, prompt: str, image_path: str, timeout: int = 120) -> str:
    """이미지 + 프롬프트로 VLM 호출."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": model,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [b64],
        }],
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_API, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            return data["message"]["content"].strip()
    except Exception as e:
        return f"[VLM 오류] {e}"


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출."""
    # <think> 태그 제거
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    clean = clean.replace("```json", "").replace("```", "").strip()
    try:
        start = clean.find("{")
        end   = clean.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(clean[start:end])
    except Exception:
        pass
    return {}


def _get_context() -> dict:
    """시작 시 컨텍스트 주입 — 설치된 모델, 최근 에러 등."""
    # 설치된 Ollama 모델
    installed_models = []
    try:
        import subprocess
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        installed_models = [line.split()[0] for line in res.stdout.strip().split("\n")[1:]
                           if line.strip()]
    except Exception:
        pass

    # 최근 에러 이력 (MEMORY.md에서)
    recent_errors = []
    memory_path = Path("MEMORY.md")
    if memory_path.exists():
        try:
            content = memory_path.read_text(encoding="utf-8")
            # "실패", "에러", "오류" 줄 추출
            for line in content.split("\n"):
                if any(k in line for k in ["실패", "에러", "오류", "ERROR", "fallback"]):
                    recent_errors.append(line.strip()[:100])
            recent_errors = recent_errors[-5:]  # 최근 5개만
        except Exception:
            pass

    return {
        "installed_models": installed_models[:10],
        "recent_errors": recent_errors,
        "available_pipelines": ["yolo (object_detection)", "ccifps (anomaly_detection/heatmap)",
                                "transformers (detr/yolos)", "vlm (classification/description)"],
    }


class HarnessLoop:
    """
    Plan → Build → Verify → Fix 루프.

    - Plan: deepseek-r1이 이미지와 요청을 보고 전략 수립
    - Build: ModelScout + VisionRouter로 실행
    - Verify: qwen2.5vl이 결과 이미지를 보고 검증
    - Fix: 실패 시 deepseek-r1이 전략 수정
    """

    def __init__(self, notify_fn=None):
        """
        notify_fn: 텔레그램 전송 콜백 (chat_id, message).
        """
        self.notify = notify_fn or (lambda msg: print(f"  [Harness] {msg}"))
        self.tried_models = []
        self.attempt_history = []

    def run(self, image_path: str, user_query: str, vlm_analysis: dict) -> dict:
        """
        전체 Harness 루프 실행.

        Returns:
            dict with keys: model_decision, infer_result, out_img, det_summary,
                           harness_log, attempts, verified
        """
        context = _get_context()
        self.tried_models = []
        self.attempt_history = []
        harness_log = []

        def _hlog(msg):
            harness_log.append(msg)
            self.notify(msg)
            print(f"  [Harness] {msg}")

        # ═══════════════════════════════════════════════════════════
        # Step 1: PLAN — deepseek-r1이 전략 수립
        # ═══════════════════════════════════════════════════════════
        _hlog("📋 [Plan] 전략 수립 중... (deepseek-r1)")
        plan = self._plan(image_path, user_query, vlm_analysis, context)
        _hlog(f"📋 전략: {plan.get('strategy', '?')[:150]}")
        _hlog(f"🎯 선택 모델: {plan.get('model', '?')} ({plan.get('task_type', '?')})")

        final_result = None

        for attempt in range(MAX_FIX_ATTEMPTS):
            _hlog(f"\n🔄 시도 {attempt + 1}/{MAX_FIX_ATTEMPTS}")

            # ── Doom Loop 차단: 같은 모델 반복 방지 ──
            if plan.get("model") in self.tried_models:
                _hlog(f"⚠️ Doom Loop 감지: {plan['model']}이(가) 이미 시도됨 → 전략 전면 재검토")
                plan = self._force_alternative(plan, vlm_analysis)
                _hlog(f"🔄 대체 모델: {plan.get('model', '?')} ({plan.get('task_type', '?')})")

            self.tried_models.append(plan.get("model", "unknown"))

            # ═══════════════════════════════════════════════════════
            # Step 2: BUILD — 모델 선택 + 추론 실행
            # ═══════════════════════════════════════════════════════
            _hlog(f"🔨 [Build] {plan.get('model', '?')} 실행 중...")
            build_result = self._build(plan, image_path, vlm_analysis)

            if build_result.get("error"):
                _hlog(f"❌ Build 실패: {build_result['error'][:100]}")
                plan = self._fix(plan, {"passed": False, "reason": build_result["error"]},
                                build_result, vlm_analysis, context)
                continue

            _hlog(f"✅ Build 완료: {build_result.get('model_used', '?')}")

            # ═══════════════════════════════════════════════════════
            # Step 3: VERIFY — qwen2.5vl이 결과 검증
            # ═══════════════════════════════════════════════════════
            result_image = build_result.get("result_image_path") or image_path
            _hlog(f"🔍 [Verify] 결과 검증 중... (deepseek-r1)")
            verdict = self._verify(build_result, user_query, result_image, plan)

            self.attempt_history.append({
                "attempt": attempt + 1,
                "model": plan.get("model"),
                "verdict": verdict,
            })

            if verdict.get("passed"):
                _hlog(f"✅ 검증 통과! (시도 {attempt + 1}회)")
                final_result = build_result
                final_result["harness_verified"] = True
                final_result["harness_attempts"] = attempt + 1
                final_result["harness_log"] = harness_log
                return final_result

            # ═══════════════════════════════════════════════════════
            # Step 4: FIX — 실패 원인 분석 + 전략 수정
            # ═══════════════════════════════════════════════════════
            _hlog(f"⚠️ 검증 실패 (시도 {attempt + 1}): {verdict.get('reason', '?')[:150]}")

            if attempt < MAX_FIX_ATTEMPTS - 1:
                _hlog("🔧 [Fix] 전략 수정 중... (deepseek-r1)")
                plan = self._fix(plan, verdict, build_result, vlm_analysis, context)
                _hlog(f"🔧 수정된 전략: {plan.get('model', '?')} ({plan.get('task_type', '?')})")

        # 최대 시도 후 마지막 결과 반환
        _hlog(f"⚠️ {MAX_FIX_ATTEMPTS}회 시도 완료. 마지막 결과 반환.")
        if final_result is None:
            final_result = build_result
        final_result["harness_verified"] = False
        final_result["harness_attempts"] = MAX_FIX_ATTEMPTS
        final_result["harness_log"] = harness_log
        return final_result

    # ═══════════════════════════════════════════════════════════════════════════
    # Plan: deepseek-r1이 전략 수립 (Reasoning Sandwich 상단)
    # ═══════════════════════════════════════════════════════════════════════════
    def _plan(self, image_path: str, user_query: str,
              vlm_analysis: dict, context: dict) -> dict:
        """deepseek-r1에게 분석 전략을 수립하게 한다."""

        prompt = f"""너는 이미지 분석 전략을 수립하는 AI야.

[컨텍스트]
설치된 모델: {context.get('installed_models', [])}
사용 가능한 파이프라인: {context.get('available_pipelines', [])}
최근 에러: {context.get('recent_errors', [])}

[이미지 VLM 분석]
{json.dumps(vlm_analysis, ensure_ascii=False)[:400]}

[사용자 요청]
{user_query or "(캡션 없이 이미지만 전송)"}

[전략 수립 규칙]
- 표면 결함/스크래치/부식/균열/파손 → task_type: "anomaly" → model: "ccifps"
- 특정 객체 위치/바운딩박스 → task_type: "detection" → model: "yolov8n"
- 이미지 설명/분류 → task_type: "classification" → model: "vlm"

아래 JSON으로 전략을 수립해:
{{"strategy": "한 줄 전략 설명",
  "task_type": "anomaly/detection/classification",
  "model": "ccifps 또는 yolov8n 또는 vlm",
  "model_type": "ccifps/yolo/vlm",
  "reason": "선택 이유",
  "expected_output": "히트맵/바운딩박스/텍스트 설명"}}"""

        response = _call_llm(REASONING_MODEL, prompt)
        result = _parse_json(response)

        # 폴백
        if not result.get("model"):
            task = vlm_analysis.get("task_needed", "object_detection")
            if task == "anomaly_detection":
                result = {"strategy": "이상 탐지 → CCIFPS 히트맵",
                          "task_type": "anomaly", "model": "ccifps",
                          "model_type": "ccifps", "reason": "기본 anomaly 전략",
                          "expected_output": "히트맵"}
            elif task == "object_detection":
                result = {"strategy": "객체 탐지 → YOLOv8",
                          "task_type": "detection", "model": "yolov8n",
                          "model_type": "yolo", "reason": "기본 detection 전략",
                          "expected_output": "바운딩박스"}
            else:
                result = {"strategy": "이미지 분류/설명",
                          "task_type": "classification", "model": VLM_MODEL,
                          "model_type": "vlm", "reason": "기본 분류 전략",
                          "expected_output": "텍스트 설명"}

        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # Build: 실제 추론 실행 (Reasoning Sandwich 중단 — 빠른 실행)
    # ═══════════════════════════════════════════════════════════════════════════
    def _build(self, plan: dict, image_path: str, vlm_analysis: dict) -> dict:
        """plan에 따라 모델 설치 + 추론 실행."""
        model_type = plan.get("model_type", "yolo")

        # ── VLM (classification) → VLM 직접 호출 ──
        if model_type == "vlm":
            try:
                vlm_model = plan.get("model", VLM_MODEL)
                prompt = "이 이미지를 상세히 설명해줘. 객체, 상태, 특이사항을 포함해서."
                desc = _call_vlm(vlm_model, prompt, image_path, timeout=60)
                return {
                    "task": "classification",
                    "model_used": vlm_model,
                    "model_decision": {
                        "model": vlm_model,
                        "model_type": "vlm",
                        "reason": plan.get("reason", "VLM 분류"),
                    },
                    "description": desc,
                    "result_image_path": image_path,
                    "status": "success",
                }
            except Exception as e:
                # VLM 실패 → YOLO 폴백
                plan = dict(plan)
                plan["model"] = "yolov8n"
                plan["model_type"] = "yolo"
                plan["weights_file"] = "yolov8n.pt"
                plan["reason"] = f"VLM 실패({e}) → YOLO 폴백"

        # ── CCIFPS / YOLO → DetectorRegistry 경로 (Step 1.5: 뒷문 차단) ──
        try:
            from aria.agents.vision_agent import inspect_via_registry

            # model_decision은 로그용으로만 보존 (레지스트리가 탐지기 자동 선택)
            model_decision = {
                "model":      plan.get("model", "yolov8n"),
                "model_type": plan.get("model_type", "yolo"),
                "weights_file": plan.get("weights_file"),
                "reason":     plan.get("reason", ""),
            }

            # 추론 — DetectorRegistry가 이미지에 맞는 탐지기를 선택
            result = inspect_via_registry(image_path)
            result["model_decision"] = model_decision
            return result

        except Exception as e:
            import traceback
            return {"error": str(e), "traceback": traceback.format_exc(),
                    "model_decision": plan}


    # ═══════════════════════════════════════════════════════════════════════════
    # Verify: 결과 검증 (Reasoning Sandwich 하단 — 깊은 추론)
    # ═══════════════════════════════════════════════════════════════════════════
    def _verify(self, result: dict, user_query: str,
                result_image_path: str, plan: dict) -> dict:
        """
        모델 타입별 결정론적 검증.

        - Anomaly Detection: score + 히트맵 존재 여부 (bbox 불필요)
        - Object Detection: 탐지 개수 + 관련성 확인
        - Classification/VLM: 결과 텍스트 존재 여부
        """
        import os

        model_type = result.get("task", "unknown")
        status     = result.get("status", "")
        error      = result.get("error", "")
        has_image  = bool(result.get("result_image_path") and
                         os.path.exists(str(result.get("result_image_path", ""))))

        # ── 공통: 에러 상태면 즉시 실패 ──
        if status == "error" or error:
            return {"passed": False,
                    "reason": f"실행 에러: {error[:100]}",
                    "suggestion": "다른 모델로 재시도"}

        # ══════════════════════════════════════════════════════════
        # Anomaly Detection 검증: score + 히트맵만 확인
        # ══════════════════════════════════════════════════════════
        if model_type == "anomaly_detection":
            has_score   = result.get("anomaly_score") is not None
            has_heatmap = has_image

            if has_score and has_heatmap:
                score = result.get("anomaly_score", 0)
                return {"passed": True,
                        "reason": f"✅ anomaly score({score:.2f}) + 히트맵 생성됨"}
            elif has_score and not has_heatmap:
                return {"passed": False,
                        "reason": "❌ anomaly score 있지만 히트맵 이미지 없음",
                        "suggestion": "ccifps 히트맵 파이프라인 재실행"}
            else:
                return {"passed": False,
                        "reason": "❌ anomaly score 없음 — 모델이 anomaly를 실행하지 못함",
                        "suggestion": "ccifps로 재시도"}

        # ══════════════════════════════════════════════════════════
        # Object Detection 검증: 탐지 결과 + 관련성
        # ══════════════════════════════════════════════════════════
        elif model_type == "object_detection":
            detections = result.get("detections", [])

            if not detections:
                return {"passed": False,
                        "reason": "❌ 탐지된 객체 0개",
                        "suggestion": "yolov8n으로 재시도 또는 VLM 설명"}

            # 관련성 확인: 사용자 요청과 탐지 결과가 맞는지
            if user_query:
                relevant = self._check_relevance(detections, user_query)
                if not relevant:
                    labels = [d.get("label", "?") for d in detections[:5]]
                    return {"passed": False,
                            "reason": f"❌ 무관한 객체만 탐지: {labels}",
                            "suggestion": "사용자 요청에 맞는 모델로 재시도"}

            if has_image:
                return {"passed": True,
                        "reason": f"✅ {len(detections)}개 객체 탐지 + 바운딩박스 이미지"}
            else:
                return {"passed": False,
                        "reason": f"탐지 {len(detections)}개 있지만 결과 이미지 없음",
                        "suggestion": "결과 이미지 생성 확인"}

        # ══════════════════════════════════════════════════════════
        # Classification / VLM 검증: 설명 텍스트 존재
        # ══════════════════════════════════════════════════════════
        elif model_type == "classification":
            desc = result.get("description", "")
            if desc and len(desc) > 10:
                return {"passed": True,
                        "reason": f"✅ 이미지 설명 생성됨 ({len(desc)}자)"}
            else:
                return {"passed": False,
                        "reason": "❌ 이미지 설명이 비어있거나 너무 짧음",
                        "suggestion": "VLM으로 재시도"}

        # ══════════════════════════════════════════════════════════
        # 기본: 결과 이미지만 있으면 통과
        # ══════════════════════════════════════════════════════════
        else:
            if has_image:
                return {"passed": True,
                        "reason": f"✅ 결과 이미지 존재 (task={model_type})"}
            else:
                return {"passed": False,
                        "reason": f"결과 이미지 없음 (task={model_type})",
                        "suggestion": "ccifps 또는 yolov8n으로 재시도"}

    def _check_relevance(self, detections: list, user_query: str) -> bool:
        """
        탐지된 객체가 사용자 요청과 관련 있는지 확인.
        "book"이 탐지됐는데 "결함 탐지" 요청이면 → 관련 없음.
        """
        labels = [d.get("label", "?") for d in detections]

        # ── 빠른 규칙 기반 체크 (LLM 호출 없이) ──
        # 사용자가 결함/이상 탐지를 요청했는데 일반 객체만 나오면 실패
        anomaly_kws = ["결함", "이상", "anomaly", "defect", "crack", "스크래치",
                       "균열", "부식", "파손", "손상", "고장"]
        if any(k in user_query.lower() for k in anomaly_kws):
            # anomaly 요청인데 object detection 결과 → 항상 부적합
            return False

        # 일반적으로 무관한 객체 라벨 목록
        irrelevant_labels = {"book", "person", "cat", "dog", "bicycle", "car",
                             "airplane", "bus", "train", "truck", "bird",
                             "horse", "sheep", "cow", "elephant", "bear",
                             "zebra", "giraffe", "backpack", "umbrella",
                             "handbag", "tie", "suitcase", "frisbee",
                             "skis", "snowboard", "sports ball", "kite",
                             "baseball bat", "baseball glove", "skateboard",
                             "surfboard", "tennis racket"}

        # 모든 탐지가 무관한 라벨이면 실패
        all_irrelevant = all(
            d.get("label", "").lower() in irrelevant_labels
            for d in detections
        )
        if all_irrelevant:
            return False

        # 그 외에는 관련 있다고 판단
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # Fix: 실패 원인 분석 + 전략 수정
    # ═══════════════════════════════════════════════════════════════════════════
    def _fix(self, plan: dict, verdict: dict, result: dict,
             vlm_analysis: dict, context: dict) -> dict:
        """deepseek-r1이 실패 원인을 분석하고 전략을 수정한다."""

        tried_text = ", ".join(self.tried_models) if self.tried_models else "없음"
        history_text = "\n".join(
            f"  시도{h['attempt']}: {h['model']} → {'통과' if h['verdict'].get('passed') else '실패'}"
            f" ({h['verdict'].get('reason', '?')[:60]})"
            for h in self.attempt_history
        )

        prompt = f"""이전 시도가 실패했어. 전략을 수정해.

[실패한 Plan]
model: {plan.get('model', '?')}
task_type: {plan.get('task_type', '?')}

[실패 이유]
{verdict.get('reason', '?')}

[검증 AI 제안]
{verdict.get('suggestion', '없음')}

[이미 시도한 모델 (다시 선택 금지)]
{tried_text}

[시도 이력]
{history_text or "없음"}

[사용 가능한 파이프라인]
- ccifps: 표면 이상 탐지 → 히트맵 생성 (anomaly_score 반환)
- yolov8n: 일반 객체 탐지 → 바운딩박스
- vlm: 이미지 설명/분류

[수정 규칙]
- 이미 시도한 모델은 절대 다시 선택하지 마.
- anomaly 태스크인데 yolo/resnet으로 실패했으면 → ccifps
- detection 태스크인데 ccifps로 실패했으면 → yolov8n
- 모든 모델이 실패했으면 → vlm으로 이미지 설명

수정된 전략 JSON:
{{"strategy": "수정된 전략 설명",
  "task_type": "anomaly/detection/classification",
  "model": "모델명",
  "model_type": "ccifps/yolo/vlm",
  "reason": "수정 이유"}}"""

        response = _call_llm(REASONING_MODEL, prompt, timeout=60)
        new_plan = _parse_json(response)

        # 폴백 로직
        if not new_plan.get("model"):
            # 지능적 폴백: 이전에 안 시도한 모델로
            if "ccifps" not in self.tried_models:
                new_plan = {"strategy": "CCIFPS 히트맵으로 재시도",
                            "task_type": "anomaly", "model": "ccifps",
                            "model_type": "ccifps", "reason": "이전 모델 실패 → ccifps 시도"}
            elif "yolov8n" not in self.tried_models:
                new_plan = {"strategy": "YOLOv8으로 재시도",
                            "task_type": "detection", "model": "yolov8n",
                            "model_type": "yolo", "reason": "이전 모델 실패 → yolo 시도"}
            else:
                new_plan = {"strategy": "VLM 이미지 설명으로 폴백",
                            "task_type": "classification", "model": VLM_MODEL,
                            "model_type": "vlm", "reason": "모든 모델 실패 → VLM 설명"}

        # Doom Loop 차단: 이미 시도한 모델을 다시 선택했으면 강제 교체
        if new_plan.get("model") in self.tried_models:
            for fallback in ["ccifps", "yolov8n", VLM_MODEL]:
                if fallback not in self.tried_models:
                    new_plan["model"] = fallback
                    new_plan["model_type"] = {"ccifps": "ccifps", "yolov8n": "yolo"}.get(
                        fallback, "vlm")
                    new_plan["reason"] = f"Doom Loop 방지: {fallback}로 강제 전환"
                    break

        return new_plan

    def _force_alternative(self, plan: dict, vlm_analysis: dict) -> dict:
        """Doom Loop 감지 시 강제 대체 모델 선택."""
        for alt_model, alt_type in [("ccifps", "ccifps"), ("yolov8n", "yolo"),
                                     (VLM_MODEL, "vlm")]:
            if alt_model not in self.tried_models:
                return {
                    "strategy": f"전략 전면 재검토 → {alt_model}",
                    "task_type": {"ccifps": "anomaly", "yolo": "detection"}.get(
                        alt_type, "classification"),
                    "model": alt_model,
                    "model_type": alt_type,
                    "reason": f"Doom Loop 차단: 이전 모델 반복 → {alt_model} 강제 전환",
                }
        # 모든 모델 시도 완료
        return {
            "strategy": "모든 파이프라인 소진 → VLM 설명",
            "task_type": "classification",
            "model": VLM_MODEL,
            "model_type": "vlm",
            "reason": "모든 모델 시도 완료",
        }
