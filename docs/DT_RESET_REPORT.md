# ARIA 재설정 결과와 실행 명령

2026-10-13 Asia/Seoul. 작업 브랜치: `dt-wip-20261013`. 현재 상태: **구조 정리 및 검증 완료, 본 실행 확인 대기**.

정책 A DES와 B 사후 계산을 분리했다. DES 계획은 기준 A 2,700개와 상한 확인 270개이며, 기존 유효 A 15개를 재사용하면 신규 실행은 2,955개다. B 기본 2,700개와 단일 요인 변형 1,620개는 사후 계산한다. 계획 생성과 검증에서는 신규 연구 DES를 실행하지 않았다. 단위 테스트·골든 검증의 짧은 엔진 실행은 본 실험과 구별한다.

## 보존 결과

첫 보존 커밋 `0e5420c`에 기존 미커밋 코드·설정·문서를 저장했다. 대용량 검증 자료 2,995개, 3,204,675,688 bytes는 원래 경로에 유지하고 [manifest](provenance/dt-wip-20261013/external_artifacts.json)에 경로·크기·SHA-256을 저장했다. Git만 복제하면 외부 원자료는 복원되지 않으므로 원래 위치를 별도로 보존해야 한다.

초기 보존 커밋에는 이전 작업의 화면 변경도 들어 있다. **이번 재설정 변경 범위는 보존 커밋 이후 diff로 판단한다.** 그 이후 frontend·server·DES 엔진·라인 파라미터·AGENTS.md·TOOLS.md·SKILL.md는 변경하지 않았다. main 브랜치는 변경하지 않았다.

기존 실행 도구는 `archive/dt_legacy_20261013/`에 원본을 보존하고 INVALID 실행 구조로 표시했다. 이전 경로는 명시적으로 새 도구를 안내하며 실패한다. 이는 과거 연구 자료나 유효 P1·15쌍 파일럿의 무효 선언이 아니다.

## 디렉터리 구조

```text
aria/simulation/dt/
  plan.py                 기준 A 2700 + 상한 A 270 + B 사후 조건
  posthoc.py              저장 NG 도착의 FCFS 처리와 1000개당 정규화
  evaluation.py           기존 5% 소스 준비와 평가 유지
  replay.py               기존 결정론과 GT 경계 유지
  line.py                 기존 출처 태그와 라인 구성 유지
tools/
  run_dt_matrix.py        입력·재사용 hash 확인 및 현행 계획 출력
  benchmark_dt.py         A trial만 허용; 예전 독립 실행 CLI 차단
  postprocess_dt.py       저장 A 하나의 B 기본·해당 OFAT 결과 생성
  dt_posthoc_reinspection.py  기존 import 호환
  verify_dt_posthoc.py    저장 15쌍 B 일치·GT hash·부품 집합 검증
archive/dt_legacy_20261013/
  INVALID.md              이전 실행 도구와 초기 명세 보존 설명
  *.py                    이전 도구 원본
docs/specs/ARIA_DT_Reset_BuildSpec_v3.md
  사용자 확정 최신 명세
docs/provenance/dt-wip-20261013/
  external_artifacts.json 대용량 기존 원자료 목록
docs/validation/aria_dt_reset_20261013/
  plan/execution_plan.json
  posthoc_verified/gate.json
  postprocess-smoke/completion.json
  golden-trace.txt
  constant-regression.json
  backend-tests-host.txt
```

## 검증 결과

| 검증 | 결과 |
|---|---|
| 백엔드 전체 | **141 passed**, 13 warnings, 13.05초 |
| PostgreSQL 통합 | 기존 격리 fixture `aria_dt`의 3개 시험 포함, skip 없음 |
| 비전 골든 | **diff 0** |
| constant DES | **6/6 조건 바이트 일치** |
| 사후 B 파일럿 | **15쌍·615개 지표 통과**, 부품 시각 허용오차 2µs |
| 사후 계산 CLI | 저장 A 하나에서 기본 B + 6변형 생성, 신규 DES 0 |
| 계획 완전성 | DES 2,970개 고유 조건, 상한 270개, B 사후 4,320개 |
| 실행 제한 | `--execute`는 입력 읽기·출력 생성 전에 거부 |
| filesystem MCP | 프로젝트 루트와 uploads/outputs/data 구성 경로 시험 통과 |

