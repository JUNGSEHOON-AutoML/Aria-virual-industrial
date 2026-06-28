# 👁️ SKILL: CCIFPS Anomaly Detector

## 1. Description
이 도구는 "클래스 조건부 비중복 특징 패치 선별(Class-Conditioned Irredundant Feature Patch Selection)" 알고리즘을 기반으로 한 초정밀/초경량 픽셀 단위 이상 탐지기다.
강한 반복 무늬(Repetitive Textures) 환경에서도 유사 패치로 인한 메모리 포화를 방지하고 이웃 간격을 유지하여 배경 유사 오탐을 획기적으로 줄인 신뢰도 높은 도구다.

## 2. Technical Specs

| 항목 | 사양 |
|---|---|
| **Backbone** | WideResNet-50 (layer2 + layer3, avg_pool2d 공간 융합) |
| **Feature Dim** | 1,536 (512ch + 1024ch, 채널 의미 완전 보존) |
| **Memory Bank** | `memory_bank.npy` (CC-IFPS로 사전 압축된 비중복 벡터) |
| **Distance Metric** | L2 distance 기반 k-NN scoring (k=1) |
| **Spatial Resolution** | 28×28 = 784 patches per image |

## 3. Algorithm Pipeline
```
[Feature Extraction]
  Input Image (224×224)
    → WideResNet-50 Forward
    → layer2: [512, 28, 28] + layer3: [1024, 14→28, 28]
    → 3×3 AvgPool2d (공간 스무딩, 채널 보존)
    → Channel Concat → [1536, 28, 28]
    → Reshape → [784 patches, 1536 dim]

[CC-IFPS Redundancy Removal (빌드 시)]
  전체 패치 (예: 163,856개)
    → L2 정규화 → 코사인 유사도 계산
    → Greedy 순회: sim ≥ τ(0.95) 중복 제거
    → 비중복 Memory Bank (예: 1,684개)

[Anomaly Scoring (추론 시)]
  Query [784, 1536] × Memory [M, 1536]
    → L2 거리 행렬 [784, M]
    → 각 Query의 1-NN 최소 거리 [784]
    → max(min_distances) = Anomaly Score
```

## 4. How to Use
- **Input**: `webcam_frame` (이미지 스트림) 또는 단일 이미지 파일
- **Output**: `{"status": "normal"|"anomaly", "score": float, "threshold": float}`
- **Execution**: 로컬 파이썬 스크립트 `local_agent.py`가 프레임을 처리하여 점수 반환

## 5. Agent Instruction
이 스킬에서 반환된 `score`가 임계값을 넘으면 제품 불량(스크래치, 이물질 등)이 확실시된다.
즉각 `MEMORY.md`에 불량 발생 시간과 점수를 기록하라.

## 6. Reference
> Jung, S. et al. "클래스 조건부 비중복 특징 패치 선별을 이용한 산업 이상 위치 탐지 연구"
