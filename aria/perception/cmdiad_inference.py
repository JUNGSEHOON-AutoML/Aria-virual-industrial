import os
import time
import math
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
import torch
import torch.nn.functional as F

# ── DINO & CMDIAD 경로 설정 ────────────────────────────────────────────────
# 환경변수 우선 → 로컬 워크스테이션 경로 폴백
# Docker 컨테이너: CMDIAD_DIR=/app, CHECKPOINT_BASE_PATH=/app/checkpoints 등으로 주입됨
# 로컬 실행:     .env의 값이 사용됨
_DEFAULT_CMDIAD_DIR = "/userHome/userhome4/sehoon/CMDIAD-main"
CMDIAD_DIR   = os.environ.get("CMDIAD_DIR", _DEFAULT_CMDIAD_DIR)
BANK_DIR     = os.environ.get(
    "BANK_DIR",
    os.path.join(CMDIAD_DIR, "results", "ccifps_banks"),
)
DATASET_DIR  = os.environ.get(
    "DATASET_BASE_PATH",
    os.path.join(CMDIAD_DIR, "datasets", "mvtec_3d"),
)
OUTPUT_DIR   = os.environ.get(
    "OUTPUT_DIR",
    "/userHome/userhome4/sehoon/Agentic-CCIFPS-main/outputs",
)
# DINO 체크포인트 (dino_vitbase8_pretrain.pth)
_DEFAULT_CKPT_DIR = os.path.join(CMDIAD_DIR, "checkpoints")
CHECKPOINT_DIR = os.environ.get("CHECKPOINT_BASE_PATH", _DEFAULT_CKPT_DIR)


AVAILABLE_CATEGORIES = []
try:
    from aria.core.product_registry import ProductRegistry
    AVAILABLE_CATEGORIES = [p["product_id"] for p in ProductRegistry().list_products()]
except Exception:
    pass

class DINOBackbone:
    """DINO ViT-B/8 피처 추출기."""
    def __init__(self, device="cuda", caller_context: str = "ProductRegistry"):
        """caller_context: 'ProductRegistry'(식별용) 또는 'CMDIADDetector'(이상탐지용) 중 하나.
        
        로그 접두어가 caller_context에 따라 달라져 혼선을 방지한다.
        - 'ProductRegistry' → [ProductRegistry/DINO] : 제품 식별용 임베딩
        - 'CMDIADDetector'  → [CMDIADDetector/DINO]  : 이상탐지 추론용 백본
        """
        import timm
        self.device = device
        self._log_prefix = f"  [{caller_context}/DINO]"
        print(f"{self._log_prefix} DINO ViT-B/8 backbone 로드 중 ({'제품 식별용 임베딩' if caller_context == 'ProductRegistry' else '이상탐지 추론용 백본'})...")
        
        # Local checkpoint path — CHECKPOINT_DIR 환경변수 또는 기본 경로 사용
        local_ckpt_path = os.path.join(CHECKPOINT_DIR, "dino_vitbase8_pretrain.pth")

        # Create model without pretraining first
        self.model = timm.create_model(
            model_name="vit_base_patch8_224_dino",
            pretrained=False,
        )
        if os.path.exists(local_ckpt_path):
            print(f"{self._log_prefix} 로컬 체크포인트 탐색 성공: {local_ckpt_path}")
            try:
                state_dict = torch.load(local_ckpt_path, map_location="cpu")
                if "model" in state_dict:
                    state_dict = state_dict["model"]
                self.model.load_state_dict(state_dict, strict=True)
                print(f"{self._log_prefix} 가중치 로딩 완료 (strict=True)")
            except Exception as e:
                print(f"{self._log_prefix} 로딩 실패 ({e}), strict=False 시도...")
                try:
                    state_dict = torch.load(local_ckpt_path, map_location="cpu")
                    if "model" in state_dict:
                        state_dict = state_dict["model"]
                    self.model.load_state_dict(state_dict, strict=False)
                    print(f"{self._log_prefix} 가중치 로딩 완료 (strict=False)")
                except Exception as ex:
                    print(f"{self._log_prefix} 로딩 완전 실패: {ex}. 온라인 가중치 다운로드.")
                    self.model = timm.create_model(
                        model_name="vit_base_patch8_224_dino",
                        pretrained=True,
                    )
        else:
            print(f"{self._log_prefix} 로컬 체크포인트 없음 → 온라인 가중치 다운로드.")
            self.model = timm.create_model(
                model_name="vit_base_patch8_224_dino",
                pretrained=True,
            )
            
        self.model.eval()
        self.model.to(device)
        print(f"{self._log_prefix} DINO ViT-B/8 backbone 로드 완료")

    @torch.no_grad()
    def extract_features(self, image_tensor: torch.Tensor) -> torch.Tensor:
        x = image_tensor.to(self.device)
        x = self.model.patch_embed(x)       # [1, 784, 768]
        x = self.model._pos_embed(x)        # [1, 785, 768]
        x = self.model.norm_pre(x)
        x = self.model.blocks(x)            # [1, 785, 768]
        x = self.model.norm(x)
        features = x[:, 1:]                 # CLS 토큰 제거 → [1, 784, 768]
        features = features.squeeze(0).cpu() # [784, 768]
        return features

