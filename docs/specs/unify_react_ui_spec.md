# ARIA 통합 명세서 — React 단일 UI 일원화 + 6A 포팅 (for Antigravity IDE)

> 대상: Antigravity 에이전트가 구현 → 빌드 → 브라우저로 검증(녹화) → 푸시.

## 0. 목표 (Why)

프론트엔드를 **React 하나로 통합**한다:
- React = 유일한 UI. FastAPI는 순수 백엔드 + **React 빌드(dist)를 `/`로 서빙**.
- `templates/index.html` 서빙은 내린다(파킹). 어느 URL로 들어와도 React로 수렴.
- **6A 라이브 학습 뷰를 React로 포팅**(현재 templates에만 있음) → 통합해도 라이브 뷰 유지.

백엔드 6A(`/api/train/upload` + WS `type:"training"` 브로드캐스트)는 **이미 완성** → B는 순수 프론트.

---

## 1. 범위 (Scope)

**포함:**
- A) FastAPI가 `frontend/dist`를 `/`로 서빙(+ `/assets` 마운트), templates 라우트 파킹
- B) `TrainingViewer.jsx`(ZIP 업로드 + WS `type:"training"` 렌더) + Dashboard 연결 + `uploadTraining` API
- C) README 표준 UI를 **React**로 정정(직전 templates 표기 뒤집기)

**제외(다음):**
- "고도화" 검사 기능 추가 → 통합 후 별도 슬라이스
- 실제 학습/CAD/MCP 관측 서버 → 6D/6E/6C
- 공개 배포(Vercel/터널) → 통합 후 별도

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/` (빌드) | `npm install && npm run build` → `frontend/dist` 생성 |
| `frontend/.env.production` | `VITE_API_URL=''`(빈 값) 확인 — 빌드본이 same-origin(8080)으로 API/WS 호출 |
| `app.py` | `/assets` 마운트 + `/`가 `frontend/dist/index.html` 서빙 + (선택)SPA 폴백, templates 라우트 파킹 |
| `frontend/src/api/apiClient.js` | `uploadTraining(file)` → `POST /api/train/upload` 추가 |
| `frontend/src/components/TrainingViewer.jsx` (신규) | ZIP 업로드 + 진행바·loss·프리뷰 렌더 |
| `frontend/src/components/Dashboard.jsx` | WS `type:"training"` → state 라우팅 + `<TrainingViewer>` 마운트 |
| `README.md` | 표준 UI = React로 정정 |

---

## 3. 작업 명세 (What)

### 3-A. 백엔드 서빙 일원화 — `app.py`

빌드 먼저:
```
cd frontend && npm install && npm run build   # → frontend/dist/ (index.html + assets/)
```

`app.py` 정적 마운트 부근(현재 L89~90)에 추가:
```python
from fastapi.responses import FileResponse
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")
```

`/` 라우트(현재 L614 templates 서빙)를 dist 서빙으로 교체:
```python
@app.get("/", response_class=HTMLResponse)
async def root_spa():
    return FileResponse("frontend/dist/index.html")
```

(선택) SPA 폴백 — `/api`·`/ws`·`/static`·`/uploads`·`/outputs`·`/assets`는 이미 별도 라우트/마운트라
먼저 매칭되므로, 맨 끝에 두는 catch-all만 추가하면 안전하다(이 앱은 클라이언트 라우터가 없어 필수는 아님):
```python
@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str):
    return FileResponse("frontend/dist/index.html")
```
- `templates/`는 **삭제하지 말 것**(파킹). 더 이상 `/`에서 서빙되지 않으면 충분.
- Vite `base: './'`이므로 `/`에서 서빙 시 `/assets/...`로 해석되어 위 마운트와 일치한다.

### 3-B. 6A를 React로 포팅 (프론트 전용)

**(1) `apiClient.js` — 업로드 함수 추가** (기존 `analyzeImage` 패턴 재사용):
```javascript
export async function uploadTraining(file) {
  const fd = new FormData();
  fd.append('file', file);
  const { data } = await api.post('/api/train/upload', fd,
    { headers: { 'Content-Type': 'multipart/form-data' } });
  return data;   // { run_id, n_images, classes, status }
}
```

**(2) `TrainingViewer.jsx` 신규** — 표현 + 업로드 컨트롤:
```jsx
import { useState } from 'react'
import { uploadTraining } from '../api/apiClient'

