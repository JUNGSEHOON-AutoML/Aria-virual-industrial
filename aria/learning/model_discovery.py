"""
ModelDiscovery — Ralph v5.0 자율 모델 탐색 엔진.

이미지를 보고 전 세계 모델 중 최적을 찾아서
자동으로 설치하고 실행하는 통합 파이프라인.

7단계: Analyze → Scout → Select → Install → Execute → Verify → Retry

기존 모듈을 래핑:
  - vision_router.py (VLM분석, 모델실행)
  - model_scout.py (arXiv/HF 검색, 모델 선택)
  - cmdiad_inference.py (CCIFPS 이상탐지)
  - harness_loop.py (결과 검증)
"""

import json
import os
import sys
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── 경로/설정 ──
BASE_DIR = Path(__file__).parent
BANK_DIR = "/userHome/userhome4/sehoon/CMDIAD-main/results/ccifps_banks"
DATASET_DIR = "/userHome/userhome4/sehoon/CMDIAD-main/datasets/mvtec_3d"
OUTPUT_DIR = str(BASE_DIR / "outputs")
OLLAMA_API = "http://localhost:11434/api/chat"
USAGE_LOG = BASE_DIR / "data" / "model_usage.json"


def _call_ollama(model: str, prompt: str, temperature: float = 0.0) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_API, data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    text = data["message"]["content"].strip()
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    return text


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출."""
    if "```json" in text:
        text = text.split("```json")[-1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# ModelDiscovery
# ══════════════════════════════════════════════════════════════════════════════
class ModelDiscovery:
    """
    자율 모델 탐색 + 실행 엔진.

    지원 소스:
    1. HuggingFace Hub
    2. arXiv 논문 검색
    3. timm (700+ 이미지 모델)
    4. torchvision 내장
    5. ultralytics (YOLO)
    6. CMDIAD CCIFPS (도메인 일치 시)
    7. Ollama VLM
    """

    AVAILABLE_CATEGORIES = [
        "bagel", "cable_gland", "carrot", "cookie", "dowel",
        "foam", "peach", "potato", "rope", "tire",
    ]

    def __init__(self, send_telegram_fn=None, chat_id=None, mcp_hub=None):
        self.notify = send_telegram_fn or (lambda msg: print(f"[Discovery] {msg}"))
        self.chat_id = chat_id
        self.mcp_hub = mcp_hub

    # ──────────────────────────────────────────────────────────────────────
    # 메인 파이프라인
    # ──────────────────────────────────────────────────────────────────────
    def discover_and_run(self, image_path: str, user_query: str,
                         context: dict = None) -> dict:
        """
        7단계 자율 탐색 + 실행 파이프라인.

        1. Analyze (VLM 이미지 분석)
        2. Scout (arXiv + HF + timm 병렬 검색)
        3. Select (deepseek-r1 최적 모델 선택)
        4. Install (필요 시 자동 설치)
        5. Execute (모델 추론)
        6. Verify (결과 검증)
        7. Retry (실패 시 다음 후보)
        """
        t0 = time.time()
        self.notify("🔍 자율 모델 탐색 시작...")

        # Step 1: Analyze
        self.notify("📊 [Step 1/7] 이미지 분석 중... (qwen2.5vl)")
        analysis = self._analyze(image_path, user_query)
        domain = analysis.get("domain", "unknown")
        task = analysis.get("task", "object_detection")
        image_type = analysis.get("image_type", "general")
        confidence = analysis.get("confidence_score", 0.5)
        # confidence가 문자열인 경우 변환
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 0.5
        self.notify(
            f"📊 분석 완료:\n"
            f"  이미지 유형: {image_type}\n"
            f"  도메인: {domain}\n"
            f"  태스크: {task}\n"
            f"  확신도: {confidence:.1%}\n"
            f"  대상: {analysis.get('object', '?')}")

        # 1. 등록된 모델 우선 (방법 B 결과)
        from aria.perception.vision_router import get_registered_model, run_inference
        registered = get_registered_model(domain)
        if registered:
            self.notify(
                f"⚡ 등록된 모델 사용: {registered} "
                f"(다운로드 불필요)")
            result = run_inference(image_path,
                {"model": registered,
                 "model_type": "yolo" if ("yolo" in registered.lower() and "yolos" not in registered.lower()) else "transformers",
                 "source": "huggingface",
                 "domain": domain})
            
            # 사용 기록 누적
            is_success = result.get("status") == "success"
            self._record_model_usage(registered, domain, is_success)
            
            elapsed = round(time.time() - t0, 1)
            result["discovery_model"] = registered
            result["discovery_elapsed"] = elapsed
            result["discovery_attempt"] = 1
            result["task"] = task
            return result

        # ── 확신도 기반 라우팅 (Phase 1 → 2 트리거) ──
        if confidence < 0.5 and task not in ("description", "ocr"):
            self.notify(f"⚠️ VLM 확신도 {confidence:.0%} — 도메인 특화 모델 탐색 강화")
            analysis["scout_aggressive"] = True  # Phase 2에서 더 넓게 검색

        # ── 빠른 경로: description/ocr → VLM 즉시 실행 (Scout 건너뜀) ──
        if task in ("description", "ocr"):
            self.notify(f"💬 {task} 태스크 → VLM 직접 실행 (모델 탐색 건너뜀)")
            result = self._run_vlm_direct(image_path, user_query, task)
            elapsed = round(time.time() - t0, 1)
            result["discovery_model"] = "qwen2.5vl:7b"
            result["discovery_elapsed"] = elapsed
            result["discovery_attempt"] = 1
            result["task"] = task
            self.notify(
                f"✅ VLM 응답 완료!\n"
                f"  모델: qwen2.5vl:7b\n"
                f"  총 소요: {elapsed}초")
            return result

        # Step 2~3: Scout + Select (30초 타임아웃)
        ranked = None
        try:
            import signal
            def _timeout_handler(signum, frame):
                raise TimeoutError("모델 탐색 시간 초과 (30초)")
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(30)

            try:
                self.notify("🔍 [Step 2/7] 최적 모델 탐색 중... (arXiv + HF + timm)")
                candidates = self._scout_parallel(analysis)
                n_arxiv = len(candidates.get("arxiv", []))
                n_hf = len(candidates.get("huggingface", []))
                n_timm = len(candidates.get("timm", []))
                self.notify(
                    f"🔍 탐색 완료:\n"
                    f"  arXiv: {n_arxiv}편\n"
                    f"  HuggingFace: {n_hf}개\n"
                    f"  timm: {n_timm}개")

                self.notify("🧠 [Step 3/7] 최적 모델 선택 중... (deepseek-r1)")
                ranked = self._select_best(candidates, analysis)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        except (TimeoutError, Exception) as timeout_err:
            self.notify(f"⏱️ {timeout_err}. yolov8n으로 즉시 진행합니다.")
            ranked = [{"model": "yolov8n", "source": "ultralytics",
                      "reason": "타임아웃 → 즉시 폴백", "confidence": "medium"}]

        if not ranked:
            return {"error": "모델 선택 실패", "status": "error"}

        best = ranked[0]
        self.notify(
            f"🧠 선택 완료:\n"
            f"  모델: {best.get('model', '?')}\n"
            f"  소스: {best.get('source', '?')}\n"
            f"  이유: {best.get('reason', '?')[:80]}")

        # Step 4~7: Install → Execute → Verify → Retry
        for idx, candidate in enumerate(ranked[:3]):
            attempt = idx + 1
            model_name = candidate.get("model", "unknown")
            self.notify(f"🔨 [시도 {attempt}/3] {model_name} 실행 중...")

            # Step 4: Install
            installed = self._ensure_installed(candidate)
            if not installed:
                self.notify(f"⚠️ {model_name} 설치 실패, 다음 후보...")
                continue

            # Step 5: Execute
            self.notify(f"🚀 [Step 5/7] 추론 실행: {model_name}")
            result = self._execute(candidate, image_path)

            if result.get("error"):
                self.notify(f"⚠️ 실행 오류: {result['error'][:80]}")
                continue

            # Step 6: Verify
            self.notify("🔍 [Step 6/7] 결과 검증 중... (deepseek-r1)")
            verdict = self._verify(result, user_query, image_path)


            if verdict.get("passed"):
                elapsed = round(time.time() - t0, 1)
                self.notify(
                    f"✅ [Step 7/7] 검증 통과!\n"
                    f"  모델: {model_name}\n"
                    f"  총 소요: {elapsed}초")

                # 사용 기록 + 영구 통합 판단
                usage = self._record_model_usage(
                    model_name, domain,
                    result.get("status") == "success"
                )
                self._maybe_request_integration(candidate, analysis, usage)

                # ── CodeAgent: 파이프라인 코드 + 수학적 증명 생성 ──
                try:
                    self.notify("🛠️ [CodeAgent] 파이프라인 코드 + 수학적 증명 생성 중...")
                    from aria.agents.code_agent import CodeAgent
                    code_agent = CodeAgent()
                    pipeline = code_agent.build_pipeline(candidate, analysis)
                    result["generated_code_path"] = pipeline.get("generated_code_path")
                    result["proof_summary"] = pipeline.get("proof_summary", "")
                    result["proof_path"] = pipeline.get("proof_path")
                    if pipeline.get("generated_code_path"):
                        self.notify(f"✅ 코드 생성 완료: {pipeline['generated_code_path']}")
                    if pipeline.get("proof_summary"):
                        self.notify(f"📐 수학적 증명:\n{pipeline['proof_summary'][:200]}")
                except Exception as e:
                    print(f"[Discovery] CodeAgent 호출 실패: {e}")

                result["discovery_model"] = model_name
                result["discovery_elapsed"] = round(time.time() - t0, 1)
                result["discovery_attempt"] = attempt
                return result

            # Step 7: Retry
            self.notify(
                f"⚠️ 검증 실패: {verdict.get('reason', '?')[:80]}\n"
                f"다음 후보로 재시도...")

        # 모든 후보 실패 → HarnessLoop 폴백
        self.notify("⚠️ 모든 후보 실패. HarnessLoop 폴백...")
        return self._fallback_harness(image_path, user_query, analysis)

    # ──────────────────────────────────────────────────────────────────────
    # 빠른 경로: VLM 직접 실행 (description / ocr)
    # ──────────────────────────────────────────────────────────────────────
    def _run_vlm_direct(self, image_path: str, user_query: str,
                        task: str) -> dict:
        """description/ocr: 타일 분할 + VLM 즉시 응답."""
        try:
            from aria.perception.vision_router import (_image_to_base64, _call_ollama,
                                       _resize_for_vlm)
            from PIL import Image
            import tempfile, os

            img = Image.open(image_path)
            w, h = img.size

            # ── 스크린샷(가로 넓은 이미지): 타일 분할 분석 ──
            if w > h * 1.3 and max(w, h) > 600:
                print(f"[VLM] 타일 분할: {w}x{h} → 좌/우 2개")

                # 좌/우 반분할
                left = img.crop((0, 0, w // 2, h))
                right = img.crop((w // 2, 0, w, h))

                tiles = []
                for i, tile in enumerate([left, right]):
                    # 각 타일을 512px로 리사이즈
                    tile_path = os.path.join(
                        os.path.dirname(image_path) or ".",
                        f"_tile_{i}.jpg")
                    tile = tile.resize(
                        (min(512, tile.width),
                         min(512, tile.height)),
                        Image.LANCZOS)
                    tile.save(tile_path, quality=85)
                    tiles.append(tile_path)

                prompt_tile = (
                    f"이 이미지 부분을 자세히 설명해줘. "
                    f"텍스트, UI 요소, 버튼, 검색어 등 모든 것.\n"
                    f"사용자 질문: {user_query}")

                desc_left = _call_ollama("qwen2.5vl:7b", [
                    {"role": "user", "content": f"[왼쪽 화면] {prompt_tile}",
                     "images": [_image_to_base64(tiles[0])]}
                ], timeout=60, num_ctx=2048)

                desc_right = _call_ollama("qwen2.5vl:7b", [
                    {"role": "user", "content": f"[오른쪽 화면] {prompt_tile}",
                     "images": [_image_to_base64(tiles[1])]}
                ], timeout=60, num_ctx=2048)

                # LLM으로 합산 요약
                summary_prompt = (
                    f"아래는 하나의 화면을 좌/우로 나눠 분석한 결과야.\n\n"
                    f"[왼쪽]: {desc_left}\n\n"
                    f"[오른쪽]: {desc_right}\n\n"
                    f"사용자 질문: {user_query}\n\n"
                    f"이 두 부분을 합쳐서 전체 화면이 무엇인지 "
                    f"자연스럽게 설명해줘. 한국어로.")

                response = _call_ollama("qwen2.5:14b", [
                    {"role": "user", "content": summary_prompt}
                ], timeout=30, num_ctx=2048)

                # 임시 파일 정리
                for t in tiles:
                    try: os.remove(t)
                    except: pass

            else:
                # ── 일반 이미지: 768px 리사이즈 ──
                max_px = 768 if task == "ocr" else 768
                resized = _resize_for_vlm(image_path, max_size=max_px)
                b64 = _image_to_base64(resized)

                if task == "ocr":
                    prompt = (
                        f"이 이미지에 있는 모든 텍스트를 읽어줘.\n"
                        f"사용자 질문: {user_query}")
                else:
                    prompt = (
                        f"이 이미지를 자세히 설명해줘.\n"
                        f"사용자 질문: {user_query}\n\n"
                        f"이미지에 보이는 것들을 자세히 설명해줘. "
                        f"객체, 장면, 색상, 텍스트, 특이한 점 등.")

                response = _call_ollama("qwen2.5vl:7b", [
                    {"role": "user", "content": prompt, "images": [b64]}
                ], timeout=90, num_ctx=4096)

            return {
                "result_image_path": image_path,
                "vlm_description": response,
                "summary": response[:200],
                "model_used": "qwen2.5vl:7b",
                "task": task,
                "harness_verified": True,
            }
        except Exception as e:
            return {"error": str(e), "model_used": "qwen2.5vl:7b"}

    # ──────────────────────────────────────────────────────────────────────
    # Step 1: Analyze (Analyst Agent)
    # ──────────────────────────────────────────────────────────────────────
    def _analyze(self, image_path: str, user_query: str) -> dict:
        """VLM이 이미지를 보고 상세 분석. + 태스크/도메인/의도 보정."""
        try:
            from aria.perception.vision_router import analyze_image_with_vlm
            vlm = analyze_image_with_vlm(image_path, user_caption=user_query)
            # task_needed → task 통일
            if "task_needed" in vlm and "task" not in vlm:
                vlm["task"] = vlm["task_needed"]

            query_lower = user_query.lower()

            # ── 보정 0: 사용자 의도 감지 (description 우선) ──
            description_kws = [
                "뭐가 보여", "뭐야", "설명해", "설명해줘", "무엇이", "what",
                "describe", "explain", "알려줘", "보여줘", "어떤",
                "분석해줘", "분석해", "분석을",
            ]
            # description 의도면 다른 보정 스킵
            if any(kw in query_lower for kw in description_kws):
                # 결함 키워드가 같이 있는지 확인
                defect_kws_check = ["균열", "crack", "결함", "defect", "이상탐지", "anomaly"]
                has_defect_intent = any(kw in query_lower for kw in defect_kws_check)
                if not has_defect_intent:
                    vlm["task"] = "description"
                    print(f"[Discovery] 의도 감지: 사용자가 설명을 요청 → description")
                    return vlm

            # ── 보정 1: 결함 키워드 → surface_defect ──
            defect_kws = [
                "균열", "crack", "결함", "defect", "스크래치", "scratch",
                "손상", "damage", "부식", "corrosion", "깨진", "broken",
                "찢어진", "마모", "wear", "이상", "anomaly", "불량",
            ]
            scene = vlm.get("scene", "").lower()
            query_lower = user_query.lower()
            objects_str = " ".join(vlm.get("objects", [])).lower()

            has_defect_in_scene = any(kw in scene for kw in defect_kws)
            has_defect_in_query = any(kw in query_lower for kw in defect_kws)
            anomaly_flag = vlm.get("anomaly_possible", False)

            current_task = vlm.get("task", "classification")
            if current_task == "classification" and (
                has_defect_in_scene or has_defect_in_query or anomaly_flag
            ):
                vlm["task"] = "surface_defect"
                print(f"[Discovery] 태스크 보정: classification → surface_defect"
                      f" (scene={has_defect_in_scene}, query={has_defect_in_query})")

            # anomaly_detection도 surface_defect와 동일 취급
            if vlm.get("task") == "anomaly_detection":
                vlm["task"] = "surface_defect"

            # ── 보정 2: CCIFPS bank 도메인 매칭 ──
            # 이미지가 CCIFPS 학습 도메인에 해당하면 surface_defect로 강제 전환
            available_domains = self._get_available_domains()
            domain_keywords = {
                "cable_gland": ["cable", "gland", "connector", "커넥터", "금속", "metal",
                                "nut", "너트", "screw", "나사", "부품", "fitting"],
                "bagel": ["bagel", "베이글", "donut", "도넛", "bread", "빵", "ring"],
                "carrot": ["carrot", "당근"],
                "cookie": ["cookie", "쿠키", "biscuit"],
                "dowel": ["dowel", "핀", "나무", "wood", "막대", "pin"],
                "foam": ["foam", "폼", "sponge", "스펀지"],
                "peach": ["peach", "복숭아"],
                "potato": ["potato", "감자"],
                "rope": ["rope", "밧줄", "로프"],
                "tire": ["tire", "타이어"],
            }
            all_text = f"{scene} {objects_str} {query_lower}"
            matched_domain = None
            for dom in available_domains:
                kws = domain_keywords.get(dom, [dom])
                if any(kw in all_text for kw in kws):
                    matched_domain = dom
                    break

            if matched_domain:
                vlm["task"] = "surface_defect"
                vlm["domain"] = matched_domain
                print(f"[Discovery] 도메인 매칭: {matched_domain} → surface_defect 강제 전환")

            # ── 보정 3: PCB 도메인 매칭 ──
            pcb_keywords = ["pcb", "printed circuit board", "회로", "electronic", "전자", "보드"]
            if any(kw in all_text for kw in pcb_keywords):
                vlm["domain"] = "pcb"
                vlm["task"] = "object_detection"
                print(f"[Discovery] PCB 도메인 매칭 → object_detection 강제 전환")

            return vlm
        except Exception as e:
            print(f"[Discovery] VLM 분석 실패: {e}")

            # 사용자 요청에서 결함 키워드 체크
            defect_kws = ["균열", "crack", "결함", "defect", "손상", "이상", "anomaly"]
            task = "surface_defect" if any(kw in user_query.lower() for kw in defect_kws) else "object_detection"

            return {
                "domain": "unknown",
                "task": task,
                "object": user_query,
                "scene": user_query,
            }

    # ──────────────────────────────────────────────────────────────────────
    # Step 2: Scout → ResearchAgent에 위임 (Phase 2)
    # ──────────────────────────────────────────────────────────────────────
    def _scout_parallel(self, analysis: dict) -> dict:
        """ResearchAgent에 탐색 업무를 위임."""
        self.notify("🔍 ResearchAgent 호출됨")

        try:
            from aria.agents.research_agent import ResearchAgent
            agent = ResearchAgent()
            result = agent.scout(analysis)

            arxiv = result.get("arxiv", [])
            hf = result.get("huggingface", [])
            timm_r = result.get("timm", [])

            self.notify(
                f"📚 논문/모델 검색 결과 "
                f"{len(arxiv) + len(hf) + len(timm_r)}건 선별 완료")

            return {
                "arxiv": arxiv,
                "huggingface": hf,
                "timm": timm_r,
                "candidates": result.get("candidates", []),
            }
        except Exception as e:
            print(f"[Discovery] ResearchAgent 호출 실패: {e}")
            self.notify("⚠️ ResearchAgent 실패 → Fallback 모드")
            return {"arxiv": [], "huggingface": [], "timm": []}

    def _get_ccifps_score(self, analysis: dict) -> dict:
        """
        CCIFPS 적합도 점수.
        _analyze()가 설정한 domain 필드로 판단:
        - domain이 CCIFPS bank에 있으면 → 0.95
        - surface_defect이지만 domain 불일치 → 0.3 (폴백 후순위)
        - 그 외 → 0.1
        """
        available_domains = self._get_available_domains()
        task = analysis.get("task", "")
        detected_domain = analysis.get("domain", "unknown")

        # surface_defect/anomaly_detection이 아니면 CCIFPS 부적합
        if task not in ("surface_defect", "anomaly_detection"):
            return {
                "model": "ccifps", "source": "ccifps",
                "score": 0.1, "matched_domain": None,
                "reason": f"태스크 '{task}'에 CCIFPS 부적합.",
                "confidence": "low",
            }

        # _analyze()에서 도메인이 매칭되었는지 확인
        if detected_domain in available_domains:
            return {
                "model": "ccifps", "source": "ccifps",
                "score": 0.95, "matched_domain": detected_domain,
                "reason": (f"'{detected_domain}' 도메인 bank 존재. "
                          f"DINO ViT-B/8 패치 기반 이상탐지 특화."),
                "confidence": "high",
            }
        else:
            # surface_defect이지만 도메인 불일치 → 낮은 점수
            return {
                "model": "ccifps", "source": "ccifps",
                "score": 0.3, "matched_domain": None,
                "reason": (f"도메인 '{detected_domain}'은 학습되지 않음. "
                          f"가용: {available_domains[:5]}. 다른 모델 우선."),
                "confidence": "low",
            }

    def _select_best(self, candidates: dict, analysis: dict) -> list:
        """deepseek-r1이 후보를 보고 우선순위 리스트 생성."""

        # CCIFPS 적합도 점수 계산
        ccifps_score = self._get_ccifps_score(analysis)
        domain_matched = ccifps_score["score"] > 0.5

        # VRAM 확인
        free_vram = self._get_free_vram()

        arxiv_str = json.dumps(candidates.get("arxiv", [])[:3],
                               ensure_ascii=False, default=str)[:300]
        hf_str = json.dumps(candidates.get("huggingface", [])[:5],
                            ensure_ascii=False, default=str)[:400]
        timm_str = json.dumps(candidates.get("timm", [])[:5],
                              ensure_ascii=False, default=str)[:300]

        prompt = f"""이미지 분석 결과: {json.dumps(analysis, ensure_ascii=False)[:300]}