13개 경고는 기존 FastAPI 이벤트 등록 방식의 deprecation이다. 샌드박스 실행은 CAD HTTP 시험에서 멈추고 PostgreSQL 접속이 제한됐다. 대기 프로세스는 종료했으며, 허용된 호스트 환경에서 전체 테스트를 다시 실행해 위 결과를 얻었다. 패키지를 설치하거나 DB 서비스를 새로 구성하지 않았다.

5%는 소스 생성 확률이다. 기존 소스 재샘플링 구현과 회귀를 보존했으며 관측 불량률을 정확히 5%로 보정하지 않았다. 1,000개당 지표의 분모는 워밍업 이후 본 라인 출구 전체(HOLD 포함)다. NG·오탐·인시는 정규화하며, 큐 잔량·대기시간·활용률도 별도 보존한다.

## 재현 명령

저장소 루트에서 기존 `aria` 환경을 사용한다. 아래 경로가 이미 존재하면 새 출력 이름을 사용한다. 출력 폴더와 원자료를 덮어쓰지 않는다.

```sh
conda activate aria
export PYTHONPATH=.

# 계획만 출력: 본 실행 없음
python -m tools.run_dt_matrix \
  --p1 docs/validation/aria_dt_20261012_02/p1_verified \
  --pilot-results docs/validation/aria_dt_20261013_03/des_pilot30 \
  --out outputs/dt_review_plan

# 기존 15쌍으로 사후 B 검증: 신규 DES 없음
python -m tools.verify_dt_posthoc \
  --pilot docs/validation/aria_dt_20261013_03/des_pilot30 \
  --p1 docs/validation/aria_dt_20261012_02/p1_verified \
  --out outputs/dt_posthoc_review

# 저장된 A 하나를 사후 계산; 실제 A run ID로 치환
python -m tools.postprocess_dt \
  --run docs/validation/aria_dt_20261013_03/des_pilot30/runs/<A_RUN_ID> \
  --p1 docs/validation/aria_dt_20261012_02/p1_verified \
  --out outputs/dt_posthoc_one_run

python tests/golden_trace.py --verify
python tools/verify_dt_constant.py \
  --baseline docs/validation/aria_dt_20261012_01/baseline/des_golden.json \
  --out /tmp/aria_constant_review.json

# 이 워크스테이션의 기존 격리 DB와 기존 임시 Python 의존성 사용
PYTHONPATH=/tmp/aria-dt-dbdeps:. \
ARIA_TEST_POSTGRES_DSN='host=127.0.0.1 port=55433 user=aria dbname=aria_dt connect_timeout=3' \
python -m pytest tests -q
```

마지막 명령은 현재 워크스테이션의 테스트 fixture용이다. 다른 환경에서는 격리 DB·스키마·테스트 데이터를 준비하고 해당 DSN을 사용해야 한다. DSN 없이 실행하면 PostgreSQL 3개는 skip되므로 전체 통과와 구별한다.

## filesystem MCP와 추가 확인 대상

`aria/mcp/servers/filesystem_mcp.py`의 BASE_DIR를 `Path(__file__).resolve().parents[3]`로 수정했다. SANDBOX_ROOTS는 프로젝트의 uploads·outputs·downloads·logs·scratch·data를 가리킨다. data가 외부 심볼릭 링크인 현재 환경에서 실제 외부 대상 접근 권한을 확장한 것은 아니다.

아래 같은 패턴은 목록만 확인했으며 수정하지 않았다. 수정하려면 별도 확인이 필요하다.

| 파일 | 현재 표현 |
|---|---|
| `aria/mcp/servers/database_mcp.py:25` | `Path(__file__).parent.parent.resolve()` |
| `aria/mcp/servers/huggingface_mcp.py:19` | `Path(__file__).parent.parent.resolve()` |
| `aria/mcp/servers/shell_exec_mcp.py:38` | `Path(__file__).parent.parent.resolve()` |

## 본 실행 전 남은 조건

본 실행과 상한 seed0 비용 탐색은 시작하지 않았다. `--execute`는 현재 차단되어 있으며 사용자 확인 후 실행 단계에서 활성화해야 한다. 기존 계획의 시간·저장량은 추정이며, 8시간 제한과 저장 여유 조건을 새 실측으로 확인해야 한다. 원자료 로그 최적화·추가 P1 측정·화면 개선을 이번 작업에 포함하지 않았다.

변경 목록은 보존 커밋을 기준으로 `git diff 0e5420c --stat`로 확인한다. 세부 파일 통계는 [변경 통계](provenance/dt-wip-20261013/refactor-diff-stat.txt)에 남긴다.
