# 🌉 Agent Bridge Protocol

## Ralph ↔ Antigravity 파일 기반 통신 규약

### 디렉토리 구조
```
agent_bridge/
├── PROTOCOL.md                    ← 이 파일 (프로토콜 문서)
├── ralph_to_antigravity.json      ← Ralph → Antigravity 요청
└── antigravity_to_ralph.json      ← Antigravity → Ralph 응답
```

---

## Ralph → Antigravity 요청 형식

```json
{
  "from": "ralph",
  "request_id": "20260527_090000",
  "timestamp": "2026-05-27T09:00:00",
  "type": "fix_request | escalation | question",
  "status": "pending",
  "problem": "YOLO 바운딩박스 이미지가 텔레그램으로 안 옴",
  "file": "/absolute/path/to/vision_router.py",
  "function": "_run_yolo",
  "evidence": "result_image_path가 None으로 반환됨",
  "suggested_fix": "cv2.imwrite 후 result에 경로 저장 확인"
}
```

### 요청 타입
| type | 설명 |
|------|------|
| `fix_request` | Ralph가 문제를 발견하여 수정 요청 |
| `escalation` | Ralph가 자력 수정 시도 후 실패 → Antigravity에 위임 |
| `question` | 설계/구조 질문 |

---

## Antigravity → Ralph 응답 형식

```json
{
  "from": "antigravity",
  "request_id": "20260527_090000",
  "timestamp": "2026-05-27T09:05:00",
  "status": "fixed | rejected | needs_info",
  "file": "/absolute/path/to/vision_router.py",
  "summary": "result_image_path 키 이름을 output_image_path에서 수정",
  "detail": "수정 상세 내용",
  "changes_made": [
    "line 860: output_image_path → result_image_path"
  ]
}
```

### 응답 상태
| status | 설명 |
|--------|------|
| `fixed` | 코드 수정 완료 → Ralph가 구문 검사 후 텔레그램 보고 |
| `rejected` | 수정 불가 또는 불필요 (이유를 detail에 기록) |
| `needs_info` | 추가 정보 필요 (질문을 detail에 기록) |

---

## 통신 흐름

```
사용자 (텔레그램) → Ralph → 문제 발견
                            ↓
                  ralph_to_antigravity.json 작성
                            ↓
              Antigravity IDE 감지 (cron or watch)
                            ↓
                      코드 분석 & 수정
                            ↓
                  antigravity_to_ralph.json 작성
                            ↓
              Ralph 30분 루프에서 감지
                            ↓
                    구문 검사 (py_compile)
                            ↓
              텔레그램으로 결과 보고 → 사용자
```
