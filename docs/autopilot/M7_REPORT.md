# M7 캠퍼스 배치·브랜딩 결과

`dt-cnotta`에서 요청한 캠퍼스 배치·브랜딩을 구현했다. 실행 순서는 L1(완료) → M7 → L2 → L3 → L4 → V1–V3 → M3 → M4 → M5 → M6이다. 화면 자동 게이트는 통과했다. 9번째 저장 실행이 아직 없어 전체 M7 데이터 게이트는 **pending_data**이며, 실제 GPU FPS·홀 진입 시간은 미확인이다.

## 화면과 데이터

- `campus.layout.json`에서 **1공장 BOTTLE / 2공장 SCREW / 3공장 CARPET**과 각 3개 모델 레인, 로봇 셀 동, 장식 물류 야드를 생성한다. 홀 치수는 CAD 설계 치수·레인 수 기반 32×29.6m이며 `assumed`다. 반복 소품은 seed 7로 재현한다.
- 각 지붕의 마크·워드마크는 실제 `ExtrudeGeometry`이고 합산 폭은 55%다. 홀 진입 시 지붕·상부 벽·두 로고가 0.8초 페이드 목표로 함께 사라지고 복귀 시 나타난다. 각 홀 정면 간판과 입구 기둥형 사인 1개를 두었다.
- 상단 홀 선택, 지붕·간판 클릭, 미니맵으로 이동한다. 전체 sim 시계 하나로 재생/정지/배속/시각 탐색을 공유하고 선택 홀의 세 레인·부품·NG·재검사 박스를 표시한다. 활성 로봇 운영은 다음 L2 범위다.
- API는 저장 결과를 읽기만 한다. 완료 실행의 raw/input hash 검증을 유지하고, 본 실험 최종 요약/95% CI는 기존 전체 검증 조건을 통과해야 공개한다. 본 실험 상태를 읽었을 때 A 2,094/2,970으로 진행 중이었다. 프로세스나 GPU는 변경하지 않았다.
- 현재 8/9개 레인이 준비됐다. CARPET `random_same_k`의 seed 0 / inline / 0.5 m/s / profile이 완료 대기다. 다른 조건의 실행으로 채우지 않으며 30초마다 목록을 재확인한다.
- 입력 ID/이미지 순서는 각 홀의 준비된 모델 사이에서 일치한다. 실제 born 시각 차이는 보존한다(최대 BOTTLE 0.023864685s, SCREW 0.001985120s, CARPET 0.001704567s). 같은 시계 사용을 투입 시각 강제 변경으로 구현하지 않았다.

## 검증

| 항목 | 결과 |
|---|---|
| 1440×900 지붕 워드마크 글자 높이 | 세 홀 각각 29.657px ≥24px |
| 지붕 브랜드 폭 | 세 홀 각각 55% |
| 세 홀·홀 이름 | 화면 안, 이름 겹침 0, 워드마크 패널 가림 0 |
| 캠퍼스 draw calls / triangles | 60 / 11,854 |
| 홀 draw calls / triangles | 46 / 19,542 (재생 중 calls 45) |
| 장식 이벤트 핸들러 | 0 |
| 지붕 페이드·미니맵·seed 재로드 | 통과 |
| 부품·NG·재검사 대기열 | t=1800의 표시와 원기록/사후 계산 일치; 선택 홀 부품 3, 대기 박스 1,477 |
| 재생 / 정지 | 위치 변화 확인, 정지 위치 고정, 공유 시계 유지 |
| 콘솔 / HTTP 오류 | 0 / 0 |
| CPU production build | 통과 (기존 대형 3D 번들 경고만 존재) |
| 백엔드 전체 | 184 passed, 14 warnings |
| 골든 트레이스 | diff 0 |
| 실제 GPU FPS·1초 진입 | 미확인; SwiftShader만 사용 |
| 전체 9레인 | 8개 통과, 1개 실행 대기 |

증거: [화면 게이트](gates/m7-scene.json), [전체 게이트](gates/m7.json), [캠퍼스 캡처](local/m7-campus.png), [BOTTLE 홀](local/m7-hall-bottle.png), [SCREW 홀](local/m7-hall-screw.png). 캡처와 브라우저 상세 로그는 기존 ignore 대상이다. 실제 GPU 화면은 같은 URL에서 확인할 수 있으며, 이를 기다리지 않고 다음 L2 작업을 진행할 수 있다.

## 경로와 실행

