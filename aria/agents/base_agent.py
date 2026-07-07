"""
BaseAgent — 모든 서브 에이전트의 공통 인터페이스.

각 에이전트는 이 클래스를 상속하고 run()을 구현합니다.
"""

import time
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """서브 에이전트 베이스 클래스."""

    name: str = "base"
    description: str = "기본 에이전트"

    @abstractmethod
    def run(self, user_input: str, image_path: str = None,
            context: dict = None) -> dict:
        """
        에이전트 실행.

        Args:
            user_input: 사용자 요청 텍스트
            image_path: 이미지 경로 (선택)
            context: 이전 에이전트의 결과 딕셔너리 (순차 실행 시)

        Returns:
            dict: {
                "agent": 에이전트 이름,
                "status": "success" | "error",
                "summary": 결과 요약 (500자 이내),
                "data": 상세 데이터 (선택),
                "image_path": 결과 이미지 경로 (선택),
                "elapsed": 실행 시간 (초)
            }
        """
        raise NotImplementedError

    def safe_run(self, user_input: str, image_path: str = None,
                 context: dict = None, status_cb: callable = None) -> dict:
        """에이전트 실행 + 예외 처리 + 시간 측정."""
        if status_cb:
            status_cb(self.name, "running", detail=self.description)
        t0 = time.time()
        try:
            result = self.run(user_input, image_path, context)
            result["agent"] = self.name
            result["elapsed"] = round(time.time() - t0, 2)
            if result.get("status") is None:
                result["status"] = "success"
            
            if status_cb:
                elapsed_ms = int((time.time() - t0) * 1000)
                status_cb(self.name, "ok", elapsed_ms=elapsed_ms)
            return result
        except Exception as e:
            if status_cb:
                status_cb(self.name, "error", detail=str(e)[:120])
            return {
                "agent": self.name,
                "status": "error",
                "summary": f"[{self.name}] 오류: {str(e)[:200]}",
                "elapsed": round(time.time() - t0, 2),
            }
