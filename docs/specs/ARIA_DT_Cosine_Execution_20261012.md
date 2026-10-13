> 최신 사용자 확정 사항 (2026-10-13): 아래 초기 수량 계획보다 우선한다.
> bottle·screw·carpet 전부 본 공정 실험에 포함한다. 본 실험 5,400회 + 단일요인 민감도 1,620회 = 7,020회.
> bottle은 사전 지정 대조군. 클래스는 P1 성능으로 변경/제외하지 않는다.
> 별도 30회 파일럿 후 8시간 이하일 때만 전체 실행한다. 실제 파일럿 및 판단은 `docs/validation/aria_dt_20261012_02/des_pilot30/cost_gate.json`.
> 비용 비율은 후처리이며 추가 실행 축이 아니다. 아래 초기 계획의 2,340/2,700회 표기는 최신 총량으로 사용하지 않는다.

# ARIA DT — 승인된 C 비교 / 2026-10-12

## 우선순위
사용자의 격리 환경 및 정확 cosine 검색 지시가 첨부 PDF와 기존 L2 profiler보다 우선한다. 역사적 논문 R 및 기존 recovery/integration 결과를 대체하지 않는다.

## 고정 조건
- 기존 aria 및 CCIFPS source/results 보존. 별도 conda `aria-faiss`에서만 NumPy/FAISS GPU 설치. 30분 설치 제한.
- 정상 train/test 특징은 기존 공식 WR50 L2+3 D1024 float32 캐시를 읽는다. 입력/가중치/특징 SHA-256 확인. 두 환경의 캐시 경로와 해시 동일성 기록. 전체 캐시 중복 추출 금지.
- bank fit / calibration을 정상 train 이미지 단위로 분리(seed 20260916, calibration ceil(20%)). test로 설정 선택 금지.
- 세 selector는 기존 CCIFPS recovery 설정, 공식 ApproximateGreedyCoresetSampler 10%, CCIFPS 실제 K와 같은 random(without replacement). ApproximateGreedy는 뱅크 선별 알고리즘 명칭이며 검색은 근사하지 않는다.
- 비교 search는 float32 L2 normalize, exact max inner product, anomaly=1-max(dot), k1, inference density off, sigma2. selector 내부 설정은 원본 그대로.
- FAISS IndexFlatIP GPU, useFloat16=False. NumPy chunk 동일 입력의 최대 점수 차이 <=1e-5 및 이미지 판정 변화 0을 calibration/test 전체에서 먼저 확인. 검사 실패 시 로그 보존 및 PyTorch exact matmul+max, TF32 off로 같은 게이트를 검사.
- threshold는 normal calibration score mean + 3 population SD, strict >. 세 방법 모두 동일 규칙. Pixel AP의 원 평가 함수와 image 판정 임계값은 별도 기록.
- 정상화 zero/nonfinite vector는 실패. 점수 clipping 없음.
- 사용 직전 compute PID와 여유 메모리 확인. worker당 GPU UUID 하나, cuda:0, CPU threads<=4. 다른 사용자 GPU 회피.
- 게이트 후 warmup50+실측1000, 단계 pre/feat/search/post와 실제 wall-clock total. 프로파일 입력은 정상 holdout round-robin. train/query 캐시 구축과 반복 추론 지연 측정은 구분.
- GPU/NumPy backend 결과 및 원/격리 환경 차이를 기록한다. 원 환경의 PyTorch fallback 결과를 FAISS 결과로 표기하지 않는다.

## 실행 경로
기존 `tools/profile_banks.py`는 L2 비교 경로로 보존한다. 신규 `tools/profile_dt_cosine.py`와 `tools/dt_exact_search.py`만 사용한다. 새 결과 root는 `docs/validation/aria_dt_20261012_02/`이다.

## 게이트와 후속 범위
P0 tests+baseline, P1 exact search+실측, P2 legacy 회귀 이후 P3–P6를 순서대로 수행한다. 전체 실행 미완료 상태에서 완료를 선언하지 않는다. 기본 P5 2700 DES 조건; 비용 민감도는 후처리. multi-k on/off는 사용자 k1 max 명세와 구분해 후속 범위를 명시한 후 실행하며, 기본 P5에 임의 추가하지 않는다.