| 경로 | 역할 |
|---|---|
| `frontend/src/campus/campus.layout.json` | 사이트·도로·카메라·레인·설계 치수 |
| `frontend/src/campus/` | 캠퍼스 장면, 카메라, 미니맵, 공유 재생·요약 |
| `frontend/public/brand/identity.json` | 로고 파일 경로의 단일 정의 |
| `frontend/public/brand/*.svg` | 임시 마크와 자체 기하 워드마크, 원본 교체 지점 |
| `aria/dashboard/campus.py` | 읽기 전용 조건 매칭 API |
| `tools/gates/capture_campus.py`, `tools/gates/m7.py` | CPU 캡처·자동 게이트 |

기존 `scripts/demo.sh`로 기동한다. 기본 `http://127.0.0.1:5278/cnotta.html`은 캠퍼스, `?view=line`은 기존 단일 실행이다. 현재 사용자의 포워딩 URL은 `http://localhost:63727/cnotta.html`이다. 홀 클릭 후 아래 **재생** 버튼을 사용한다. 본 실험이나 GPU를 시작하는 명령은 없다.

```sh
CNOTTA_PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python \
CNOTTA_NODE=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/node ./scripts/demo.sh
# 이미 서버가 실행 중이면 위 명령을 중복 실행하지 않고 기존 URL 사용
python tools/gates/capture_campus.py
PYTHONPATH=. python -m tools.gates.m7
```

원본은 fill path와 viewBox를 가진 윤곽선 SVG로 brand 폴더에 교체한다. 이름이 바뀌면 같은 폴더의 identity.json만 수정한다. 장면 코드는 경로 문자열을 중복 정의하지 않는다. 게이트에서 새로운 워드마크 비율의 24px 조건을 다시 확인한다. 새 가중치·외부 에셋 다운로드는 없었다.

새 결정 6건은 [DECISIONS](DECISIONS.md)에, 9번째 실행 대기는 [BLOCKERS](BLOCKERS.md)에 기록했다. 본 단계 다음은 L2 운영 연결이다.

## 변경 파일 통계

아래는 커밋 직전 `git diff --stat HEAD` 출력이다(이 보고서의 마지막 통계 블록 추가 직전 측정).

```text
 README.md                                     |   6 +
 aria/dashboard/campus.py                      |  23 +++
 aria/dashboard/server.py                      |   2 +
 aria/dashboard/store.py                       |  18 +-
 docs/autopilot/BLOCKERS.md                    |   4 +-
 docs/autopilot/DECISIONS.md                   |   7 +
 docs/autopilot/M7_REPORT.md                   |  63 +++++++
 docs/autopilot/PROGRESS.md                    |  12 +-
 docs/autopilot/gates/m7-scene.json            | 238 ++++++++++++++++++++++++
 docs/autopilot/gates/m7.json                  | 252 ++++++++++++++++++++++++++
 docs/specs/CNOTTA_ARIA_Autopilot_BuildSpec.md | 166 ++++++++++++++---
 frontend/README.md                            |   6 +
 frontend/public/brand/cnotta-mark.svg         |   2 +-
 frontend/public/brand/cnotta-wordmark.svg     |  11 ++
 frontend/public/brand/identity.json           |   1 +
 frontend/src/brand/identity.js                |   3 +
 frontend/src/campus/App.jsx                   |  27 +++
 frontend/src/campus/Camera.jsx                |  25 +++
 frontend/src/campus/Geometry.jsx              |  85 +++++++++
 frontend/src/campus/Interior.jsx              |   6 +
 frontend/src/campus/Replay.jsx                |  35 ++++
 frontend/src/campus/campus.layout.json        | 200 ++++++++++++++++++++
 frontend/src/campus/data.js                   |  18 ++
 frontend/src/campus/layout.js                 |   9 +
 frontend/src/campus/style.css                 |   2 +
 frontend/src/cnotta/main.jsx                  |   7 +-
 frontend/src/cnotta/scene.jsx                 |   3 +-
 frontend/src/cnotta/style.css                 |   2 +-
 tests/test_cnotta_campus.py                   |  49 +++++
 tools/gates/capture_browser.py                |   2 +-
 tools/gates/capture_campus.py                 |  67 +++++++
 tools/gates/m7.py                             |  52 ++++++
 tools/gates/record_demo.py                    |   2 +-
 33 files changed, 1365 insertions(+), 40 deletions(-)
```
