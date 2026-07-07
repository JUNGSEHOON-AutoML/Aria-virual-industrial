"""
local_agent.py — CCIFPS 실시간 이상 탐지 추론 에이전트 (로컬 실행용)

역할:
  1. memory_bank.npy를 로드하여 정상 패턴 참조 데이터로 사용
  2. OpenCV 웹캠(index 0)으로 실시간 프레임 캡처
  3. WideResNet-50(CPU)으로 패치 특징 추출
  4. k-NN 최단 거리 기반 Anomaly Score 계산
  5. 프레임에 Score 오버레이하여 실시간 표시

사용법:
  python local_agent.py --memory memory_bank.npy --threshold 15.0
"""

import argparse
import os
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as transforms


# ──────────────────────────────────────────────
# 1. Feature Extractor (build_memory.py와 동일 구조)
# ──────────────────────────────────────────────
class FeatureExtractor:
    """WideResNet-50 중간 레이어에서 패치 특징을 추출한다 (CPU 모드)."""

    def __init__(self, layers=("layer2", "layer3"), device="cpu"):
        self.device = torch.device(device)
        self.layers = layers
        self.outputs = {}

        print("[모델] WideResNet-50 로딩 중 (CPU 모드)...")
        self.model = models.wide_resnet50_2(pretrained=True).to(self.device)
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad = False

        self._register_hooks()

        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])
        print("[모델] ✓ 로드 완료")

    def _register_hooks(self):
        for layer_name in self.layers:
            layer = dict(self.model.named_modules())[layer_name]
            layer.register_forward_hook(self._make_hook(layer_name))

    def _make_hook(self, name):
        def hook(_module, _input, output):
            self.outputs[name] = output
        return hook

    def extract(self, frame_bgr):
        """
        OpenCV BGR 프레임 → 패치 특징 [N_patches, 1024]
        """
        # BGR → RGB 변환 후 전처리
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img_tensor = self.transform(frame_rgb).unsqueeze(0).to(self.device)

        self.outputs.clear()
        with torch.no_grad():
            _ = self.model(img_tensor)

        features_list = []
        ref_shape = None

        for layer_name in self.layers:
            feat = self.outputs[layer_name]

            if ref_shape is None:
                ref_shape = (feat.shape[2], feat.shape[3])
            elif (feat.shape[2], feat.shape[3]) != ref_shape:
                feat = F.interpolate(
                    feat, size=ref_shape, mode="bilinear", align_corners=False
                )

            # 3×3 AvgPool2d: 공간적 스무딩 (채널 수 C 그대로 유지)
            feat = F.avg_pool2d(feat, kernel_size=3, stride=1, padding=1)
            features_list.append(feat)

        # 레이어별 특징 병합: [1, 1536, H, W]
        concat_features = torch.cat(features_list, dim=1)

        # 패치(픽셀) 단위로 펼치기: [H*W, 1536]
        N_patches = concat_features.shape[2] * concat_features.shape[3]
        pooled = concat_features.permute(0, 2, 3, 1).reshape(N_patches, -1)

        return pooled.cpu().numpy()


# ──────────────────────────────────────────────
# 2. k-NN Anomaly Scorer
# ──────────────────────────────────────────────
class KNNScorer:
    """Memory Bank에 대한 k-NN 기반 Anomaly Score 계산."""

    def __init__(self, memory_bank, k=1):
        """
        Args:
            memory_bank: np.ndarray [M, D] — 정상 패턴 메모리 뱅크
            k: int — k-Nearest Neighbours 수
        """
        self.memory_bank = memory_bank.astype(np.float32)
        self.k = k
        print(f"[Scorer] Memory Bank: {self.memory_bank.shape[0]} patches, "
              f"dim={self.memory_bank.shape[1]}, k={k}")

    def score(self, query_features):
        """
        query 패치들과 메모리 뱅크 간 k-NN 최단 거리의 최대값을 Anomaly Score로 반환.

        Args:
            query_features: np.ndarray [N, D]

        Returns:
            float — Anomaly Score (높을수록 이상)
        """
        query = query_features.astype(np.float32)

        # L2 거리 계산 (효율적 구현)
        # ||q - m||^2 = ||q||^2 + ||m||^2 - 2*q·m
        q_sq = np.sum(query ** 2, axis=1, keepdims=True)       # [N, 1]
        m_sq = np.sum(self.memory_bank ** 2, axis=1)           # [M]
        dot = query @ self.memory_bank.T                        # [N, M]
        distances = q_sq + m_sq - 2 * dot                      # [N, M]
        distances = np.maximum(distances, 0)                    # 수치 안정성

        # 각 쿼리 패치의 k-NN 최소 거리
        if self.k == 1:
            min_distances = np.min(distances, axis=1)           # [N]
        else:
            # k개 최소 거리의 평균
            k_nearest = np.partition(distances, self.k, axis=1)[:, :self.k]
            min_distances = np.mean(k_nearest, axis=1)          # [N]

        # 이미지 레벨 점수: 패치별 최소 거리의 최대값
        anomaly_score = float(np.max(min_distances))
        return anomaly_score


