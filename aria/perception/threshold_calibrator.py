import os
import json
import numpy as np
from pathlib import Path

class ThresholdCalibrator:
    def __init__(self, registry=None):
        self._registry = registry
        self._threshold_cache = {}

    @property
    def registry(self):
        if self._registry is None:
            from aria.core.product_registry import ProductRegistry
            self._registry = ProductRegistry()
        return self._registry

    def calibrate(self, product_id: str) -> dict:
        """등록된 제품의 good_images_dir을 대상으로 캘리브레이션을 수동 재실행."""
        prod = self.registry.get(product_id)
        if not prod:
            raise ValueError(f"등록되지 않은 제품입니다: {product_id}")

        good_images_dir = prod["meta"].get("good_images_dir")
        if not good_images_dir or not os.path.exists(good_images_dir):
            raise FileNotFoundError(f"정상 이미지 경로를 찾을 수 없습니다: {good_images_dir}")

        import glob
        from aria.perception.cmdiad_inference import CMDIADInference, preprocess_image
        
        extensions = ('*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG')
        image_files = []
        for ext in extensions:
            image_files.extend(glob.glob(os.path.join(good_images_dir, "**", ext), recursive=True))
        image_files = sorted(list(set(image_files)))

        if not image_files:
            raise ValueError(f"정상 이미지 폴더에 이미지가 없습니다: {good_images_dir}")

        engine = CMDIADInference()
        max_images = min(len(image_files), 100)
        enrolled_images = image_files[:max_images]

        scores = []
        for img_path in enrolled_images:
            try:
                res = engine.run(img_path, product_id)
                if res and "anomaly_score" in res:
                    scores.append(res["anomaly_score"])
            except Exception as e:
                print(f"[ThresholdCalibrator] 캘리브레이션 추론 실패 ({img_path}): {e}")

        if scores:
            scores_np = np.array(scores)
            mean_score = float(np.mean(scores_np))
            std_score = float(np.std(scores_np))
            threshold = mean_score + 3.0 * std_score
            threshold = max(threshold, 5.0)  # 최소값 필터링
        else:
            mean_score = 0.0
            std_score = 0.0
            threshold = 15.0  # 기본값

        thresh_info = {
            "mean": mean_score,
            "std": std_score,
            "threshold": threshold,
            "n_images": len(scores)
        }

        # 저장
        prod_dir = self.registry.root / product_id
        prod_dir.mkdir(parents=True, exist_ok=True)
        with open(prod_dir / "threshold.json", "w", encoding="utf-8") as f:
            json.dump(thresh_info, f, ensure_ascii=False, indent=2)

        # 캐시 무효화 및 갱신
        self._threshold_cache[product_id] = threshold

        print(f"[ThresholdCalibrator] 캘리브레이션 완료 - 제품: {product_id}, Threshold: {threshold:.3f}")
        return thresh_info

    def get_threshold(self, product_id: str) -> float:
        """제품의 임계치 획득 (메모리 캐시 및 파일 로딩 우선)."""
        if product_id in self._threshold_cache:
            return self._threshold_cache[product_id]

        prod = self.registry.get(product_id)
        if prod:
            threshold = prod.get("threshold", 15.0)
            self._threshold_cache[product_id] = threshold
            return threshold

        return 15.0

    def get_decision(self, score: float, product_id: str) -> dict:
        """결정론적 판정 판결."""
        threshold = self.get_threshold(product_id)
        verdict = "fail" if score > threshold else "pass"
        margin = score - threshold
        return {
            "verdict": verdict,
            "threshold": threshold,
            "margin": margin,
            "score": score
        }
