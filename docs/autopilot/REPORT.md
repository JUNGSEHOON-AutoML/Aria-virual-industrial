# CNOTTA × ARIA 최종 데모 보고서

기준 브랜치 `dt-dashboard-p6` (`157c364`) → `dt-cnotta`. 작성 2026-10-13T03:16:38.946513+00:00.
M0–M4와 파일럿 기준 M6 자동 게이트를 통과했다. M5는 본 실험 대기이며 **완료로 표시하지 않는다**. 실제 GPU 화풍·FPS는 미확인이다.

| 단계 | 결과 | 근거 |
|---|---|---|
| M0 | 완료 | 토큰 16개, 활성 UI의 토큰 외 hex 0 |
| M1 | 자동 통과 | 지면 오차 0·바닥 오차 4/채널, 레인/랙 겹침 0, 조립체 접지 위반 0, 투영 바운딩 사각형 채움 87.26%, primary 색 영역 4.85% |
| M2 | 완료 | 동일 시각 부품 수 일치, 정지 위치 변화 0, 10× 순서 유지, API 테스트 |
| M3 | 완료 | 검색 선택, per_image.csv 점수·판정 일치, 장식 9개 클릭 핸들러 0 |
| M4 | 완료 | KPI 화면/API/오프라인 평가값 일치, 큐 0·2·2564와 인스턴스 수 일치, 설비 픽셀 가림 0/83678 |
| M5 | 실험 대기 | 실제 결과 API 404, 미검증 완료 파일 차단·REPORT 불일치 409 테스트 통과 |
| M6 | 파일럿 완료 | 새 로컬 클론 기동·동일 포트 즉시 재기동 성공, 백엔드 163 passed, golden diff 0, CPU 빌드 성공, 60.0초 녹화 |

게이트: `gates/m0.json`–`gates/m6.json`. M1 접지는 조립체 AABB와 바닥의 2cm 허용 오차이며 모든 내부 메시 연결을 검증하는 것은 아니다. 채움률은 실루엣 면적이 아닌 클리핑된 공정 바운딩 사각형이다. M4 가림은 컨베이어·부스·로봇 셀·캐비닛·랙·분류기를 이진 렌더한 설비 픽셀을 분모로 쓴다. 모두 1440×900 기본 시점에서 측정했다. API 오류 테스트 포함 총 163개이며 경고 14개는 기존 수명주기 API 및 TestClient 사용 중 발생했다.

## 실행 및 확인

현재 데모: http://127.0.0.1:5278/cnotta.html (원격 PC는 5278 포트 전달 후 Chrome). API는 5277, 두 서버 모두 loopback이다.

```bash
CNOTTA_PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python \
CNOTTA_NODE=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/node \
./scripts/demo.sh
```

이미 실행 중인 포트에 재실행하면 안전하게 거절한다. 다른 포트는 CNOTTA_API_PORT/CNOTTA_WEB_PORT로 지정한다. 종료 시 이 스크립트가 시작한 두 프로세스만 정리한다. 새 클론은 외부의 검증된 CNOTTA_PILOT/CNOTTA_P1과 기존 격리 Python·로컬 node_modules를 사용해 실제 timeline/KPI까지 조회했다. 데이터·의존성을 포함한 자체 완결 배포물이라는 뜻은 아니다. 상세 준비 명령은 README의 CNOTTA 절에 있다.

녹화: [60초 데모](local/demo.mp4), [녹화 측정](local/recording.json), [패널 캡처](local/m4.png). 실제 60.22초 동안 94장을 수집하고 경과 시간을 보존해 60.0초 MP4로 인코딩했다. 10fps는 출력 프레임률이고 GPU 성능 측정값이 아니다. 녹화와 캡처는 내부 로컬 산출물로 Git에서 제외했다.

## 데이터 및 남은 확인

- 확인 시 본 실험 `DES_A`: A 1,494/2,970, 경과 2.40시간. 이 값은 확인 시점 스냅샷이다. 본 실험 프로세스·GPU에 변경을 가하지 않았다.
- 완료 수량·원시 해시 검증·30 seed 그룹 검증을 모두 만족한 뒤 비교 API가 열린다. 대표 조건 summary를 REPORT 표의 출력 정밀도까지 대조한다. 결과가 준비되면 `PYTHONPATH=. python -m tools.gates.m5`를 실행하고 대기 상태를 갱신해야 한다. 현재 실데이터 REPORT 일치 여부는 미검증이다.
- 실제 GPU 화풍·FPS, 최종 데모 확인이 남았다. 소프트웨어 렌더링만 사용했다. 원본 로고가 없어 임시 SVG를 사용했다.
- 저장 부품과 사후 계산 큐만 재생한다. 순간 이동 기록에 가상 이동 시간을 붙이지 않는다. 설비 배치·로봇 고정 자세와 랙 초과분 1/4 축소 적재는 assumed다. GT 파일은 평가기/오라클로만 읽고 공개 타임라인에 이미지 경로·GT·하드웨어 기록을 보내지 않는다.
- 같은 조건 coreset가 없는 파일럿은 Δ가 —다. 미기록 로봇 상태도 —다. 처리량 최대값을 가정하지 않으므로 처리량 고리는 비율을 표시하지 않는다. 재생 중 KPI는 카드의 표기 시각 스냅샷이다.
- 참고 이미지 폴더는 계속 ignored이며 CNOTTA 화면과 커밋에 포함하지 않았다. DES·평가기·사후 계산·AGENTS.md·TOOLS.md·SKILL.md·docs/validation 변경은 0이다.

## 디렉터리 및 검증 명령

| 경로 | 용도 |
|---|---|
| frontend/src/brand/ · frontend/public/brand/ | 단일 토큰 정의·임시 SVG |
| frontend/src/cnotta/ · frontend/cnotta.html | 장면·재생·선택·KPI·자원·비교 |
| aria/dashboard/ | 검증된 저장 결과를 읽는 전용 API |
| tools/gates/ | 마일스톤 게이트·CPU 브라우저 측정·녹화 |
| scripts/demo.sh | 백엔드·프런트 동시 기동 |
| tests/test_cnotta_api.py | 실 파일럿 API·평가기·결과 공개 조건 테스트 |
| docs/autopilot/ | PROGRESS·DECISIONS·BLOCKERS·게이트·이 보고서 |
| docs/autopilot/local/ | 비커밋 캡처·녹화·검증 로그 |

```bash
PYTHONPATH=. python -m tools.gates.capture_browser
PYTHONPATH=. python -m tools.gates.m0  # m1…m6 동일 모듈 형식
PYTHONPATH=. python tests/golden_trace.py --verify
PYTHONPATH=/tmp/aria-dt-dbdeps:. \
ARIA_TEST_POSTGRES_DSN='host=127.0.0.1 port=55433 user=aria dbname=aria_dt connect_timeout=3' \
python -m pytest tests -q
(cd frontend && node node_modules/vite/bin/vite.js build --config vite.cnotta.config.js)
PYTHONPATH=. python -m tools.gates.record_demo
```

결정 21건은 [DECISIONS.md](DECISIONS.md), 남은 항목은 [BLOCKERS.md](BLOCKERS.md). 각 단계는 M0–M6 접두어 커밋으로 보존했다. 전체 변경 파일 목록은 완료 후 실행한 `git diff --stat dt-dashboard-p6..HEAD`의 [출력](local/diff-stat.txt)을 참고한다.
