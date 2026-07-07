# ARIA 구현 명세서 (Implementation Spec) — 핸드오프용

> 브랜치 `claude/busy-wright-cb336r` 에 구현된 내용의 단일 명세.
> 목적: 이 문서만 보면 (사람·AI가) 무엇이 어떻게 동작하는지, 어떤 계약(스키마·엔드포인트)을
> 가지는지, 어떻게 실행/통합하는지 파악할 수 있게 한다.
> 작성 시점 기준 tip: `a8bb2a7`.

---

## 0. 배경 (왜 이 구조인가)

두 차례 시도(구 god-file ARIA, ARIArefactored)가 안정성·탐지·유지보수·데모가치에서
실패. 원인 = ① 범위 폭주, ② LLM을 제어 흐름의 핵심에 둠(→방어 패치 누적),
③ god-file(2,750/2,250줄), ④ 무거운 로컬모델 필수 의존. 참고 레포(xlerobot,
mobile_robot)의 교훈 = **한 도메인 수직 슬라이스 + 결정론 제어 + ML은 부품 + 레이어드**.
→ 이 명세의 모든 코드는 **god-file과 분리된 깨끗한 새 모듈**이며, **LLM 라우터가 없다.**
설계 배경 전문: `docs/REDESIGN.md`.

---

## 1. 커밋 이력 (이 브랜치에서 쌓은 것)

| 커밋 | 내용 |
|------|------|
| `febbb00` | 문서 체계 재구성(단일 TOC) + 1회용 spec 40개 아카이브 |
| `0a91e32` | 포폴 North Star 재설계(`docs/REDESIGN.md`) |
| `68b0d0e` | **M1**: 결정론 검사 코어 `/api/inspect` + 히트맵 + 독립 UI |
| `e1cdb63` | **M3+텔레메트리**: 2D 디지털 트윈 + GPU/발열 모니터 |
| `a8bb2a7` | **3D 트윈**: Three.js 3D 라인 + 현실 공장 지표(택트·처리량·설비상태) |

---

## 2. 모듈 지도

```
pipeline/            결정론 검사 파이프라인 (핵심)
  inspector.py       OODA 진입점: image → score → verdict → heatmap
  scorer.py          BankScorer(실제 DINO+뱅크) / FallbackScorer(numpy+PIL)
  heatmap.py         패치점수 → 컬러 히트맵 오버레이
  twin.py            FactoryTwin — 디지털 트윈 라인 + 현실 공장 지표
hardware/
  telemetry.py       GPU 온도/VRAM/util + CPU/RAM + 학습부하·발열 추정
  monitor.py         (기존) pynvml+psutil 원시 스냅샷 — telemetry가 재사용
api/
  inspect.py         POST /api/inspect (단일 검사)
  twin.py            WS /ws/twin + REST (트윈·텔레메트리)
inspect_app.py       독립 서버 + UI 3종(/, /twin, /twin3d) + /vendor 마운트
scorer/feature_bank.py   (기존) + cosine_patch_scores_features 추가(히트맵용)
static/vendor/three/     three.js 로컬 번들(CDN 의존 제거)
tests/                   24개 (torch/GPU 불필요, 폴백 경로로 전부 검증)
```

---

## 3. 데이터 계약 (Contracts) — 통합 시 이 스키마를 따르세요

### 3-1. 검사 결과 `InspectResult` (`POST /api/inspect` 응답)
```json
{
  "score": 0.8363,            // 이미지 이상 점수 (높을수록 이상)
  "threshold": 0.5,           // 판정 기준
  "decision": "NG",           // "OK" | "NG"  (결정론: score>=threshold → NG)
  "model_name": "classical-residual (fallback)",  // 또는 "dino_vit_b8+cosine-bank"
  "is_fallback": true,        // 폴백 스코어러 사용 여부
  "grid": [32, 32],           // 패치 격자 (gh, gw)
  "elapsed_ms": 66,
  "heatmap_url": "/api/inspect/result/<name>_heatmap.png",
  "source_filename": "part.png"
}
```

### 3-2. 라인 이벤트 (WS `/ws/twin`, type="part")
```json
{
  "type": "part",
  "part_id": "P00007",
  "source": "upload_x.PNG",
  "station": "AI-INSPECT-01",
  "decision": "NG", "route": "REJECT",   // OK→PASS / NG→REJECT
  "score": 0.83, "threshold": 0.5,
  "model_name": "...", "is_fallback": true,
  "heatmap_url": "/api/inspect/result/...png",
  "stats": {                              // 누적 통계
    "total": 7, "ok": 0, "ng": 7,
    "defect_rate": 1.0, "avg_score": 0.83,
    "avg_latency_ms": 60.0, "line_status": "ALERT", "defect_target": 0.30
  },
  "line": {                               // 현실 공장 지표
    "conveyor_speed_mps": 0.5, "tact_time_s": 1.4,
    "transit_time_s": 8.0, "throughput_per_min": 43.9,
    "uptime_s": 12.3, "equipment_status": "QA_ALERT"
  },
  "telemetry": { ... }                    // (telemetry_every 마다 포함) 아래 3-3
}
```
- `line_status`: WARMUP(<3개) | NORMAL | ALERT(불량률>defect_target)
- `equipment_status`: RUNNING | QA_ALERT | MODEL_TRAINING | THERMAL_FAULT

