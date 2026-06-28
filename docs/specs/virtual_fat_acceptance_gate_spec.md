# ARIA 명세서 — 가상 FAT 합격 게이트 (PASS/FAIL) for Antigravity

> 목표: VERIFIER의 escape율/오검출율을 **합격 기준에 대한 PASS/FAIL 판정**으로. 원점 비평("3σ만으론 놓침률 모름")을 *합격선*으로 닫고, 산업현장 씬의 상태판이 이 판정을 표시.
> 단일 `main` 위 첫 슬라이스. 백엔드 가벼운 확장 + 배지.

## 1. 범위 (Scope)

**포함:** `run_validation`에 `pass_criteria`(설정형) + `fat_verdict`(PASS/FAIL); `/api/sim/validate`가 기준 받아 전달 + FAT agent_status emit; SimulationView PASS/FAIL 배지.
**제외:** Test Runner(스위트), Fault Framework, 실NG 데이터 정교화 — 후속.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `validation/validate.py` | pass_criteria + fat_verdict 계산·반환 |
| `app.py` `/api/sim/validate` | 기준 수신 + FAT agent_status |
| `frontend/src/components/SimulationView.jsx` | PASS/FAIL 배지 |

## 3. 작업 명세 (What)

### 3-A. `validation/validate.py` — 합격 판정
`run_validation` 끝, 반환 직전:
```python
# 합격 기준(기본값 — payload로 덮어쓸 수 있게 인자로 받음)
max_escape = (criteria or {}).get("max_escape_rate", 0.05)   # 놓침 ≤ 5%
max_fp     = (criteria or {}).get("max_fp_rate",     0.20)   # 오검출 ≤ 20%(놓침이 더 치명적이라 느슨)
er = escapes / n_def if n_def else None
fpr = fp / len(good)
if n_def == 0:
    fat_verdict = "N/A"        # NG 표본 없음 → 합격 판정 불가
else:
    fat_verdict = "PASS" if (er <= max_escape and fpr <= max_fp) else "FAIL"
# 반환 dict에 추가:
#   "pass_criteria": {"max_escape_rate": max_escape, "max_fp_rate": max_fp},
#   "fat_verdict": fat_verdict
```
- `run_validation(manifest, score_fn=None, criteria=None)`로 시그니처에 `criteria` 추가(기본 None).

### 3-B. `app.py` `/api/sim/validate` — 기준 전달 + FAT 에이전트
```python
criteria = payload.get("criteria")                 # 없으면 기본값 사용
result = run_validation(manifest, criteria=criteria)
# FAT 판정을 에이전트 상태로 broadcast (씬 상태판/칩이 읽음)
v = result.get("fat_verdict", "N/A")
state = "done" if v == "PASS" else ("idle" if v == "FAIL" else "running")
await manager.broadcast({"type": "agent_status", "agent": "FAT",
    "state": state, "detail": f"{v} · escape {result.get('escape_rate')}"})
return result
```

### 3-C. SimulationView — PASS/FAIL 배지
검증 결과 표시 영역에, 기존 escape/FP 옆:
```jsx
{validation?.fat_verdict && validation.fat_verdict !== 'N/A' && (
  <div style={{
    display:'inline-block', padding:'4px 14px', borderRadius:8, fontWeight:700, fontSize:13,
    color: validation.fat_verdict === 'PASS' ? '#34d399' : '#f87171',
    border: `1.5px solid ${validation.fat_verdict === 'PASS' ? 'rgba(52,211,153,0.6)' : 'rgba(248,113,113,0.6)'}`,
    background: validation.fat_verdict === 'PASS' ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)' }}>
    가상 FAT · {validation.fat_verdict}
  </div>
)}
{validation?.pass_criteria && (
  <span style={{ fontSize:11, color:'#94a3b8', marginLeft:8 }}>
    기준: escape ≤ {(validation.pass_criteria.max_escape_rate*100).toFixed(0)}% ·
    FP ≤ {(validation.pass_criteria.max_fp_rate*100).toFixed(0)}%
  </span>
)}
```

## 4. 수용 기준
```
grep -n "fat_verdict\|pass_criteria\|max_escape_rate" validation/validate.py
grep -n "criteria\|FAT\|fat_verdict" app.py
grep -n "가상 FAT\|fat_verdict" frontend/src/components/SimulationView.jsx
grep -c "build_bank\|loopRef\|factoryLoop" app.py frontend/src/components/SimulationView.jsx  # 회귀: 루프·스코어러 보존
python -m py_compile validation/validate.py app.py
```
- 런타임: 검증 시 escape/FP와 함께 **PASS/FAIL 배지** + 기준선 표시. NG 없으면 N/A로 숨김.

## 5. 검증 (내가 수행)
재clone → grep(fat_verdict·criteria·배지) + py_compile + 회귀. 통과 시 — 산업현장 씬이 이 판정을 상태판에 띄움.

## 6. 커밋
- 브랜치: `feat/virtual-fat-gate` · 메시지: `feat(validation): virtual FAT acceptance gate — PASS/FAIL vs configurable escape/FP criteria`

## 7. 주의
- 기준은 **설정형**(payload.criteria) — 기본 escape≤5%·FP≤20%. 놓침이 더 치명적이라 escape를 엄격히.
- NG 표본 0 → **N/A**(합격 판정 불가). 솔직하게 표기.
- 합성 NG로 판정하면 데모용 — *진짜* 합격은 실NG 필요(후속). 지금은 게이트 *메커니즘*.
- main 단일 라인 위에서 작업, 새 분기 남발 금지.
