from __future__ import annotations
"""VisionAgent — 이미지 분석 서브 에이전트.

v4 §1: 탐지기 플러그인 레지스트리 기반으로 재배선.
- cmdiad_inference 직접 import 제거 — CMDIADDetector 플러그인이 내부에서 지연 임포트.
- industrial 하드코딩 분기 제거 — registry.rank_for()가 탐지기를 선택.
- 가짜 점수(len(detections)*상수) 제거.
- 다운스트림 소비처(orchestrator, app.py, DiagnosticReport)의 필드 스키마는 유지.

v4 §2: 자율 선택 대화 추가.
- ESCALATION_GAP_THRESHOLD: 적합도 간격이 0.35 미만이면 escalation.
- Fast Path: 1위 탐지기만 실행 (이미지당 탐지기 최대 1개).
- Debate Path: 상위 2개 실행 → orchestrator._run_debate_detectors() 호출 → 채택.
- 비용 가드: 이미지당 탐지기 최대 2개, escalation은 모호할 때만.

Refactor Step 1 (routing-unification):
- 핵심 추론 로직을 모듈 레벨 함수 `inspect_via_registry()`로 추출.
- image entry: autonomous_agent.py → inspect_via_registry() → DetectorRegistry.
- VisionRouter 직접 호출 경로(레거시)는 autonomous_agent.py에서 완전히 제거됨.
"""

import base64
import json
import urllib.request
import os
import time
from pathlib import Path
from aria.agents.base_agent import BaseAgent

_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_API = f"{_OLLAMA_BASE}/api/chat"

# [v4] ProductRegistry는 identify()에만 사용 — 탐지기 선택 분기에 쓰지 않는다.
from aria.core.product_registry import ProductRegistry

# ──────────────────────────────────────────────────────────────────────────────
# 모듈 레벨 공용 함수 — Step 1 라우팅 통합
# autonomous_agent.py 등 외부에서 직접 import하여 사용한다.
# image entry → DetectorRegistry 경로.
# ──────────────────────────────────────────────────────────────────────────────

_DOMAIN_MAP: dict[str, str] = {
    "industrial_anomaly" : "industrial_anomaly",
    "industrial_defect"  : "industrial_anomaly",  # 구버전 호환
    "counting"           : "counting",
    "count"              : "counting",
    "label_inspect"      : "label_inspect",
    "label"              : "label_inspect",
    "ocr"                : "label_inspect",
    "dimension"          : "dimension",
    "measurement"        : "dimension",
    "general_object"     : "general_object",
}

ESCALATION_GAP_THRESHOLD = 0.35  # 1위-2위 간격이 이 미만이면 Debate Path


def _call_vlm_module(image_path: str, prompt: str) -> str:
    """모듈 레벨 VLM 호출 헬퍼 — config.vlm.get_vlm()로 위임 (Step 2)."""
    from aria.core.config.vlm import get_vlm
    return get_vlm().analyze(image_path, prompt)