def preprocess_image(image_path: str) -> torch.Tensor:
    """이미지를 DINO 입력 형식으로 변환 (224×224, ImageNet 정규화)."""
    from torchvision import transforms
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"이미지 로드 실패: {image_path}")
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    tensor = transform(img_rgb).unsqueeze(0)  # [1, 3, 224, 224]
    return tensor

class CMDIADInference:
    """CMDIAD RGB 전용 추론 엔진."""
    def __init__(self, device=None):
        from aria.core.resource.policy import choose_device
        if device is None:
            self.device, self.device_reason = choose_device()
        else:
            self.device = device
            self.device_reason = "명시적으로 디바이스 지정됨"
        print(f"  [CMDIAD] device={self.device} ({self.device_reason})")
        self.backbone = None
        self._bank_cache = {}  # 도메인별 bank 캐시

    @staticmethod
    def _pick_best_gpu():
        from aria.core.resource.policy import choose_device
        dev, _ = choose_device()
        return dev

    def _ensure_backbone(self, caller_context: str = "CMDIADDetector"):
        """caller_context: 'CMDIADDetector'(이상탐지) 또는 'ProductRegistry'(제품 식별) 중 하나."""
        if self.backbone is None:
            print(f"  [{caller_context}] DINO ViT-B/8 백본 로드 시작 (caller: {caller_context})...")
            self.backbone = DINOBackbone(self.device, caller_context=caller_context)

    def _load_train_bank(self, domain: str) -> dict:
        if domain in self._bank_cache:
            return self._bank_cache[domain]

        # 1. ProductRegistry에서 로드 시도
        try:
            from aria.core.product_registry import ProductRegistry
            registry = ProductRegistry()
            prod_info = registry.get(domain)
            if prod_info and os.path.exists(prod_info["memory_bank_path"]):
                print(f"  [CMDIAD] 레지스트리에서 bank 로드: {prod_info['memory_bank_path']}")
                bank_data = torch.load(prod_info["memory_bank_path"], map_location="cpu")
                self._bank_cache[domain] = bank_data
                return bank_data
        except Exception as e:
            print(f"  [CMDIAD] Registry 로딩 실패/건너뜀: {e}")

        cache_path = os.path.join(OUTPUT_DIR, f"cmdiad_bank_{domain}.pt")
        if os.path.exists(cache_path):
            print(f"  [CMDIAD] 캐시된 bank 로드: {cache_path}")
            bank_data = torch.load(cache_path, map_location="cpu")
            self._bank_cache[domain] = bank_data
            return bank_data

        # 2. 레지스트리에도 없고 캐시도 없을 경우, train_dir에서 동적 빌드
        train_dir = domain if os.path.isdir(domain) else os.path.join(DATASET_DIR, domain, "train", "good")
        if not os.path.isdir(train_dir):
            alt_dir = os.path.join(DATASET_DIR, domain, "train", "good", "rgb")
            if os.path.isdir(alt_dir):
                train_dir = alt_dir
            else:
                print(f"  [CMDIAD] train 디렉토리 없음: {train_dir}")
                return None

        print(f"  [CMDIAD] 정상 이미지 폴더에서 bank 빌드 중: {train_dir}")
        self._ensure_backbone()

        import glob
        extensions = ('*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG')
        image_files = []
        for ext in extensions:
            image_files.extend(glob.glob(os.path.join(train_dir, "**", ext), recursive=True))
        image_files = sorted(list(set(image_files)))

        if not image_files:
            print(f"  [CMDIAD] 폴더에 이미지가 없음: {train_dir}")
            return None

        all_patches = []
        max_images = min(len(image_files), 100)  # 최대 100장
        for i, img_path in enumerate(image_files[:max_images]):
            try:
                tensor = preprocess_image(img_path)
                features = self.backbone.extract_features(tensor)  # [784, 768]
                all_patches.append(features)
            except Exception as e:
                print(f"  [CMDIAD] 이미지 처리 실패 ({img_path}): {e}")

        if not all_patches:
            return None

        patch_lib = torch.cat(all_patches, dim=0)  # [N*784, 768]
        rgb_mean = torch.mean(patch_lib)
        rgb_std  = torch.std(patch_lib)
        patch_lib = (patch_lib - rgb_mean) / rgb_std

        # Coreset subsampling (10%)
        n_coreset = max(int(0.1 * patch_lib.shape[0]), 500)
        if patch_lib.shape[0] > n_coreset:
            indices = self._greedy_coreset(patch_lib, n_coreset)
            patch_lib = patch_lib[indices]

        bank_data = {
            "patch_lib": patch_lib,
            "rgb_mean": rgb_mean,
            "rgb_std": rgb_std,
            "domain": domain,
            "n_images": len(image_files[:max_images]),
            "n_patches": patch_lib.shape[0],
        }

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        torch.save(bank_data, cache_path)
        self._bank_cache[domain] = bank_data
        return bank_data

    def _greedy_coreset(self, z_lib: torch.Tensor, n: int) -> torch.Tensor:
        z = z_lib.half().cuda()
        select_idx = 0
        coreset_idx = [select_idx]
        last_item = z[select_idx:select_idx + 1]
        min_distances = torch.linalg.norm(z - last_item, dim=1, keepdims=True)

        for _ in range(n - 1):
            distances = torch.linalg.norm(z - last_item, dim=1, keepdims=True)
            min_distances = torch.minimum(distances, min_distances)
            select_idx = torch.argmax(min_distances).item()
            last_item = z[select_idx:select_idx + 1]
            min_distances[select_idx] = 0
            coreset_idx.append(select_idx)

        return torch.tensor(coreset_idx)

    def run(self, image_path: str, domain: str) -> dict:
        t0 = time.time()
        bank_data = self._load_train_bank(domain)
        if bank_data is None:
            return None

        patch_lib = bank_data["patch_lib"]
        rgb_mean  = bank_data["rgb_mean"]
        rgb_std   = bank_data["rgb_std"]

        self._ensure_backbone()
        test_tensor = preprocess_image(image_path)
        test_features = self.backbone.extract_features(test_tensor)  # [784, 768]
        test_features = (test_features - rgb_mean) / rgb_std

        dist = torch.cdist(test_features, patch_lib)  # [784, N_bank]
        min_val, min_idx = torch.min(dist, dim=1)      # [784]

        s_idx = torch.argmax(min_val)
        s_star = torch.max(min_val)

        m_test = test_features[s_idx].unsqueeze(0)
        m_star = patch_lib[min_idx[s_idx]].unsqueeze(0)
        w_dist = torch.cdist(m_star, patch_lib)
        _, nn_idx = torch.topk(w_dist, k=3, largest=False)
        m_star_knn = torch.linalg.norm(m_test - patch_lib[nn_idx[0, 1:]], dim=1)
        D = torch.sqrt(torch.tensor(float(test_features.shape[1])))
        w = 1 - (torch.exp(s_star / D) / (torch.sum(torch.exp(m_star_knn / D))))
        anomaly_score = (w * s_star).item()

        # Segmentation map (28×28 → 224×224)
        feat_size = int(math.sqrt(test_features.shape[0]))  # 28
        s_map = min_val.view(1, 1, feat_size, feat_size)
        s_map = F.interpolate(s_map, size=(224, 224), mode='bilinear', align_corners=False)
        s_map_np = s_map.squeeze().numpy()

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        orig = cv2.imread(image_path)
        orig_resized = cv2.resize(orig, (224, 224))
        
        s_map_norm = (s_map_np - s_map_np.min()) / (s_map_np.max() - s_map_np.min() + 1e-8)
        heatmap_color = cv2.applyColorMap((s_map_norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
        overlay = cv2.addWeighted(orig_resized, 0.5, heatmap_color, 0.5, 0)
        
        heatmap_path = os.path.join(OUTPUT_DIR, f"cmdiad_heatmap_{domain}_{ts}.png")
        cv2.imwrite(heatmap_path, overlay)
        
        elapsed = time.time() - t0
        return {
            "anomaly_score": anomaly_score,
            "heatmap_path": heatmap_path,
            "model_used": f"CMDIAD-DINO-CCIFPS ({domain})",
            "elapsed": elapsed,
            "device": self.device,
            "device_reason": self.device_reason
        }
