"""ScoutAgent — arXiv + HuggingFace + timm 모델 탐색.
ModelDiscovery의 _scout_parallel()을 에이전트로 래핑."""

from aria.agents.base_agent import BaseAgent


class ScoutAgent(BaseAgent):
    name = "scout"
    description = "arXiv 논문 + HuggingFace + timm 모델 탐색"

    def run(self, user_input, image_path=None, context=None):
        try:
            from aria.learning.model_discovery import ModelDiscovery
            discovery = ModelDiscovery()

            # context에서 analysis 가져오거나 기본값
            analysis = {}
            if context and isinstance(context, dict):
                for v in context.values():
                    if isinstance(v, dict) and v.get("task"):
                        analysis = v
                        break

            if not analysis:
                analysis = {"task": "object_detection", "scene": user_input}

            candidates = discovery._scout_parallel(analysis)

            n_arxiv = len(candidates.get("arxiv", []))
            n_hf = len(candidates.get("huggingface", []))
            n_timm = len(candidates.get("timm", []))

            summary_parts = [f"🔍 모델 탐색 결과:"]
            summary_parts.append(f"  arXiv: {n_arxiv}편")
            summary_parts.append(f"  HuggingFace: {n_hf}개")
            summary_parts.append(f"  timm: {n_timm}개")

            # 상위 후보 표시
            for source, items in candidates.items():
                for item in items[:2]:
                    if isinstance(item, dict):
                        name = item.get("model", item.get("title", "?"))
                        summary_parts.append(f"  • [{source}] {name[:60]}")

            return {
                "status": "success",
                "summary": "\n".join(summary_parts),
                "data": candidates,
            }
        except Exception as e:
            return {"status": "error", "summary": f"Scout 오류: {e}"}
