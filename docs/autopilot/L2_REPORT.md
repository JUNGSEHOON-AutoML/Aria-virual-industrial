# L2 CPU Live Ops 연결

`/cnotta.html?mode=live` → **Live 시작**. 첫 화면은 M0609 검사 셀, **공정 전체 보기**는 레인/순찰 시점이다. 최근 검사 결과 또는 부품을 누르면 실제 입력 이미지와 CCIFPS 히트맵을 표시한다. **고장 주입**은 가상 설비만 격리하며 출동 → 현장 확인 → 진단 → 수리 → 자가검사 → 인터록 해제 → 공정 재개가 서버 상태로 진행된다. **Replay 보기**는 저장된 9레인 비교와 G2 물류로 돌아간다.

## 검증

- CPU 빌드 성공; 기존 3D 번들 크기 경고는 남아 있다.
- 백엔드 전체 207 passed / 3 skipped (PostgreSQL DSN 미설정). Live 전용 16개 포함, 고장 10 seed·동일 ID 판정/배출·추론 중 스냅샷·OPEN 고정·NG/HOLD 위치·수리 중 그립·API/WS.
- `tests/golden_trace.py --verify`: diff 0. 기존 DES 엔진·평가기·사후 B 코드 변경 없음.
- SwiftShader 브라우저: 49개 표본에서 렌더 수 = 서버 WIP, CLOSED 33개 표본의 메시 좌표와 실제 CAD 도구 행렬 TCP 최대 차이 1.306e-7m, OPEN 후 함께 이동 0. 정지 프레임 고정.
- 실제 CPU 검사 OK/NG 및 원본/히트맵 표시, UI 고장 주입의 DISPATCHED → DIAGNOSING → REPAIRING → VERIFYING → RESTORED, 콘솔/HTTP 오류 0.
- 실제 GPU 화풍·FPS는 미확인. 물리 충돌·동역학·실제 로봇 컨트롤러 검증은 아니다.

자동 게이트: `PYTHONPATH=. python -m tools.gates.l2`. 새 화면 증거는 로컬 서버에서 `python tools/gates/capture_live.py`로 생성한다. 브라우저 원기록·캡처는 Git에서 제외된 `docs/autopilot/local/`에 보존한다. 첫 검증에서 수리 자가검사의 누락 필드를 발견해 수정했고, 버튼이 준비되기 전에 클릭하던 검증 스크립트도 실제 enabled 상태를 기다리도록 고쳤다. 이전 시도 JSON도 보존한다.

## 실행과 경계

```bash
CNOTTA_PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python \
CNOTTA_NODE=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/node ./scripts/demo.sh
# http://127.0.0.1:5278/cnotta.html?mode=live
```

`demo.sh`는 자식 API의 CUDA_VISIBLE_DEVICES를 비워 CPU만 사용한다. Live 시작을 누르기 전에는 추론이나 Live 시계를 시작하지 않는다. 본 실험 프로세스·GPU·연구 결과는 건드리지 않는다. 서버와 포워딩을 유지해야 접속할 수 있다. 포워딩 주소는 앱 세션마다 달라질 수 있다.

실행은 기존 FactoryService/InspectionAdapter/PatrolSupervisor/MaintenanceHarness와 M0609 CAD·FK를 재사용한다. 전용 저장 위치는 `outputs/cnotta-live/<session>/`; 이전 근거의 보존 정책을 실행하지 않는다. 현재 bundle은 BOTTLE CCIFPS만 준비되어 다른 클래스는 Replay만 제공한다. 실제 입력은 64개 로컬 테스트 이미지를 순환하며 연구의 5% 재샘플링과 구분된다. CPU 추론 중에는 시계를 고정하고 INSPECT 상태를 계속 송신한다. 검사 결과는 기존 완료 경계에서 같은 ID로 재사용한다.

`configs/live_ops.json`은 투입 주기·검사 hold·NG/HOLD 관절 목표 등 시연 가정값을 assumed로 관리한다. 프런트는 WebSocket ref/useFrame으로 그리며 자체 공정 시계·난수는 없다. 모든 동작은 `configs/ambient_motion.json`에 등록한다. 다음 단계는 L3 에이전트 작업, 이어서 L4 4족 표현이다.