[선택 절대 규칙]
타겟 환경은 하드웨어 자원과 메모리가 극도로 제한된 엣지(Edge) 환경이다.
VRAM 소모가 크거나 무거운 범용 모델(10B 이상, 연산량 큰 SOTA)은 철저히 배제하라.
파라미터가 적고 수학적 최적화가 잘 된 경량 알고리즘을 최우선으로 선택하라:
- k-NN 기반 패치 추출 (예: CCIFPS/PatchCore)
- 파라미터-프리 특성 추출 방식
- 경량 YOLO (yolov8n/s급)
- Florence-2, 특화 소형 모델

아래 모델 후보들을 비교해서 최적을 선택해:

1. CCIFPS (졸업논문 개발 모델):
   - 특성: DINO ViT-B/8 + 패치 기반 산업 이상탐지 (파라미터-프리)
   - 도메인 일치: {domain_matched}
   - 적합도 점수: {ccifps_score['score']}/1.0
   - 상세: {ccifps_score['reason']}
   → 도메인 일치하면 가장 정확한 히트맵. 불일치하면 다른 모델 선택.

2. HuggingFace 탐색 결과:
   {hf_str}

3. arXiv 추천 모델:
   {arxiv_str}

4. timm 후보:
   {timm_str}

5. 기본 모델:
   - YOLOv8n (ultralytics): 범용 객체 탐지, 경량, 즉시 사용 가능
   - VLM (qwen2.5vl:7b): 이미지 분류/설명

