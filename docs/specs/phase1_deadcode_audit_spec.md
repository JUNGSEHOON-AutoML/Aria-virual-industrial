# ARIA 명세서 — Phase 1: 정밀 안전 정리 (죽은 코드 감사) for Antigravity

> import 그래프로 **검증한 것만** 제거한다. 엔진(검사 Dashboard와 그 5개 컴포넌트)은 **절대 손대지 않는다.**
> 원칙: "UI에서 빼기"가 아니라 진짜 파일 삭제 — 그래서 **삭제 가능 근거 + 보존 목록**을 함께 명시한다.

## 0. 검증 근거 (왜 안전한가)

| 대상 | 근거 | 판정 |
|---|---|---|
| `ImageTo3D.jsx` (이미지3D) | App.jsx만 import(잎) | ✂ 삭제 |
| `templates/index.html` | app.py가 `TemplateResponse`로 안 씀(둘 다 `dist/index.html` 서빙) | ✂ 삭제 |
| `static/css/style.css`·`static/js/main.js` | **오직 templates/index.html만 참조**(죽은 Jinja UI) | ✂ 삭제 |
| `capture_ws.py` | imported_by=0, 엔트리/동적import 없음 | ✂ 삭제 |
| **`static/images/aria_logo.png`** | **Dashboard.jsx:90이 `/static/images/aria_logo.png` 사용** | 🔒 **보존** |
| **`/static` 마운트 (app.py L89)** | 위 로고를 서빙 | 🔒 **보존** |
| **`/api/quick` (app.py L492)** | 검사 이력(handleHistory)이 사용 | 🔒 **보존** |
| **Dashboard + 5 엔진 컴포넌트** | 가상공장 두뇌(WS·학습·스웜·HW·검사+인테이크) | 🔒 **보존** |
| `local_agent.py` | 독립 CLI 스크립트(`__main__`) — 무해, 별개 도구 | 보류(건드리지 않음) |

## 1. 범위 (Scope)

**포함(검증된 삭제만):**
1. **이미지3D 제거** — App.jsx에서 import·탭·렌더 분기 제거 + `ImageTo3D.jsx` 삭제.
2. **죽은 Jinja UI 제거** — `templates/index.html`, `static/css/style.css`, `static/js/main.js` 삭제 + app.py의 `TEMPLATES_DIR`(L43)·`Jinja2Templates`(L92) 정의 제거.
3. **고아 모듈 제거** — `capture_ws.py` 삭제.

**제외(절대 금지):** Dashboard/검사 및 5개 엔진 컴포넌트, `/static` 마운트, `aria_logo.png`, `/api/quick`, `local_agent.py`, SimulationView.

## 2. 작업 명세 (What)

### 2-A. 이미지3D 제거 (App.jsx + 파일)
```jsx
// App.jsx
// 1) import 줄 삭제: import ImageTo3D from './components/ImageTo3D'
// 2) 탭 버튼 삭제: {tab('image3d', '이미지 3D', '📐')}
// 3) 우상단 라벨 분기에서 image3d 제거
//    ARIA · {view === 'simulation' ? 'SIM-4' : 'INSPECTION'}
// 4) 렌더 분기 단순화:
{view === 'simulation' ? <SimulationView /> : <Dashboard />}
```
- 파일 삭제: `frontend/src/components/ImageTo3D.jsx`.
- (기본 랜딩은 이미 `'simulation'` — 유지.)

### 2-B. 죽은 Jinja UI 제거 (파일 + app.py)
- 파일 삭제: `templates/index.html`, `static/css/style.css`, `static/js/main.js`.
- `app.py`에서 제거:
  - L43 `TEMPLATES_DIR = BASE_DIR / "templates"`
  - L92 `templates = Jinja2Templates(directory=str(TEMPLATES_DIR))`
  - 관련 unused import(`Jinja2Templates`)가 있으면 함께 제거.
- **반드시 유지:** L89 `app.mount("/static", StaticFiles(directory="static"), name="static")` — 로고 서빙.
- **선행 확인:** `grep -n "templates\." app.py` 로 `templates` 객체 사용처가 **없음**을 확인 후 정의 삭제(있으면 그 호출부터 처리). `static/` 디렉토리는 남기고 `images/`만 보존.

### 2-C. 고아 모듈 제거
- 파일 삭제: `capture_ws.py`.

## 3. 수용 기준

### 3-1. 삭제 확인 (Greppable)
```
test ! -f frontend/src/components/ImageTo3D.jsx && echo "ImageTo3D 삭제 OK"
grep -c "ImageTo3D\|image3d" frontend/src/App.jsx          # → 0
test ! -f templates/index.html && echo "templates 삭제 OK"
test ! -f static/js/main.js && test ! -f static/css/style.css && echo "죽은 static 삭제 OK"
test ! -f capture_ws.py && echo "capture_ws 삭제 OK"
grep -c "Jinja2Templates\|TEMPLATES_DIR" app.py            # → 0
```

### 3-2. 🔒 보존 확인 (가장 중요 — 엔진/로고 살아있나)
```
test -f static/images/aria_logo.png && echo "로고 보존 OK"
grep -c 'mount("/static"' app.py                            # 1 (유지)
grep -c "/api/quick" app.py                                  # >0 (검사 이력 유지)
grep -c "SwarmChat\|TrainingViewer\|AgentSwarm\|HardwarePanel\|InspectionViewer" frontend/src/components/Dashboard.jsx  # 5 전부
grep -c "Dashboard\|SimulationView" frontend/src/App.jsx     # 둘 다 유지
```

### 3-3. 빌드 + 기동 (삭제가 안 깨뜨렸나)
- `npm run build` 무에러(이미지3D 참조 잔재 없음).
- **`uvicorn app:app` 기동 에러 없음** — Jinja 제거가 startup을 깨지 않는지(이게 최대 리스크). `python -m py_compile app.py` 통과.
- 빌드 후 8080: **검사 탭에 로고 정상 표시**(/static 살아있음), 탭은 검사·시뮬레이션 둘만.

### 3-4. 회귀 (엔진 작동 유지)
- 검사 탭에서 학습(ZIP/TAR 업로드)·인테이크·스웜·하드웨어 패널 여전히 동작.
- 시뮬레이션 정상.

## 4. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 3-1 삭제확인, **3-2 보존확인(엔진/로고)**, 3-3 `py_compile`. 빌드·기동은 Antigravity. 통과 시 — **Phase 2(엔진을 시뮬 공간으로 이주)** 설계로.

## 5. 커밋
- 브랜치: `chore/phase1-deadcode-audit`
- 메시지(예): `chore: remove image3d leaf + dead Jinja UI + orphan capture_ws (keep engine, static, logo)`

## 6. 주의 (꼭)
- **검사(Dashboard)·5개 엔진 컴포넌트 삭제 절대 금지** — 가상공장 두뇌. 이번엔 "이주"가 아니라 "안전 정리"만.
- **`/static` 마운트와 `aria_logo.png` 보존** — Dashboard가 로고를 거기서 불러옴. `static/` 통째 rm 금지(`css/`·`js/`만).
- **`/api/quick` 보존** — 검사 이력이 사용. HF/파일시스템은 이미 프론트에서 빠졌고 엔드포인트는 무해하게 남김.
- Jinja 정의 제거 전 `templates.` 사용처 없음을 확인 — 있으면 기동이 깨진다.
- `local_agent.py`는 독립 CLI라 건드리지 않음.