def _parse_json_module(text: str) -> dict:
    """모듈 레벨 JSON 파서 헬퍼."""
    if "```json" in text:
        text = text.split("```json")[-1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except Exception:
            pass
    return {}


def inspect_via_registry(image_path: str, user_caption: str | None = None) -> dict:
    """이미지 1장을 DetectorRegistry 경로로 검사하고 표준 result dict를 반환한다.

    단계:
      1) ProductRegistry 선행 식별 → enrolled 시 VLM 생략(CMDIAD fast-track)
      2) VLM 분석 → image_meta {domain, defect_suspected, primary_object, scene, scene_text}
      3) get_registry().rank_for(image_meta, product_for_detector)
      4) Fast/Debate Path 분기 (ESCALATION_GAP_THRESHOLD = 0.35 유지)
      5) top_detector.run(image_path, product_for_detector) 결과 반환

    반환 dict 키는 detectors/base.py Detector.run() 계약 키를 따른다:
      score, threshold, decision, confidence, render_type,
      overlay_path, regions, model_name + 다운스트림 호환 필드.
    """
    t0 = time.time()

    # ── 0. ProductRegistry 선행 식별 ──────────────────────────────────────────
    prod_registry = ProductRegistry()
    pre_identified = prod_registry.identify(image_path, primary_object=None, scene_description=None)
    print(f"  [inspect_via_registry] ProductRegistry 선행 식별: status={pre_identified['status']}, "
          f"product={pre_identified.get('product_id', '-')}")

    if pre_identified["status"] == "enrolled":
        identified   = pre_identified
        domain_class = "industrial_anomaly"
        primary_obj  = identified.get("product_id", "object")
        scene_desc   = f"{primary_obj} 표면 이상탐지 이미지"
        defect_loc   = "정상 상태입니다."
        anomaly_like = True
        print(f"  [inspect_via_registry] ✓ enrolled 제품({primary_obj}) — VLM 생략, CMDIAD 직행")
    else:
        # ── 1. VLM 통합 호출 ───────────────────────────────────────────────────
        unified_prompt = (
            "이 이미지를 분석하고 아래 항목들을 JSON 형식으로만 응답하라. "
            "다른 텍스트나 인사말 없이 유효한 JSON 오브젝트만 반환해야 한다:\n"
            '1. "domain": 이미지 도메인. 아래 중 정확히 하나를 선택:\n'
            '   - "industrial_anomaly": 공장 부품/금속 표면/알약/케이블/식품/로프/타이어/다웰/폼 등 '
            "산업용 제품을 클로즈업으로 찍은 결함 검사용 이미지 (배경이 단색/검정/흰색인 클로즈업 촬영물)\n"
            '   - "counting": 동일한 물체가 다수 배열된 이미지 (알약 여러 개, 볼트/너트 다량 등). 수량 파악이 주 목적인 이미지.\n'
            '   - "label_inspect": 텍스트/라벨/바코드/QR코드/시리얼넘버/유통기한 등 인쇄 정보가 주된 검사 대상인 이미지.\n'
            '   - "dimension": 단색 배경에 단일 부품 클로즈업으로 치수/크기/간격/직경 측정이 주 목적인 이미지.\n'
            '   - "general_object": 논문 표/차트/그래프, 스크린샷, 문서, 일반 사진, UI 화면 등\n'
            "   중요: 텍스트·숫자·표·그래프가 포함된 이미지는 항상 \"general_object\"\n"
            '2. "scene_description": 이미지에 대한 전체적인 묘사 (한국어로 1~2문장)\n'
            '3. "primary_object": 이미지의 주된 객체 종류 (영어 단어 하나)\n'
            '4. "is_defective": 실제 결함/이상이 있으면 true, 정상이거나 산업용이 아닌 일반 이미지이면 false\n'
            '5. "defect_location_description": 결함/이상 부위 정밀 묘사 (한국어. 결함 없으면 "정상 상태입니다.")'
        )

        from aria.core.config.vlm import get_vlm as _get_vlm
        print(f"  [inspect_via_registry] VLM ({_get_vlm().name}) 도메인 분류 + 상세 분석 호출...")
        vlm_res  = _call_vlm_module(image_path, unified_prompt)
        vlm_data = _parse_json_module(vlm_res)

        domain_raw   = vlm_data.get("domain", "general_object").strip().lower()
        domain_class = _DOMAIN_MAP.get(domain_raw, "general_object")
        print(f"  [inspect_via_registry] VLM 도메인 분류: {domain_raw!r} → {domain_class}")

        scene_desc  = vlm_data.get("scene_description", "이미지 묘사를 생성하지 못했습니다.")
        primary_obj = vlm_data.get("primary_object", "object").lower()
        defect_loc  = vlm_data.get("defect_location_description", "정상 상태입니다.")

        if domain_class in ("counting", "label_inspect", "dimension"):
            anomaly_like = False
        elif "is_defective" in vlm_data:
            anomaly_like = bool(vlm_data["is_defective"])
        else:
            NORMAL_PHRASES = ["정상", "normal", "no defect", "intact",
                              "undamaged", "결함 없", "good condition"]
            anomaly_like = not any(ph in defect_loc.lower() for ph in NORMAL_PHRASES)
            if domain_class == "general_object":
                anomaly_like = False

        identified = pre_identified

    product_for_detector = identified if identified["status"] == "enrolled" else None

    # ── 2. DetectorRegistry 선택 → Fast/Debate Path ───────────────────────────
    image_meta = {
        "domain"           : domain_class,
        "defect_suspected" : anomaly_like,
        "primary_object"   : primary_obj,
        "scene"            : scene_desc,
        "scene_text"       : (scene_desc + " " + primary_obj).lower(),
    }

    from aria.perception.detectors.registry import get_registry
    det_registry = get_registry()
    ranked = det_registry.rank_for(image_meta, product_for_detector)

    top_detector, top_score = ranked[0]
    second_detector = ranked[1][0] if len(ranked) > 1 else None
    second_score    = ranked[1][1] if len(ranked) > 1 else 0.0
    gap = top_score - second_score
    debate_log: dict | None = None

    if second_detector is None or gap >= ESCALATION_GAP_THRESHOLD:
        print(f"  [inspect_via_registry §Fast] {top_detector.name} (gap={gap:.2f} ≥ {ESCALATION_GAP_THRESHOLD})")
        det_result = top_detector.run(image_path, product_for_detector)
    else:
        print(f"  [inspect_via_registry §Debate] {top_detector.name} vs {second_detector.name} "
              f"(gap={gap:.2f} < {ESCALATION_GAP_THRESHOLD})")
        det_a = top_detector.run(image_path, product_for_detector)
        det_b = second_detector.run(image_path, product_for_detector)
        try:
            import aria.orchestration.agent_orchestrator as _ao_module
            _orch = _ao_module.AgentOrchestrator.__new__(_ao_module.AgentOrchestrator)
            debate_result = _ao_module.AgentOrchestrator._run_debate_detectors(
                _orch, det_a, det_b, image_meta
            )
        except Exception as _de:
            print(f"  [inspect_via_registry] debate 호출 실패: {_de} — 1위 탐지기 폴백")
            debate_result = {"adopted_detector": top_detector.name}

        debate_log = debate_result
        adopted_name = debate_result.get("adopted_detector", "")
        if adopted_name == second_detector.name or adopted_name == second_detector.modality:
            print(f"  [inspect_via_registry] 토론 결정: {second_detector.name} 채택")
            top_detector, det_result = second_detector, det_b
        else:
            print(f"  [inspect_via_registry] 토론 결정: {top_detector.name} 채택")
            det_result = det_a

    print(f"  [inspect_via_registry] 탐지기: {top_detector.name} (applicability={top_score:.2f})")
    print(f"    순위: " + ", ".join(f"{d.name}={s:.2f}" for d, s in ranked))

    # ── 3. 탐지기 결과 → 다운스트림 필드 매핑 ────────────────────────────────
    anomaly_score: float = det_result.get("score", 0.0)
    threshold: float     = det_result.get("threshold", 0.0)
    verdict: str         = det_result.get("decision", "n/a")
    render_type: str     = det_result.get("render_type", "none")
    result_image_path    = det_result.get("overlay_path") or image_path
    detections: list     = det_result.get("regions", [])
    model_used: str      = det_result.get("model_name", top_detector.name)
    vlm_scene: str       = scene_desc
    hf_models_summary: str = ""

    if det_result.get("description"):
        defect_loc = det_result["description"]

    if identified["status"] != "enrolled" and top_detector.modality == "surface_anomaly":
        model_disc = (
            "이미지가 산업용 도메인으로 식별되었으나 레지스트리에 등록되지 않은 "
            "제품(unenrolled)입니다."
        )
    elif identified["status"] == "enrolled":
        model_disc = (
            f"제품 레지스트리에 등록된 {identified['product_id']}의 메모리뱅크 및 "
            f"캘리브레이션 임계값을 사용한 정밀 이상 탐지({model_used}) 경로로 라우팅했습니다."
        )
    else:
        model_disc = (
            f"이미지가 {domain_class} 도메인으로 식별되어 "
            f"{model_used} 탐지기({top_detector.name})로 자동 라우팅했습니다."
        )

    # HuggingFace MCP 탐색 — general_object + unenrolled일 때만
    if domain_class == "general_object" and product_for_detector is None:
        try:
            import app
            mcp_hub = getattr(app, "mcp_client", None)
            if mcp_hub:
                print("  [inspect_via_registry] 일반 객체 도메인 → HuggingFace MCP 모델 탐색")
                resp = mcp_hub.call_tool("huggingface.search_models", {
                    "query": f"{primary_obj} anomaly detection",
                    "max_results": 2
                })
                if isinstance(resp, dict) and resp.get("success"):
                    models_list = resp.get("models", [])
                    if models_list:
                        hf_models_summary = "\n".join(
                            f"- {m['model_id']} (Downloads: {m['downloads_last_month']})"
                            for m in models_list
                        )
        except Exception as e:
            print(f"  [inspect_via_registry] HuggingFace MCP search failed: {e}")

    # overlay_path가 없으면 OpenCV fallback (이상탐지 탐지기에 한정)
    if not result_image_path or result_image_path == image_path:
        if top_detector.modality not in ("object_detection", "vlm_inspect"):
            from pathlib import Path as _Path
            try:
                import cv2
                from datetime import datetime
                img = cv2.imread(image_path)
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    edges = cv2.cvtColor(cv2.Canny(gray, 50, 150), cv2.COLOR_GRAY2BGR)
                    cv2.putText(edges, "FALLBACK: OpenCV Canny Edge", (15, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    out_dir = _Path(image_path).resolve().parent.parent / "outputs"
                    out_dir.mkdir(exist_ok=True)
                    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
                    out_path = str(out_dir / f"fallback_edge_{ts}.jpg")
                    cv2.imwrite(out_path, edges)
                    result_image_path = out_path
            except Exception:
                pass

    elapsed = round(time.time() - t0, 2)
    print(f"  [inspect_via_registry] 완료 — detector={top_detector.name}, "
          f"verdict={verdict}, score={anomaly_score:.3f}, elapsed={elapsed}s")

    # ── 4. 결과 요약문(Summary) ───────────────────────────────────────────────
    summary_parts = [f"🔍 **VLM 관측 장면**: {scene_desc}"]
    if verdict == "n/a":
        summary_parts.append(f"📦 **감지 대상 객체**: {primary_obj} (이상 의심: 판단 불가)")
        summary_parts.append(f"🤝 **채택된 탐지기**: {model_used}")
        summary_parts.append(f"⚠️ **결함 위치 및 상태**: {defect_loc}")
        if identified["status"] != "enrolled":
            summary_parts.append(
                "💡 **조치 안내**: 이 제품은 아직 제품 레지스트리에 등록되지 않았습니다. "
                "정상 이미지 폴더를 지정해 제품을 먼저 등록(enroll)해 주십시오."
            )
    else:
        summary_parts.append(
            f"📦 **감지 대상 객체**: {primary_obj} "
            f"(이상 의심: {'있음' if verdict in ('fail', 'detected') else '없음'})"
        )
        summary_parts.append(f"🤝 **채택된 탐지기**: {model_disc}")
        summary_parts.append(f"⚠️ **결함 위치 및 상태**: {defect_loc}")
        if hf_models_summary:
            summary_parts.append(f"🌐 **HuggingFace 관련 모델**:\n{hf_models_summary}")
        summary_parts.append(
            f"⚡ **채택된 최종 분석 모델**: {model_used} "
            f"(Anomaly Score: {anomaly_score:.2f} / Threshold: {threshold:.2f})"
        )
    summary = "\n".join(summary_parts)

    # ── 5. 반환 — 다운스트림 소비처 필드 스키마 완전 유지 ─────────────────────
    return {
        "status": verdict,
        "verdict": verdict,
        "summary": summary,
        "result_image_path": result_image_path,
        "vlm_scene": vlm_scene,
        "defect_location_description": defect_loc,
        "model_discussion": model_disc,
        "model_used": model_used,
        "anomaly_score": anomaly_score,
        "score": anomaly_score,
        "threshold": threshold,
        "render_type": render_type,
        "detections": detections,
        "elapsed": elapsed,
        "domain": domain_class,
        "detector_name": top_detector.name,
        "detector_modality": top_detector.modality,
        "detector_confidence": det_result.get("confidence", 0.0),
        "detector_ranking": [(d.name, round(s, 3)) for d, s in ranked],
        "debate_log": debate_log,
        "device": det_result.get("device", "cpu"),
        "device_reason": det_result.get("device_reason", "VLM 또는 기본 디바이스"),
        "data": {
            "vlm_description": scene_desc,
            "primary_object": primary_obj,
            "anomaly_likelihood": (verdict in ("fail", "detected")),
            "model_discussion": model_disc,
            "defect_location": defect_loc,
            "hf_models": hf_models_summary,
            "detections": detections,
            "inference_time_ms": int(elapsed * 1000),
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# VisionAgent 클래스 — inspect_via_registry()의 얇은 래퍼
# ──────────────────────────────────────────────────────────────────────────────

class VisionAgent(BaseAgent):
    name = "vision"
    description = "이미지 분석, 객체 탐지, 이상 탐지, 바운딩박스, 자율 모델 비교 토론"

    def run(self, user_input, image_path=None, context=None):
        if not image_path:
            return {
                "status": "error",
                "summary": "이미지가 필요합니다.",
            }

        # 사용자 커스텀 질의응답 (예: 어떤 이미지가 보여?, 묘사해줘 등) 우회 처리
        is_custom_query = user_input and user_input.strip() not in (
            "이 이미지에서 이상/결함 또는 객체를 감지하라",
            "detect", "analyze", "검사해줘", "분석해줘"
        )
        if is_custom_query and not any(kw in user_input for kw in ["검사", "측정", "이상치", "디텍션"]):
            print(f"  [VisionAgent] 사용자 커스텀 비전 질의 감지: '{user_input}'")
            vlm_reply = self._call_vlm(image_path, user_input)
            if "</think>" in vlm_reply:
                vlm_reply = vlm_reply.split("</think>")[-1].strip()
            return {
                "status": "success",
                "summary": vlm_reply,
                "response": vlm_reply,
                "result_image_path": image_path,
                "verdict": "success",
                "anomaly_score": 0.0,
                "device": "cpu",
                "device_reason": "VLM 커스텀 쿼리 (Ollama) CPU 모드 실행"
            }

        # 표준 검사 경로 → 모듈 레벨 함수에 위임
        return inspect_via_registry(image_path, user_caption=user_input)


    def _call_vlm(self, image_path: str, prompt: str) -> str:
        """커스텀 질의 전용 VLM 호출 — config.vlm.get_vlm()로 위임 (Step 2)."""
        from aria.core.config.vlm import get_vlm
        return get_vlm().analyze(image_path, prompt)


    def _parse_json(self, text: str) -> dict:
        if "```json" in text:
            text = text.split("```json")[-1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except Exception:
                pass
        return {}

    def _run_opencv_fallback(self, image_path: str) -> str:
        import cv2
        from datetime import datetime
        img = cv2.imread(image_path)
        if img is None:
            return image_path
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edges_color = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        
        cv2.putText(edges_color, "FALLBACK: OpenCV Canny Edge", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
        base_dir = Path(__file__).resolve().parent.parent
        out_dir = base_dir / "outputs"
        out_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = str(out_dir / f"fallback_edge_{ts}.jpg")
        cv2.imwrite(out_path, edges_color)
        return out_path

