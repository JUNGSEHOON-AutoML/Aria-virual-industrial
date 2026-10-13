# BLOCKERS

- M5: 실험 대기. 확인 시 A 2,094/2,970, B·최종 REPORT 미생성. API 404와 진행 중 화면은 구현·검증; 완료 후 `python -m tools.gates.m5` 재실행. M6는 파일럿으로 진행.
- 실제 GPU 화풍·FPS 미확인: SwiftShader만 사용. GPU 확인은 작업 진행을 막지 않음.


- V2/V3 입력 범위: 이번 요청은 L1 오탐·미탐·판정 차이 이미지에 한정. 현재 L1 테스트 이미지 목록에는 V2의 별도 3D-AD 클래스 및 V3의 정상 학습 이미지가 포함되지 않으므로 자동 추가하지 않는다. 상세는 BuildSpec 11.5절. 명세 등록은 완료했으며 해당 입력 처리는 보류.

- M7 데이터 게이트: 3개 홀 9개 레인 중 8개 완료 실행 연결. CARPET random_same_k의 seed 0 / inline / 0.5 / profile은 아직 없음. 다른 조건으로 대체하거나 실험을 재실행하지 않음. 화면 게이트는 통과했고 `gates/m7.json`은 `pending_data`, pass=false로 보존. 해당 complete.json 도착 후 목록에 자동 반영되며 게이트 재실행 필요. 다음 독립 작업은 L2.
