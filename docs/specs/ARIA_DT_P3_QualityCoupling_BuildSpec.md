# P3 — AI replay + 정책 A/B

2026-10-13 사용자 메시지를 최우선으로 적용. 첨부 PDF를 재추출했으나 해당 파일의 P3에는 아직 oracle 수정 내용이 없으므로 최신 사용자 메시지의 요구를 여기에 명시한다.

- A: AI NG 즉시 폐기, OK 출하, deadline 초과 HOLD.
- B: AI NG를 유한 buffer 및 capacity1 사람 재검사 스테이션으로 보낸다. `reinspect_oracle`만 GT를 읽어 가정 민감도/특이도와 seed 고정 독립 RNG로 최종 OK/NG를 생성한다. GT가 없거나 prediction ID의 GT가 누락되면 실행 전에 실패.
- 기본 sensitivity=specificity=1.0; 대안 .95/.98, 처리시간10/30/60초. 전부 assumed. 실제 사람 성능·AI 성능으로 보고 금지.
- 전체 코드에서 GT 파일 reader는 `reinspect_oracle` 및 `evaluation`으로 한정. AI catalog는 image/score/threshold/verdict의 whitelist만 읽는다.
- AI 판정은 GT 열 삭제/변경에 불변. B 전체 공정 출력은 GT에 의존하므로 GT 불변성을 요구하지 않는다.
- 이벤트 source는 `ai_replay` 또는 `reinspect_oracle`로 구분. oracle은 AI score/threshold를 위조하지 않는다.
- paired 비교에서 seed+part+image keyed RNG로 선택된 NG 집합 변화 때문에 사람 RNG가 밀리는 문제를 방지한다.
- 오탐 회복, 잘못된 폐기, 유출, HOLD, 재검사 queue/활용률, generated=completed+WIP를 평가한다.
- rework 순환 없음: DAG의 별도 스테이션. 미탐 OK는 재검사로 보내지 않는다.
- A/B 기본 full matrix 및 B 민감도 교차 범위는 실행 비용과 사용자 답변으로 고정한다. score가 좋다는 이유로 범위를 늘리지 않는다.

## 최종 실행 수 (사용자 2026-10-13 확정)
3클래스 전부 포함. 본 실험5400 + 일변량 민감도1620 = 7020. bottle은 대조군. 먼저 class×cell/speed×policy를 포함한 30개만 실행하여 비용을 측정한다. 예상 총시간8시간 초과 시 본 실행 금지. 비용 비율은 후처리. P1 결과로 클래스 교체/제외 금지. 모델 순위 변화는 보고만 하고 무승인 확대 금지.