### 3-3. 텔레메트리 (`GET /api/twin/telemetry`)
```json
{
  "ts": 1783..., "cuda_available": false,
  "gpus": [ { "index":0, "name":"NVIDIA ...", "util_pct":63,
              "vram_used_mb":8300, "vram_total_mb":24576, "temp_c":72,
              "vram_pct":33.8, "thermal":"warm", "load":"training" } ],
  "cpu_pct": 12.0, "ram_used_mb": 577, "ram_total_mb": 16075,
  "summary": { "has_gpu":true, "mode":"gpu", "gpu_name":"...", "temp_c":72,
               "vram_pct":33.8, "util_pct":63, "thermal":"warm",
               "load":"training", "training":true }
}
```
- `thermal`: cool(<55) | warm(<70) | hot(<84) | critical(≥84) °C
- `load`: idle | light | training (util≥50 & vram≥40% → training)
- GPU/pynvml/nvidia-smi 없으면 `gpus:[]`, `mode:"cpu"` (안전 폴백)

---

## 4. 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/inspect` | 이미지 업로드 → 검사(3-1 응답) |
| GET | `/api/inspect/result/{name}` | 히트맵 이미지 서빙 |
| GET | `/api/inspect/health` | 스코어러 가용성(real/fallback, bank_path) |
| WS | `/ws/twin?interval_ms&telemetry_every&speed` | 라인 이벤트+텔레메트리 스트리밍 |
| GET | `/api/twin/telemetry` | 텔레메트리 스냅샷(3-3) |
| GET | `/api/twin/snapshot` | 현재 라인 상태 |
| GET | `/api/twin/step` | 부품 1개 수동 투입(디버그) |
| GET | `/` `/twin` `/twin3d` | UI: 단일검사 / 2D트윈 / 3D트윈 |

---

## 5. 핵심 동작 규칙 (불변식)

1. **판정은 결정론**: `decision = "NG" if score >= threshold else "OK"`. LLM 개입 금지.
2. **스코어러 자동 선택**: torch 설치 + 뱅크 파일 존재 → `BankScorer`(실제 DINO+코사인뱅크),
   아니면 `FallbackScorer`(numpy+PIL 고주파 잔차). **예외 없이 항상 결과 반환.**
   폴백 여부는 `is_fallback`/`model_name`에 정직하게 표기.
3. **뱅크 경로 탐색**: env `MEMORY_BANK_PATH` → `memory_bank_t95.npy` → `memory_bank.npy`.
4. **설정은 호출 시점 env 반영**: `ARIA_THRESHOLD`(0.5), `ARIA_OUTPUT_DIR`(outputs),
   `ARIA_UPLOAD_DIR`(uploads).
5. **트윈 검사 캐시**: 같은 부품 이미지는 1회만 실제 검사(성능).
6. **3D는 자립**: three.js를 `static/vendor/`에 번들 → CDN/네트워크 없이 동작.

---

## 6. 실행

```bash
# 최소(폴백) — 어디서나 즉시 동작
pip install numpy pillow fastapi "uvicorn[standard]" python-multipart psutil
uvicorn inspect_app:app --host 0.0.0.0 --port 8088
#   /        단일 이미지 검사
#   /twin    2D 디지털 트윈 대시보드
#   /twin3d  3D 디지털 트윈

# 실제 탐지 경로(정밀) — 워크스테이션(GPU)
pip install torch torchvision timm opencv-python pynvml   # + 위 최소셋
#   memory_bank.npy(사전학습 뱅크) 존재 시 자동으로 DINO+코사인뱅크 경로 사용
#   pynvml 설치 시 GPU 온도/VRAM 텔레메트리 실수치 표시

pytest tests/    # 24개
```

---

## 7. 아직 안 된 것 / 통합 필요 (중요)

1. **ARIArefactored(회원님 Vite HMI) 미통합.** 위 코드는 GitHub 브랜치의 **독립 데모**이며,
   회원님이 로컬에서 돌리는 `server/app.py`(P-core)+`aria/planes/inspection_node.py`
   +Vite HMI 구조에는 아직 들어가지 않았다. 통합하려면 그 구조를 봐야 한다
   (브랜치 push 또는 tree+핵심파일 공유 필요).
   - 통합 지점: HMI는 `/ws/twin` 이벤트(3-2)와 `/api/twin/telemetry`(3-3)를 그대로
     구독하면 되고, R3F 씬은 `inspect_app.py`의 `/twin3d` Three.js 로직을 컴포넌트화하면 된다.
2. **정밀 탐지 미완(우선순위에서 후순위였음).** 현재 데모는 폴백 스코어러라 샘플이 전부 NG.
   정밀도를 올리려면: 실제 PatchCore/DINO 경로 활성화 + **클래스별 메모리뱅크** +
   **threshold 보정**(AUROC/F1 기반, `threshold_calibrator.py` 연계).
3. **레거시 정리 미완.** 구 `app.py`/`agent_orchestrator.py` 등 god-file은 그대로 존재
   (제품 경로엔 미사용). 별도 아카이브 단계 필요.

---

## 8. 다음 마일스톤 후보

- **통합**: ARIArefactored HMI에 `/twin3d` R3F 이식 + P-producer를 `/api/inspect`에 배선.
- **정밀(M2)**: MVTec 클래스별 사전학습 뱅크 번들 → 실제 PatchCore 경로 + 보정 threshold.
- **실측 학습 연동**: 실제 뱅크 빌드(학습) 중 텔레메트리를 라인 상태와 연동해 표시.
