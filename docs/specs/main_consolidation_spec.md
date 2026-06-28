# ARIA 명세서 — main 통합(consolidation): 완전판을 단일 진실로 for Antigravity

> 목표: 흩어진 분기들을 멈추고, **완전판 `feat/loop-heartbeat-trainer-agent`를 `main`으로 fast-forward** 해 `main`을 단일 진실로 만든다.
> 코드 수정 없음 — **git 통합 작업**. 안전 원칙: **fast-forward만**, 강제 푸시 금지, FF 불가하면 *중단하고 보고*.

## 0. 왜 / 안전 전제

- `main`(`de1c2f8`, 옛 zip-tar)은 완전판보다 **12커밋 뒤**. 지금 main엔 자율루프·FM 스코어러·뱃지가 **없음**.
- `feat/loop-heartbeat-trainer-agent`(`1eb4e12`)는 main의 **깨끗한 후손** → 충돌 0, **fast-forward 가능**(확인됨).
- FF이므로 main이 *잃을 것은 없음*(main의 모든 것이 이미 완전판에 포함). **머지 커밋·리베이스·강제 푸시 만들지 말 것.**

## 1. 범위 (Scope)

**포함:** main 백업 ref 생성 → main을 완전판으로 FF → push → `dist/` 재빌드 → 잉여 배치 분기 삭제.
**제외:** 코드/파일 편집, 다른 기능 분기 머지(vis3d 등은 별건—건드리지 않음), 강제 푸시.

## 2. 단계 (정확한 명령)

### 2-1. 백업(되돌리기 안전망)
```bash
git fetch origin
git branch backup/main-pre-consolidation origin/main      # 옛 main 보존
git push origin backup/main-pre-consolidation
```

### 2-2. fast-forward (핵심)
```bash
git checkout main
git merge --ff-only origin/feat/loop-heartbeat-trainer-agent
```
- **`--ff-only`가 안전핀**: fast-forward가 안 되면 명령이 *실패*한다. 그 경우 **여기서 중단하고**, 머지 커밋이나 `-f`를 쓰지 말고 상황을 보고할 것.

### 2-3. push
```bash
git push origin main          # 강제(-f) 금지. 일반 push가 성공해야 정상(FF라서 성공함)
```

### 2-4. 8080용 정적 빌드 (dist는 gitignore라 직접 빌드)
```bash
# 호스트 Node16이면 crypto 오류 → 이전처럼 conda patchcore의 Node20 사용
conda run -n patchcore npm --prefix frontend run build
```
- `frontend/dist/` 생성 확인(index.html + assets).

### 2-5. 잉여 배치 분기 삭제(선택, 내용 이미 포함됨)
```bash
git push origin --delete feat/inspection-verdict-badge
git push origin --delete chore/clean-dead-files
```
- 이 둘은 옛 main에서 갈라져 *뱃지만* 들고 있고, 그 뱃지는 이미 완전판에 있음 → 안전하게 삭제.

## 3. 수용 기준 (통합 후 `main` 기준)

### 3-1. main이 완전판인가 (Greppable)
```
git fetch origin && git checkout main && git pull --ff-only
test -f scorer/feature_bank.py && echo "S1 스코어러 ✓"
grep -c "factoryLoop\|loopRef" frontend/src/components/SimulationView.jsx     # 자율루프 ≥1
grep -c "armStall\|stallMs" frontend/src/components/SimulationView.jsx        # 하트비트 ≥1
grep -c "verdict" frontend/src/components/InspectionViewer.jsx                # OK/NG 뱃지 ≥1
grep -rc "build_bank\|bank.npy" app.py                                       # FM 학습/검증 배선 ≥1
```

### 3-2. 죽은 코드가 정말 없는가
```
test ! -f capture_ws.py && echo "capture_ws 삭제 ✓"
test ! -f frontend/src/components/ImageTo3D.jsx && echo "ImageTo3D 삭제 ✓"
test ! -f templates/index.html && echo "templates 삭제 ✓"
grep -c "학습 실행\|검증 실행" frontend/src/components/SimulationView.jsx     # 수동버튼 0 (회귀 없음)
```

### 3-3. 빌드 + 기동
- `frontend/dist/` 존재. `./start_aria.sh` → 8080 React UI 정상, 자율 루프(▶ 자동 순환) 동작.

### 3-4. main 위치
```
git log -1 --format="%h %s"     # = 1eb4e12 heartbeat 커밋(또는 그 이후)이어야
git rev-list --count origin/main..origin/feat/loop-heartbeat-trainer-agent   # 0 (main이 따라잡음)
```

## 4. 검증 절차 (내가 수행)
"완료" 알려주시면 → `main`을 재clone → 3-1·3-2 grep(feature_bank·loop·heartbeat·verdict·삭제확인·수동버튼0) + 3-4 위치 확인. 빌드/기동은 Antigravity 로그/녹화. 통과 시 — **이제 단일 main 위에서 Virtual FAT(합격 게이트)로.**

## 5. 주의 / 가드
- **`--ff-only` 실패 시 절대 강제하지 말 것** — 중단·보고. (FF 가능함이 확인됐으나, 그 사이 누가 main을 바꿨다면 실패할 수 있음.)
- **강제 푸시(`-f`) 금지**, 머지 커밋 만들지 말 것(FF는 새 커밋을 안 만듦).
- 백업 ref(`backup/main-pre-consolidation`)는 통합이 검증될 때까지 **삭제하지 말 것**(되돌리기용).
- `vis3d1-image-to-relief`, `zip-tar`(=옛 main) 등 다른 분기는 **이번 범위 밖** — 건드리지 않음. (relief 기능을 원하면 이후 별도 cherry-pick.)
- `dist/`는 gitignore라 **커밋되지 않음** — 매 배포 시 `npm run build` 필요(Node20).
- 커밋/태그 메시지(선택): `chore(repo): consolidate complete autonomous-factory product into main (ff)`.
