# S1–S3 검사 스테이션

BuildSpec 14절과 S1 3h / S2 6h / S3 3h를 등록하고, O1 다음에 적용했다. 기존 L2 완료 기록은 보존하고 새 고정 카메라·이송 역할에 맞춰 다시 검증했다. 작업 브랜치는 `dt-cnotta`다.

## 구현

- S1: 패턴 벨트, 회전 롤러, 프레임·가이드·발·가새, 구동부, DES 상태 램프, 트리거 센서, 비상정지·통로 펜스. 재생 시계가 멈추면 형상도 멈춘다.
- S2: BOTTLE 비전 터널·하향 카메라·링 조명·NG 푸셔·HOLD 게이트, SCREW 볼 피더·유리 원판·하향 카메라·배출 노즐, CARPET 언와인더·라인 카메라·라벨러·리와인더. 측면 카메라는 데이터 없음/비활성이다.
- S2 상세 카드: 실제 원본 해상도, 모델, 임계값, 최근 판정 10개의 입력/히트맵, 서버 p50/p95. Replay는 저장 히트맵과 입력 SHA를 검증하고 새 추론 없이 제공한다. Live는 기존 BOTTLE CCIFPS CPU 검출기 근거를 연결한다.
- CARPET: 원본 part ID를 구간 ID로 보존하며 OK/NG/HOLD를 모두 롤에 포함한다. 정시 NG 라벨 수만 등급에 쓰고, GT는 그 뒤 평가 조인에서만 읽는다. 무라벨 결함과 OK 판정 미탐은 별도 수치다. SCREW OK 통과 CARPET 롤은 제품별 상세 목록으로 확인하며 기존 개별 조각 폐기 차량은 표시하지 않는다.
- S3: 기존 `robot.py`를 수정하지 않고 FK·관절 한계를 사용하는 별도 7단계 TRANSFER를 추가했다. 생산 박스/통/롤과 B 재검사 도착 이벤트를 actor별로 직렬 처리한다. 원본 물체 ID를 유지하며 OPEN 동안은 집기/놓기 지점에 고정한다. 등급별 놓기 자세가 다르다. 기존 제품 CAD 외형은 마운트하지 않고 코드로 만든 일반 링크만 표시한다.

## 검증 결과

| 항목 | 결과 |
|---|---|
| 백엔드 전체 | 223 passed, 3 skipped |
| 골든 트레이스 | diff 0 |
| 기존 robot.py 및 기존 테스트 26개 파일 | 변경 0 (d64e815와 바이트 비교) |
| DES·DT 평가/사후 계산 코드 | 변경 0 |
| 웹 CPU 빌드 | 성공, 기존 큰 번들 경고 유지 |
| 카메라 9대 | 하향 각도 0°, 트리거 제품 경계 전체 frustum 안 |
| 센서·조명·배출 | 원본 시각 샘플 및 도착 +1/120초에서 일치 |
| 벨트 이동량·정지 | 저장 상태/속도 적분 오차 0, 정지 변환 동일 |
| SCREW 3개 모델 | 원호 경로 겹침 0 (이 저장 실행은 원판 구간 동시 점유 쌍 0) |
| CARPET 3개 모델 | 각 175개 완료 롤, 모든 구간 보존, 라벨 수와 등급 일치 |
| 9개 레인의 TRANSFER | 출처 이벤트 15,469건 = 작업 15,469건, ID 일치 |
| OPEN / CLOSED 물체 위치 | OPEN 고정 지점 이동 0m, CLOSED TCP 차이 0m |
| 브라우저 | JS/HTTP 오류 0, 최대 183 draw calls |
| 실제 CPU Live | 실제 NG 1건·입력/히트맵 HTTP 200, 19.232s에서 일시정지 동일 |

자동 게이트: `gates/s1.json`, `gates/s2.json`, `gates/s3.json`, `gates/l2-stations.json`. 로컬 캡처는 `local/stations/{bottle,screw,carpet}.png`, 각 `*-detail.png`, `local/station-live/actual-evidence.png`에 있다. 데이터셋 이미지가 포함된 캡처·브라우저 원문은 무시 경로에 보존하고 커밋하지 않았다. 렌더러는 SwiftShader이며 **실제 GPU 화풍·FPS는 미확인**이다.

