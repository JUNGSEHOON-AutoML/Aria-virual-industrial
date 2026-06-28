# 👁️ ARIA: Anomaly Reasoning Intelligence Agent

**ARIA**는 자율 산업 비전 오케스트레이션 에이전트 시스템입니다. 본 저장소에는 가상 FAT(Factory Acceptance Test) 합격 게이트 연동 및 3D 다중 라인 공장 환경이 안전하게 병합되어 최신 원격 저장소(`main` 브랜치)에 푸시 완료되었습니다.

---

## 🚀 최신 업데이트 & 깃허브 푸시 증거 (Push Evidence)

가상 FAT 합격 기준 판정 및 다중 생산 라인, 작업자, 산업 설비에 이르는 3D 시뮬레이션 환경 확장이 성공적으로 커밋 및 푸시 완료되었습니다.

### 1. 깃허브 커밋 내역 (Git Commit History)

```bash
$ git log -n 3 --oneline
2bbc926 feat(sim): factory-scale floor — multi-line, workers, equipment (capture-safe)
932b7b5 feat(sim): living factory line — continuous conveyor, OK/NG routing, status board, learning core (capture-safe)
ac20440 feat(validation): virtual FAT acceptance gate — PASS/FAIL vs configurable escape/FP criteria
```

* **원격 저장소 반영 완료**: `To https://github.com/JUNGSEHOON-AutoML/ARIA-Anomaly-Reasoning-Intelligence-Agent-.git`

---

## 🛠️ 주요 수정 및 추가 내역

### 1. 가상 FAT 합격 판정 게이트 (PASS/FAIL) 연동
* **[validate.py](file:///userHome/userhome4/sehoon/ARIA-Anomaly-Reasoning-Intelligence-Agent--main/validation/validate.py)**: `run_validation()`에 `criteria` 인자를 지원하여 임계치를 초과하지 않는 escape율(놓침 ≤ 5%) 및 오검출율(FP ≤ 20%)에 근거해 `PASS`/`FAIL` 합격 판정(`fat_verdict`)을 연동했습니다.
* **[app.py](file:///userHome/userhome4/sehoon/ARIA-Anomaly-Reasoning-Intelligence-Agent--main/app.py)**: `/api/sim/validate` 호출 시 동적으로 기준을 수신하고, WebSocket을 통해 `FAT` 에이전트 상태를 브로드캐스트합니다.
* **[SimulationView.jsx](file:///userHome/userhome4/sehoon/ARIA-Anomaly-Reasoning-Intelligence-Agent--main/frontend/src/components/SimulationView.jsx)**: 시뮬레이션 결과 화면에 가상 FAT PASS/FAIL 결과 뱃지 및 합격 기준 텍스트를 렌더링하도록 반영했습니다.

### 2. 3D 가상 산업현장 다중 라인 (<FactoryLine />) 확장
* **[factory.jsx](file:///userHome/userhome4/sehoon/ARIA-Anomaly-Reasoning-Intelligence-Agent--main/frontend/src/sim/factory.jsx)**:
  - **다중 생산 라인**: 단일 라인을 `ProductionLine` 컴포넌트로 분리하고 z=3, z=5, z=6.5 오프셋을 주어 3개의 라인이 동시에 부품을 분류하도록 확장했습니다.
  - **작업자 (Workers)**: 라인 통로에 작업자 5명을 배치하고, 들숨(Y축 바이브레이션) 및 고갯짓(머리 회전) idle 애니메이션을 주었습니다.
  - **산업 설비 (Equipment)**: 관절 각도가 수평/수직으로 회전하는 로봇팔 2대, 제어판 에미시브 점등창, 황색 안전통로선, 기둥 및 상단 구조물 빔 골조를 배치했습니다.
  - **성능 제어 및 캡처 가드**: 라인당 렌더링 부품 수를 `cap=10`으로 관리해 성능 저하를 방지했으며, 모든 시뮬레이션 요소를 `<FactoryLine />` 그룹 내에 마운트하여 데이터셋 캡처 시 완전히 숨겨지도록(visible = false) 구현하여 캡처 무결성을 완벽 수호했습니다.

---

## 🗂️ 프로젝트 구조 (리팩토링 v0.2)

코드를 단일 `aria/` 패키지로 재편하고, 모든 설계 문서를 `docs/`로 분리했습니다.
참고 프로젝트(`mobile_robot_Simulation`의 관심사 분리, `xlerobot-learning-guide`의 계층형 구조)의
설계 로직을 차용했습니다. 전체 매핑은 [`docs/STRUCTURE.md`](docs/STRUCTURE.md) 참고.

```
aria/
├── perception/     # 이상탐지·비전 (vision_router, detectors, scorer, cmdiad ...)
├── simulation/     # 가상 공장 데이터/결함 + FAT 합격 게이트 (validation)
├── agents/         # 스웜 에이전트 노드 (vision/code/research/... + autonomous)
├── orchestration/  # 스웜 라우팅·상태·이벤트 버스
├── mcp/            # MCP 클라이언트 + 서버(filesystem/system/database/hf...)
├── learning/       # 자가개선·모델탐색·학습
└── core/           # database·config·registry·utils 공통 인프라
docs/               # specs/ · harness/ · protocol/ · report/  (코드와 분리)
app.py              # 진입점 (uvicorn app:app) — 위치 유지
src/patchcore/      # 벤더링된 CCIFPS 핵심 알고리즘 (src-layout 유지)
```

## 📦 설치 및 실행 방법

1. **아나콘다 환경 및 패키지 준비**:
   ```bash
   conda create -n patchcore python=3.10 && conda activate patchcore
   pip install -r requirements.txt
   ```

2. **프론트엔드 빌드 및 실행**:
   ```bash
   conda run -n patchcore npm --prefix frontend run build
   ./start_aria.sh
   ```

---

## 👤 Author

정세훈 (JUNG SEHOON) — [JUNGSEHOON-AutoML](https://github.com/JUNGSEHOON-AutoML)