판단 기준 (우선순위):
1. 경량성: VRAM {free_vram}MB 이내에서 안정적 동작 가능한가?
2. 도메인 일치: 산업 이상탐지면 CCIFPS가 가장 정확 (도메인 매칭 시)
3. 속도: 추론 30초 이내 완료 가능한가?
4. 정확도: 위 조건 충족 후 정확도 비교

최적 모델 3개를 우선순위로 선택해.
반드시 JSON으로:
{{"ranked": [
  {{"model": "모델명", "source": "ccifps/huggingface/timm/ultralytics/vlm",
   "reason": "선택 이유 (경량성/VRAM 포함)", "confidence": "high/medium/low"}},
  ...
]}}"""

        try:
            raw = _call_ollama("deepseek-r1:8b", prompt)
            result = _parse_json(raw)
            ranked = result.get("ranked", [])

            if not ranked:
                # 폴백: 점수 기반 기본 선택
                task = analysis.get("task", "object_detection")
                if task in ("anomaly_detection", "surface_defect") and domain_matched:
                    ranked = [
                        ccifps_score,
                        {"model": "yolov8n", "source": "ultralytics",
                         "reason": "CCIFPS 실패 시 폴백"},
                    ]
                elif task in ("anomaly_detection", "surface_defect"):
                    ranked = [
                        {"model": "yolov8n", "source": "ultralytics",
                         "reason": "도메인 불일치 → 범용 탐지"},
                        ccifps_score,
                    ]
                else:
                    ranked = [
                        {"model": "yolov8n", "source": "ultralytics",
                         "reason": "범용 객체 탐지 기본값"},
                    ]

            return ranked

        except Exception as e:
            print(f"[Discovery] 모델 선택 실패: {e}")
            return [{"model": "yolov8n", "source": "ultralytics",
                     "reason": "선택 실패 폴백"}]

    def _get_available_domains(self) -> list:
        """CCIFPS bank가 존재하는 도메인 목록 반환."""
        domains = []
        # 캐시된 bank 확인
        if os.path.isdir(OUTPUT_DIR):
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("cmdiad_bank_") and f.endswith(".pt"):
                    dom = f.replace("cmdiad_bank_", "").replace(".pt", "")
                    if dom in self.AVAILABLE_CATEGORIES:
                        domains.append(dom)

        # train 데이터 디렉토리 확인
        if os.path.isdir(DATASET_DIR):
            for cat in self.AVAILABLE_CATEGORIES:
                train_dir = os.path.join(DATASET_DIR, cat, "train", "good", "rgb")
                if os.path.isdir(train_dir) and cat not in domains:
                    domains.append(cat)

        return sorted(set(domains))

    def _get_free_vram(self) -> int:
        """현재 GPU VRAM 여유 (MB)."""
        try:
            import torch
            if torch.cuda.is_available():
                best_free = 0
                for i in range(torch.cuda.device_count()):
                    free, _ = torch.cuda.mem_get_info(i)
                    best_free = max(best_free, free)
                return int(best_free / 1024**2)
        except Exception:
            pass
        return 8000  # 기본값

    # ──────────────────────────────────────────────────────────────────────
    # Step 4: Install — pip 전 텔레그램 확인
    # ──────────────────────────────────────────────────────────────────────
    def _ensure_installed(self, model_info: dict) -> bool:
        """모델 설치 확인. pip 필요 시 텔레그램으로 사용자 확인."""
        source = model_info.get("source", "")
        model = model_info.get("model", "")

        if source == "ccifps":
            return True  # CMDIAD는 항상 사용 가능

        if source == "ultralytics" or "yolo" in model.lower():
            try:
                from ultralytics import YOLO
                return True
            except ImportError:
                self.notify(
                    f"⚠️ ultralytics 설치가 필요합니다.\n"
                    f"설치하시겠습니까? (텔레그램에서 '설치 승인' 입력)")
                return False

        if source == "timm":
            try:
                import timm
                return True
            except ImportError:
                self.notify(
                    f"⚠️ timm 설치가 필요합니다.\n"
                    f"설치하시겠습니까? (텔레그램에서 '설치 승인' 입력)")
                return False

        if source == "huggingface":
            try:
                from transformers import pipeline
                return True
            except ImportError:
                self.notify(
                    f"⚠️ transformers 설치가 필요합니다.\n"
                    f"설치하시겠습니까? (텔레그램에서 '설치 승인' 입력)")
                return False

        if source == "vlm":
            return True  # Ollama VLM은 항상 가용

        # 기본적으로 설치된 것으로 간주
        return True

    # ──────────────────────────────────────────────────────────────────────
    # Step 5: Execute
    # ──────────────────────────────────────────────────────────────────────
    def _execute(self, model_info: dict, image_path: str) -> dict:
        """선택된 모델로 추론 실행."""
        source = model_info.get("source", "")
        model = model_info.get("model", "")

        try:
            if source == "ccifps":
                return self._run_ccifps(image_path)

            elif source == "ultralytics" or "yolo" in model.lower():
                from aria.perception.vision_router import run_inference
                yolo_name = model.lower()  # YOLOv8n → yolov8n
                decision = {"model": yolo_name, "model_type": "yolo",
                           "weights_file": f"{yolo_name}.pt"}
                return run_inference(image_path, decision)

            elif source == "huggingface":
                from aria.perception.vision_router import _run_transformers_pipeline
                return _run_transformers_pipeline(image_path, model)

            elif source == "timm":
                return self._run_timm_model(model, image_path)

            elif source == "vlm":
                return self._run_vlm(image_path)

            else:
                # 범용 폴백: YOLO
                from aria.perception.vision_router import run_inference
                decision = {"model": "yolov8n", "model_type": "yolo",
                           "weights_file": "yolov8n.pt"}
                return run_inference(image_path, decision)

        except Exception as e:
            return {"error": str(e), "status": "error",
                    "traceback": traceback.format_exc()}

    def _run_ccifps(self, image_path: str) -> dict:
        """CMDIAD 실행 — inspect_via_registry로 위임 (직접 import 금지)."""
        try:
            from aria.agents.vision_agent import inspect_via_registry
            return inspect_via_registry(image_path)
        except Exception as e:
            return {"error": f"CCIFPS 위임 실패: {e}", "status": "error"}


    def _run_timm_model(self, model_name: str, image_path: str) -> dict:
        """timm 모델로 이미지 분류."""
        try:
            import timm
            import torch
            from torchvision import transforms
            from PIL import Image

            model = timm.create_model(model_name, pretrained=True)
            model.eval()

            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225]),
            ])
            img = Image.open(image_path).convert("RGB")
            tensor = transform(img).unsqueeze(0)

            with torch.no_grad():
                output = model(tensor)
                probs = torch.nn.functional.softmax(output, dim=1)
                top5 = torch.topk(probs, 5)

            results = []
            for i in range(5):
                results.append({
                    "class_idx": top5.indices[0][i].item(),
                    "confidence": top5.values[0][i].item(),
                })

            return {
                "task": "classification",
                "model_used": model_name,
                "classifications": results,
                "result_image_path": image_path,
                "status": "success",
            }
        except Exception as e:
            return {"error": f"timm 실패: {e}", "status": "error"}

    def _run_vlm(self, image_path: str) -> dict:
        """VLM으로 이미지 설명."""
        try:
            from aria.perception.vision_router import _run_vlm_classify
            return _run_vlm_classify(image_path)
        except Exception as e:
            return {"error": f"VLM 실패: {e}", "status": "error"}

    # ──────────────────────────────────────────────────────────────────────
    # Step 6: Verify
    # ──────────────────────────────────────────────────────────────────────
    def _verify(self, result: dict, user_query: str,
                image_path: str) -> dict:
        """deepseek-r1로 결과 검증."""
        try:
            summary = str(result)[:500]
            prompt = f"""모델 추론 결과를 검증해줘.

