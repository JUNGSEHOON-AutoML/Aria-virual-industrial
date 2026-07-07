"""detectors/segmentation_detector.py — 결함 영역 분리 및 면적 판정 탐지기.

산업 활용:
  - 스크래치/균열의 정확한 형상 및 면적 추출
  - 불량 면적 비율 산출 (전체 대비 결함 비율)
  - 결함 위치 정밀 보고 (상단/중앙/하단/좌/우)
  - unenrolled 산업 이미지에서 표면 이상 추정

v4 §1 규칙:
  - applicability()는 image_meta의 domain/defect_suspected만 참조.
  - decision은 결정론적: 마스크 면적 비율 vs 임계값 비교.
  - SAM 시도 → 실패 시 OpenCV Watershed/Canny 기반 fallback.
  - enrolled 제품은 CMDIAD가 담당하므로 applicability 낮게 설정.
"""
from __future__ import annotations

import os
import time


# 결함 마스크 면적 비율 기본 임계값 (전체 이미지 대비 2%)
DEFAULT_DEFECT_THRESHOLD = 0.02


class SegmentationDetector:
    """SAM + OpenCV Watershed 기반 결함 영역 분리 탐지기.

    modality = "segmentation"
    표면 이상 이미지에서 결함 영역을 마스크로 분리하고 면적 비율을 판정한다.
    """

    name     = "segmentation"
    modality = "segmentation"

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """표면 이상 + unenrolled 이미지에 최적.

        - enrolled 제품 → 0.05 (CMDIAD가 담당)
        - domain == "industrial_anomaly" + defect_suspected=True + unenrolled → 0.78
        - domain == "industrial_anomaly" + defect_suspected=False → 0.40
        - domain == "segmentation" (명시) → 0.90
        - general_object → 0.20
        - 기타 → 0.10
        """
        if product and product.get("status") == "enrolled":
            return 0.05

        domain          = image_meta.get("domain", "")
        defect_suspected = image_meta.get("defect_suspected", False)

        if domain == "segmentation":
            return 0.90

        if domain == "industrial_anomaly":
            if defect_suspected:
                return 0.78
            return 0.40

        if domain == "general_object":
            return 0.20

        return 0.10

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """SAM → OpenCV Watershed 순서로 결함 영역을 분리하고 면적 비율을 판정.

        Returns: Detector.run() 표준 스키마
        """
        print("  [SegmentationDetector] 결함 영역 분리 구동")
        t0 = time.time()

        # 임계값 설정
        threshold = DEFAULT_DEFECT_THRESHOLD
        if product:
            threshold = float(product.get("defect_area_threshold", DEFAULT_DEFECT_THRESHOLD))

        # ── SAM 시도 ─────────────────────────────────────────────────────
        mask_result = self._try_sam(image_path)
        model_name  = "Segmentation (SAM)"

        if mask_result is None:
            # ── OpenCV Fallback ──────────────────────────────────────────
            print("  [SegmentationDetector] SAM 미설치/실패 → OpenCV Watershed fallback")
            mask_result = self._opencv_watershed(image_path)
            model_name  = "Segmentation (OpenCV Watershed)"

        if mask_result is None:
            # 완전 실패
            return self._na_result("세그멘테이션 모든 방법 실패")

        defect_ratio  = mask_result["defect_ratio"]
        overlay_path  = mask_result["overlay_path"]
        regions       = mask_result["regions"]

        # ── 결정론적 판정 ─────────────────────────────────────────────────
        decision = "fail" if defect_ratio >= threshold else "pass"
        score    = round(min(defect_ratio / max(threshold, 1e-6), 1.0), 4)

        elapsed = round(time.time() - t0, 2)
        print(f"  [SegmentationDetector] 완료 (defect_ratio={defect_ratio:.4f}, "
              f"threshold={threshold:.4f}, decision={decision}, {elapsed}s)")

        return {
            "score"         : score,
            "threshold"     : threshold,
            "decision"      : decision,
            "confidence"    : 0.72,
            "render_type"   : "heatmap",
            "overlay_path"  : overlay_path,
            "regions"       : regions,
            "model_name"    : model_name,
            # 세그멘테이션 전용 추가 필드
            "defect_ratio"  : defect_ratio,
            "defect_percent": round(defect_ratio * 100, 2),
        }

    # ── SAM 추론 ─────────────────────────────────────────────────────────

    def _try_sam(self, image_path: str) -> dict | None:
        """SAM (Segment Anything Model)으로 결함 마스크 생성."""
        try:
            import torch
            from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
            import cv2
            import numpy as np
            from pathlib import Path
            from datetime import datetime

            # SAM 체크포인트 탐색
            base_dir = Path(image_path).resolve().parent.parent
            ckpt_candidates = [
                base_dir / "models" / "sam_vit_b_01ec64.pth",
                base_dir / "models" / "sam_vit_h_4b8939.pth",
                Path.home() / ".cache" / "sam" / "sam_vit_b_01ec64.pth",
            ]
            ckpt = next((p for p in ckpt_candidates if p.exists()), None)
            if ckpt is None:
                print("  [SegmentationDetector] SAM 체크포인트 없음 — fallback")
                return None

            model_type = "vit_h" if "vit_h" in ckpt.name else "vit_b"
            device     = "cuda" if torch.cuda.is_available() else "cpu"

            print(f"  [SegmentationDetector] SAM 로드 중 ({model_type}, {device})")
            sam   = sam_model_registry[model_type](checkpoint=str(ckpt))
            sam.to(device=device)
            generator = SamAutomaticMaskGenerator(
                sam,
                points_per_side=16,
                pred_iou_thresh=0.88,
                stability_score_thresh=0.95,
            )

            img      = cv2.imread(image_path)
            img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            masks    = generator.generate(img_rgb)

            # 전체 면적 대비 결함 마스크 비율 계산
            h, w = img.shape[:2]
            total_area  = h * w
            defect_mask = np.zeros((h, w), dtype=np.uint8)

            # 면적 기준 상위 마스크를 "결함 후보"로 취급
            masks.sort(key=lambda m: m["area"], reverse=True)
            # 1위(배경)를 제외하고 나머지를 결함으로 분류
            for m in masks[1:6]:
                defect_mask = np.logical_or(defect_mask, m["segmentation"]).astype(np.uint8)

            defect_ratio = float(defect_mask.sum()) / total_area

            # 컬러 오버레이
            overlay = img.copy()
            overlay[defect_mask == 1] = (0, 0, 200)  # 빨간색 마스크
            blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)
            cv2.putText(blended,
                f"Defect Area: {defect_ratio*100:.2f}% (SAM)",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 200, 255), 2)

            out_dir = Path(image_path).resolve().parent.parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = str(out_dir / f"seg_sam_{ts}.jpg")
            cv2.imwrite(out_path, blended)

            regions = self._mask_to_regions(defect_mask, masks[1:6], total_area)

            return {
                "defect_ratio" : defect_ratio,
                "overlay_path" : out_path,
                "regions"      : regions,
            }

        except ImportError:
            print("  [SegmentationDetector] segment-anything 미설치 — fallback")
            return None
        except Exception as e:
            print(f"  [SegmentationDetector] SAM 오류: {e}")
            return None

    # ── OpenCV Watershed Fallback ─────────────────────────────────────────

    def _opencv_watershed(self, image_path: str) -> dict | None:
        """OpenCV Watershed + GrabCut으로 결함 영역 추정."""
        import cv2
        import numpy as np
        from pathlib import Path
        from datetime import datetime

        try:
            img = cv2.imread(image_path)
            if img is None:
                return None

            h, w = img.shape[:2]
            total_area = h * w

            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Otsu 이진화
            _, binary = cv2.threshold(blurred, 0, 255,
                                       cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # 노이즈 제거
            kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)

            # 확실한 배경/전경 마커 생성
            sure_bg  = cv2.dilate(opening, kernel, iterations=3)
            dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
            _, sure_fg = cv2.threshold(
                dist_transform, 0.5 * dist_transform.max(), 255, 0
            )
            sure_fg  = sure_fg.astype(np.uint8)
            unknown  = cv2.subtract(sure_bg, sure_fg)

            # 레이블링
            _, markers = cv2.connectedComponents(sure_fg)
            markers    = markers + 1
            markers[unknown == 255] = 0

            img_color = img.copy()
            markers   = cv2.watershed(img_color, markers)

            # 결함 마스크 (-1은 경계선)
            defect_mask = (markers == -1).astype(np.uint8)

            # 경계선 팽창으로 결함 영역 확장
            defect_mask = cv2.dilate(defect_mask, kernel, iterations=2)
            defect_ratio = float(defect_mask.sum()) / total_area

            # 오버레이
            overlay = img.copy()
            overlay[defect_mask == 1] = (0, 0, 200)
            blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)
            cv2.putText(blended,
                f"Defect Area: {defect_ratio*100:.2f}% (Watershed)",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 200, 255), 2)

            # Canny 엣지로 보완 오버레이
            edges = cv2.Canny(blurred, 50, 150)
            blended[edges > 0] = (50, 200, 50)

            out_dir = Path(image_path).resolve().parent.parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = str(out_dir / f"seg_watershed_{ts}.jpg")
            cv2.imwrite(out_path, blended)

            # 결함 영역 위치 파악
            regions = self._defect_location(defect_mask, total_area)

            return {
                "defect_ratio" : defect_ratio,
                "overlay_path" : out_path,
                "regions"      : regions,
            }

        except Exception as e:
            print(f"  [SegmentationDetector] OpenCV Watershed 실패: {e}")
            return None

    # ── 헬퍼 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _mask_to_regions(defect_mask, sam_masks: list, total_area: int) -> list:
        """SAM 마스크 → regions 변환."""
        import numpy as np
        regions = []
        for i, m in enumerate(sam_masks):
            seg = m["segmentation"]
            area_ratio = float(seg.sum()) / total_area

            # 결함 bbox 계산
            rows = np.any(seg, axis=1)
            cols = np.any(seg, axis=0)
            rmin, rmax = np.where(rows)[0][[0, -1]] if rows.any() else (0, 0)
            cmin, cmax = np.where(cols)[0][[0, -1]] if cols.any() else (0, 0)

            cx = int((cmin + cmax) / 2)
            cy = int((rmin + rmax) / 2)
            h, w = seg.shape
            location = (
                ("top" if cy < h * 0.33 else "bottom" if cy > h * 0.67 else "center")
                + "-" +
                ("left" if cx < w * 0.33 else "right" if cx > w * 0.67 else "center")
            )

            regions.append({
                "id"         : i + 1,
                "bbox"       : [int(cmin), int(rmin), int(cmax - cmin), int(rmax - rmin)],
                "area_ratio" : round(area_ratio, 4),
                "location"   : location,
            })
        return regions

    @staticmethod
    def _defect_location(defect_mask, total_area: int) -> list:
        """OpenCV 마스크에서 결함 위치 파악."""
        import cv2
        import numpy as np
        from datetime import datetime

        try:
            contours, _ = cv2.findContours(
                defect_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            h, w = defect_mask.shape
            regions = []
            for i, c in enumerate(contours[:5]):
                area = cv2.contourArea(c)
                if area < 5:
                    continue
                x, y, bw, bh = cv2.boundingRect(c)
                cx, cy = x + bw // 2, y + bh // 2
                loc_v = "top" if cy < h * 0.33 else ("bottom" if cy > h * 0.67 else "center")
                loc_h = "left" if cx < w * 0.33 else ("right" if cx > w * 0.67 else "center")
                regions.append({
                    "id"         : i + 1,
                    "bbox"       : [x, y, bw, bh],
                    "area_ratio" : round(area / total_area, 4),
                    "location"   : f"{loc_v}-{loc_h}",
                })
            return regions
        except Exception:
            return []

    @staticmethod
    def _na_result(reason: str) -> dict:
        return {
            "score"       : 0.0,
            "threshold"   : DEFAULT_DEFECT_THRESHOLD,
            "decision"    : "n/a",
            "confidence"  : 0.0,
            "render_type" : "none",
            "overlay_path": None,
            "regions"     : [],
            "model_name"  : "SegmentationDetector (N/A)",
            "_reason"     : reason,
        }
