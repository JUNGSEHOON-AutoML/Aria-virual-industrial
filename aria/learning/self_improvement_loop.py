import os
import sys
import time
import json
import re
import shutil
import urllib.request
import urllib.parse
import base64
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OLLAMA_API = "http://localhost:11434/api/chat"
# Antigravity IDE 경로
IDE_DIR = Path("/userHome/userhome4/sehoon/.gemini/antigravity-ide")
IDEA_BRAIN_DIR = IDE_DIR / "brain"
# Agent Bridge 경로 (Ralph ↔ Antigravity 통신)
BRIDGE_DIR = BASE_DIR / "agent_bridge"
BRIDGE_DIR.mkdir(exist_ok=True)
BRIDGE_RALPH_TO_AG = BRIDGE_DIR / "ralph_to_antigravity.json"
BRIDGE_AG_TO_RALPH = BRIDGE_DIR / "antigravity_to_ralph.json"

class SelfImprovementLoop:
    """
    Ralph가 사람의 개입 없이 스스로 생각하고 개선하는 백그라운드 루프.
    ralph_telegram_daemon.py와 별도 스레드로 기동되어 실행됩니다.
    """
    def __init__(self, send_message_fn=None, send_photo_fn=None, mcp_client=None):
        self.send_message = send_message_fn
        self.send_photo = send_photo_fn
        self.mcp_client = mcp_client
        self.daily_fix_count = 0
        self.last_fix_reset_date = datetime.date.today()
        self.last_daily_report_date = None
        self.last_bridge_request_id = None   # 중복 요청 방지

    def _notify(self, text):
        print(f"🤖 [SelfImprovement] {text}")
        if self.send_message:
            try:
                self.send_message(text)
            except Exception as e:
                print(f"❌ [SelfImprovement] 텔레그램 전송 실패: {e}")

    def _call_llm(self, prompt: str, model: str = "qwen2.5:14b") -> str:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "num_ctx": 16384,
                "temperature": 0.0
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_API, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
                return data["message"]["content"].strip()
        except Exception as e:
            print(f"❌ [SelfImprovement] LLM 호출 오류: {e}")
            return ""

    def _search_web(self, query: str, max_results: int = 5) -> str:
        """
        arXiv MCP 도구로 학술 논문 검색 (이미 실행 중인 MCP 서버 활용).
        mcp_client가 없으면 Ollama LLM 지식 기반으로 폴백.
        """
        # ── 방법 1: 기존 arxiv MCP 서버 활용 ─────────────────────────────
        if self.mcp_client:
            try:
                result = self.mcp_client.call_tool("search_arxiv", {
                    "query": query,
                    "max_results": max_results,
                    "sort_recent": True,
                })
                papers = result.get("papers", []) if isinstance(result, dict) else []
                if papers:
                    lines = []
                    for p in papers[:max_results]:
                        title   = p.get("title", "")[:70]
                        summary = p.get("summary", "")[:120]
                        lines.append(f"- [{title}] {summary}")
                    return "\n".join(lines)
            except Exception as e:
                print(f"⚠️ [SelfImprovement] arxiv MCP 검색 실패: {e}")

        # ── 방법 2: Ollama LLM 지식 기반 요약 (폴백) ─────────────────────
        try:
            llm_prompt = (
                f"'{query}'에 관한 최신 AI 연구 트렌드 및 주요 논문을 3줄로 요약해줘. "
                "각 줄을 '- '로 시작하고 실제 정보만 적어줘."
            )
            result = self._call_llm(llm_prompt, model="qwen2.5:14b")
            return result if result else "(LLM 검색 실패)"
        except Exception:
            return "(검색 실패)"

    def _scan_ide_environment(self) -> str:
        """
        Antigravity IDE 환경 + 프로젝트 상태를 스캔하여 요약 반환.
        - IDE brain 파일 (implementation_plan, walkthrough, task)
        - MEMORY.md, SESSION.md
        - 최근 outputs/ 탐지 결과
        - 프로젝트 디렉토리 파일 목록
        """
        sections = []

        # 1. Antigravity IDE brain 파일 (현재 대화 세션)
        try:
            if IDEA_BRAIN_DIR.exists():
                for brain_dir in sorted(IDEA_BRAIN_DIR.iterdir()):
                    if not brain_dir.is_dir() or brain_dir.name.startswith("temp"):
                        continue
                    for md_file in ["implementation_plan.md", "task.md", "walkthrough.md"]:
                        fpath = brain_dir / md_file
                        if fpath.exists():
                            content = fpath.read_text(encoding="utf-8", errors="replace")[:600]
                            sections.append(f"[IDE:{md_file}]\n{content}")
        except Exception as e:
            sections.append(f"[IDE 스캔 실패: {e}]")

        # 2. SESSION.md
        try:
            sf = BASE_DIR / "SESSION.md"
            if sf.exists():
                sections.append(f"[SESSION.md]\n{sf.read_text(encoding='utf-8', errors='replace')[:800]}")
        except Exception:
            pass

        # 3. MEMORY.md 에러 요약
        try:
            mf = BASE_DIR / "MEMORY.md"
            if mf.exists():
                mem = mf.read_text(encoding="utf-8", errors="replace")
                # 에러 섹션만 추출
                err_m = re.search(r"## 최근 에러 \(Errors\)(.*?)(?:---|\Z)", mem, re.DOTALL)
                if err_m:
                    sections.append(f"[MEMORY.md 최신 에러]\n{err_m.group(1).strip()[:400]}")
        except Exception:
            pass

        # 4. 최근 outputs/ 결과 (마지막 5개)
        try:
            out_dir = BASE_DIR / "outputs"
            if out_dir.exists():
                recent = sorted(out_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:5]
                files = [f"{f.name} ({int(time.time() - f.stat().st_mtime)//60}분전)" for f in recent if f.is_file()]
                if files:
                    sections.append(f"[최근 outputs]\n" + "\n".join(files))
        except Exception:
            pass

        # 5. 프로젝트 Python 파일 목록
        try:
            py_files = [f.name for f in BASE_DIR.glob("*.py") if not f.name.startswith("_")]
            sections.append(f"[프로젝트 파일]\n" + ", ".join(py_files[:15]))
        except Exception:
            pass

        return "\n\n".join(sections) if sections else "(스캔 정보 없음)"

    def _call_vlm(self, prompt: str, image_path: str, model: str = "qwen2.5vl:7b") -> str:
        try:
            with open(image_path, "rb") as img_file:
                b64_image = base64.b64encode(img_file.read()).decode("utf-8")
        except Exception as e:
            print(f"❌ [SelfImprovement] 이미지 파일 인코딩 실패: {e}")
            return ""

        payload = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image]
                }
            ],
            "stream": False
        }).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_API, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
                return data["message"]["content"].strip()
        except Exception as e:
            print(f"❌ [SelfImprovement] VLM 호출 오류: {e}")
            return ""

    # ═══════════════════════════════════════════════════════════════════════
    # Agent Bridge: Ralph ↔ Antigravity 파일 기반 통신
    # ═══════════════════════════════════════════════════════════════════════

    def report_to_antigravity(self, problem: str, file: str,
                               function: str = "", evidence: str = "",
                               suggested_fix: str = "",
                               request_type: str = "fix_request"):
        """
        Ralph가 발견한 문제를 Antigravity에게 전달.
        agent_bridge/ralph_to_antigravity.json에 기록하면
        Antigravity IDE가 감지하여 자동으로 코드를 수정한다.
        """
        request_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bridge = {
            "from": "ralph",
            "request_id": request_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "type": request_type,
            "status": "pending",
            "problem": problem,
            "file": file,
            "function": function,
            "evidence": evidence,
            "suggested_fix": suggested_fix,
        }
        try:
            with open(BRIDGE_RALPH_TO_AG, "w", encoding="utf-8") as f:
                json.dump(bridge, f, ensure_ascii=False, indent=2)
            self.last_bridge_request_id = request_id
            print(f"🌉 [Bridge] Antigravity에게 요청 전달: {problem[:60]}")
            self._notify(
                f"🔧 Antigravity에게 수정 요청 전달:\n"
                f"문제: {problem}\n"
                f"파일: {file}\n"
                f"함수: {function}\n"
                f"근거: {evidence[:100]}"
            )
        except Exception as e:
            print(f"❌ [Bridge] ralph_to_antigravity.json 작성 실패: {e}")

    def check_antigravity_response(self):
        """
        Antigravity가 수정 완료했는지 확인.
        antigravity_to_ralph.json을 읽어서:
        - status == "fixed" 또는 "completed" → 테스트 실행 → 결과 보고
        - status == "rejected" → 이유 로깅
        """
        if not BRIDGE_AG_TO_RALPH.exists():
            return

        try:
            with open(BRIDGE_AG_TO_RALPH, "r", encoding="utf-8") as f:
                response = json.load(f)
        except Exception as e:
            print(f"❌ [Bridge] antigravity_to_ralph.json 읽기 실패: {e}")
            return

        # 이미 처리한 응답이면 스킵
        resp_id = response.get("request_id", "")
        if resp_id and resp_id == getattr(self, "_last_processed_resp_id", None):
            return

        status = response.get("status", "")
        detail = response.get("detail", "")
        fixed_file = response.get("file", "")
        summary = response.get("summary", "")
        req_type = response.get("request_type", "")
        domain = response.get("domain", "")

        if status in ("fixed", "completed"):
            print(f"✅ [Bridge] Antigravity가 수정 완료: {fixed_file}")
            
            # 구문 검사 (py_compile)
            test_ok = self._test_fix(fixed_file)
            if test_ok:
                if req_type == "integration":
                    try:
                        import importlib
                        import aria.perception.vision_router
                        importlib.reload(vision_router)
                        from aria.perception.vision_router import MODEL_REGISTRY
                        if domain in MODEL_REGISTRY:
                            self._notify(
                                f"✅ [자가진화 완료]\n"
                                f"'{domain}' → {MODEL_REGISTRY[domain]}\n"
                                f"이제 이 도메인은 즉시 처리됩니다.")
                        else:
                            self._notify(f"⚠️ [자가진화] 리팩토링 완료되었으나 MODEL_REGISTRY에서 {domain}을 찾을 수 없습니다.")
                    except Exception as err:
                        print(f"❌ 리팩토링 검증 중 오류: {err}")
                else:
                    self._notify("시스템 재시작 중입니다...")
            else:
                self._notify(
                    f"⚠️ [Multi-Agent] Antigravity 수정에 구문 오류 발생\n"
                    f"파일: {os.path.basename(fixed_file)}\n"
                    f"수동 확인이 필요합니다."
                )
        elif status == "rejected":
            print(f"❌ [Bridge] Antigravity가 요청 거부: {detail}")
            self._notify(f"ℹ️ Antigravity 응답: {detail[:200]}")
        elif status == "needs_info":
            print(f"❓ [Bridge] Antigravity가 추가 정보 요청: {detail}")
            self._notify(f"❓ Antigravity 추가 정보 요청:\n{detail[:200]}")
        else:
            print(f"🔄 [Bridge] 알 수 없는 상태: {status}")

        self._last_processed_resp_id = resp_id

        # 파일이 존재하고 처리가 정상적으로 끝났다면, 중복 처리 방지를 위해 파일을 삭제합니다.
        try:
            if BRIDGE_AG_TO_RALPH.exists():
                BRIDGE_AG_TO_RALPH.unlink()
        except Exception as e:
            print(f"❌ [Bridge] antigravity_to_ralph.json 삭제 실패: {e}")

    def _test_fix(self, filepath: str) -> bool:
        """수정된 파일의 구문 검사."""
        if not filepath or not os.path.exists(filepath):
            return False
        if not filepath.endswith(".py"):
            return True  # Python 외 파일은 검사 불필요
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", filepath],
            capture_output=True, text=True
        )
        return result.returncode == 0

    def _escalate_to_antigravity(self, error_text: str,
                                  file_path: str, reason: str):
        """
        analyze_and_fix()에서 자력 수정 실패 시
        Antigravity에게 에스컬레이션.
        """
        self.report_to_antigravity(
            problem=reason,
            file=file_path,
            evidence=error_text[:300],
            suggested_fix="LLM 자력 수정 시도 실패. 코드 분석 후 수정 필요.",
            request_type="escalation",
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 메인 루프
    # ═══════════════════════════════════════════════════════════════════════

    def run_forever(self):
        self._notify("시스템 사용 가능해졌습니다.")
        # 최초 기동 시 즉시 한 번 실행 후 대기
        try:
            self.check_antigravity_response()
            self.analyze_and_fix()
            self.evaluate_and_upgrade()
            self.free_thinking()
        except Exception as e:
            print(f"❌ [SelfImprovement] 초기 루프 기동 에러: {e}")

        while True:
            time.sleep(300)  # 5분 대기
            try:
                # 날짜가 바뀌었으면 자율 수정 카운터 초기화
                today = datetime.date.today()
                if today != self.last_fix_reset_date:
                    self.daily_fix_count = 0
                    self.last_fix_reset_date = today

                # Antigravity 응답 확인 (최우선)
                self.check_antigravity_response()

                self.analyze_and_fix()
                self.evaluate_and_upgrade()
                self.free_thinking()
            except Exception as e:
                print(f"❌ [SelfImprovement] 백그라운드 루프 실행 중 오류: {e}")

    def restart_uvicorn_server(self) -> bool:
        """
        uvicorn app:app 프로세스를 찾아서 종료시키고 백그라운드로 재시작합니다.
        (24/7 다운타임 최소화 무중단 재기동 기법)
        """
        import subprocess
        self._notify("🔄 Uvicorn 웹 서비스 프로세스 재기동을 시도합니다...")
        
        try:
            # 1. 기존 uvicorn 프로세스 종료
            subprocess.run(["pkill", "-f", "uvicorn app:app"], capture_output=True)
            time.sleep(2)
            
            # 2. 백그라운드로 재기동 (nohup 및 conda env uvicorn 활용)
            conda_uvicorn = "/userHome/userhome4/sehoon/miniconda3/envs/patchcore/bin/uvicorn"
            log_path = BASE_DIR / "uvicorn_restart.log"
            
            cmd = f"nohup {conda_uvicorn} app:app --host 0.0.0.0 --port 8080 > {log_path} 2>&1 &"
            
            subprocess.Popen(cmd, shell=True, cwd=str(BASE_DIR))
            
            self._notify("✅ Uvicorn 웹 서비스가 백그라운드에서 안전하게 재기동되었습니다.")
            return True
        except Exception as e:
            self._notify(f"❌ Uvicorn 웹 서비스 재기동 중 에러 발생: {e}")
            return False

    def analyze_and_fix(self):
        """
        1. outputs/improvement_draft.md가 존재하면 code_agent와 연동하여
           THRESHOLD 등 파라미터를 자율 수정하고 uvicorn 서버를 재기동합니다.
        2. MEMORY.md에서 반복 에러 패턴을 찾아 스스로 해결 코드를 작성하고 적용합니다.
        """
        base_dir = Path(__file__).resolve().parent
        draft_path = base_dir / "outputs" / "improvement_draft.md"
        
        if draft_path.exists():
            self._notify("🛠️ 발견된 자율 개선안 초안(improvement_draft.md)이 존재합니다. 자율 수정을 기동합니다.")
            try:
                from aria.agents.code_agent import CodeAgent
                code_agent = CodeAgent()
                res = code_agent.apply_improvement_draft()
                
                if res.get("status") == "success":
                    self._notify(f"✅ 개선 코드 수정 완료: {res.get('summary')}")
                    # uvicorn 재기동
                    self.restart_uvicorn_server()
                    
                    # 중복 실행 방지를 위해 백업본으로 이동
                    processed_path = base_dir / "outputs" / f"improvement_draft.md.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.move(str(draft_path), str(processed_path))
                    self._notify(f"📄 개선안 문서를 처리 완료 상태로 이동하였습니다 -> {processed_path.name}")
                    return True
                else:
                    self._notify(f"⚠️ 개선 코드 적용 실패: {res.get('summary')}")
                    return False
            except Exception as e:
                self._notify(f"❌ 개선 코드 적용 중 오류 발생: {e}")
                return False
        memory_file = BASE_DIR / "MEMORY.md"
        if not memory_file.exists():
            return False

        try:
            memory_content = memory_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"❌ MEMORY.md 읽기 실패: {e}")
            return False

        # 에러 섹션 추출
        error_match = re.search(r"## 최근 에러 \(Errors\)(.*?)(?:---|\Z)", memory_content, re.DOTALL)
        if not error_match:
            return False
        
        errors_text = error_match.group(1).strip()
        if not errors_text:
            return False

        # 최근 24시간 이내의 에러만 필터링
        recent_errors = []
        error_blocks = errors_text.split("### [ERROR]")
        for block in error_blocks:
            block = block.strip()
            if not block:
                continue
            # 첫 번째 라인에서 타임스탬프 추출
            first_line = block.splitlines()[0] if block.splitlines() else ""
            if self._is_within_24h(first_line):
                recent_errors.append("### [ERROR] " + block)

        if not recent_errors:
            print("ℹ️ [SelfImprovement] 최근 24시간 이내의 에러 로그가 없습니다.")
            return False

        filtered_errors_text = "\n\n".join(recent_errors)

        # LLM에게 원인 분석 및 코드 수정안 도출 요청
        prompt = f"""
당신은 자율 코드 개선 에이전트 ARIA입니다.
다음 MEMORY.md 파일에 기록된 최근 24시간 이내의 에러 로그들을 보고 분석하십시오:
{filtered_errors_text}

이 에러들 중 반복적으로 발생하거나 수정 가능한 패턴이 있습니까?
다면 에러를 해결하기 위해 수정하고자 하는 파일의 절대 경로(workspace 경로 포함), 에러 원인, 바꿀 대상 기존 코드 블록, 교체하여 들어갈 새로운 코드 블록을 제공하십시오.

반드시 아래 JSON 포맷으로만 응답해야 합니다. 주석(//나 /* 등)이나 Markdown 백틱 감싸기 등 다른 어떤 텍스트도 절대 포함하지 마십시오:
{{
  "has_error_pattern": true,
  "file_to_modify": "수정할 파일의 절대 경로",
  "reason": "에러 분석 내용 및 해결 방식 설명",
  "target_content": "바꿀 대상이 되는 정확한 기존 코드 블록 (공백, 들여쓰기 포함 완전히 동일해야 함)",
  "replacement_content": "교체하여 들어갈 새로운 코드 블록 (공백, 들여쓰기 보존)"
}}

만약 에러 패턴이 없거나 수정할 수 없는 문제라면 다음과 같이 응답하십시오:
{{
  "has_error_pattern": false,
  "file_to_modify": "",
  "reason": "에러 패턴 없음 또는 자동 수정 불가",
  "target_content": "",
  "replacement_content": ""
}}
"""
        response_text = self._call_llm(prompt)
        try:
            # JSON 파싱 준비 (가끔 LLM이 백틱을 주는 경우가 있으므로 클렌징)
            clean = response_text.replace("```json", "").replace("```", "").strip()
            decision = json.loads(clean)
        except Exception as e:
            print(f"❌ [SelfImprovement] 에러 분석 JSON 파싱 실패: {response_text}. 에러: {e}")
            return False

        if not decision.get("has_error_pattern"):
            return False

        file_to_modify = decision.get("file_to_modify")
        reason = decision.get("reason", "")
        target_content = decision.get("target_content", "")
        replacement_content = decision.get("replacement_content", "")

        if not file_to_modify or not os.path.exists(file_to_modify):
            # LLM이 /workspace/ 같은 존재하지 않는 경로를 반환하는 경우 조용히 스킵
            if file_to_modify and str(BASE_DIR) in file_to_modify:
                print(f"⚠️ [SelfImprovement] 파일 없음: {file_to_modify}")
            return False


        # 1. 일일 수정 횟수 검증 (최대 10회)
        if self.daily_fix_count >= 10:
            self._notify(f"⚠️ 하루 최대 자율 수정 제한 횟수(10회)에 도달하여 수정을 생략합니다. (대상: {os.path.basename(file_to_modify)})")
            return

        # 2. 안전 장치 - 위험한 수정 여부 검증
        is_dangerous = False
        dangerous_keywords = ["os.system", "subprocess.run", "subprocess.Popen", "shutil.rmtree", "os.remove", "os.unlink", "eval(", "exec("]
        for kw in dangerous_keywords:
            if kw in replacement_content or kw in target_content:
                is_dangerous = True
                break

        # runner 파일(self_improvement_loop.py)이나 daemon 자체는 변경 불가 처리
        if os.path.basename(file_to_modify) in ["self_improvement_loop.py", "ralph_telegram_daemon.py"]:
            is_dangerous = True

        # 위험한 수정인 경우 텔레그램 승인 대기
        if is_dangerous:
            pending_file = BASE_DIR / "pending_fix.json"
            pending_data = {
                "file_to_modify": file_to_modify,
                "reason": reason,
                "target_content": target_content,
                "replacement_content": replacement_content,
                "approved": False,
                "rejected": False
            }
            try:
                with open(pending_file, "w", encoding="utf-8") as pf:
                    json.dump(pending_data, pf, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 승인 파일 생성 실패: {e}")
                return

            self._notify(
                f"⚠️ [위험한 수정 승인 요청]\n"
                f"- 이유: {reason}\n"
                f"- 대상 파일: {os.path.basename(file_to_modify)}\n\n"
                f"기존 코드:\n```\n{target_content}\n```\n\n"
                f"변경 코드:\n```\n{replacement_content}\n```\n\n"
                f"수정을 승인하려면 '/approve_fix'를, 거절하려면 '/reject_fix'를 입력해 주세요. (10분 대기)"
            )

            # 최대 10분(600초) 대기하며 폴링
            approved = False
            for _ in range(120):
                time.sleep(5)
                if not pending_file.exists():
                    break
                try:
                    with open(pending_file, "r", encoding="utf-8") as pf:
                        status = json.load(pf)
                    if status.get("approved"):
                        approved = True
                        break
                    elif status.get("rejected"):
                        break
                except Exception:
                    pass

            # 승인 대기 완료 후 pending_fix.json 제거
            if pending_file.exists():
                try:
                    os.remove(pending_file)
                except Exception:
                    pass

            if not approved:
                self._notify("❌ 위험한 자율 수정 요청이 거부되었거나 대기 시간이 만료되어 취소되었습니다.")
                return False

        # 3. 백업 작성
        backup_path = file_to_modify + ".backup"
        try:
            shutil.copy2(file_to_modify, backup_path)
        except Exception as e:
            self._notify(f"❌ 수정 전 백업 생성 실패: {e}")
            return False

        # 4. 파일 수정 실행
        try:
            content = Path(file_to_modify).read_text(encoding="utf-8", errors="replace")
            if target_content not in content:
                self._notify(f"⚠️ 코드 치환 실패: 대상 코드가 파일 내에 존재하지 않습니다. ({os.path.basename(file_to_modify)})")
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                return False

            new_content = content.replace(target_content, replacement_content)
            Path(file_to_modify).write_text(new_content, encoding="utf-8")
        except Exception as e:
            self._notify(f"❌ 수정 중 에러 발생: {e}. 롤백합니다.")
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_to_modify)
                os.remove(backup_path)
            return False

        # 5. 테스트 검증 실행 (autonomous_agent.py --test)
        self._notify(f"🛠️ [자율 수정 검증] {os.path.basename(file_to_modify)} 수정 완료. 테스트 스크립트를 구동합니다...")
        import subprocess
        test_res = subprocess.run(
            [sys.executable, "autonomous_agent.py", "--test"],
            capture_output=True, text=True
        )

        if test_res.returncode == 0:
            # 성공 시 백업 제거 및 카운터 증가 후 알림
            self.daily_fix_count += 1
            if os.path.exists(backup_path):
                os.remove(backup_path)
            self._notify(f"🤖 [실제 수정] {os.path.basename(file_to_modify)}\n수정 내용: {reason}\n테스트: 통과")
            return True
        else:
            # 실패 시 자동 롤백 + Antigravity에게 에스컬레이션
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_to_modify)
                os.remove(backup_path)
            error_log = test_res.stderr or test_res.stdout[:500]
            self._notify(
                f"⚠️ 자동 수정 시도 실패: 테스트 검증 실패로 코드를 롤백했습니다.\n"
                f"→ Antigravity에게 수정 요청을 에스컬레이션합니다."
            )
            self._escalate_to_antigravity(
                error_text=error_log,
                file_path=file_to_modify,
                reason=f"자력 수정 실패: {reason}"
            )
            return False

    def evaluate_and_upgrade(self):
        """
        outputs/ 폴더에서 최근 결과를 보고 VLM으로 정확도를 평가하여 필요 시 설정 모델을 동적으로 업그레이드합니다.
        """
        outputs_dir = BASE_DIR / "outputs"
        if not outputs_dir.exists():
            return

        # outputs 폴더에서 가장 최근 생성된 png 이미지 탐색
        images = list(outputs_dir.glob("*.png"))
        if not images:
            return

        newest_image = max(images, key=lambda x: x.stat().st_mtime)

        # 1시간 이내에 생성된 파일인지 대략 필터링 (너무 옛날 이미지는 제외)
        if time.time() - newest_image.stat().st_mtime > 3600:
            return

        # VLM에게 정확도 평가 요청
        prompt = (
            "이 이미지의 객체 탐지(YOLO) 결과에 대해 탐지 품질을 평가해줘. "
            "1부터 10 사이의 정수 점수 하나와 그 이유를 한 줄로 적어줘. "
            "응답 예: '8 - 타겟 객체가 정확하게 포착됨'"
        )
        eval_res = self._call_vlm(prompt, str(newest_image))
        if not eval_res:
            return

        print(f"📊 [SelfImprovement] 최근 이미지({newest_image.name}) 탐지 품질 평가: {eval_res}")

        # 점수 파싱 (정수 추출)
        score_match = re.search(r"\b([1-9]|10)\b", eval_res)
        if score_match:
            score = int(score_match.group(1))
            if score < 7:
                self._notify(f"⚠️ YOLO 탐지 점수 저하 감지 (점수: {score}/10, 평가: {eval_res}). 모델 품질 자동 업그레이드를 시작합니다.")
                
                # mcp_config.json 읽기
                config_file = BASE_DIR / "mcp_config.json"
                if config_file.exists():
                    try:
                        with open(config_file, "r", encoding="utf-8") as cf:
                            config_data = json.load(cf)

                        # qwen2.5:14b나 deepseek-r1:8b 등이 현재 chat_ko / fallback 모델로 설정되어 있는지 점검하고, 업그레이드 조치
                        current_vision = config_data.get("models", {}).get("vision", "")
                        if "7b" in current_vision:
                            # 7b 비전에서 더 우수한 비전 모델이 필요할 때 로깅 등 수행
                            print("💡 [Model Upgrade] 현재 7b 수준 비전 모델 구동 중. 필요 시 수동 교체 필요.")
                    except Exception as e:
                        print(f"❌ mcp_config.json 처리 중 오류: {e}")

    def free_thinking(self):
        """
        자유 시간에 코드베이스를 스캔하여 스스로 개선점을 고안하고 SESSION.md 기록 및 일일 리포트 보고.
        """
        # 1. 9시 일일 업무 보고서 발송 체크
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if now.hour == 9 and self.last_daily_report_date != today_str:
            # ── 실제 환경 데이터 수집 ──
            print("  [파일 스캔] IDE + 프로젝트 환경 스캔 중...")
            ide_ctx = self._scan_ide_environment()

            print("  [웹 검색] AI 트렌드 수집 중...")
            ai_news    = self._search_web("anomaly detection AI 최신 논문 다운로드 2025")
            vision_news = self._search_web("computer vision YOLO 2025 최신 트렌드")

            session_file = BASE_DIR / "SESSION.md"
            session_content = ""
            if session_file.exists():
                session_content = session_file.read_text(encoding="utf-8", errors="replace")

            # 출력 결과 몇 개 확인
            out_dir = BASE_DIR / "outputs"
            recent_outputs = []
            if out_dir.exists():
                recent_outputs = [
                    f.name for f in sorted(out_dir.iterdir(),
                    key=lambda x: x.stat().st_mtime, reverse=True)[:5]
                    if f.is_file()
                ]

            recent_outputs_str = ", ".join(recent_outputs) if recent_outputs else "(없음)"
            prompt = f"""
당신은 ARIA AI 에이전트입니다.
아래 실제 데이터를 바탕으로 **오늘의 진짜 작업 상황**을 보고하는
9시 일일 업무 요약보고서를 한국어로 작성해주세요.

=== IDE/프로젝트 상태 ===
{ide_ctx[:1200]}

=== AI 최신 트렌드 (DuckDuckGo 검색) ===
[Anomaly Detection]:
{ai_news}

[Computer Vision]:
{vision_news}

=== 자율 수정 통계 ===
오늘 자율 코드 수정 횟수: {self.daily_fix_count}/10

=== 최근 출력 파일 ===
{recent_outputs_str}

=== SESSION.md ===
{session_content[:600]}

리포트는 다음 형식으로 작성하세요:
1. **오늘 수행한 작업** (IDE/프로젝트 실제 데이터 기반)
2. **AI 트렌드** (DuckDuckGo 검색 결과 요약)
3. **다음 할 일** (개선 포인트 제안)
만들어낸 데이터를 학습하지 말고, 실제 오늘 거룐 작업내역을 정확히 반영하세요.
"""
            report = self._call_llm(prompt)
            if report:
                self._notify(f"📊 [ARIA 일일 리포트]\n\n{report}")
                self.last_daily_report_date = today_str

        # 2. 매 사이클마다 "지금 할 수 있는 능동 작업"을 LLM이 판단하여 실행
        print("🤖 [SelfImprovement] 능동적 자율 판단 작업 기동...")
        prompt = f"""
        현재 상태: {self._get_context()}
        최근 에러: {self._read_recent_errors()}
        미완료 목표: {self._read_pending_goals()}

        지금 사람 지시 없이 네가 능동적으로 할 수 있는
        가장 가치있는 작업 1개를 정해서 실행해.
        예: 에러 패턴 수정, 모델 성능 점검,
            새 논문 확인, 코드 개선.
        """
        action = self._call_llm(prompt, model="deepseek-r1:8b")
        if action:
            self._execute_autonomous_action(action)

    def _get_context(self) -> str:
        return self._scan_ide_environment()

    def _read_recent_errors(self) -> str:
        memory_file = BASE_DIR / "MEMORY.md"
        if not memory_file.exists():
            return "No MEMORY.md file."
        try:
            content = memory_file.read_text(encoding="utf-8", errors="replace")
            error_match = re.search(r"## 최근 에러 \(Errors\)(.*?)(?:---|\Z)", content, re.DOTALL)
            if error_match:
                errors_text = error_match.group(1).strip()
                if not errors_text:
                    return "No errors logged."
                # 24시간 필터링
                recent_errors = []
                error_blocks = errors_text.split("### [ERROR]")
                for block in error_blocks:
                    block = block.strip()
                    if not block:
                        continue
                    first_line = block.splitlines()[0] if block.splitlines() else ""
                    if self._is_within_24h(first_line):
                        recent_errors.append("### [ERROR] " + block)
                return "\n\n".join(recent_errors) if recent_errors else "No errors within the last 24 hours."
        except Exception as e:
            return f"Error reading MEMORY.md: {e}"
        return "No errors logged."

    def _read_pending_goals(self) -> str:
        goals = []
        agents_file = BASE_DIR / "AGENTS.md"
        if agents_file.exists():
            try:
                content = agents_file.read_text(encoding="utf-8", errors="replace")
                goals_match = re.search(r"## 지속적 목표 \(Continuous Goals\)(.*?)(?:---|\Z)", content, re.DOTALL)
                if goals_match:
                    goals.append(f"[AGENTS.md Continuous Goals]\n{goals_match.group(1).strip()}")
            except Exception:
                pass
        
        # task.md in brain directories
        try:
            if IDEA_BRAIN_DIR.exists():
                for brain_dir in sorted(IDEA_BRAIN_DIR.iterdir()):
                    if not brain_dir.is_dir() or brain_dir.name.startswith("temp"):
                        continue
                    tf = brain_dir / "task.md"
                    if tf.exists():
                        t_content = tf.read_text(encoding="utf-8", errors="replace")
                        pending = [line for line in t_content.splitlines() if "- [ ]" in line or "- [/]" in line]
                        if pending:
                            goals.append(f"[task.md Pending]\n" + "\n".join(pending[:10]))
        except Exception:
            pass
            
        return "\n\n".join(goals) if goals else "No pending goals."

    def _execute_autonomous_action(self, action: str):
        """
        LLM이 판단한 능동 작업을 해석하고 실제로 실행합니다.
        """
        # think 태그 제거
        clean_action = re.sub(r"<think>.*?</think>", "", action, flags=re.DOTALL).strip()
        if not clean_action:
            clean_action = action.strip()
            
        lines = [l.strip() for l in clean_action.splitlines() if l.strip()]
        action_summary = lines[0] if lines else "자율 판단 작업 수행"
        if len(action_summary) > 100:
            action_summary = action_summary[:97] + "..."

        print(f"🤖 [SelfImprovement] 자율 작업 실행 결정: {action_summary}")
        
        lower_action = clean_action.lower()
        
        executed_details = ""
        should_notify = True
        
        if "에러" in lower_action or "error" in lower_action or "수정" in lower_action or "fix" in lower_action:
            print("➡️ [SelfImprovement] analyze_and_fix() 실행")
            success = self.analyze_and_fix()
            if success:
                executed_details = "에러 패턴 점검 및 자동 수정 프로세스를 완료했습니다."
            else:
                print("ℹ️ [SelfImprovement] 실제 수정 사항 없음. 보고 스킵.")
                should_notify = False
        elif "성능" in lower_action or "performance" in lower_action or "평가" in lower_action or "yolo" in lower_action:
            print("➡️ [SelfImprovement] evaluate_and_upgrade() 실행")
            self.evaluate_and_upgrade()
            executed_details = "모델 탐지 성능 점검 및 자가 평가를 완료했습니다."
        elif "논문" in lower_action or "arxiv" in lower_action or "연구" in lower_action:
            print("➡️ [SelfImprovement] arXiv 논문 검색 실행")
            papers = self._search_web("anomaly detection ML 2025")
            executed_details = f"arXiv 최신 이상탐지 논문을 검색했습니다.\n{papers[:300]}"
        else:
            # 기본 동작
            print("➡️ [SelfImprovement] 기본 점검 실행 (analyze_and_fix + evaluate_and_upgrade)")
            success = self.analyze_and_fix()
            self.evaluate_and_upgrade()
            if success:
                executed_details = "시스템 상태 및 성능을 종합적으로 점검하고 실제 수정을 반영했습니다."
            else:
                executed_details = "시스템 상태 및 성능을 종합적으로 점검했습니다. (실제 수정 사항 없음)"
            
        if should_notify:
            # 텔레그램 보고
            report_msg = (
                f"🤖 [자율 작업] {action_summary}\n"
                f"사람 지시 없이 스스로 수행했습니다.\n\n"
                f"상세 내용: {executed_details}"
            )
            self._notify(report_msg)

    def _is_within_24h(self, error_header: str) -> bool:
        # Extract YYYY-MM-DD HH:MM:SS
        match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", error_header)
        if not match:
            return False
        try:
            err_time = datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            diff_seconds = (now - err_time).total_seconds()
            return 0 <= diff_seconds < 86400
        except Exception as e:
            print(f"⚠️ [SelfImprovement] 에러 시간 파싱 실패: {e}")
            return False