export default function TrainingViewer({ training }) {
  const [busy, setBusy] = useState(false)
  const onPick = async (e) => {
    const f = e.target.files?.[0]; if (!f) return
    setBusy(true)
    try { await uploadTraining(f) } finally { setBusy(false) }
  }
  const pct = training
    ? Math.round((training.step / training.total_steps) * 100) : 0
  return (
    <div className="training-viewer">
      <label className="btn">
        ZIP 업로드(학습)
        <input type="file" accept=".zip" hidden onChange={onPick} disabled={busy} />
      </label>
      {training && (
        <div>
          <div style={{ height: 8, background: '#222', borderRadius: 4 }}>
            <div style={{ width: `${pct}%`, height: 8, background: '#3DCAA5',
                          borderRadius: 4, transition: 'width .3s' }} />
          </div>
          <div>step {training.step}/{training.total_steps} ·
               loss {training.metrics?.loss ?? '-'} · {training.status}</div>
          {training.preview_image &&
            <img src={training.preview_image} alt="preview"
                 style={{ maxWidth: 300, marginTop: 8 }} />}
        </div>
      )}
    </div>
  )
}
```

**(3) `Dashboard.jsx` — WS 라우팅 + 마운트**
- 기존 WS `onmessage`(약 L173 useEffect) 핸들러에 분기 추가, training state 도입:
```jsx
const [training, setTraining] = useState(null)
// onmessage 안:
if (data.type === 'training') { setTraining(data); return }
```
- 렌더 트리(예: InspectionViewer 인근, 약 L443)에 마운트:
```jsx
<TrainingViewer training={training} />
```
> WS는 Dashboard의 기존 연결 하나만 사용(새 소켓 만들지 말 것). preview_image는 백엔드가
> `/uploads/...` 경로로 주므로 same-origin(8080) 또는 dev proxy에서 그대로 표시된다.

### 3-C. README 정정
직전에 "표준 UI = templates/index.html"로 적었던 부분을 **React**로 뒤집는다:
```markdown
## Frontend (단일 표준 UI = React)
- 표준 UI: `frontend/` React 앱. 프로덕션은 `npm run build` 후 FastAPI가 `frontend/dist`를 `/`로 서빙(→ http://<host>:8080/).
- 개발: `cd frontend && npm run dev` (5173, Vite proxy로 8080 백엔드 연결).
- `templates/index.html`은 비활성(parked) — 더 이상 서빙되지 않음.
```

---

## 4. 수용 기준 (Antigravity가 확인 + 내가 grep)

### 4-1. 서빙 일원화 (grep, app.py)
```
grep -n "frontend/dist/index.html\|/assets\|FileResponse" app.py
grep -n "TemplateResponse" app.py    # '/'가 더는 templates 서빙 안 함을 확인
```

### 4-2. 6A React 포팅 (grep, frontend)
```
grep -n "uploadTraining\|/api/train/upload" frontend/src/api/apiClient.js
test -f frontend/src/components/TrainingViewer.jsx && echo OK
grep -n "type === 'training'\|TrainingViewer\|setTraining" frontend/src/components/Dashboard.jsx
```

### 4-3. 회귀 가드
```
grep -c "/api/train/upload" app.py                 # 백엔드 6A 유지 >0
grep -c "inspect_via_registry" autonomous_agent.py # >0
grep -c "get_vlm" agents/vision_agent.py           # >0
grep -c "get_backbone" product_registry.py         # >0
grep -c "mcpDetectors" mcp_config.json             # >0
```

### 4-4. 빌드 + 런타임 (Antigravity가 수행)
- `cd frontend && npm install && npm run build` → 에러 없이 `dist/` 생성.
- 백엔드 기동(8080) 후 **`http://<host>:8080/` 가 React UI**로 뜨는지(템플릿 아님).
- React UI에서 ZIP 업로드 → 진행바·loss·프리뷰가 움직이는지.
- **Antigravity 브라우저 에이전트로 그 화면을 녹화/스크린샷** → walkthrough 아티팩트로 첨부(시각 증거).

> 4-1·4-2·4-3 grep 통과 + 4-4 빌드/녹화 증거면 완료.

---

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 브랜치 재clone → 4-1·4-2·4-3 grep 확인. 4-4는 Antigravity 녹화/스크린샷으로 확인.
(주의: `frontend/dist`는 `.gitignore` 대상일 수 있어 clone엔 없을 수 있음 → 빌드 산출물은 4-4 런타임으로 검증, 코드 배선은 4-1·4-2로 검증.)

---

## 6. 커밋
- 브랜치: `feat/unify-react-ui`
- 메시지(예): `feat(ui): serve React as single FastAPI UI on :8080, port 6A live-training view to React, park templates`

---

## 7. Antigravity 실행 가이드 / 주의
- **권장 자율 모드:** Agent-assisted(결정 후 검증 체크포인트). 빌드·서빙 교체는 되돌리기 쉬우나 검증을 끼우는 게 안전.
- **`.env.production`의 `VITE_API_URL`은 빈 값**이어야 빌드본이 same-origin(8080)으로 API/WS를 부른다. 절대경로가 박혀 있으면 빌드본이 엉뚱한 백엔드를 호출한다.
- **`templates/` 삭제 금지**(파킹만). `frontend/` 이동 금지(`test_s3_led.py`가 참조).
- WS는 Dashboard의 기존 연결 **하나만** 사용 — TrainingViewer가 새 소켓을 열지 않게.
- 개발은 그대로 5173(Vite proxy), 프로덕션만 8080(dist 서빙) — 둘이 같은 React 코드라 더는 화면이 갈리지 않는다.
- 빌드/서빙이 끝나면 8080 좀비 프로세스가 없는지 확인(`ss -ltnp | grep :8080`) 후 단일 인스턴스로 기동.
