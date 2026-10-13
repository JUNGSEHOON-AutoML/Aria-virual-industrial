# L1 비전 분석 연결 결과

캠퍼스 9절과 Site 선행 준비는 `f55468e`에 커밋했다. LiveOps 첨부 10.0–10.6을 BuildSpec 끝에 병합하고 5절·6절에 L1–L4 범위와 4h/4h/5h/3h 예산을 추가했다. 새 순서는 M1→M2→L1→L2→L3→L4→M3→M4→M5→M6→M7이다. 이미 완료된 Replay 기능은 보존했다. 이번 단계에서 L1을 구현했으며 L2–L4와 M7 구현은 아직 대기다.

## 산출물

- `docs/reports/vision_audit/{bottle,screw,carpet}/REPORT.md` 및 클래스/모델별 `report.json`, 9개 모델 REPORT·점수 분포 SVG.
- 상단 **비전 분석**: 클래스·모델 선택, 점수 분포, 유형별 탐지율, 오탐 배경 반응, 원본/입력시야/히트맵/GT/proxy 갤러리, 모델 판정 차이 전체, 파일럿 B 공정 영향.
- 오탐 갤러리는 점수 상위 8개, 미탐은 전부. screw 미탐은 coreset 82, ccifps 75, random_same_k 103개이며 임계값을 바꿔 숨기지 않았다.
- 새 읽기 API는 JSON 파일의 바이트를 그대로 반환한다. 임의 파일 경로·근거 metadata.json은 공개하지 않는다.

## 재사용 및 검증

기존 `aria/simulation/des/evidence.py:EvidenceStore`로 히트맵을 생성했다. 200개 보관 제한에 도달하지 않도록 모델별 독립 디렉터리에 저장하고 각 갤러리 크기를 확인했다. 기존 `aria/simulation/dt/posthoc.py:reconstruct_b`로 파일럿 공정 영향을 인용했다. 9개 P1 모델 모두 저장된 common_maps/raw_patch_scores가 있어 재추론하지 않았다. 주요 P1 파일 SHA를 complete.json과 대조했다.

176개 백엔드 테스트 통과(14 warnings), 골든 diff 0, CPU 프런트 빌드 성공. `gates/l1.json`에서 9개 CSV 재집계·갤러리 정합성과 3클래스 화면/보고서 JSON·표시 수치를 확인했다. 실제 GPU 미확인. 모든 생성 작업은 CPU, CUDA_VISIBLE_DEVICES 빈 값으로 수행했다. 본 실험과 GPU는 변경하지 않았다.

정상 fit 이미지 테두리 색 중앙값에 대한 RGB 거리의 고정 Otsu proxy를 물체 마스크로 사용했다. 테스트/GT로 튜닝하지 않았다. 색이 비슷하거나 화면 전체가 질감인 carpet에 부정확할 수 있으므로 배경 간섭 원인을 단정하지 않는다. 분포 중첩은 두 경험적 점수 범위 교집합의 이미지 수로 정의한다. 입력 시야·GT·히트맵은 resize 256, center crop 224 좌표이며 GT는 보고서 표시 전용이다. 서로 다른 파일럿 조건의 공정 결과를 모델 효과로 직접 비교하지 않는다.

## 기존 기능 연결 조사

| 기능 | 기존 구현 | 현재 연결 상태 |
|---|---|---|
| P1 점수·맵 | 검증된 P1 per_image/common_maps/raw_patch_scores | L1 읽기 전용 재사용 |
| 근거 이미지 | DES EvidenceStore | L1 재사용 |
| B 평가 | DT reconstruct_b | L1 재사용 |
| 라이브 공정 | FactoryService·factory router·FactoryScene | L2 대상, 새 구현 안 함 |
| 실제 검출 | InspectionAdapter·detectors·EvidenceWorkbench | L2 대상, 새 구현 안 함 |
| 팔 작업 | robot.py·RobotArm/RobotWorkbench | L2 대상, 새 구현 안 함 |
| 순찰·수리 | PatrolSupervisor·MaintenanceHarness·PatrolPanel | L2/L4 대상, 새 구현 안 함 |
| 에이전트 | IndustrialAgent·factory_mcp·MessagePanel | L3 대상, 새 구현 안 함 |

갤러리 이미지·GT·원본은 ignored 로컬 산출물이다. 공개 커밋에는 집계 JSON·Markdown·점수 분포 SVG와 코드만 포함한다. 새 클론은 보존된 P1·data를 연결한 뒤 `CUDA_VISIBLE_DEVICES='' PYTHONPATH=. python -m tools.build_vision_audit`로 이미지를 생성해야 한다.