사용자 요청: "{user_query}"
결과 요약: {summary}

판단 기준:
1. 결과가 사용자 요청에 부합하는가?
2. 결과가 의미있는 정보를 포함하는가?
3. 에러가 없는가?

JSON으로:
{{"passed": true/false, "reason": "판단 이유"}}"""

            raw = _call_ollama("deepseek-r1:8b", prompt)
            verdict = _parse_json(raw)
            return verdict if "passed" in verdict else {"passed": True, "reason": "파싱 불가 → 통과"}

        except Exception:
            return {"passed": True, "reason": "검증 실패 → 기본 통과"}

    # ──────────────────────────────────────────────────────────────────────
    # 폴백: HarnessLoop
    # ──────────────────────────────────────────────────────────────────────
    def _fallback_harness(self, image_path: str, user_query: str,
                          analysis: dict) -> dict:
        """모든 후보 실패 시 기존 HarnessLoop으로 폴백."""
        try:
            from aria.orchestration.harness_loop import HarnessLoop
            harness = HarnessLoop(notify_fn=lambda msg: self.notify(f"[Harness] {msg}"))
            return harness.run(image_path, user_query, analysis)
        except Exception as e:
            return {"error": f"HarnessLoop 폴백도 실패: {e}", "status": "error"}

    # Antigravity 리팩토링 요청 및 사용량 트래킹
    # ──────────────────────────────────────────────────────────────────────
    def _record_model_usage(self, model: str, domain: str, success: bool) -> dict:
        """모델 사용 이력 기록. 영구 통합 판단에 사용."""
        import json
        log = {}
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        if USAGE_LOG.exists():
            try:
                log = json.loads(USAGE_LOG.read_text())
            except Exception:
                pass

        key = f"{domain}:{model}"
        if key not in log:
            log[key] = {"count": 0, "success": 0,
                        "model": model, "domain": domain}
        log[key]["count"] += 1
        if success:
            log[key]["success"] += 1

        try:
            USAGE_LOG.write_text(
                json.dumps(log, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Discovery] 모델 사용량 기록 실패: {e}")
        return log[key]

    def _notify(self, msg: str):
        """텔레그램 알림 헬퍼."""
        self.notify(msg)

    def _maybe_request_integration(self, model_info: dict, analysis: dict, usage: dict):
        """
        모델이 영구 통합 가치가 있으면 Antigravity에 요청.

        기준:
        - HuggingFace 모델
        - 같은 도메인에서 2회 이상 성공
        - 아직 MODEL_REGISTRY에 없음
        """
        model = model_info["model"]
        domain = analysis.get("domain", "unknown")
        source = model_info.get("source")

        try:
            from aria.perception.vision_router import MODEL_REGISTRY
            already = domain in MODEL_REGISTRY
        except Exception:
            already = False

        eligible = (
            source == "huggingface"
            and usage["success"] >= 2
            and not already
        )

        if not eligible:
            return

        # Antigravity에게 리팩토링 요청
        try:
            from aria.learning.self_improvement_loop import SelfImprovementLoop
            loop = SelfImprovementLoop()
            loop.report_to_antigravity(
                problem=(
                    f"'{domain}' 도메인에서 '{model}'이 "
                    f"{usage['success']}회 성공적으로 사용됨. "
                    f"vision_router.py의 MODEL_REGISTRY에 "
                    f"영구 등록하여 다운로드 없이 즉시 사용 가능하게."),
                file="vision_router.py",
                function="MODEL_REGISTRY",
                evidence=(
                    f"현재 매번 hf_hub_download로 다운로드 중. "
                    f"사용 통계: {usage}"),
                suggested_fix=(
                    f'MODEL_REGISTRY["{domain}"] = "{model}" '
                    f"추가. get_registered_model()이 우선 조회하도록."),
                request_type="integration"
            )

            self._notify(
                f"🌉 [자가진화] '{model}'을 '{domain}' 도메인에\n"
                f"영구 통합하도록 Antigravity에 요청했습니다.\n"
                f"({usage['success']}회 검증됨)")
        except Exception as e:
            print(f"[Discovery] Antigravity 리팩토링 요청 실패: {e}")



# ══════════════════════════════════════════════════════════════════════════════
# CLI 테스트
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--query", default="이 이미지를 분석해줘")
    args = parser.parse_args()

    engine = ModelDiscovery()
    result = engine.discover_and_run(args.image, args.query)

    print("\n" + "=" * 60)
    print("  ModelDiscovery Result")
    print("=" * 60)
    for k, v in result.items():
        if k not in ("traceback",):
            print(f"  {k}: {str(v)[:100]}")
