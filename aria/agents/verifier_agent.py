"""VerifierAgent — 추론 결과 품질 검증.
deepseek-r1이 결과가 사용자 요청에 부합하는지 판단."""

from aria.agents.base_agent import BaseAgent


class VerifierAgent(BaseAgent):
    name = "verifier"
    description = "추론 결과 검증 — 품질 평가 및 재시도 결정"

    def run(self, user_input, image_path=None, context=None):
        """
        context에서 이전 에이전트(executor)의 결과를 받아 검증.
        """
        if not context:
            return {"status": "error",
                    "summary": "검증할 결과가 없습니다."}

        # executor 결과 찾기
        exec_result = None
        for k, v in context.items():
            if isinstance(v, dict) and v.get("data"):
                exec_result = v.get("data", v)
                break

        if exec_result is None:
            exec_result = context

        try:
            from aria.learning.model_discovery import ModelDiscovery
            discovery = ModelDiscovery()
            verdict = discovery._verify(exec_result, user_input, image_path)

            passed = verdict.get("passed", False)
            reason = verdict.get("reason", "알 수 없음")

            emoji = "✅" if passed else "❌"
            summary = f"{emoji} 검증 결과: {'통과' if passed else '실패'}\n이유: {reason}"

            return {
                "status": "success",
                "summary": summary,
                "data": verdict,
            }
        except Exception as e:
            return {"status": "error", "summary": f"검증 오류: {e}"}
