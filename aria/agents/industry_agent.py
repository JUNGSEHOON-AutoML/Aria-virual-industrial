"""IndustryAgent — CMDIAD 산업 이상탐지 전용 에이전트.
v4: CMDIADDetector(레지스트리)로 교체. cmdiad_inference 직접 import 제거."""

from aria.agents.base_agent import BaseAgent


class IndustryAgent(BaseAgent):
    name = "industry"
    description = "CMDIAD 기반 산업 이상탐지, MVTec 3D, 결함 탐지"

    def run(self, user_input, image_path=None, context=None):
        if not image_path:
            return {
                "status": "error",
                "summary": "산업 이상탐지는 이미지가 필요합니다.",
            }

        try:
            from aria.perception.detectors.cmdiad_detector import CMDIADDetector
            det = CMDIADDetector()
            result = det.run(image_path, product=None)

            score    = result.get("score", 0.0)
            thr      = result.get("threshold", 0.5)
            decision = result.get("decision", "n/a")
            det_name = result.get("model_name", "CMDIADDetector")

            return {
                "status": "success",
                "summary": (f"🔬 CMDIAD 이상탐지\n"
                           f"결과: {decision}\n"
                           f"Anomaly Score: {score:.3f} (임계값: {thr:.3f})\n"
                           f"모델: {det_name}"),
                "result_image_path": result.get("overlay_path"),
                "data": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "summary": f"IndustryAgent 오류: {e}",
            }
