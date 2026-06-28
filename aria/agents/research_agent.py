import os
"""ResearchAgent — 논문/모델 검색 서브 에이전트.
arXiv + HuggingFace MCP 래핑.
Phase 2: 도메인 특화 알고리즘 탐색 전담."""

import json
import urllib.request
import urllib.parse

from aria.agents.base_agent import BaseAgent

_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://172.17.0.1:11434")
OLLAMA_API = f"{_OLLAMA_BASE}/api/chat"

# 엣지 환경에서 배제할 무거운 모델 패턴
HEAVY_MODEL_PATTERNS = [
    "llama", "70b", "40b", "13b", "mixtral", "falcon",
    "bloom", "gpt", "opt-", "175b", "chatglm",
]


class ResearchAgent(BaseAgent):
    name = "research"
    description = "논문 검색, 모델 탐색, 학술 연구, arXiv, HuggingFace"

    # ──────────────────────────────────────────────────────────────────
    # scout(): Phase 2 전용 — model_discovery에서 위임받아 실행
    # ──────────────────────────────────────────────────────────────────
    def scout(self, analysis: dict) -> dict:
        """
        VLM 분석 결과를 받아 도메인 특화 모델/논문 탐색.

        Args:
            analysis: VLM이 출력한 dict (task, scene, objects, domain 등)

        Returns:
            {"candidates": [...], "arxiv": [...], "huggingface": [...], "timm": [...]}
        """
        task = analysis.get("task", "object_detection")
        scene = analysis.get("scene", "")
        domain = analysis.get("domain", "unknown")
        confidence = analysis.get("confidence_score", 0.5)

        print(f"[ResearchAgent] 🔍 엣지 환경에 적합한 알고리즘 탐색 중...")
        print(f"[ResearchAgent] 도메인={domain}, 태스크={task}, 확신도={confidence}")

        # 검색 쿼리 생성
        query = self._generate_query(
            f"{task} {scene} {domain} lightweight edge deployment",
            context={"analysis": analysis})

        arxiv_results = []
        hf_results = []
        timm_results = []
        max_retries = 3

        # ── arXiv 검색 (3회 재시도) ──
        for attempt in range(max_retries):
            try:
                arxiv_results = self._search_arxiv(query)
                if arxiv_results:
                    break
                print(f"[ResearchAgent] arXiv 시도 {attempt+1}/{max_retries}: 결과 없음")
            except Exception as e:
                print(f"[ResearchAgent] arXiv 시도 {attempt+1}/{max_retries} 실패: {e}")

        # ── HuggingFace 검색 (3회 재시도) ──
        for attempt in range(max_retries):
            try:
                hf_results = self._search_huggingface(query)
                if hf_results:
                    # 경량 모델 필터링 (GAP 3)
                    hf_results = self._filter_lightweight(hf_results)
                    break
                print(f"[ResearchAgent] HF 시도 {attempt+1}/{max_retries}: 결과 없음")
            except Exception as e:
                print(f"[ResearchAgent] HF 시도 {attempt+1}/{max_retries} 실패: {e}")

        # HF 결과가 없고 domain이 지정되어 있으면 간소화된 쿼리로 재시도
        if not hf_results and domain and domain != "unknown":
            fallback_query = f"{domain} defect" if "defect" not in domain.lower() else domain
            print(f"[ResearchAgent] HuggingFace 검색 결과 없음 → 간소화된 쿼리로 재시도: '{fallback_query}'")
            try:
                hf_results = self._search_huggingface(fallback_query)
                if hf_results:
                    hf_results = self._filter_lightweight(hf_results)
            except Exception as e:
                print(f"[ResearchAgent] HF 폴백 시도 실패: {e}")

        # ── timm 검색 ──
        try:
            timm_results = self._search_timm(task)
        except Exception as e:
            print(f"[ResearchAgent] timm 검색 실패: {e}")

        # ── 구조화된 candidates 생성 ──
        candidates = self._build_candidates(
            arxiv_results, hf_results, timm_results, analysis)

        total = len(arxiv_results) + len(hf_results) + len(timm_results)
        print(f"[ResearchAgent] 📚 논문/모델 검색 결과 {total}건 선별 완료")

        # ── Fallback: 아무것도 못 찾으면 기본 후보 ──
        if not candidates:
            print("[ResearchAgent] ⚠️ 유효한 후보 없음 → Fallback (ccifps/yolov8n)")
            candidates = [
                {"name": "ccifps", "source": "local",
                 "reason": "탐색 실패 시 기본 이상탐지 모델. k-NN 패치 기반 파라미터-프리."},
                {"name": "yolov8n", "source": "ultralytics",
                 "reason": "범용 경량 객체 탐지. VRAM 130MB."},
            ]

        return {
            "candidates": candidates,
            "arxiv": arxiv_results,
            "huggingface": hf_results,
            "timm": timm_results,
        }

    def _filter_lightweight(self, models: list) -> list:
        """무거운 모델 배제 (GAP 3 규칙)."""
        filtered = []
        for m in models:
            model_id = m.get("id", "").lower()
            is_heavy = any(p in model_id for p in HEAVY_MODEL_PATTERNS)
            if not is_heavy:
                filtered.append(m)
        if filtered:
            print(f"[ResearchAgent] 경량 필터: {len(models)} → {len(filtered)}개")
        return filtered or models[:3]  # 전부 무거우면 상위 3개 유지

    def _build_candidates(self, arxiv, hf, timm_models, analysis) -> list:
        """검색 결과를 명세서 규격의 candidates JSON으로 변환."""
        candidates = []

        for paper in arxiv[:2]:
            candidates.append({
                "name": paper.get("title", "")[:60],
                "source": "arXiv",
                "reason": paper.get("summary", "")[:150],
            })

        for model in hf[:3]:
            candidates.append({
                "name": model.get("id", "unknown"),
                "source": f"HuggingFace (⬇{model.get('downloads', 0):,})",
                "reason": f"HF 모델. 다운로드 {model.get('downloads', 0):,}회.",
            })

        for t in timm_models[:3]:
            if isinstance(t, str):
                candidates.append({
                    "name": t, "source": "timm",
                    "reason": "timm 사전학습 모델."})
            elif isinstance(t, dict):
                candidates.append({
                    "name": t.get("model", t.get("name", "unknown")),
                    "source": "timm",
                    "reason": t.get("reason", "timm 사전학습 모델."),
                })

        return candidates

    def _search_timm(self, task: str) -> list:
        """timm에서 경량 모델 검색. surface_defect/anomaly면 분류 모델 제외."""
        try:
            import timm
            all_models = timm.list_models(pretrained=True)

            if task in ("surface_defect", "anomaly_detection"):
                skip = ["resnet", "efficientnet", "vgg", "densenet",
                        "mobilenet", "inception", "convnext"]
                filtered = [m for m in all_models
                           if not any(s in m.lower() for s in skip)]
            else:
                filtered = all_models

            return filtered[:10]
        except Exception:
            return []

    # ──────────────────────────────────────────────────────────────────
    # run(): 기존 인터페이스 유지 (대화형 호출용)
    # ──────────────────────────────────────────────────────────────────
    def run(self, user_input, image_path=None, context=None):
        # deepseek-r1로 검색 쿼리 생성
        query = self._generate_query(user_input, context)

        results = []

        # arXiv 검색
        arxiv_results = self._search_arxiv(query)
        if arxiv_results:
            results.append(("arXiv", arxiv_results))

        # HuggingFace 검색
        hf_results = self._search_huggingface(query)
        if hf_results:
            results.append(("HuggingFace", hf_results))

        if not results:
            return {
                "status": "success",
                "summary": f"'{query}' 관련 검색 결과가 없습니다.",
            }

        summary = self._format_results(results)
        return {
            "status": "success",
            "summary": summary,
            "data": {"query": query, "results": results},
        }

    def _generate_query(self, user_input, context=None):
        """사용자 입력에서 검색 쿼리 추출."""
        try:
            prompt = f"""사용자가 다음을 요청했습니다: "{user_input}"

학술 논문/모델 검색에 적합한 영어 검색 쿼리를 생성해줘.
쿼리만 답해. 다른 설명 없이."""

            payload = json.dumps({
                "model": "deepseek-r1:8b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.0, "num_ctx": 1024},
            }).encode()

            req = urllib.request.Request(
                OLLAMA_API, data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())

            query = data["message"]["content"].strip()
            # <think> 태그 제거
            if "</think>" in query:
                query = query.split("</think>")[-1].strip()
            # 따옴표 제거
            query = query.strip('"\'')
            return query[:100]
        except Exception:
            return user_input[:50]

    def _search_arxiv(self, query):
        """arXiv API 검색."""
        try:
            q = urllib.parse.quote(query)
            url = (f"http://export.arxiv.org/api/query?"
                   f"search_query=all:{q}&max_results=3&sortBy=submittedDate")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode()

            # 간단 XML 파싱
            papers = []
            entries = text.split("<entry>")[1:]
            for entry in entries[:3]:
                title = entry.split("<title>")[1].split("</title>")[0].strip()
                summary = entry.split("<summary>")[1].split("</summary>")[0].strip()
                papers.append({
                    "title": title,
                    "summary": summary[:150],
                })
            return papers
        except Exception:
            return []

    def _search_huggingface(self, query):
        """HuggingFace MCP 또는 API를 통해 모델 검색."""
        print(f"  [Scout] Searching for HF models matching '{query}'...")
        
        # 1. MCP Hub가 사용 가능한 경우 우선적으로 search_models 도구 호출
        try:
            import sys
            # app 모듈 임포트 시도하여 mcp_client 확인
            if 'app' in sys.modules:
                app_module = sys.modules['app']
                if hasattr(app_module, 'mcp_client') and app_module.mcp_client and app_module.mcp_client.is_running():
                    print(f"  [Scout] 📡 huggingface_mcp.search_models 도구 호출 ('{query}')")
                    res = app_module.mcp_client.call_tool("huggingface.search_models", {"query": query, "max_results": 5})
                    if res and res.get("success") and "models" in res:
                        return [{"id": m["model_id"], "downloads": m.get("downloads_last_month", 0)} for m in res["models"]]
        except Exception as e:
            print(f"  [Scout] ⚠️ MCP search_models 호출 실패: {e}. Fallback to Web API.")

        # 2. Fallback: Web API 직접 호출
        try:
            q = urllib.parse.quote(query)
            url = f"https://huggingface.co/api/models?search={q}&limit=5&sort=downloads"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as r:
                models = json.loads(r.read())

            return [{"id": m["id"],
                     "downloads": m.get("downloads", 0)}
                    for m in models[:5]]
        except Exception:
            return []

    def _format_results(self, results):
        parts = []
        for source, items in results:
            parts.append(f"📚 {source}:")
            for item in items[:3]:
                if "title" in item:
                    parts.append(f"  • {item['title'][:80]}")
                elif "id" in item:
                    parts.append(f"  • {item['id']} "
                               f"(⬇{item.get('downloads', 0):,})")
        return "\n".join(parts)

