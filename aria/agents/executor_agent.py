"""ExecutorAgent — 모델 추론 실행.
선택된 모델을 설치하고 추론을 실행."""

from aria.agents.base_agent import BaseAgent


class ExecutorAgent(BaseAgent):
    name = "executor"
    description = "모델 설치 및 추론 실행"

    def run(self, user_input, image_path=None, context=None):
        if not image_path:
            return {"status": "error", "summary": "이미지가 필요합니다."}

        # context에서 모델 선택 결과 가져오기
        model_info = None
        if context:
            for v in context.values():
                if isinstance(v, dict):
                    data = v.get("data", {})
                    if isinstance(data, list) and data:
                        model_info = data[0]  # ranked[0]
                    elif isinstance(data, dict) and data.get("model"):
                        model_info = data

        # 기본 모델
        if not model_info:
            model_info = {
                "model": "yolov8n",
                "source": "ultralytics",
                "reason": "기본 객체 탐지",
            }

        try:
            from aria.learning.model_discovery import ModelDiscovery
            discovery = ModelDiscovery()

            # 설치 확인
            installed = discovery._ensure_installed(model_info)
            if not installed:
                return {
                    "status": "error",
                    "summary": f"⚠️ {model_info['model']} 설치 실패",
                }

            # 실행
            result = discovery._execute(model_info, image_path)
            model_name = model_info.get("model", "?")

            if result.get("error"):
                return {
                    "status": "error",
                    "summary": f"⚠️ {model_name} 실행 실패: {result['error'][:80]}",
                }

            return {
                "status": "success",
                "summary": f"✅ {model_name} 추론 완료",
                "result_image_path": result.get("result_image_path"),
                "data": result,
            }

        except Exception as e:
            return {"status": "error", "summary": f"Executor 오류: {e}"}
