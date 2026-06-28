"""detectors/ocr_defect_detector.py — OCR 기반 텍스트/라벨 검사 탐지기.

산업 활용:
  - 제품 라벨 글자 오인쇄 감지
  - 유통기한 형식 불일치 검사
  - 시리얼넘버 / 바코드 패턴 검증
  - 인쇄 품질 이상 탐지

v4 §1 규칙:
  - applicability()는 image_meta의 domain/primary_object/scene만 참조.
  - decision은 결정론적: 정규식 패턴 매칭 결과로만 결정.
  - 패턴 없을 때는 decision="n/a", 추출 텍스트만 반환.
  - PaddleOCR → Tesseract → qwen2.5vl 순 fallback 체인.
"""
from __future__ import annotations

import os
import re
import time


class OCRDefectDetector:
    """OCR 기반 텍스트/라벨 검사 탐지기.

    modality = "ocr_inspection"
    라벨, 바코드 영역의 텍스트를 추출하고 규격 패턴과 비교한다.
    """

    name     = "ocr_defect"
    modality = "ocr_inspection"

    # 라벨/텍스트 관련 키워드
    _LABEL_KEYWORDS = {
        "label", "tag", "barcode", "qr", "serial", "lot", "expiry",
        "date", "number", "code", "print", "text", "marking",
        "라벨", "바코드", "시리얼", "제조일", "유통기한", "인쇄", "마킹",
        "태그", "번호", "코드", "텍스트",
    }

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """텍스트/라벨/마킹이 포함된 산업 이미지에 최적.

        - domain == "label_inspect" → 0.95
        - primary_object / scene에 라벨 키워드 → 0.88
        - enrolled 제품 + label_pattern 있을 때 → 0.85
        - document/screenshot → 0.70 (VLMInspector와 경쟁)
        - industrial_anomaly unenrolled → 0.20
        - 기타 → 0.05
        """
        domain  = image_meta.get("domain", "")
        scene   = (image_meta.get("scene", "") + " " +
                   image_meta.get("primary_object", "")).lower()

        if domain == "label_inspect":
            return 0.95

        # 라벨 키워드 탐지
        for kw in self._LABEL_KEYWORDS:
            if kw in scene:
                # enrolled 제품에 패턴 정보가 있으면 더 높게
                if product and product.get("label_pattern"):
                    return 0.88
                return 0.82

        if domain in ("document", "screenshot"):
            return 0.70

        if product and product.get("label_pattern"):
            return 0.75

        if domain == "industrial_anomaly":
            return 0.20

        return 0.05

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """OCR로 텍스트를 추출하고 패턴 검증을 수행한다.

        Fallback 체인: PaddleOCR → Tesseract → qwen2.5vl

        Returns: Detector.run() 표준 스키마
        """
        print("  [OCRDefectDetector] OCR 텍스트 검사 구동")
        t0 = time.time()

        # product에서 검증 패턴 읽기
        label_pattern  = product.get("label_pattern")  if product else None
        expected_texts = product.get("expected_texts") if product else None

        # ── OCR 텍스트 추출 ───────────────────────────────────────────────
        ocr_results, overlay_path, model_name = self._extract_text(image_path)

        # ── 결정론적 판정 ─────────────────────────────────────────────────
        regions, decision, score = self._validate(
            ocr_results, label_pattern, expected_texts
        )

        elapsed = round(time.time() - t0, 2)
        all_text = " | ".join(r.get("text", "") for r in ocr_results)
        print(f"  [OCRDefectDetector] 완료 (texts={len(ocr_results)}, "
              f"decision={decision}, {elapsed}s)")
        print(f"  [OCRDefectDetector] 추출 텍스트: {all_text[:120]}")

        return {
            "score"        : score,
            "threshold"    : 0.5,
            "decision"     : decision,
            "confidence"   : 0.82,
            "render_type"  : "bounding_box",
            "overlay_path" : overlay_path or image_path,
            "regions"      : regions,
            "model_name"   : model_name,
            # OCR 전용 추가 필드
            "extracted_text": all_text,
            "label_pattern" : label_pattern,
        }

    # ── 텍스트 추출 (Fallback 체인) ───────────────────────────────────────

    def _extract_text(self, image_path: str) -> tuple[list, str | None, str]:
        """PaddleOCR → Tesseract → qwen2.5vl 순서로 시도."""

        # 1️⃣ PaddleOCR 시도
        results, overlay = self._try_paddleocr(image_path)
        if results:
            return results, overlay, "OCR Defect Inspector (PaddleOCR)"

        # 2️⃣ Tesseract 시도
        results, overlay = self._try_tesseract(image_path)
        if results:
            return results, overlay, "OCR Defect Inspector (Tesseract)"

        # 3️⃣ qwen2.5vl VLM fallback
        results, overlay = self._try_vlm(image_path)
        return results, overlay, "OCR Defect Inspector (VLM Fallback)"

    def _try_paddleocr(self, image_path: str) -> tuple[list, str | None]:
        try:
            from paddleocr import PaddleOCR
            import cv2
            from datetime import datetime
            from pathlib import Path

            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            result = ocr.ocr(image_path, cls=True)

            regions = []
            img     = cv2.imread(image_path)

            for line in (result[0] if result else []):
                box, (text, conf) = line
                regions.append({
                    "text"      : text,
                    "confidence": round(conf, 3),
                    "box"       : [list(map(int, pt)) for pt in box],
                    "valid"     : True,  # 패턴 검증은 _validate()에서
                })
                # 오버레이 그리기
                if img is not None:
                    pts = [[int(p[0]), int(p[1])] for p in box]
                    import numpy as np
                    cv2.polylines(img, [np.array(pts)], True, (0, 200, 50), 2)
                    cv2.putText(img, text, (pts[0][0], pts[0][1] - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 50), 1)

            if not regions:
                return [], None

            out_dir = Path(image_path).resolve().parent.parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = str(out_dir / f"ocr_paddle_{ts}.jpg")
            if img is not None:
                cv2.imwrite(out_path, img)

            return regions, out_path

        except ImportError:
            print("  [OCRDefectDetector] PaddleOCR 미설치 — Tesseract 시도")
            return [], None
        except Exception as e:
            print(f"  [OCRDefectDetector] PaddleOCR 오류: {e}")
            return [], None

    def _try_tesseract(self, image_path: str) -> tuple[list, str | None]:
        try:
            import subprocess
            import cv2
            from pathlib import Path
            from datetime import datetime

            # Tesseract 설치 확인
            res = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode != 0:
                return [], None

            # 이미지 전처리 (가독성 향상)
            img  = cv2.imread(image_path)
            if img is None:
                return [], None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255,
                                       cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                cv2.imwrite(tmp.name, binary)
                tess_res = subprocess.run(
                    ["tesseract", tmp.name, "stdout", "-l", "eng"],
                    capture_output=True, text=True, timeout=30
                )
                os.unlink(tmp.name)

            raw_text = tess_res.stdout.strip()
            if not raw_text:
                return [], None

            # 줄 단위로 분리
            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            regions = [{"text": l, "confidence": 0.7, "box": [], "valid": True}
                       for l in lines]
            return regions, None

        except FileNotFoundError:
            print("  [OCRDefectDetector] Tesseract 미설치 — VLM fallback 시도")
            return [], None
        except Exception as e:
            print(f"  [OCRDefectDetector] Tesseract 오류: {e}")
            return [], None

    def _try_vlm(self, image_path: str) -> tuple[list, str | None]:
        """qwen2.5vl로 텍스트 추출 (최후 fallback)."""
        try:
            import base64, json, urllib.request

            _OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
            OLLAMA_API   = f"{_OLLAMA_BASE}/api/chat"

            prompt = (
                "이 이미지에 보이는 모든 텍스트, 숫자, 코드, 날짜를 빠짐없이 추출하라. "
                "JSON 배열로만 응답하라. 예: "
                '[{"text": "LOT-2025-001", "location": "top-left"}, ...]'
            )

            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            payload = json.dumps({
                "model"   : "qwen2.5vl:7b",
                "messages": [{"role": "user", "content": prompt, "images": [b64]}],
                "stream"  : False,
            }).encode()

            req = urllib.request.Request(
                OLLAMA_API, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
                raw  = data["message"]["content"].strip()
                if "</think>" in raw:
                    raw = raw.split("</think>")[-1].strip()

            # JSON 배열 파싱
            start = raw.find("[")
            end   = raw.rfind("]") + 1
            items = json.loads(raw[start:end]) if start >= 0 else []

            regions = [
                {"text": item.get("text", ""), "confidence": 0.5,
                 "box": [], "valid": True, "location": item.get("location", "")}
                for item in items if item.get("text")
            ]
            return regions, None

        except Exception as e:
            print(f"  [OCRDefectDetector] VLM fallback도 실패: {e}")
            return [{"text": "OCR 추출 실패", "confidence": 0.0,
                     "box": [], "valid": False}], None

    # ── 패턴 검증 (결정론적) ──────────────────────────────────────────────

    @staticmethod
    def _validate(
        ocr_results: list,
        label_pattern: str | None,
        expected_texts: list | None,
    ) -> tuple[list, str, float]:
        """추출된 텍스트를 정규식 패턴/기대 텍스트와 비교."""

        if not ocr_results:
            return [], "n/a", 0.0

        if label_pattern is None and expected_texts is None:
            # 패턴 없음 → 추출만 반환
            return ocr_results, "n/a", 0.0

        fail_count = 0
        regions    = []

        for item in ocr_results:
            text  = item.get("text", "")
            valid = True
            reason = ""

            if label_pattern:
                if not re.search(label_pattern, text, re.IGNORECASE):
                    valid  = False
                    reason = f"패턴 불일치: '{label_pattern}'"
                    fail_count += 1

            if expected_texts and valid:
                matched = any(exp.lower() in text.lower() for exp in expected_texts)
                if not matched:
                    valid  = False
                    reason = f"기대 텍스트 없음: {expected_texts}"
                    fail_count += 1

            regions.append({**item, "valid": valid, "reason": reason})

        total = len(ocr_results)
        if fail_count == 0:
            return regions, "pass", 0.0

        score    = round(fail_count / total, 4)
        decision = "fail" if score >= 0.5 else "pass"
        return regions, decision, score