# ──────────────────────────────────────────────
# 3. 실시간 추론 루프
# ──────────────────────────────────────────────
def draw_overlay(frame, score, threshold, fps):
    """프레임에 Anomaly Score 및 상태 정보를 오버레이한다."""
    h, w = frame.shape[:2]
    is_anomaly = score > threshold

    # 상단 바 배경
    bar_color = (0, 0, 180) if is_anomaly else (0, 140, 0)
    cv2.rectangle(frame, (0, 0), (w, 80), bar_color, -1)

    # 상태 텍스트
    status = "⚠ ANOMALY DETECTED" if is_anomaly else "✓ NORMAL"
    cv2.putText(
        frame, status, (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
    )

    # Score 표시
    cv2.putText(
        frame, f"Score: {score:.2f}  (Threshold: {threshold:.1f})",
        (15, 55),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1
    )

    # FPS 표시
    cv2.putText(
        frame, f"FPS: {fps:.1f}", (w - 120, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1
    )

    # 이상 시 빨간 테두리
    if is_anomaly:
        cv2.rectangle(frame, (2, 2), (w - 2, h - 2), (0, 0, 255), 4)

    return frame


def main():
    parser = argparse.ArgumentParser(
        description="CCIFPS 실시간 이상 탐지 에이전트"
    )
    parser.add_argument(
        "--memory", type=str, default="memory_bank.npy",
        help="Memory Bank 파일 경로 (.npy)"
    )
    parser.add_argument(
        "--threshold", type=float, default=15.0,
        help="이상 판정 임계값 (Score > threshold → 이상)"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="웹캠 인덱스 (기본값: 0)"
    )
    parser.add_argument(
        "--k", type=int, default=1,
        help="k-NN에서 사용할 k값 (기본값: 1)"
    )
    parser.add_argument(
        "--device", type=str, default="cpu",
        help="추론 디바이스 (기본값: cpu)"
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  CCIFPS Real-Time Anomaly Detection Agent")
    print(f"{'='*60}")

    # Step 1: Memory Bank 로드
    if not os.path.exists(args.memory):
        print(f"\n❌ 오류: '{args.memory}' 파일을 찾을 수 없습니다.")
        print(f"   먼저 build_memory.py를 실행하여 Memory Bank를 생성하세요:")
        print(f"   $ python build_memory.py --data_dir ./data/bottle/train/good")
        return

    print(f"\n[Step 1] Memory Bank 로딩: {args.memory}")
    memory_bank = np.load(args.memory)
    print(f"  ✓ {memory_bank.shape[0]} patches, dim={memory_bank.shape[1]}")

    # Step 2: 모델 & Scorer 초기화
    print(f"\n[Step 2] Feature Extractor 초기화 (device={args.device})")
    extractor = FeatureExtractor(device=args.device)
    scorer = KNNScorer(memory_bank, k=args.k)

    # Step 3: 웹캠 실시간 추론 루프
    print(f"\n[Step 3] 웹캠 열기 (index={args.camera})")
    cap = cv2.VideoCapture(args.camera)

    if not cap.isOpened():
        print(f"\n❌ 오류: 웹캠(index={args.camera})을 열 수 없습니다.")
        print(f"   카메라가 연결되어 있는지 확인하세요.")
        return

    print(f"\n{'='*60}")
    print(f"  🎥 실시간 추론 시작!")
    print(f"  Threshold : {args.threshold}")
    print(f"  종료      : 'q' 키를 누르세요")
    print(f"{'='*60}\n")

    frame_count = 0
    fps = 0.0
    fps_start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[경고] 프레임 읽기 실패, 재시도 중...")
                continue

            # 특징 추출 & 스코어링
            t0 = time.time()
            features = extractor.extract(frame)
            score = scorer.score(features)
            infer_time = (time.time() - t0) * 1000  # ms

            # FPS 계산
            frame_count += 1
            elapsed = time.time() - fps_start_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                fps_start_time = time.time()

            # 오버레이 그리기
            display = draw_overlay(frame.copy(), score, args.threshold, fps)

            # 하단에 추론 시간 표시
            cv2.putText(
                display,
                f"Inference: {infer_time:.0f}ms",
                (15, frame.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1
            )

            cv2.imshow("CCIFPS Anomaly Detection", display)

            # 'q' 키로 종료
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\n[종료] Ctrl+C 감지")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("\n✅ 실시간 추론 종료")


if __name__ == "__main__":
    main()
