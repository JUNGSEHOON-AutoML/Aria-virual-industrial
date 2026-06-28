from __future__ import annotations
import os
import json
import time
import shutil
import glob
from pathlib import Path
from datetime import datetime
import numpy as np
import torch
import torch.nn.functional as F
# CMDIADInference dependency removed. Using config.backbone.
class ProductRegistry:
    def __init__(self, root: str = None):
        if not root:
            root = os.environ.get("ARIA_PRODUCTS_DIR", "products")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        
        self._cached_centroids = {}
        self._auto_enroll_mvtec_if_empty()

    def _auto_enroll_mvtec_if_empty(self):
        """레지스트리가 비어 있고 MVTec AD 데이터셋이 존재할 경우 자동 등록하여 하위 호환성 유지."""
        # meta.json이 있는 하위 폴더 개수 체크
        existing_products = [d for d in self.root.iterdir() if d.is_dir() and (d / "meta.json").exists()]
        if existing_products:
            return

        from aria.core.config.models import DATASET_DIR
        if not DATASET_DIR or not os.path.exists(DATASET_DIR):
            print(f"[ProductRegistry] DATASET_DIR ({DATASET_DIR})가 존재하지 않아 자동 등록을 건너뜁니다.")
            return

        print(f"[ProductRegistry] 레지스트리가 비어 있습니다. MVTec 카테고리를 스캔합니다: {DATASET_DIR}")
        for cat in os.listdir(DATASET_DIR):
            cat_dir = os.path.join(DATASET_DIR, cat)
            if not os.path.isdir(cat_dir):
                continue
            
            # train/good 폴더가 있는지 체크 (rgb 하위 포함)
            train_good = os.path.join(cat_dir, "train", "good")
            if os.path.isdir(train_good):
                print(f"[ProductRegistry] '{cat}' 제품을 자동으로 등록합니다...")
                try:
                    self.enroll(name=cat, good_images_dir=train_good)
                except Exception as e:
                    print(f"[ProductRegistry] '{cat}' 자동 등록 실패: {e}")

    def enroll(self, name: str, good_images_dir: str, *, backbone="dino_vit_b8") -> dict:
        """정상 이미지 폴더를 읽어 메모리뱅크 빌드 및 임계치 캘리브레이션 후 제품 등록."""
        print(f"[ProductRegistry] 제품 등록 시작 - 이름: {name}, 경로: {good_images_dir}")
        
        # 이미지 파일 검색 (재귀적 스캔)
        extensions = ('*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG')
        image_files = []
        for ext in extensions:
            image_files.extend(glob.glob(os.path.join(good_images_dir, "**", ext), recursive=True))
        image_files = sorted(list(set(image_files)))

        if not image_files:
            raise ValueError(f"정상 이미지 폴더에 이미지가 존재하지 않습니다: {good_images_dir}")

        from aria.core.config.backbone import get_backbone
        bb = get_backbone()

        all_patches = []
        img_vecs = []

        max_images = min(len(image_files), 100)
        enrolled_images = image_files[:max_images]

        for img_path in enrolled_images:
            try:
                features = bb.extract_features(img_path)  # [784, 768]
                all_patches.append(features)

                # 이미지당 L2 normalized 평균 임베딩 벡터 생성
                img_vec = torch.mean(features, dim=0)  # [768]
                img_vec_norm = F.normalize(img_vec, dim=-1)
                img_vecs.append(img_vec_norm)
            except Exception as e:
                print(f"[ProductRegistry] 이미지 처리 에러 ({img_path}): {e}")

        if not all_patches:
            raise RuntimeError("정상 이미지 임베딩 추출에 실패했습니다.")

        # 1) 메모리뱅크 빌드 (z-score 정규화 및 코어셋 추출)
        patch_lib = torch.cat(all_patches, dim=0)  # [N*784, 768]
        rgb_mean = torch.mean(patch_lib)
        rgb_std = torch.std(patch_lib)
        patch_lib = (patch_lib - rgb_mean) / rgb_std

        n_coreset = max(int(0.1 * patch_lib.shape[0]), 500)
        if patch_lib.shape[0] > n_coreset:
            indices = torch.randperm(patch_lib.shape[0])[:n_coreset]
            patch_lib = patch_lib[indices]

        # 2) Centroid (대표 벡터) 계산 및 정규화
        centroid = torch.mean(torch.stack(img_vecs), dim=0)
        centroid = F.normalize(centroid, dim=-1)

        # 영구 저장 디렉토리 생성
        product_id = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in name.lower()]).strip("_")
        if not product_id:
            product_id = f"product_{int(time.time())}"

        prod_dir = self.root / product_id
        prod_dir.mkdir(parents=True, exist_ok=True)

        # 임시 가중치 데이터
        bank_data = {
            "patch_lib": patch_lib,
            "rgb_mean": rgb_mean,
            "rgb_std": rgb_std,
            "centroid": centroid,
            "product_id": product_id,
            "n_images": len(enrolled_images),
            "n_patches": patch_lib.shape[0]
        }

        # 3) 저장 파일 쓰기 (임계값 캘리브레이션을 위해 먼저 저장)
        torch.save(bank_data, prod_dir / "memory_bank.pt")

        meta = {
            "product_id": product_id,
            "name": name,
            "good_images_dir": good_images_dir,
            "n_images": len(enrolled_images),
            "backbone": backbone,
            "enrolled_at": datetime.now().isoformat()
        }
        with open(prod_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # 레퍼런스 이미지 복사
        ref_dir = prod_dir / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        for idx, img_path in enumerate(enrolled_images[:5]):
            src_path = Path(img_path)
            dest_path = ref_dir / f"ref_{idx}{src_path.suffix}"
            try:
                shutil.copy(img_path, dest_path)
            except Exception:
                pass

        # 센트로이드 캐시 갱신
        self._cached_centroids[product_id] = centroid

        # 4) 임계값 캘리브레이션 (ThresholdCalibrator 위임)
        from aria.perception.threshold_calibrator import ThresholdCalibrator
        try:
            calibrator = ThresholdCalibrator(self)
            thresh_info = calibrator.calibrate(product_id)
            threshold = thresh_info.get("threshold", 15.0)
        except Exception as e:
            print(f"[ProductRegistry] 임계값 캘리브레이션 위임 실패: {e}")
            threshold = 15.0

        print(f"[ProductRegistry] 제품 등록 완료 - ID: {product_id}, Threshold: {threshold:.3f}")
        return {
            "product_id": product_id,
            "name": name,
            "n_images": len(enrolled_images),
            "threshold": threshold,
            "backbone": backbone
        }

    def list_products(self) -> list[dict]:
        """등록된 모든 제품 메타데이터 리스트 반환."""
        products = []
        if not self.root.exists():
            return products

        for d in self.root.iterdir():
            if d.is_dir() and (d / "meta.json").exists():
                try:
                    with open(d / "meta.json", "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    products.append(meta)
                except Exception:
                    pass
        return products

    def get(self, product_id: str) -> dict | None:
        """제품 상세 정보 조회."""
        prod_dir = self.root / product_id
        if not prod_dir.exists() or not (prod_dir / "meta.json").exists():
            return None

        try:
            with open(prod_dir / "meta.json", "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            threshold = 15.0
            if (prod_dir / "threshold.json").exists():
                with open(prod_dir / "threshold.json", "r", encoding="utf-8") as f:
                    t_info = json.load(f)
                    threshold = t_info.get("threshold", 15.0)

            ref_dir = prod_dir / "references"
            references = [str(p) for p in ref_dir.glob("*") if p.is_file()] if ref_dir.exists() else []

            return {
                "product_id": product_id,
                "name": meta.get("name", product_id),
                "memory_bank_path": str(prod_dir / "memory_bank.pt"),
                "threshold": threshold,
                "meta": meta,
                "references": references
            }
        except Exception:
            return None

    def identify(self, image_path: str, primary_object: str = None, scene_description: str = None) -> dict:
        """DINO 임베딩 코사인 유사도 및 VLM 힌트를 바탕으로 등록 제품 식별."""
        products = self.list_products()
        if not products:
            return {"product_id": None, "status": "unenrolled"}

        # 1. 쿼리 이미지 임베딩 추출 (ProductRegistry 식별 전용)
        from aria.core.config.backbone import get_backbone
        try:
            features = get_backbone().extract_features(image_path)
            query_vec = F.normalize(torch.mean(features, dim=0), dim=-1)
        except Exception as e:
            print(f"[ProductRegistry] Query 이미지 임베딩 추출 실패: {e}")
            return {"product_id": None, "status": "unenrolled"}

        best_prod_id = None
        best_sim = -1.0

        # 2. 유사도 계산
        for p in products:
            prod_id = p["product_id"]
            
            # Centroid 로드 및 캐시
            centroid = self._cached_centroids.get(prod_id)
            if centroid is None:
                try:
                    bank_path = self.root / prod_id / "memory_bank.pt"
                    bank_data = torch.load(bank_path, map_location="cpu")
                    centroid = bank_data["centroid"]
                    self._cached_centroids[prod_id] = centroid
                except Exception:
                    continue
            
            sim = torch.dot(query_vec, centroid).item()
            if sim > best_sim:
                best_sim = sim
                best_prod_id = prod_id

        # 3. 보조 매칭 (VLM 정보 활용)
        name_matched = False
        if best_prod_id and (primary_object or scene_description):
            p_info = self.get(best_prod_id)
            p_name = p_info["name"].lower() if p_info else ""
            p_id_lower = best_prod_id.lower()

            if primary_object:
                po = primary_object.lower()
                if po in p_name or po in p_id_lower or p_name in po:
                    name_matched = True
            
            if not name_matched and scene_description:
                sd = scene_description.lower()
                if p_name in sd or p_id_lower in sd:
                    name_matched = True

        print(f"[ProductRegistry] 식별 후보: {best_prod_id}, Similarity: {best_sim:.3f}, Name Matched: {name_matched}")

        # 매칭 임계치 설정
        # - DINO ViT-B/8 코사인 유사도는 도메인이 달라도(표 캡처, 문서 등) 0.85~0.94까지 나올 수 있음
        # - 0.95 이상: 실제 동일 도메인 등록 제품만 통과 (일반 이미지 오탐 방지)
        # - 0.92 초과 + name_matched: VLM 컨텍스트 힌트가 명확히 제품명과 일치할 때만 추가 허용
        STRICT_THRESHOLD = 0.95  # ← 0.92에서 상향 (일반 이미지 오탐 차단)
        LOOSE_THRESHOLD  = 0.92  # ← 0.88에서 상향 (name_matched 조건 강화)

        if best_sim >= STRICT_THRESHOLD:
            print(f"[ProductRegistry] ✓ enrolled 판정 (similarity={best_sim:.3f} >= {STRICT_THRESHOLD})")
            return {
                "product_id": best_prod_id,
                "status": "enrolled",
                "similarity": best_sim
            }
        elif best_sim >= LOOSE_THRESHOLD and name_matched:
            print(f"[ProductRegistry] ✓ enrolled 판정 (similarity={best_sim:.3f} >= {LOOSE_THRESHOLD} + name_matched)")
            return {
                "product_id": best_prod_id,
                "status": "enrolled",
                "similarity": best_sim
            }
        else:
            print(f"[ProductRegistry] ✕ unenrolled 판정 (similarity={best_sim:.3f} < threshold, name_matched={name_matched}) → VLM 라우팅")
            return {"product_id": None, "status": "unenrolled"}
