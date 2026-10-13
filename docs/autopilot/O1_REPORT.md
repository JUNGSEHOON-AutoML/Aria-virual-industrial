# O0/O1 결과

BuildSpec 끝에 13절을 추가했다. 웹 순서 및 본 실험·GPU 프로세스는 변경하지 않았다.
O0은 점검 완료/환경 조건 실패, O1은 독립 CPU 작업 완료다. O2/O3는 실행하지 않았다.

항목 | 결과
--- | ---
O0 드라이버 / OS | 550.54.14 / Ubuntu 20.04 — 요구 조건 미달
Kit 예정 경로 | 약 64.16 GB 여유, 요구 250 GB — 미달
대체 볼륨 | userhome1 약 1,039.66 GB, userhome3 약 964.71 GB; 쓰기 할당 필요, 설치하지 않음
GPU | RTX 3090 4개에 기존 Xorg/일부 GNOME 세션 관측; compute 작업 미관측을 실험 종료로 간주하지 않음
O1 설치 | `venv/omniverse/`의 Python 3.10.20 / usd-core 26.8만 설치; 시스템·기존 Python 환경 불변
USD | m / Y-up / 5개 사이트 / 3개 홀 / 9개 레인 / 기본 메시 268개
브랜드 | 기존 임시 SVG 돌출 로고 6개 메시; 토큰→linear RGB 최대 오차 2.77304989e-08
바운딩박스 | 웹 원본↔USD 및 실제 Replay 화면↔정적 원본 최대 차이 **0m** (전체·사이트·레인·컴포넌트)
검증기 | OpenUSD 공식 UsdValidation 28종, 기본 및 개별 CAD 변형 55회 모두 문제 0; CAD 자산 3개 통과
도구 테스트 | 10개 통과: 단위·회전·반사·오래된 입력 거부·끊어진 참조 차단·O0 경계/실패 조건
웹 | CPU 빌드 통과; 실제 브라우저 오류 0; 117 draw calls (<300), 실제 GPU 미확인
백엔드 | 변경 없음; 기존 L2 207 passed/3 skipped·골든 diff 0을 이 작업에서 새 검증으로 주장하지 않음

원시 O0 보고서는 `omniverse_preflight.json`, 미달 조건·공유 서버 영향·실험 종료 후 일정 요청은
`omniverse_admin_request.md`에 있다. 요청서는 생성만 했으며 외부로 전송하지 않았다.
`gates/o0.json`, `gates/o1.json`에 측정값과 자동 검사 결과를 보존한다.

## 표현 범위

`/World/Campus/{Hall_bottle,Hall_screw,Hall_carpet,RobotCell,Yard,Landscape}` 아래에
공유 웹 prefab에서 추출한 메시·변환이 있다. 각 홀의 Lane_coreset/Lane_ccifps/Lane_random_same_k
하위에 MainConveyor/Booth/Diverter/Reinspection이 있다. CAD 원자료는 수정하지 않았다.

STEP을 USD 참조인 것처럼 직접 연결하지 않는다. 기존 dims.json이 기록한 STEP/GLB 해시와
치수를 검증해 GLB를 USD 자산으로 변환하고, 27개 컴포넌트의 `cad_envelope` 변형에서 참조한다.
기본 `web` 변형은 웹 형상 그대로다. CAD 변형은 원래 치수의 설계 외피를 웹 컴포넌트 중심에
두는 **assumed** 표현이며 완성된 기계 조립이나 안전성 검증이 아니다. 1cm 게이트의 대상은 기본 web 표현이다.
M0609는 검증된 공식 URDF→USD 도구가 없어 기존 정적 자리 표시 형상만 포함했다.
DOM 간판·패널, 조명, 이동 부품·로봇 동작은 정적 USD 범위 밖이다.

PyPI wheel에는 upstream usdchecker 실행 파일이 없다. 프로젝트 CLI 어댑터가 공식
UsdValidation 엔진의 모든 검증기를 호출하며, 이를 upstream CLI 실행으로 표시하지 않는다.
기본/모든 개별 CAD 변형과 상대 참조를 검증한다. 실행 시 다른 variant를 저장하지 않는다.

## 재실행

기존 aria Python 환경, CPU 웹 서버가 실행 중인 저장소 루트에서:

```bash
python -m tools.omniverse_preflight
# 환경 실패면 exit 2. 시스템 변경 없이 관리자 요청서만 갱신.
bash tools/omniverse/run_o1.sh
# 생성물만 읽기 검증:
venv/omniverse/bin/python -m tools.omniverse.usdchecker exports/usd/cnotta_campus.usda
```

상세 환경 설정과 선택 인자: `tools/omniverse/README.md`.
설치된 패키지의 선언 라이선스·해시: `tools/omniverse/environment.json`.

## 변경 파일

O0 시작 전 `212c535` 대비 이번 O0/O1 변경 목록 (격리 환경·로컬 캡처 제외):

- `docs/autopilot/BLOCKERS.md`
- `docs/autopilot/DECISIONS.md`
- `docs/autopilot/O1_REPORT.md`
- `docs/autopilot/PROGRESS.md`
- `docs/autopilot/gates/o0.json`
- `docs/autopilot/gates/o1.json`
- `docs/autopilot/omniverse_admin_request.md`
- `docs/autopilot/omniverse_preflight.json`
- `docs/specs/CNOTTA_ARIA_Autopilot_BuildSpec.md`
- `exports/usd/assets/conveyor.usda`
- `exports/usd/assets/diverter.usda`
- `exports/usd/assets/inspection_booth.usda`
- `exports/usd/cnotta_campus.usda`
- `exports/usd/manifest.json`
- `frontend/src/campus/Geometry.jsx`
- `frontend/src/omniverse/export.jsx`
- `frontend/src/omniverse/serialize.js`
- `frontend/usd-export.html`
- `tools/gates/test_omniverse_preflight.py`
- `tools/gates/test_omniverse_usd.py`
- `tools/omniverse/README.md`
- `tools/omniverse/capture_static.py`
- `tools/omniverse/environment.json`
- `tools/omniverse/export_usd.py`
- `tools/omniverse/requirements.txt`
- `tools/omniverse/run_o1.sh`
- `tools/omniverse/sources.json`
- `tools/omniverse/usdchecker.py`
- `tools/omniverse/validate_export.py`
- `tools/omniverse_preflight.py`

`git diff --stat 212c535`로 전체 변경 통계를 확인한다. 생성된 USDA/manifest가 대부분의 추가 행이며, AGENTS.md·TOOLS.md·SKILL.md·원시 실험 자료는 변경하지 않았다.
