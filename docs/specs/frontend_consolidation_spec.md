# ARIA 정리 명세서 — 프론트엔드 통합 (Frontend Consolidation)

## 0. 목표 (Why)

"URL마다 다른 화면"의 원인은 **UI 코드가 두 벌** 공존하기 때문이다:
- `templates/index.html`(+ `static/js/main.js`) — FastAPI `/`가 서빙. **작동 중 + 6A 패널 보유.**
- `frontend/` React SPA — 빌드(dist) 없음. **Vercel만 이걸(의 index) 서빙해 분기를 만듦.**

가장 작동하는 `templates/index.html`을 **단일 표준 UI**로 굳히고, 분기를 만드는 **Vercel 배포를 끈다.**
`frontend/`는 **이동/삭제하지 않는다**(테스트가 참조) — 단지 서빙되지 않게만 한다.

---

## 1. 범위 (Scope)

**포함:**
- 분기 원인인 `vercel.json` 비활성화(파킹)
- 표준 UI를 문서로 명시(README/주석)
- `frontend/`에 "비활성" 표식 1개

**건드리지 말 것:**
- `frontend/` 디렉터리 자체 이동/삭제 금지 — `test_s3_led.py:179,208`이 `frontend/src/components/*.jsx`를 읽는다.
- `app.py`의 라우트/CORS(`*.vercel.app` 허용)는 그대로 둬도 무해(원하면 나중에 정리).
- 6A·1~4단계 코드 일체.

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `vercel.json` | `_deprecated/vercel.json.bak`로 이동(파킹) — Vercel이 React SPA를 서빙하지 않게 |
| `README.md` (또는 신규 `FRONTEND.md`) | "표준 UI = templates/index.html (FastAPI `/`)" 명시 |
| `frontend/PARKED.md` (신규) | "비활성 — 표준 UI 아님" 한 줄 표식 |

---

## 3. 작업 명세 (What)

### 3-A. Vercel 분기 차단 (핵심)

```
mkdir -p _deprecated
git mv vercel.json _deprecated/vercel.json.bak
```

- 이걸로 `vercel.app`이 더 이상 다른 페이지(React SPA)를 서빙하지 않는다.
- 참고: 현재 `vercel.json`의 API 프록시 대상(`freebsd-wav-...trycloudflare.com`)은 trycloudflare
  특성상 매 실행마다 바뀌는 임시 주소라 이미 죽었을 가능성이 높다 → 끄는 게 맞다.

### 3-B. 표준 UI 문서화

`README.md`에 한 단락 추가(또는 `FRONTEND.md` 신규):

```markdown
## Frontend (단일 표준 UI)

- **표준 UI:** `templates/index.html` (+ `static/js/main.js`) — FastAPI가 `/`로 서빙.
  로컬: `uvicorn app:app --port 8080` → http://localhost:8080/
- `frontend/`(React SPA)는 **비활성(parked)**. 빌드(dist)도 없고 서빙되지 않음.
  추후 React로 전환하려면 별도 작업으로 6A 등 기능을 포팅해야 함.
- 공개 URL이 필요하면: 안정적 터널(named cloudflared/ngrok)로 FastAPI를 노출하고,
  Vercel을 쓸 경우 catch-all `/(.*)`도 그 터널로 프록시해 **같은 templates UI**가 뜨게 한다
  (별도 index를 서빙하지 않는다).
```

### 3-C. frontend 비활성 표식

`frontend/PARKED.md` 신규:

```markdown
# PARKED — 비활성 React SPA

이 디렉터리는 현재 표준 UI가 아닙니다. 표준 UI는 `/templates/index.html`(FastAPI 서빙)입니다.
빌드/배포하지 마세요. (test_s3_led.py가 이 안의 컴포넌트를 참조하므로 이동/삭제도 금지.)
```

---

## 4. 수용 기준 (Acceptance Criteria) — GitHub 확인

1. `vercel.json`이 루트에서 사라지고 백업으로 이동:
   ```
   test -f vercel.json && echo "FAIL: 아직 루트에 있음" || echo "OK: 루트에 없음"
   ls _deprecated/vercel.json.bak
   ```
2. 표준 UI 문서화:
   ```
   grep -ni "templates/index.html" README.md FRONTEND.md 2>/dev/null
   ```
3. `frontend/` **그대로 유지**(테스트 경로 유효):
   ```
   test -f frontend/src/components/Dashboard.jsx && echo OK
   test -f frontend/PARKED.md && echo "표식 OK"
   ```
4. (회귀 가드) 표준 UI·6A·1~4단계 유지:
   ```
   grep -n '@app.get("/"' app.py                 # templates 서빙 유지
   grep -c "renderTrainingPanel" static/js/main.js   # 6A 패널 유지(>0)
   grep -c "inspect_via_registry" autonomous_agent.py # >0
   grep -c "/api/train/upload" app.py             # 6A 엔드포인트 유지(>0)
   ```

> 1~3 통과 + 4 회귀 없음이면 완료. 이후 브라우저로 들어가는 UI는 어느 경로든 **templates/index.html 하나**로 수렴.

---

## 5. 검증 절차 (내가 수행)

"푸시 완료" → 브랜치 재clone → 4-1~4-4 확인 → 통과 시 6B(ZIP→tar 샤딩 + 에이전트 판단)로.

---

## 6. 커밋

- 브랜치: 기존 작업 브랜치 연속 또는 `chore/frontend-consolidation`
- 메시지(예): `chore(frontend): standardize on FastAPI templates UI, park Vercel/React SPA`

---

## 7. 주의

- **`frontend/` 이동 금지** — `test_s3_led.py`가 깨진다. 끄는 건 Vercel(`vercel.json`)만.
- 지금 6A를 보려면 표준 UI(`http://<서버>:8080/`)에서 ZIP을 `/api/train/upload`로 POST. Vercel URL 아님.
- 공개 배포는 별도 작업(안정 터널 + Vercel을 순수 프록시로). 지금은 "하나의 작동하는 UI"에 집중.
