"""AnalystAgent — VLM 기반 이미지 상세 분석.
도메인, 태스크, 결함 유형, 재질 등을 파악."""

import json

from aria.agents.base_agent import BaseAgent


class AnalystAgent(BaseAgent):
    name = "analyst"
    description = "VLM 이미지 분석 — 도메인, 태스크, 결함 유형 파악"

    def run(self, user_input, image_path=None, context=None):
        if not image_path:
            return {"status": "error", "summary": "이미지가 필요합니다."}

        try:
            from aria.learning.model_discovery import ModelDiscovery
            discovery = ModelDiscovery()

            # 1. VLM 이미지 분석
            analysis = discovery._analyze(image_path, user_input)

            # 2. 백엔드 통계 데이터 분석 (ModelScout을 통해 피처 통계 추출)
            from aria.learning.model_scout import ModelScout
            scout = ModelScout()
            stats_data = scout.analyze_image_features(image_path)
            
            summary_parts = [
                "📊 이미지 분석 및 심층 통계 리포트 (ARIA)",
                f"  도메인: {analysis.get('domain', '?')}",
                f"  태스크: {analysis.get('task', '?')}",
                f"  대상: {analysis.get('object', analysis.get('scene', '?')[:50])}",
            ]

            if analysis.get("defect_type"):
                summary_parts.append(f"  결함유형: {analysis.get('defect_type')}")
            if analysis.get("material"):
                summary_parts.append(f"  재질: {analysis.get('material')}")

            if "error" not in stats_data:
                stats = stats_data["stats"]
                score = stats["score"]
                mean = stats["mean"]
                var = stats["variance"]
                ci_l = stats["ci_lower"]
                ci_u = stats["ci_upper"]
                
                # 통계적 신뢰성 검정 (Statistical Hypothesis Testing)
                # 귀무가설 H0: 샘플이 정상 분포에 속한다.
                # 대립가설 H1: 샘플이 정상 분포를 벗어난 이상치이다.
                # 임계값(ci_upper) 초과 시 p < 0.05 수준에서 H0 기각
                is_significant = score > ci_u
                sig_text = "⚠️ 통계적으로 유의미한 이상치 검출 (p < 0.05)" if is_significant else "✅ 통계적으로 정상 범위 내 존재 (p >= 0.05)"
                
                summary_parts.extend([
                    "\n📈 피처 분포 통계량 (Pure Numpy PCA):",
                    f"  - Anomaly Score (Max L2 Dist): {score:.3f}",
                    f"  - Mean L2 Distance: {mean:.3f}",
                    f"  - Variance: {var:.3f}",
                    f"  - 95% Confidence Interval: [{ci_l:.3f}, {ci_u:.3f}]",
                    f"  - 통계적 유의미도: {sig_text}"
                ])
                analysis["stats"] = stats
                analysis["pca_data"] = stats_data["pca_data"]
                analysis["statistical_significance"] = sig_text
            else:
                summary_parts.append(f"\n⚠️ 통계 분석 실패: {stats_data['error']}")

            # CCIFPS 적합성 체크
            available = discovery._get_available_domains()
            if available:
                summary_parts.append(f"\n  CCIFPS 가용 도메인: {', '.join(available)}")

            return {
                "status": "success",
                "summary": "\n".join(summary_parts),
                "data": analysis,
            }
        except Exception as e:
            return {"status": "error", "summary": f"분석 오류: {e}"}