## 계산 경계와 남은 사항

Replay에는 별도 컨베이어 제어 로그가 없으므로 AI-INSPECTION PROCESSING 상태 × 저장된 실행 속도로 벨트 진행을 매핑한다. Live는 기존 CONVEYOR-02의 PROCESSING 누적 시간을 사용한다. 이 매핑, 원호/원단 이동, 형상·통/롤 용량·등급 기준·이송 자세와 시간은 assumed다.

생산 박스는 기존 정책 A 박스 완성 계산을 재사용하고, 재검사 이송은 정책 B NG 도착을 별도 actor로 표현한다. 이송 대기가 원본 생산/사후 B 서비스 시각·KPI를 늦추지 않는다. 이는 화면·하류 작업 매핑이며 로봇을 포함한 생산성 재평가나 기계 안전 검증이 아니다. 팔레트는 등급별 대표 형상이고 완료 목록에는 실제 제품 ID를 표시한다.

완료된 본 실험이 파일럿 기준선에 섞여 기존 테스트 1건이 실패한 원인을 수정했다. 기준선은 같은 결과 컬렉션 안에서만 선택하며 개별 KPI·DES·평가기 값은 유지한다. 기존 테스트를 수정하거나 건너뛰지 않고 전체를 다시 통과시켰다.

이전 O1 USD는 d64e815의 정적 스냅샷으로 보존했다. 이번 프리팹이 포함된 웹과의 일치는 다시 검증해야 하므로 현재 일치한다고 주장하지 않는다. O2/O3의 드라이버·OS·공간 차단은 유지한다. Live는 기존 BOTTLE CCIFPS 한 레인이며 나머지 8개는 저장 Replay다. L3 이후 웹 순서는 유지한다. M5는 본 실험 완료 마커가 확인되어 실데이터 UI 게이트 재검증이 남았다.

## 경로와 실행

- `aria/dashboard/stations.py`: 저장 실행·제품/라벨/등급·근거 API
- `aria/dashboard/station_live.py`: 기존 Live 스냅샷의 읽기 전용 스테이션 투영
- `aria/dashboard/transfer.py`: 별도 TRANSFER, 관절/FK 재사용
- `frontend/src/stations/`: 설비·제품·이송·상세 카드
- `configs/inspection_stations.json`, `configs/logistics.yaml`: 형상 및 assumed 파라미터
- `configs/ambient_motion.json`: 모든 신규 움직임 출처 등록
- `tests/test_inspection_stations.py`, `tools/gates/*stations*`, `tools/gates/capture_station_live.py`: 새 검증

현재 별도 CPU 미리보기: `http://127.0.0.1:5288/cnotta.html?mode=live`. Live 시작으로 재개하고, Replay 보기에서 홀을 선택한 뒤 재생을 누른다. 스테이션의 HMI 버튼으로 검사 근거를 연다. 최초 원기록 검증은 60초 이상 걸릴 수 있다.

```sh
# 저장소 루트, 기존 격리 환경과 로컬 node_modules 사용
CNOTTA_PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python \
CNOTTA_NODE=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/node \
CNOTTA_API_PORT=5287 CNOTTA_WEB_PORT=5288 \
CNOTTA_LOG_DIR=docs/autopilot/local/stations-demo bash scripts/demo.sh

# 검증 (aria 환경의 Python / Node 20 사용)
CUDA_VISIBLE_DEVICES='' OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pytest tests -q
CUDA_VISIBLE_DEVICES='' python tests/golden_trace.py --verify
node tools/gates/stations_test.mjs
python tools/gates/capture_stations.py
python -m tools.gates.check_stations
python tools/gates/capture_station_live.py
python tools/gates/finalize_stations.py
# 웹 빌드: frontend 디렉터리에서
node node_modules/vite/bin/vite.js build --config vite.cnotta.config.js
```

이미 실행 중인 포트를 다시 시작하지 않는다. `scripts/demo.sh`는 해당 스크립트가 띄운 API·웹 프로세스만 종료한다. 이번 작업에서 본 실험·GPU·드라이버·CUDA·시스템 패키지는 변경하지 않았다.
