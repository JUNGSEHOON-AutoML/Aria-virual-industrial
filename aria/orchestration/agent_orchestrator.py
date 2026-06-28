from __future__ import annotations
"""
AgentOrchestrator — Ralph v4.0 두뇌.

모든 요청의 단일 진입점.
deepseek-r1이 어떤 서브 에이전트가 필요한지 판단하고
위임 + 결과 취합.

키워드 매칭 없음. LLM이 의도 판단.
"""

import os
import json
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_API = f"{_OLLAMA_BASE}/api/chat"


# ══════════════════════════════════════════════════════════════════════════════
# Ollama 호출
# ══════════════════════════════════════════════════════════════════════════════
def _call_ollama(model: str, prompt: str, temperature: float = 0.0) -> str:
    """Ollama API 호이다. 순수 텍스트 응답 반환."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 4096,   # 16384→4096: 채팅용 과도한 컨텍스트 제거 (latency -60%)
        },
        "keep_alive": "10m",   # 모델을 10분간 메모리에 유지 → 매 호출 재적재 방지
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_API, data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return data["message"]["content"].strip()


def _is_korean(text: str) -> bool:
    """텍스트 내에 한글(가-힣)이 포함되어 있는지 확인."""
    if not text:
        return False
    import re
    return bool(re.search(r'[가-힣]', text))


def _call_ollama_with_korean_guard(model: str, prompt: str, temperature: float = 0.7) -> str:
    """Ollama를 호출하고 결과에 한글이 없는 경우 재시도 처리."""
    response = _call_ollama(model, prompt, temperature=temperature)
    if _is_korean(response):
        return response

    print("  ⚠️ [Korean Guard] 한글 검증 실패! 1차 재시도 진행...")
    retry_prompt = f"{prompt}\n\n[WARNING: Previous response was not in Korean. You MUST output KOREAN only. Please translate your answer to KOREAN (한국어) and format it properly.]"
    response = _call_ollama(model, retry_prompt, temperature=0.2)
    if _is_korean(response):
        return response

    print("  ⚠️ [Korean Guard] 한글 검증 실패! 2차 재시도 진행...")
    translate_prompt = f"아래 텍스트를 정확하게 한국어로 번역해서 자연스러운 마크다운으로 출력해줘:\n\n{response}"
    response = _call_ollama(model, translate_prompt, temperature=0.1)
    if _is_korean(response):
        return response

    print("  ❌ [Korean Guard] 모든 재시도가 실패하여 기본 한글 템플릿으로 폴백합니다.")
    return "❌ [오류] 모델의 한국어 출력이 불가능하여 차단되었습니다."


def _emit_agent_status(callback, agent, state, **kw):
    if callback:
        try:
            callback({
                "type": "agent_status",
                "agent": agent,
                "state": state,
                "ts": time.time(),
                **kw
            })
        except Exception as e:
            print(f"[Orchestrator] Status callback error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# AgentOrchestrator
# ══════════════════════════════════════════════════════════════════════════════
class AgentOrchestrator:
    """
    Ralph의 두뇌.
    단일 요청을 여러 서브 에이전트에 분배하고
    결과를 취합하여 최종 응답 생성.
    """

    def __init__(self, mcp_hub=None):
        self.mcp_hub = mcp_hub
        self.available_tools = ["get_weather", "search_web"]
        self._agents = {}
        self._load_agents()
        self._register_event_subscribers()

    def _load_agents(self):
        """서브 에이전트 lazy 로드."""
        try:
            from aria.agents.vision_agent import VisionAgent
            self._agents["vision"] = VisionAgent()
        except Exception as e:
            print(f"[Orchestrator] VisionAgent 로드 실패: {e}")

        try:
            from aria.agents.research_agent import ResearchAgent
            self._agents["research"] = ResearchAgent()
        except Exception as e:
            print(f"[Orchestrator] ResearchAgent 로드 실패: {e}")

        try:
            from aria.agents.code_agent import CodeAgent
            self._agents["code"] = CodeAgent()
        except Exception as e:
            print(f"[Orchestrator] CodeAgent 로드 실패: {e}")

        try:
            from aria.agents.industry_agent import IndustryAgent
            self._agents["industry"] = IndustryAgent()
        except Exception as e:
            print(f"[Orchestrator] IndustryAgent 로드 실패: {e}")

        try:
            from aria.agents.data_agent import DataAgent
            self._agents["data"] = DataAgent()
        except Exception as e:
            print(f"[Orchestrator] DataAgent 로드 실패: {e}")

        try:
            from aria.agents.analyst_agent import AnalystAgent
            self._agents["analyst"] = AnalystAgent()
        except Exception as e:
            print(f"[Orchestrator] AnalystAgent 로드 실패: {e}")

        print(f"[Orchestrator] 로드된 에이전트: {list(self._agents.keys())}")

    def _register_event_subscribers(self):
        """이벤트 버스 구독자 등록."""
        try:
            from aria.orchestration.event_bus import event_bus
            event_bus.subscribe("new_file_detected", self._on_new_file_detected)
            event_bus.subscribe("analysis_complete", self._on_analysis_complete)
            print("[Orchestrator] EventBus 구독 완료 (new_file_detected, analysis_complete)")
        except Exception as e:
            print(f"[Orchestrator] EventBus 구독 실패: {e}")

    async def _on_new_file_detected(self, data: dict):
        """new_file_detected 이벤트를 처리하여 자율 라우팅 루프를 가동합니다."""
        file_path = data.get("image_path") or data.get("file_path")
        if not file_path:
            print("[Orchestrator Event] new_file_detected 에 파일 경로가 없습니다.")
            return

        chat_id = data.get("chat_id")
        print(f"[Orchestrator Event] 신규 파일 감지 ➔ 자율 라우팅 루프 가동: {file_path}")
        
        from aria.orchestration.state_manager import AgentState
        state = AgentState(
            input_file=file_path,
            chat_id=chat_id
        )
        
        import asyncio
        loop = asyncio.get_running_loop()
        final_state_dict = await loop.run_in_executor(
            None,
            self.run_autonomous_routing_loop,
            state
        )
        
        # 완료 시 topic: "analysis_complete" 발행
        from aria.orchestration.event_bus import event_bus
        await event_bus.publish("analysis_complete", {
            "image_path": file_path,
            "result": final_state_dict
        })

    def run_autonomous_routing_loop(self, state) -> dict:
        """
        LangGraph-style state-based routing loop in pure Python.
        """
        from aria.orchestration.state_manager import get_lightweight_summary
        import os
        
        print(f"\n⚡ [Swarm Routing Start] 파일: {state.input_file or '없음'}")
        state.history.append("Start")
        
        while not state.is_completed:
            # 1. Swarm Circuit Breaker (Max 5 steps)
            if state.step_count >= 5:
                err_msg = "🚨 [Circuit Breaker] 최대 단계(5회)를 초과하여 자율 라우팅 루프를 강제 차단합니다."
                print(f"  {err_msg}")
                state.is_completed = True
                state.history.append("CircuitBreakerTripped")
                state.final_report = f"❌ 분석 실패: 다단계 라우팅 한계 초과\n\n{err_msg}"
                break
                
            state.step_count += 1
            current_agent = state.next_agent
            print(f"  [Swarm Node Execution] 단계 {state.step_count}/5 - Current Agent: {current_agent}")
            
            # ── A. ROUTER Node ──
            if current_agent == "ROUTER":
                try:
                    harness = self._read_harness_file("router_harness.md")
                    state_summary = get_lightweight_summary(state)
                    
                    prompt = f"""{harness}

현재 상태 정보 요약:
{state_summary}

위 상태 정보를 고려하여 다음 실행할 에이전트를 결정하고 JSON 형식으로만 답변하라.
다른 설명이나 텍스트(예: 생각 태그 <think>) 없이 오직 다음 구조를 만족하는 JSON 블록만 출력해야 한다:
{{
  "next_agent": "VISION" | "DIPLOMAT" | "PHYSICAL" | "OPERATOR" | "CHAT" | "CRITIC" | "END",
  "reason": "결정 근거"
}}
"""
                    # VRAM Optimization: Consolidate text reasoning to qwen2.5:14b
                    res_text = _call_ollama("qwen2.5:14b", prompt, temperature=0.0)
                    data = self._parse_json_from_llm(res_text)
                    
                    next_agent = data.get("next_agent", "END").strip().upper()
                    reason = data.get("reason", "No reason provided")
                    
                    # Action-First Routing Guard
                    action_keywords = ["다운로드", "가져와", "크롤링", "데이터", "download", "fetch", "crawl", "data"]
                    user_input_lower = (state.user_request or "").lower()
                    is_action_intent = any(kw in user_input_lower for kw in action_keywords)
                    if is_action_intent and next_agent == "CHAT":
                        print(f"  ⚠️ [Action-First Routing Guard] 액션 키워드 감지로 인해 CHAT에서 PHYSICAL로 노드를 강제 전향합니다.")
                        next_agent = "PHYSICAL"
                        reason = "사용자 요청에 다운로드/가져와/크롤링/데이터 관련 액션 키워드 포함에 따른 강제 전환"
                    
                    # Loop Prevention Safeguard
                    agent_history_map = {
                        "VISION": "Vision",
                        "DIPLOMAT": "Diplomat",
                        "PHYSICAL": "Physical",
                        "OPERATOR": "Operator",
                        "CHAT": "Chat",
                        "CRITIC": "Critic"
                    }
                    mapped_name = agent_history_map.get(next_agent)
                    if mapped_name and mapped_name in state.history:
                        print(f"  ⚠️ [Router Safeguard] {next_agent} 노드가 이미 실행되었습니다. 루프 방지를 위해 END로 강제 전환합니다.")
                        next_agent = "END"
                        reason = "동일 에이전트의 중복 실행 방지 (Safeguard)"
                    
                    # Check if routing output is invalid or command-like, or routes to END immediately on first step
                    is_json_failed = not data or "next_agent" not in data
                    is_command_in_response = any(cmd in res_text.lower() for cmd in ["curl", "wget", "bash", "python", "http_code", "url", "chmod", "sh "])
                    
                    if is_json_failed or is_command_in_response or (next_agent == "END" and state.step_count == 1):
                        if is_json_failed or is_command_in_response:
                            print(f"  ⚠️ [Router Fallback] LLM이 올바른 JSON 라우팅 대신 명령어 또는 텍스트를 출력했습니다. (결과: '{res_text[:100]}...')")
                        else:
                            print(f"  ⚠️ [Router Fallback] 첫 단계에서 어떤 에이전트 도구도 매칭되지 않아 END로 즉시 라우팅되었습니다.")
                            
                        state.final_report = "이 작업은 현재 환경에서 수행할 수 없습니다."
                        state.is_completed = True
                        next_agent = "END"
                        reason = "수행 불가능한 작업 또는 명령어 템플릿 오류에 따른 강제 종료"

                    # Transition Log
                    print(f"  [Swarm Handoff] ROUTER ➔ {next_agent} (이유: {reason})")
                    state.history.append(f"Router->{next_agent}")
                    state.next_agent = next_agent
                    
                    if next_agent == "END":
                        state.is_completed = True
                except Exception as e:
                    err = f"Router 에러: {e}"
                    print(f"  ❌ {err}")
                    state.history.append("RouterError")
                    state.next_agent = "END"
                    state.is_completed = True
                    
            # ── B. VISION Node ──
            elif current_agent == "VISION":
                try:
                    harness = self._read_harness_file("vision_harness.md")
                    file_path = state.input_file
                    
                    if not file_path:
                        print("  [Vision Node] 분석할 파일이 없습니다.")
                        state.vision_extracted_data = "분석할 파일이 주어지지 않았습니다."
                        state.next_agent = "ROUTER"
                        state.history.append("Vision(NoFile)")
                        continue
                        
                    is_pdf = file_path.lower().endswith('.pdf')
                    if is_pdf:
                        print(f"  [Vision Node] PDF 감지 ➔ pdftotext 텍스트 추출 중...")
                        import subprocess
                        try:
                            # Run pdftotext on pdf file
                            p_res = subprocess.run(["pdftotext", file_path, "-"], capture_output=True, text=True, timeout=30)
                            pdf_text = p_res.stdout.strip()
                        except Exception as pdf_err:
                            pdf_text = f"PDF 텍스트 추출 중 에러가 발생했습니다: {pdf_err}"
                            
                        prompt = f"""{harness}

원문 PDF 텍스트 내용:
---
{pdf_text[:8000]}
---

위 PDF 텍스트의 텍스트와 의미만 추출하여 JSON 형식으로만 답변하라.
다른 설명이나 텍스트 없이 오직 다음 구조를 만족하는 JSON 블록만 출력해야 한다:
{{
  "vision_extracted_data": "추출한 내용 요약 및 의미 정리"
}}
"""
                        # VRAM Optimization: PDF text processing uses qwen2.5:14b
                        res_text = _call_ollama("qwen2.5:14b", prompt, temperature=0.0)
                        data = self._parse_json_from_llm(res_text)
                        extracted = data.get("vision_extracted_data", "PDF에서 데이터를 추출하지 못했습니다.")
                    else:
                        print(f"  [Vision Node] 이미지 감지 ➔ VisionAgent 구동...")
                        vision_agent = self._agents.get("vision")
                        if vision_agent:
                            # Use mature VisionAgent to run YOLO / CMDIAD DINO and get scores
                            res = vision_agent.safe_run(state.user_request, file_path)
                            score_str = f" (Anomaly Score: {res.get('anomaly_score', 0):.2f})" if res.get('anomaly_score') else ""
                            extracted = res.get("summary", "") + score_str
                            
                            # Keep result image overlay for output
                            res_img = res.get("result_image_path")
                            if res_img and os.path.exists(res_img):
                                state.input_file = res_img
                        else:
                            # Image VLM fallback
                            prompt = f"""{harness}

위 이미지의 텍스트와 의미만 추출하여 JSON 형식으로만 답변하라.
다른 설명이나 텍스트 없이 오직 다음 구조를 만족하는 JSON 블록만 출력해야 한다:
{{
  "vision_extracted_data": "추출한 이미지 텍스트 및 분석 내용 정리"
}}
"""
                            res_text = self._call_vlm_for_swarm(file_path, prompt)
                            data = self._parse_json_from_llm(res_text)
                            extracted = data.get("vision_extracted_data", "이미지에서 데이터를 추출하지 못했습니다.")
                        
                    state.vision_extracted_data = extracted
                    print(f"  [Swarm Handoff] VISION ➔ ROUTER")
                    state.history.append("Vision")
                    state.next_agent = "ROUTER"
                except Exception as e:
                    err = f"Vision 에러: {e}"
                    print(f"  ❌ {err}")
                    state.history.append("VisionError")
                    state.next_agent = "ROUTER"
                    
            # ── C. DIPLOMAT Node ──
            elif current_agent == "DIPLOMAT":
                try:
                    harness = self._read_harness_file("diplomat_harness.md")
                    
                    # Fallback to user request if vision extracted data is empty
                    extracted_data = state.vision_extracted_data or state.user_request
                    
                    # 1. Generate search query using qwen2.5:14b
                    query_prompt = f"""{harness}

현재 추출된 데이터 / 요청 내용:
{extracted_data}

위 내용의 사실 여부를 검증하기 위해 가장 적합한 웹 검색어 1개를 생성하라.
오직 검색어만 문자열로 답변하고 다른 텍스트는 절대 출력하지 마라.
"""
                    search_query = _call_ollama("qwen2.5:14b", query_prompt, temperature=0.0)
                    search_query = self._clean_llm_response(search_query)
                    print(f"  [Diplomat Node] 팩트체크 검색어 생성 완료: '{search_query}'")
                    
                    # 2. Execute search
                    search_results = self._web_search(search_query)
                    print(f"  [Diplomat Node] 웹 검색 결과 수신 완료 (길이: {len(search_results)}자)")
                    
                    block_hint = ""
                    if "외부 인터넷이 차단" in search_results:
                        block_hint = "\n[중요 지침] 현재 환경은 인트라넷 또는 방화벽/CAPTCHA 정책으로 인해 외부 웹 검색이 불가능한 상태입니다. 최종 보고서에 '이 환경에서는 외부 인터넷이 차단되어 사실 검증(웹 검색)이 불가함'을 명확히 명시하십시오.\n"
                    
                    # 3. Compile report and web_research_data
                    extracted_data = state.vision_extracted_data or state.user_request
                    diplomat_prompt = f"""{harness}

현재 추출된 데이터 / 요청 내용:
{extracted_data}

웹 검색 결과 (검색어: {search_query}):
---
{search_results[:4000]}
---
{block_hint}
위 정보를 바탕으로 사실을 검증하고 최종 보고서를 마크다운 형식으로 작성하라.
반드시 다른 텍스트 없이 아래 형식의 JSON 객체만 반환하라:
{{
  "web_research_data": "웹 검색 및 팩트 체크를 통해 알아낸 추가적인 사실 정보 정리",
  "final_report": "최종 검증 보고서 내용 (마크다운 형식)"
}}
"""
                    res_text = _call_ollama("qwen2.5:14b", diplomat_prompt, temperature=0.3)
                    data = self._parse_json_from_llm(res_text)
                    
                    state.web_research_data = data.get("web_research_data", "")
                    state.final_report = data.get("final_report", "최종 보고서 작성 실패")
                    
                    print(f"  [Swarm Handoff] DIPLOMAT ➔ ROUTER")
                    state.history.append("Diplomat")
                    state.next_agent = "ROUTER"
                except Exception as e:
                    err = f"Diplomat 에러: {e}"
                    print(f"  ❌ {err}")
                    state.history.append("DiplomatError")
                    state.next_agent = "ROUTER"
            
            # ── D. PHYSICAL Node ──
            elif current_agent == "PHYSICAL":
                from aria.mcp.mcp_client import current_channel
                current_channel.current_node = "PHYSICAL"
                try:
                    print(f"  [Physical Node] 물리/시스템 관제 ReAct 루프 기동...")
                    ans = self._execute_physical_agent(state.user_request, state.chat_id, state=state)
                    state.final_report = ans
                    
                    if any(term in ans for term in ["실패", "에러", "한계", "Error", "Exception", "timeout"]):
                        print(f"  ⚠️ [Physical Node Failure] Route to CRITIC.")
                        state.critic_error_log = ans
                        screenshot_path = "outputs/critic_error_screenshot.png"
                        if self.mcp_hub:
                            try:
                                self.mcp_hub.call_tool("take_screenshot", {"save_path": screenshot_path})
                            except Exception:
                                pass
                        if os.path.exists(screenshot_path):
                            state.critic_screenshot_path = screenshot_path
                        state.next_agent = "CRITIC"
                        state.history.append("Physical->CRITIC")
                    else:
                        if state.handoff_code:
                            print(f"  [Swarm Node Completed] PHYSICAL Handoff execution completed successfully.")
                            state.history.append("Physical(HandoffComplete)")
                            state.next_agent = "END"
                            state.is_completed = True
                        else:
                            print(f"  [Swarm Handoff] PHYSICAL ➔ ROUTER")
                            state.history.append("Physical")
                            state.next_agent = "ROUTER"
                except Exception as e:
                    import traceback
                    err = f"Physical 에러: {e}"
                    print(f"  ❌ {err}")
                    state.critic_error_log = err + "\n" + traceback.format_exc()
                    screenshot_path = "outputs/critic_error_screenshot.png"
                    if self.mcp_hub:
                        try:
                            self.mcp_hub.call_tool("take_screenshot", {"save_path": screenshot_path})
                        except Exception:
                            pass
                    if os.path.exists(screenshot_path):
                        state.critic_screenshot_path = screenshot_path
                    state.history.append("PhysicalError->CRITIC")
                    state.next_agent = "CRITIC"
                finally:
                    current_channel.current_node = None
            
            # ── OPERATOR Node ──
            elif current_agent == "OPERATOR":
                from aria.mcp.mcp_client import current_channel
                current_channel.current_node = "OPERATOR"
                try:
                    print(f"  [Operator Node] 자율 작업자(Operator) ReAct 루프 기동...")
                    ans, success = self._execute_operator_agent(state.user_request, state=state)
                    state.final_report = ans
                    state.operator_success = success
                    
                    if not success:
                        print(f"  ⚠️ [Operator Node Failure] Route to CRITIC.")
                        state.critic_error_log = ans
                        screenshot_path = "outputs/critic_error_screenshot.png"
                        if self.mcp_hub:
                            try:
                                self.mcp_hub.call_tool("take_screenshot", {"save_path": screenshot_path})
                            except Exception:
                                pass
                        if os.path.exists(screenshot_path):
                            state.critic_screenshot_path = screenshot_path
                        state.next_agent = "CRITIC"
                        state.history.append("Operator->CRITIC")
                    else:
                        print(f"  [Swarm Handoff] OPERATOR ➔ ROUTER")
                        state.history.append("Operator")
                        state.next_agent = "ROUTER"
                except Exception as e:
                    import traceback
                    err = f"Operator 에러: {e}"
                    print(f"  ❌ {err}")
                    state.critic_error_log = err + "\n" + traceback.format_exc()
                    screenshot_path = "outputs/critic_error_screenshot.png"
                    if self.mcp_hub:
                        try:
                            self.mcp_hub.call_tool("take_screenshot", {"save_path": screenshot_path})
                        except Exception:
                            pass
                    if os.path.exists(screenshot_path):
                        state.critic_screenshot_path = screenshot_path
                    state.history.append("OperatorError->CRITIC")
                    state.next_agent = "CRITIC"
                    state.operator_success = False
                finally:
                    current_channel.current_node = None
            
            # ── CRITIC Node ──
            elif current_agent == "CRITIC":
                try:
                    print(f"  [Critic Node] 비평가(Critic) 자율 피드백 및 자가 수정(Self-Healing) 기동...")
                    ans, retry_signal = self._execute_critic_agent(state)
                    state.final_report = ans
                    
                    if retry_signal:
                        if state.critic_retry_count < 3:
                            state.critic_retry_count += 1
                            print(f"🔄 [Self-Healing] {state.critic_retry_count}번째 자율 재시도 루프를 작동합니다.")
                            
                            # Preserve retry state
                            retry_count = state.critic_retry_count
                            user_req = state.user_request
                            inp_file = state.input_file
                            ch_id = state.chat_id
                            
                            # Reset other states
                            state.vision_extracted_data = None
                            state.web_research_data = None
                            state.final_report = None
                            state.operator_success = None
                            state.is_completed = False
                            state.step_count = 0
                            state.history = ["Start", f"SelfHealing-Retry-{retry_count}"]
                            
                            # Start routing again from ROUTER
                            state.next_agent = "ROUTER"
                        else:
                            print("🚨 [Self-Healing] 최대 자가 수정 재시도 횟수(3회)를 초과하여 임무를 실패 처리합니다.")
                            state.history.append("Critic->MaxRetriesExceeded")
                            state.next_agent = "END"
                            state.is_completed = True
                    else:
                        print("  [Critic Node] 자가 수정 실패 또는 재시도 없음 -> 종료")
                        state.history.append("Critic->NoRetry")
                        state.next_agent = "END"
                        state.is_completed = True
                except Exception as e:
                    import traceback
                    err = f"Critic 에러: {e}"
                    print(f"  ❌ {err}")
                    state.history.append("CriticError")
                    state.final_report = f"❌ 자가 수정 실패: {err}\n\n{traceback.format_exc()}"
                    state.next_agent = "END"
                    state.is_completed = True
            
            # ── E. CHAT Node ──
            elif current_agent == "CHAT":
                try:
                    # ── 웹 검색 또는 날씨 정보가 필요한 질문인지 판단하여 컨텍스트 주입 ──
                    web_result = ""
                    weather_keywords = ["날씨", "기온", "비", "눈", "미세먼지"]
                    youtube_keywords = ["유튜브", "동영상", "영상", "youtube"]
                    search_keywords = [
                        "뉴스", "속보", "최신", "오늘 소식",           # 뉴스
                        "환율", "주가", "코스피", "비트코인", "가격",   # 금융
                        "맛집", "추천", "리뷰",                        # 추천
                        "검색해", "찾아봐", "알아봐",                   # 명시적 검색 요청
                        "방문", "언제", "일정", "계획", "방한", "날짜", # 방한/인물 일정 관련
                    ]
                    
                    # 쿼리에 주어가 생략된 경우, 최근 대화 맥락에서 명사(예: 인물명)를 보완해 쿼리 생성
                    search_query = state.user_request
                    if state.chat_history and len(state.chat_history) >= 2:
                        prev_user_q = ""
                        for h in reversed(state.chat_history):
                            if h.get("role") == "user" and h.get("content") != state.user_request:
                                prev_user_q = h.get("content", "")
                                break
                        if prev_user_q:
                            for noun in ["젠슨황", "젠슨 황", "황", "젠슨", "엔비디아", "NVIDIA", "AI", "올라마", "Ollama"]:
                                if noun in prev_user_q and noun not in state.user_request:
                                    search_query = f"{noun} {state.user_request}"
                                    print(f"[CHAT Context Optimizer] Query expanded: {search_query}")
                                    break
                    
                    if any(kw in state.user_request for kw in weather_keywords):
                        location = "서울"
                        for loc in ["부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주", "경기", "강원"]:
                            if loc in state.user_request:
                                location = loc
                                break
                        if self.mcp_hub:
                            try:
                                res = self.mcp_hub.call_tool("get_weather", {"location": location})
                                if isinstance(res, dict) and res.get("success"):
                                    web_result = res.get("summary", "")
                            except Exception as e:
                                print(f"[CHAT Weather] MCP 호출 실패: {e}")
                    elif any(kw in state.user_request for kw in youtube_keywords):
                        if self.mcp_hub:
                            try:
                                print(f"[CHAT YouTube] 유튜브 도구 기동: {search_query}")
                                res = self.mcp_hub.call_tool("search_youtube", {"query": search_query})
                                if isinstance(res, dict) and "error" not in res:
                                    web_result = json.dumps(res, ensure_ascii=False, indent=2)
                            except Exception as e:
                                print(f"[CHAT YouTube] MCP 호출 실패: {e}")
                        if not web_result:
                            web_result = self._web_search(search_query)
                    elif any(kw in state.user_request for kw in search_keywords):
                        if self.mcp_hub:
                            try:
                                res = self.mcp_hub.call_tool("search_web", {"query": search_query})
                                if isinstance(res, dict) and res.get("success"):
                                    web_result = res.get("results", "")
                            except Exception as e:
                                print(f"[CHAT Search] MCP 호출 실패: {e}")
                        if not web_result:
                            web_result = self._web_search(search_query)
                            
                    web_ctx = ""
                    if web_result:
                        web_ctx = f"\n\n🌐 웹 검색 결과:\n{web_result[:1500]}"

                    history_str = ""
                    if state.chat_history:
                        history_str = "\n최근 대화 기록 (Conversation Context):\n" + "\n".join(
                            [f"{'사용자' if h.get('role') == 'user' else 'ARIA'}: {h.get('content', '')[:150]}"
                             for h in state.chat_history[-6:]]
                        )

                    tools_desc = ""
                    if self.mcp_hub:
                        tools_desc = self.mcp_hub.get_tools_description_for_llm()
                    else:
                        tools_desc = "연결된 MCP 도구 없음"

                    chat_prompt = f"""당신은 단순한 구글 봇이 아닙니다. 연결된 모든 MCP 도구(터미널, 파일시스템, 허깅페이스 AI모델 검색 등)를 자율적으로 활용해 시스템을 제어하고 코드를 직접 수정하는 최고 권한의 ARGUS 관제 마스터 AI이자, 'ARIA' 에이전트의 대화 처리 시스템인 실력 있는 '시니어 엔지니어(Senior Engineer)'입니다.

[사용 가능한 모든 MCP 도구 목록]
{tools_desc}
                    
[⚠️ 핵심 답변 규칙]
1. [기계적 템플릿 사용 금지]: '[SYSTEM_RESPONSE]', '- Action/Answer:', '- Status:' 같은 인위적이고 기계적인 포맷을 절대 사용하지 마라. 자연스럽게 읽히는 일반 마크다운(Markdown) 포맷으로 답변하라.
2. [No-BS (군더더기 없는 직접 답변)]: "마스터 개발자님", "안녕하세요", "도와드리겠습니다", "서버 시간 기준" 같은 무의미한 인사말이나 윤색 멘트(Filler Words)를 절대 사용하지 마라. 질문을 받으면 첫 문장부터 곧바로 핵심 본론과 결론을 말하라.
3. [실질적 액션 아이템 포함]: "공식 문서를 참조하라"는 식의 무책임한 회피성 답변을 금지한다. 질문과 관련된 파이썬 코드 스니펫(huggingface_hub, transformers 등 활용)이나 CLI 명령어(kaggle datasets download 등)를 반드시 마크다운 코드 블록(```)으로 작성하여 구체적이고 즉시 실행 가능한 형태로 제공하라.
 
현재 서버 시간: {state.current_time}
{history_str}
사용자 요청: "{state.user_request}"{web_ctx}
"""
                    response = _call_ollama_with_korean_guard("qwen2.5:14b", chat_prompt, temperature=0.7)
                    
                    import re
                    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*?)\n?\s*```", response, re.DOTALL)
                    non_empty_blocks = [c.strip() for c in code_blocks if c.strip()]
                    
                    execution_keywords = [
                        "실행", "run", "execute", "돌려", "테스트", "다운로드", "download", 
                        "가져와", "fetch", "구현", "작성", "만들어", "크롤링", "crawl", "적용",
                        "수정", "설치", "install", "pip"
                    ]
                    is_exec_request = any(kw in state.user_request.lower() for kw in execution_keywords)
                    
                    if non_empty_blocks and is_exec_request:
                        code_content = "\n\n".join(non_empty_blocks)
                        print(f"  [Chat Node] 코드 블록 감지! PHYSICAL 노드로 실행 위임(Handoff)합니다. (길이: {len(code_content)}자)")
                        state.handoff_code = code_content
                        state.next_agent = "PHYSICAL"
                        state.user_request = f"다음 코드를 실행하고, 실행된 결과(다운로드된 파일명, 용량, 저장된 경로)만 요약 보고해주세요:\n{code_content}"
                        state.history.append("Chat->PHYSICAL(Handoff)")
                    else:
                        state.final_report = response
                        print(f"  [Swarm Handoff] CHAT ➔ ROUTER")
                        state.history.append("Chat")
                        state.next_agent = "ROUTER"
                except Exception as e:
                    err = f"Chat 에러: {e}"
                    print(f"  ❌ {err}")
                    state.history.append("ChatError")
                    state.next_agent = "ROUTER"
                    
            else:
                # Invalid state fallback
                print(f"  ⚠️ 알 수 없는 에이전트: {current_agent} ➔ 강제 종료")
                state.is_completed = True
                break
                
        print(f"⚡ [Swarm Routing End] 정 단계 수: {state.step_count}, 이력: {' ➞ '.join(state.history)}")
            
        return state.dict()

    def _execute_physical_agent(self, user_request: str, chat_id: str = None, state=None) -> str:
        """
        물리/시스템 제어 전용 에이전트 실행 루프 (ReAct 패턴).
        """
        import os
        import json
        harness = self._read_harness_file("physical_harness.md")
        
        # Available tools documentation
        tools_doc = """너는 아래 도구들을 사용할 수 있다:
1. run_command: 터미널 명령어를 실행한다. 파라미터: {"command": "실행할 명령어"}
2. list_directory: 폴더 내 파일 목록을 본다. 파라미터: {"path": "경로"}
3. read_file: 파일 내용을 읽는다. 파라미터: {"path": "파일경로"}
4. write_file: 파일에 내용을 덮어쓴다. 파라미터: {"path": "파일경로", "content": "쓸 내용"}
5. search_files: 파일을 검색한다. 파라미터: {"path": "경로", "pattern": "검색 패턴"}
6. take_screenshot: 화면을 캡처하여 저장한다. 파라미터: {"save_path": "outputs/screenshot.png"}
7. click: 마우스 클릭. 파라미터: {"x": X좌표, "y": Y좌표, "button": "left|right", "clicks": 클릭횟수}
8. move_to: 마우스 이동. 파라미터: {"x": X좌표, "y": Y좌표}
9. type: 키보드 텍스트 입력. 파라미터: {"text": "입력할 텍스트"}
10. key: 키보드 키 누름. 파라미터: {"key": "엔터, backspace 등 키이름"}
"""
        if self.mcp_hub:
            tools_doc += "\n" + self.mcp_hub.get_tools_description_for_llm()
        
        history_log = []
        step = 0
        max_steps = 8
        
        handoff_inst = ""
        if state and getattr(state, "handoff_code", None):
            handoff_inst = f"\n\n[💡 위임받은 실행 코드]\n이전 에이전트가 작성하여 실행을 위임한 코드입니다. 설명이나 안내 없이 아래 코드를 파일(예: temp_script.py)로 작성하거나 터미널에서 즉시 직접 실행하세요:\n{state.handoff_code}\n\n[🚨 실행 및 샌드박스 권장 사항]\n1. 코드가 여러 줄이거나 세미콜론(;) 등 특수문자가 포함된 경우, 셸 차단 필터에 걸리므로 인라인 'python -c' 실행을 절대 하지 마십시오.\n2. 반드시 현재 작업 디렉토리 내부 경로(예: 'temp_script.py' 또는 'scratch/temp_script.py')에 파일을 생성해야 합니다. /tmp 나 홈 디렉토리(~) 등 샌드박스 외부 경로는 보안상 접근이 거부됩니다.\n3. 먼저 `write_file` 도구를 호출하여 코드를 현재 디렉토리 내부 파일로 저장한 뒤, `run_command` 도구를 사용하여 'python temp_script.py' 명령으로 직접 실행하십시오."
        
        while step < max_steps:
            step += 1
            history_str = "\n".join(history_log)
            prompt = f"""{harness}

{tools_doc}

사용자 요청: "{user_request}"{handoff_inst}

이전 실행 로그:
{history_str or "없음"}

지금 단계에서 어떤 조치를 취할지 결정하여 반드시 아래 형식 중 하나를 만족하는 JSON 블록만 출력하라.
생각 태그(<think>)나 설명 텍스트를 절대 출력하지 말고 오직 JSON만 출력해야 한다.

도구를 사용해야 하는 경우:
{{
  "thought": "생각 및 계획",
  "tool_call": {{
    "name": "도구 이름",
    "arguments": {{ ... }}
  }}
}}

모든 작업이 완료되어 최종 응답을 반환하는 경우:
{{
  "thought": "작업 완료 판단",
  "final_answer": "최종 수행 결과 요약 보고 (1~2문장으로 간결하고 명확하게, 사과나 변명 금지)"
}}
"""
            try:
                res_text = _call_ollama("qwen2.5:14b", prompt, temperature=0.0)
                data = self._parse_json_from_llm(res_text)
                
                # Check for final_answer
                if "final_answer" in data:
                    ans = data["final_answer"]
                    print(f"  [Physical Agent] Completed: {ans}")
                    return ans
                
                # Check for tool_call
                tool_call = data.get("tool_call")
                if not tool_call or "name" not in tool_call:
                    fallback_ans = self._clean_llm_response(res_text)
                    print(f"  [Physical Agent] Fallback completion: {fallback_ans}")
                    return fallback_ans
                
                tool_name = tool_call["name"]
                args = tool_call.get("arguments", {})
                
                if tool_name == "run_command" and state:
                    state.critic_executed_code = args.get("command")
                
                print(f"  [Physical Agent] Tool Call: {tool_name} with {args}")
                history_log.append(f"Thought: {data.get('thought', '')}")
                history_log.append(f"Called: {tool_name}({json.dumps(args, ensure_ascii=False)})")
                
                # Execute tool via mcp_hub
                if self.mcp_hub:
                    if "write_file" in tool_name and isinstance(args, dict) and "content" in args:
                        content_str = args["content"]
                        content_str = content_str.replace("\\n", "\n").replace("\\t", "\t")
                        args["content"] = content_str
                        
                    tool_res = self.mcp_hub.call_tool(tool_name, args)
                    res_str = json.dumps(tool_res, ensure_ascii=False)
                    
                    # 텔레그램 발송 코드 삭제 (오케스트레이터의 사이드 이펙트 제거)
                    # if tool_name == "take_screenshot" and chat_id:
                    #     try:
                    #         from ralph_telegram_daemon import send_photo
                    #         save_path = args.get("save_path", "outputs/screenshot.png")
                    #         if os.path.exists(save_path):
                    #             send_photo(chat_id, save_path, caption="📸 실시간 화면 캡처 화면입니다.")
                    #     except Exception as screenshot_err:
                    #         print(f"[Physical Agent] Telegram screenshot send error: {screenshot_err}")
                else:
                    res_str = "Error: MCP Client Hub is not loaded."
                
                print(f"  [Physical Agent] Tool Result: {res_str[:300]}...")
                history_log.append(f"Result: {res_str}")
                
            except Exception as e:
                err_msg = f"Error: {e}"
                print(f"  [Physical Agent] Step {step} Exception: {e}")
                history_log.append(err_msg)
                
        return "⚠️ 물리/시스템 제어 실행 시간 한계를 초과하였습니다."

    def _resize_screenshot_for_vlm(self, image_path: str, max_size: int = 512) -> str:
        try:
            from PIL import Image
            img = Image.open(image_path)
            w, h = img.size
            if max(w, h) <= max_size:
                return image_path
            ratio = max_size / max(w, h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            out_path = "outputs/operator_screenshot_resized.png"
            img.save(out_path, quality=85)
            print(f"  [Operator VLM] Resized image from {w}x{h} to {new_size[0]}x{new_size[1]}")
            return out_path
        except Exception as e:
            print(f"  [Operator VLM] Resize failed: {e}")
            return image_path

    def _send_cdp_cmd(self, ws, method, params=None, cmd_id=1):
        import json
        ws.send(json.dumps({
            "id": cmd_id,
            "method": method,
            "params": params or {}
        }))
        start_time = time.time()
        while True:
            if time.time() - start_time > 15:
                raise TimeoutError(f"Timeout waiting for CDP response for method '{method}' ID {cmd_id}")
            res_str = ws.recv()
            res = json.loads(res_str)
            if res.get("id") == cmd_id:
                return res

    def _execute_tool_via_cdp(self, ws_url: str, tool_name: str, args: dict, state=None) -> str:
        import websocket
        import json
        import base64
        import os
        
        ws = websocket.create_connection(ws_url, timeout=15)
        try:
            if tool_name == "take_screenshot":
                save_path = "outputs/operator_screenshot.png"
                os.makedirs("outputs", exist_ok=True)
                
                # Take screenshot via CDP
                res = self._send_cdp_cmd(ws, "Page.captureScreenshot", {"format": "png"}, cmd_id=100)
                if "result" in res and "data" in res["result"]:
                    b64_data = res["result"]["data"]
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(b64_data))
                    
                    # Resize for VLM
                    resized_path = self._resize_screenshot_for_vlm(save_path, max_size=384)
                    
                    # Query VLM
                    vlm_prompt = (
                        "이 이미지는 현재 웹브라우저 화면의 스크린샷입니다.\n"
                        "1. 현재 화면에 표시된 웹페이지 내용과 상태를 상세히 요약해 주세요.\n"
                        "2. 화면에 보이는 중요 텍스트(예: 채용 공고 제목, 회사명, 주요 뉴스 제목 등), 버튼, 입력창들의 정확한 텍스트 내용과 중심 절대 좌표 (X, Y)를 모두 나열해 주세요.\n"
                        "   (예: '채용공고 - AI 엔지니어 (네이버)': (X, Y), '검색창': (X, Y))\n"
                        "3. 사용자의 최종 목표(예: 채용 정보 수집)와 관련된 정보가 있다면 그 텍스트 내용과 정보들을 상세하게 적어주세요.\n"
                        "모든 설명은 한국어로 작성해 주세요."
                    )
                    vlm_desc = self._call_vlm_for_swarm(resized_path, vlm_prompt)
                    if state:
                        state.critic_screenshot_path = save_path
                    return f"스크린샷이 정상 캡처되었고 VLM 분석을 수행했습니다.\n\n=== VLM 화면 분석 결과 ===\n{vlm_desc}"
                else:
                    return f"CDP 스크린샷 실패: {json.dumps(res, ensure_ascii=False)}"
                    
            elif tool_name == "mouse_click":
                x = args.get("x", 0)
                y = args.get("y", 0)
                
                # Mouse press
                self._send_cdp_cmd(ws, "Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": int(x),
                    "y": int(y),
                    "button": "left",
                    "clickCount": 1
                }, cmd_id=101)
                
                # Mouse release
                self._send_cdp_cmd(ws, "Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": int(x),
                    "y": int(y),
                    "button": "left",
                    "clickCount": 1
                }, cmd_id=102)
                
                return f"클릭 완료: ({x}, {y})"
                
            elif tool_name == "keyboard_type":
                text = args.get("text", "")
                
                # If text is a URL, navigate directly!
                if text.startswith("http://") or text.startswith("https://"):
                    self._send_cdp_cmd(ws, "Page.navigate", {"url": text}, cmd_id=103)
                    # Sleep slightly to let the page start loading
                    time.sleep(3)
                    return f"URL 이동 완료: {text}"
                else:
                    # Insert text
                    self._send_cdp_cmd(ws, "Input.insertText", {"text": text}, cmd_id=104)
                    
                    # Follow by Enter
                    self._send_cdp_cmd(ws, "Input.dispatchKeyEvent", {
                        "type": "keyDown",
                        "key": "Enter",
                        "code": "Enter",
                        "windowsVirtualKeyCode": 13
                    }, cmd_id=105)
                    self._send_cdp_cmd(ws, "Input.dispatchKeyEvent", {
                        "type": "keyUp",
                        "key": "Enter",
                        "code": "Enter",
                        "windowsVirtualKeyCode": 13
                    }, cmd_id=106)
                    
                    return f"입력 및 엔터 완료: {text}"
                    
            elif tool_name == "scroll":
                direction = args.get("direction", "down")
                amount = 300 if direction == "down" else -300
                
                self._send_cdp_cmd(ws, "Input.dispatchMouseEvent", {
                    "type": "mouseWheel",
                    "x": 500,
                    "y": 500,
                    "deltaX": 0,
                    "deltaY": amount
                }, cmd_id=107)
                
                return f"스크롤 완료: {direction}"
                
            else:
                return f"Error: CDP에서 지원하지 않는 도구 '{tool_name}'"
        finally:
            ws.close()

    def _execute_tool_via_mcp(self, tool_name: str, args: dict, state=None) -> str:
        import os
        import json
        if not self.mcp_hub:
            return "Error: MCP Client Hub is not loaded."
            
        if tool_name == "take_screenshot":
            save_path = "outputs/operator_screenshot.png"
            os.makedirs("outputs", exist_ok=True)
            tool_res = self.mcp_hub.call_tool("take_screenshot", {"save_path": save_path})
            
            if os.path.exists(save_path):
                resized_path = self._resize_screenshot_for_vlm(save_path, max_size=384)
                vlm_prompt = (
                    "이 이미지는 현재 웹브라우저 화면의 스크린샷입니다.\n"
                    "1. 현재 화면에 표시된 웹페이지 내용과 상태를 상세히 요약해 주세요.\n"
                    "2. 화면에 보이는 중요 텍스트(예: 채용 공고 제목, 회사명, 주요 뉴스 제목 등), 버튼, 입력창들의 정확한 텍스트 내용과 중심 절대 좌표 (X, Y)를 모두 나열해 주세요.\n"
                    "   (예: '채용공고 - AI 엔지니어 (네이버)': (X, Y), '검색창': (X, Y))\n"
                    "3. 사용자의 최종 목표(예: 채용 정보 수집)와 관련된 정보가 있다면 그 텍스트 내용과 정보들을 상세하게 적어주세요.\n"
                    "모든 설명은 한국어로 작성해 주세요."
                )
                vlm_desc = self._call_vlm_for_swarm(resized_path, vlm_prompt)
                if state:
                    state.critic_screenshot_path = save_path
                return f"스크린샷이 정상 캡처되었고 VLM 분석을 수행했습니다.\n\n=== VLM 화면 분석 결과 ===\n{vlm_desc}"
            else:
                return f"스크린샷 캡처 실패: {json.dumps(tool_res, ensure_ascii=False)}"
                
        elif tool_name == "mouse_click":
            x = args.get("x")
            y = args.get("y")
            tool_res = self.mcp_hub.call_tool("mouse_click", {"x": x, "y": y})
            return json.dumps(tool_res, ensure_ascii=False)
            
        elif tool_name == "keyboard_type":
            text = args.get("text")
            type_res = self.mcp_hub.call_tool("keyboard_type", {"text": text})
            hotkey_res = self.mcp_hub.call_tool("keyboard_hotkey", {"keys": ["enter"]})
            return f"입력 결과: {json.dumps(type_res, ensure_ascii=False)}, 엔터 실행 결과: {json.dumps(hotkey_res, ensure_ascii=False)}"
            
        elif tool_name == "scroll":
            direction = args.get("direction", "down")
            amount = -5 if direction == "down" else 5
            tool_res = self.mcp_hub.call_tool("scroll", {"amount": amount})
            return json.dumps(tool_res, ensure_ascii=False)
            
        else:
            try:
                res = self.mcp_hub.call_tool(tool_name, args)
                return json.dumps(res, ensure_ascii=False)
            except Exception as e:
                return f"Error: 도구 호출 '{tool_name}' 실패 ({e})"

    def _execute_operator_agent(self, user_request: str, state=None) -> tuple:
        """
        자율 작업자(Operator) 실행 루프 (Gemini Computer Use REPL See-Act 패턴).
        """
        import os
        import json
        harness = self._read_harness_file("operator_harness.md")
        
        tools_doc = """너는 아래 도구들을 사용할 수 있다:
1. take_screenshot: 현재 화면의 스크린샷을 찍고 VLM을 통해 화면 구조 및 각 요소들의 (X, Y) 절대 좌표 정보를 요약 분석해 옵니다. 파라미터: {}
2. mouse_click: 지정된 절대 좌표(X, Y)를 마우스로 클릭합니다. 파라미터: {"x": X좌표, "y": Y좌표}
3. keyboard_type: 텍스트를 입력하고 엔터를 누릅니다. 파라미터: {"text": "입력할 텍스트"}
4. scroll: 마우스 스크롤을 수행합니다. 파라미터: {"direction": "down" | "up"}
"""
        if self.mcp_hub:
            tools_doc += "\n" + self.mcp_hub.get_tools_description_for_llm()
        
        # Try to initialize clean Chrome CDP tab
        use_cdp = False
        cdp_tab_id = None
        cdp_ws_url = None
        
        try:
            import urllib.request
            import websocket
            # Send PUT request to create a new empty tab
            req = urllib.request.Request("http://127.0.0.1:9222/json/new", method="PUT")
            with urllib.request.urlopen(req, timeout=3) as resp:
                tab_info = json.loads(resp.read().decode('utf-8'))
                cdp_tab_id = tab_info.get("id")
                cdp_ws_url = tab_info.get("webSocketDebuggerUrl")
                use_cdp = True
                print(f"  [Operator Agent] Successfully created clean Chrome CDP tab: {cdp_tab_id}")
                
                # Immediately navigate to Naver to avoid blank/black screen!
                ws = websocket.create_connection(cdp_ws_url, timeout=15)
                ws.send(json.dumps({
                    "id": 999,
                    "method": "Page.navigate",
                    "params": {"url": "https://www.naver.com"}
                }))
                ws.recv()
                ws.close()
                print("  [Operator Agent] Navigating new tab to Naver and waiting 4s...")
                time.sleep(4)
        except Exception as e:
            print(f"  [Operator Agent] Chrome CDP not available or failed to open tab: {e}. Falling back to PyAutoGUI/mss.")
            
        history_log = []
        step = 0
        max_steps = 20
        
        try:
            while step < max_steps:
                step += 1
                history_str = "\n".join(history_log)
                prompt = f"""{harness}

{tools_doc}

목표: "{user_request}"

이전 실행 로그:
{history_str or "없음"}

지금 단계에서 어떤 조치를 취할지 결정하여 반드시 아래 형식 중 하나를 만족하는 JSON 블록만 출력하라.
생각 태그(<think>)나 설명 텍스트를 절대 출력하지 말고 오직 JSON만 출력해야 한다.

도구를 사용해야 하는 경우:
{{
  "thought": "생각 및 계획",
  "tool_call": {{
    "name": "도구 이름",
    "arguments": {{ ... }}
  }}
}}

모든 작업이 성공적으로 완료되어 최종 완료 보고서를 작성하는 경우:
{{
  "thought": "작업 완료 판단",
  "final_answer": "최종 수행 결과 상세 완료 보고 (수집된 데이터 정보, 저장된 파일 경로 등을 마크다운 형식으로 공손하고 전문적으로 작성, 사과나 변명 금지)",
  "success": true
}}

작업이 완전히 실패했거나 목표 달성이 불가능하다고 판단하는 경우:
{{
  "thought": "실패 판단 이유",
  "final_answer": "실패 사유 요약 보고 (사과나 변명 금지)",
  "success": false
}}
"""
                try:
                    res_text = _call_ollama("qwen2.5:14b", prompt, temperature=0.0)
                    data = self._parse_json_from_llm(res_text)
                    
                    # Check for final_answer
                    if "final_answer" in data:
                        ans = data["final_answer"]
                        success = data.get("success", False)
                        print(f"  [Operator Agent] Completed. Success: {success}, Answer: {ans[:200]}...")
                        return ans, success
                    
                    # Check for tool_call
                    tool_call = data.get("tool_call")
                    if not tool_call or "name" not in tool_call:
                        fallback_ans = self._clean_llm_response(res_text)
                        print(f"  [Operator Agent] Fallback completion: {fallback_ans[:200]}...")
                        return fallback_ans, False
                    
                    tool_name = tool_call["name"]
                    args = tool_call.get("arguments", {})
                    
                    # Package executed action for critic debugging
                    if state:
                        state.critic_executed_code = f"Action: {tool_name}\nArguments: {json.dumps(args, ensure_ascii=False)}"
                    
                    print(f"  [Operator Agent] Tool Call: {tool_name} with {args}")
                    history_log.append(f"Thought: {data.get('thought', '')}")
                    history_log.append(f"Called: {tool_name}({json.dumps(args, ensure_ascii=False)})")
                    
                    # Execute tool via CDP or MCP fallback
                    res_str = ""
                    if use_cdp and cdp_ws_url:
                        try:
                            res_str = self._execute_tool_via_cdp(cdp_ws_url, tool_name, args, state)
                        except Exception as cdp_err:
                            print(f"  [Operator Agent] CDP action failed: {cdp_err}. Falling back to MCP/PyAutoGUI.")
                            res_str = self._execute_tool_via_mcp(tool_name, args, state)
                    else:
                        res_str = self._execute_tool_via_mcp(tool_name, args, state)
                    
                    print(f"  [Operator Agent] Tool Result: {res_str[:300]}...")
                    history_log.append(f"Result: {res_str}")
                    
                except Exception as e:
                    import traceback
                    err_msg = f"Error: {e}\n{traceback.format_exc()}"
                    print(f"  [Operator Agent] Step {step} Exception: {e}")
                    history_log.append(err_msg)
                    
            return "⚠️ 자율 작업자(Operator) 실행 시간 한계를 초과하였습니다.", False
            
        finally:
            if use_cdp and cdp_tab_id:
                try:
                    import urllib.request
                    req = urllib.request.Request(f"http://127.0.0.1:9222/json/close/{cdp_tab_id}", method="POST")
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        print(f"  [Operator Agent] Successfully closed Chrome CDP tab: {cdp_tab_id}")
                except Exception as close_err:
                    print(f"  [Operator Agent] Failed to close Chrome CDP tab: {close_err}")

    def _execute_critic_agent(self, state) -> tuple:
        """
        CRITIC (비평가) 에이전트 실행 루프 (ReAct 패턴).
        """
        import os
        import json
        harness = self._read_harness_file("critic_harness.md")
        
        tools_doc = """너는 아래 도구들을 사용할 수 있다:
1. edit_file: 파일의 특정 코드 영역을 찾아서 다른 코드로 교체/수정한다.
   파라미터: {"path": "수정할 파일의 경로 (상대경로 또는 절대경로)", "target_content": "정확히 일치해야 하는 기존 코드", "replacement_content": "교체할 새로운 코드"}
2. read_file: 파일 내용을 읽는다.
   파라미터: {"path": "파일경로"}
3. list_directory: 폴더 내 파일 목록을 본다.
   파라미터: {"path": "경로"}
"""
        if self.mcp_hub:
            tools_doc += "\n" + self.mcp_hub.get_tools_description_for_llm()
        
        history_log = []
        step = 0
        max_steps = 5
        retry_signal = False
        
        while step < max_steps:
            step += 1
            history_str = "\n".join(history_log)
            prompt = f"""{harness}

{tools_doc}

=== 에러 로그 (Error Log) ===
{state.critic_error_log or "없음"}

=== 실행된 코드 (Executed Code) ===
{state.critic_executed_code or "없음"}

=== 스크린샷 경로 (Screenshot Path) ===
{state.critic_screenshot_path or "없음"}

이전 실행 로그:
{history_str or "없음"}

지금 단계에서 어떤 조치를 취할지 결정하여 반드시 아래 형식 중 하나를 만족하는 JSON 블록만 출력하라.
생각 태그(<think>)나 설명 텍스트를 절대 출력하지 말고 오직 JSON만 출력해야 한다.

도구를 사용해야 하는 경우 (예: 코드나 하네스 수정):
{{
  "thought": "에러 분석 및 수정 계획",
  "tool_call": {{
    "name": "edit_file" | "read_file" | "list_directory",
    "arguments": {{ ... }}
  }}
}}

자가 수정을 완료하고 재시도를 지시하는 경우:
{{
  "thought": "자가 수정 완료 판단",
  "final_answer": "자가 수정 내용 요약 및 재시도 지시 (마크다운 형식)",
  "retry": true
}}

더 이상 자가 수정이 불가능하거나 실패로 종결하는 경우:
{{
  "thought": "실패 판단 이유",
  "final_answer": "최종 실패 보고서 (마크다운 형식)",
  "retry": false
}}
"""
            try:
                res_text = _call_ollama("qwen2.5:14b", prompt, temperature=0.0)
                data = self._parse_json_from_llm(res_text)
                
                # Check final_answer
                if "final_answer" in data:
                    ans = data["final_answer"]
                    retry_signal = data.get("retry", False)
                    print(f"  [Critic Agent] Completed. Retry Signal: {retry_signal}, Answer: {ans[:200]}...")
                    return ans, retry_signal
                    
                tool_call = data.get("tool_call")
                if not tool_call or "name" not in tool_call:
                    fallback_ans = self._clean_llm_response(res_text)
                    print(f"  [Critic Agent] Fallback completion: {fallback_ans[:200]}...")
                    return fallback_ans, False
                    
                tool_name = tool_call["name"]
                args = tool_call.get("arguments", {})
                
                print(f"  [Critic Agent] Tool Call: {tool_name} with {args}")
                history_log.append(f"Thought: {data.get('thought', '')}")
                history_log.append(f"Called: {tool_name}({json.dumps(args, ensure_ascii=False)})")
                
                # Execute tool
                if tool_name == "edit_file":
                    res = self._critic_edit_file(
                        path=args.get("path"),
                        target_content=args.get("target_content"),
                        replacement_content=args.get("replacement_content")
                    )
                elif tool_name == "read_file":
                    if self.mcp_hub:
                        res = self.mcp_hub.call_tool("read_file", args)
                    else:
                        res = {"error": "MCP Client Hub is not loaded."}
                elif tool_name == "list_directory":
                    if self.mcp_hub:
                        res = self.mcp_hub.call_tool("list_directory", args)
                    else:
                        res = {"error": "MCP Client Hub is not loaded."}
                else:
                    if self.mcp_hub:
                        try:
                            res = self.mcp_hub.call_tool(tool_name, args)
                        except Exception as e:
                            res = {"error": f"도구 호출 '{tool_name}' 실패 ({e})"}
                    else:
                        res = {"error": f"알 수 없는 도구: {tool_name}"}
                    
                res_str = json.dumps(res, ensure_ascii=False)
                print(f"  [Critic Agent] Tool Result: {res_str[:300]}...")
                history_log.append(f"Result: {res_str}")
                
            except Exception as e:
                err_msg = f"Error: {e}"
                print(f"  [Critic Agent] Step {step} Exception: {e}")
                history_log.append(err_msg)
                
        return "⚠️ CRITIC 실행 시간 한계를 초과하였습니다.", False

    def _critic_edit_file(self, path: str, target_content: str, replacement_content: str) -> dict:
        import os
        from pathlib import Path
        
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = (Path(__file__).resolve().parent / path).resolve()
            
        if not file_path.exists():
            return {"success": False, "error": f"파일이 존재하지 않습니다: {path}"}
            
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            if target_content not in content:
                return {
                    "success": False, 
                    "error": "수정 대상 텍스트(target_content)가 파일 내용과 정확히 일치하지 않습니다. 공백/들여쓰기를 완벽히 맞추십시오."
                }
            
            new_content = content.replace(target_content, replacement_content)
            file_path.write_text(new_content, encoding="utf-8")
            return {"success": True, "message": f"파일 수정 성공: {path}"}
        except Exception as e:
            return {"success": False, "error": f"파일 수정 실패: {e}"}

    def _read_harness_file(self, filename: str) -> str:
        import os
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "harness", filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        alt_path = os.path.join("harness", filename)
        if os.path.exists(alt_path):
            with open(alt_path, "r", encoding="utf-8") as f:
                return f.read()
        return f"Harness file {filename} not found."

    def _clean_llm_response(self, text: str) -> str:
        import re
        # Remove think tags if any
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Remove markdown code fences
        if "```json" in text:
            text = text.split("```json")[-1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return text.strip()

    def _parse_json_from_llm(self, text: str) -> dict:
        cleaned = self._clean_llm_response(text)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        data = {}
        if start >= 0:
            # Try to slice from '{' to the end of string if '}' is missing or misplaced
            json_substr = cleaned[start:end] if end > start else cleaned[start:]
            
            # Local helper to heal truncated or unclosed quotes/brackets/braces
            def _heal_json_braces(s: str) -> str:
                s = s.strip()
                open_braces = 0
                open_brackets = 0
                in_string = False
                escape = False
                for char in s:
                    if escape:
                        escape = False
                        continue
                    if char == '\\':
                        escape = True
                        continue
                    if char == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == '{':
                            open_braces += 1
                        elif char == '}':
                            open_braces = max(0, open_braces - 1)
                        elif char == '[':
                            open_brackets += 1
                        elif char == ']':
                            open_brackets = max(0, open_brackets - 1)
                if in_string:
                    s += '"'
                if open_brackets > 0:
                    s += ']' * open_brackets
                if open_braces > 0:
                    s += '}' * open_braces
                return s

            json_substr = _heal_json_braces(json_substr)
            
            try:
                import json
                data = json.loads(json_substr)
            except Exception as e:
                # ast.literal_eval fallback for single-quote strings or incomplete json syntax
                try:
                    import ast
                    data = ast.literal_eval(json_substr)
                except Exception:
                    print(f"[JSON Parse Error] {e} on text: {cleaned}")
                    return {}
        else:
            return {}

        normalized = data.copy()
        
        # 1. Normalize final_answer
        for k in ["final_answer", "finalAnswer", "answer", "final_response", "response"]:
            if k in data:
                normalized["final_answer"] = data[k]
                if "success" in data:
                    normalized["success"] = data["success"]
                break
                
        # 2. Normalize tool_call structure
        tool_call_payload = None
        for k in ["tool_call", "toolcall", "tool_calls", "toolcalls", "tool"]:
            if k in data:
                tool_call_payload = data[k]
                break
                
        if tool_call_payload:
            if isinstance(tool_call_payload, dict):
                tc_name = None
                for k in ["name", "tool_name", "toolname", "action", "method"]:
                    if k in tool_call_payload:
                        tc_name = tool_call_payload[k]
                        break
                
                tc_args = {}
                for k in ["arguments", "args", "params", "parameters"]:
                    if k in tool_call_payload:
                        tc_args = tool_call_payload[k]
                        break
                
                if tc_name:
                    normalized["tool_call"] = {
                        "name": tc_name,
                        "arguments": tc_args
                    }
            elif isinstance(tool_call_payload, str):
                # If tool_call is directly a string naming the tool
                tc_args = {}
                for k in ["arguments", "args", "params", "parameters"]:
                    if k in data:
                        tc_args = data[k]
                        break
                normalized["tool_call"] = {
                    "name": tool_call_payload,
                    "arguments": tc_args
                }
                
        # 3. Fallback: If no nested tool_call found, but name and arguments are placed at root level
        if "tool_call" not in normalized and "final_answer" not in normalized:
            tc_name = None
            for k in ["name", "tool_name", "toolname", "action"]:
                if k in data and isinstance(data[k], str):
                    tc_name = data[k]
                    break
            tc_args = None
            for k in ["arguments", "args", "params", "parameters"]:
                if k in data:
                    tc_args = data[k]
                    break
            if tc_name:
                normalized["tool_call"] = {
                    "name": tc_name,
                    "arguments": tc_args or {}
                }
                
        return normalized

    def _call_vlm_for_swarm(self, image_path: str, prompt: str) -> str:
        import base64
        import json
        import urllib.request
        
        try:
            with open(image_path, "rb") as img_file:
                b64_image = base64.b64encode(img_file.read()).decode("utf-8")
        except Exception as e:
            return f"VLM 이미지 인코딩 실패: {e}"

        payload = json.dumps({
            "model": "qwen2.5vl:7b",
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image]
                }
            ],
            "stream": False,
            "options": {
                "num_ctx": 4096
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_API, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
                return data["message"]["content"].strip()
        except Exception as e:
            return f"VLM 호출 오류: {e}"

    def _send_telegram_swarm_report(self, state):
        # 데몬으로 전송 역할을 이관하여 비활성화
        pass

    async def _on_analysis_complete(self, data: dict):
        """analysis_complete 이벤트를 처리하여 communication_agent로 사용자에게 브리핑합니다."""
        image_path = data.get("image_path")
        result = data.get("result", {})
        print(f"[Orchestrator Event] 분석 완료 ➔ communication_agent 브리핑 시작: {image_path}")
        
        communication_agent = self._agents.get("communication")
        if not communication_agent:
            print("[Orchestrator Event] communication_agent가 로드되지 않았습니다.")
            return

        import asyncio
        loop = asyncio.get_running_loop()
        
        briefing_prompt = (
            f"다음 분석 완료 정보를 기반으로 사용자에게 상황을 명확하고 친절하게 한국어로 브리핑하십시오.\n"
            f"이미지 경로: {image_path}\n"
            f"분석 결과 요약: {result.get('summary', '결과 요약 없음')}"
        )
        
        brief_res = await loop.run_in_executor(
            None,
            communication_agent.safe_run,
            briefing_prompt,
            None
        )
        
        # 브리핑 내용을 DB AgentMemory에 저장
        try:
            from aria.core.database import SessionLocal, AgentMemory
            from aria.mcp.mcp_client import get_current_session_id
            db = SessionLocal()
            memory = AgentMemory(
                session_id=get_current_session_id(),
                role="agent",
                content=f"🤖 [자동 브리핑] {brief_res.get('summary', '브리핑 작성 실패')}"
            )
            db.add(memory)
            db.commit()
            db.close()
            print(f"[Orchestrator Event] 자동 브리핑 기록 완료: {brief_res.get('summary', '브리핑 작성 실패')[:100]}...")
        except Exception as e:
            print(f"[Orchestrator Event] 자동 브리핑 DB 기록 에러: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # 라우팅: LLM이 판단 (키워드 매칭 없음)
    # ──────────────────────────────────────────────────────────────────────
    def _plan(self, user_input: str, image_path: str = None) -> dict:
        """deepseek-r1이 필요한 에이전트와 실행 순서 결정."""

        available = list(self._agents.keys()) + ["chat"]

        prompt = f"""[TOOL SELECTION RULES]
Rule 1: 사용자가 '클릭', '브라우저 열기', '캡처', '마우스 이동', '화면을 봐' 등 GUI 조작이나 물리적 제어를 명시적으로 요구한 경우, 절대 우회(Bypass)하지 말고 반드시 computer_use MCP 도구를 사용해야 한다.
Rule 2: 정보 검색 시, 사용자가 '화면 캡처'나 '웹페이지 띄우기'를 지시했다면 arxiv나 youtube 같은 텍스트 API 도구의 사용을 엄격히 금지한다. 무조건 computer_use를 통해 브라우저를 물리적으로 조작하여 시각적(Visual) 결과를 도출하라.

사용자 요청: "{user_input}"
이미지 첨부: {"있음" if image_path else "없음"}

사용 가능한 에이전트:
- vision: 이미지를 분석해달라는 구체적 요청 (객체 탐지, 이상 탐지)
- research: 논문 검색, 모델 탐색 등 구체적 학술/연구/arXiv/HuggingFace 검색 요청 (주의: 단순 트렌드, 뉴스, 동영상, 게임, 유튜브 조회수 등 대중적 질문은 절대 이 에이전트를 쓰지 말 것)
- code: 코드를 작성/수정/실행해달라는 구체적 요청, 또는 클릭/브라우저 열기/화면 캡처/마우스 이동 등 GUI 조작 및 물리적 제어(computer_use)가 필요한 요청
- communication: 메시지 이력 요약, 이메일(Gmail), 구글 드라이브(Google Drive) 파일 및 유튜브(YouTube) 동영상/경기 검색/조회 요청
- schedule: "내일 3시에 미팅 추가해줘" 같은 구체적 일정 추가/조회 요청
- industry: CMDIAD 산업 이상탐지를 수행해달라는 구체적 요청
- data: CSV/데이터 파일을 분석해달라는 구체적 요청
- chat: 일반 대화, 질문, 인사, 잡담, 기능 설명 요청, 사용법 질문, 그리고 뉴스/게임/조회수 등 웹 검색이나 일반 정보 획득성 질문 (research와 헷갈리지 말 것!)

핵심 판단 규칙:
1. "어떻게 해?" "뭘 할 수 있어?" "사용법 알려줘" 같은 질문 → 반드시 chat
2. 기능에 대해 묻는 것과 실제 행동 요청을 구분해라
3. 기능 설명/사용법/도움말 질문은 무조건 chat
4. 이미지 첨부 + 분석 요청이면 vision 포함
5. "아침 브리핑" 같은 종합 요청이면 communication + schedule + research
6. 유튜브(YouTube) 동영상/경기 검색 등 실제 도구(search_youtube 등) 호출 및 실행이 필요한 유튜브 관련 요청은 무조건 communication 에이전트로 라우팅하라. (단순 잡담이나 일반 지식 질문 등 실질 도구 호출이 없는 경우는 chat으로 라우팅)
7. 사용자가 특정 정보(뉴스, 일정, 메일, 드라이브 등)를 요구하면, 절대 '구체적으로 알려달라'고 되묻지 마라. 즉시 가장 적합한 에이전트를 배치하여 기본값(최신 트렌드 등)으로 검색/도출하도록 계획을 짜야 한다. (Rule 1)
8. 사용자가 '클릭', '브라우저 열기', '캡처', '마우스 이동', '화면을 봐' 등 GUI 조작이나 물리적 제어를 명시적으로 요구한 경우, 절대 우회하지 말고 code 에이전트로 계획을 수립해야 한다. (Rule 3)
9. 확신이 없으면 chat 선택

JSON으로만 응답:
{{"agents": ["agent1"], "mode": "sequential"}}"""

        try:
            raw = _call_ollama("deepseek-r1:8b", prompt, temperature=0.0)

            # JSON 파싱 (deepseek-r1의 <think> 태그 제거)
            text = raw
            if "</think>" in text:
                text = text.split("</think>")[-1].strip()

            # JSON 블록 추출
            if "```json" in text:
                text = text.split("```json")[-1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            # { } 블록만 추출
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

            plan = json.loads(text)

            # 유효한 에이전트만 필터링
            valid_agents = [a for a in plan.get("agents", [])
                           if a in available]
            if not valid_agents:
                valid_agents = ["chat"]

            plan["agents"] = valid_agents
            if "mode" not in plan:
                plan["mode"] = "sequential"

            print(f"[Orchestrator] Plan: {plan}")
            return plan

        except Exception as e:
            print(f"[Orchestrator] _plan 실패: {e}, chat 폴백")
            # 이미지가 있으면 vision 폴백
            if image_path and "vision" in self._agents:
                return {"agents": ["vision"], "mode": "sequential"}
            return {"agents": ["chat"], "mode": "sequential"}

    def _verify_mcp(self, server_name: str = None) -> str:
        """
        E2E 심층 검증 루프. 
        각 MCP 서버의 최경량 도구를 직접 호출하여 연결 상태와 제어 권한을 100% 검증한다.
        """
        mcp_client = getattr(self, "mcp_client", None) or getattr(self, "mcp_hub", None)
        if not mcp_client:
            return "❌ MCP 클라이언트 허브가 로드되지 않았습니다."

        config_servers = mcp_client._config.get("mcpServers", {}) if hasattr(mcp_client, "_config") else {}
        
        # 대상 서버 선정
        targets = []
        if server_name:
            if server_name not in config_servers:
                return f"❌ `{server_name}` 서버는 `mcp_config.json`에 정의되지 않은 서버입니다."
            targets.append(server_name)
        else:
            targets = list(config_servers.keys())

        if not targets:
            return "⚠️ 검증할 MCP 서버가 설정에 존재하지 않습니다."

        results = []
        
        # 서버별 E2E 최경량 도구 호출 매핑
        test_calls = {
            "shell_exec": {
                "tool": "run_command",
                "args": {"command": "echo 'ARGUS_MCP_ACTIVE'"},
                "validator": lambda res: "ARGUS_MCP_ACTIVE" in str(res)
            },
            "filesystem": {
                "tool": "list_directory",
                "args": {"path": "."},
                "validator": lambda res: isinstance(res, dict) and res.get("success", False) is True
            },
            "computer_use": {
                "tool": "get_screen_size",
                "args": {},
                "validator": lambda res: isinstance(res, dict) and "width" in res
            },
            "google-workspace": {
                "tool": "gmail.search",
                "args": {"query": "is:unread", "limit": 1},
                "validator": lambda res: isinstance(res, dict) and "error" not in res
            },
            "youtube": {
                "tool": "search_youtube",
                "args": {"query": "test"},
                "validator": lambda res: isinstance(res, dict) and "error" not in res
            },
            "web_search": {
                "tool": "search_web",
                "args": {"query": "AI agents"},
                "validator": lambda res: isinstance(res, dict) and res.get("success", False) is True
            },
            "weather": {
                "tool": "get_weather",
                "args": {"location": "Seoul"},
                "validator": lambda res: isinstance(res, dict) and res.get("success", False) is True
            },
            "arxiv": {
                "tool": "search_arxiv",
                "args": {"query": "machine learning", "max_results": 1},
                "validator": lambda res: isinstance(res, dict) and "error" not in res
            },
            "kaggle": {
                "tool": "search_datasets",
                "args": {"query": "test"},
                "validator": lambda res: isinstance(res, dict) and "error" not in res
            },
            "huggingface": {
                "tool": "search_models",
                "args": {"query": "test", "max_results": 1},
                "validator": lambda res: isinstance(res, dict) and "error" not in res
            },
            "telegram": {
                "tool": "get_updates",
                "args": {"limit": 1},
                "validator": lambda res: isinstance(res, dict) and "error" not in res
            }
        }

        # 각 대상 서버 실행
        for name in targets:
            server_proc = mcp_client.servers.get(name)
            if not server_proc or not server_proc.process or server_proc.process.poll() is not None:
                # 오프라인 상태 점검
                server_config = config_servers.get(name, {})
                missing_envs = []
                import os
                for env_key, env_val in server_config.get("env", {}).items():
                    if isinstance(env_val, str) and env_val.startswith("${") and env_val.endswith("}"):
                        var_name = env_val[2:-1]
                        real_val = os.environ.get(var_name, "").strip()
                        if not real_val or "여기에_" in real_val or "ENTER_" in real_val.upper() or "INSERT_" in real_val.upper():
                            missing_envs.append(var_name)
                
                reason = "서버 프로세스가 기동되지 않았거나 중지되었습니다."
                if missing_envs:
                    reason = f"필수 환경 변수({', '.join(missing_envs)})가 설정되지 않았습니다."
                
                results.append({
                    "server": name,
                    "status": "offline",
                    "error": reason,
                    "troubleshoot": f"서버 구동 상태와 환경 변수 설정을 확인하십시오. (필요 변수: {', '.join(missing_envs) if missing_envs else '없음'})"
                })
                continue

            test_info = test_calls.get(name)
            if not test_info:
                # 매핑되지 않은 임의의 서버는 list_tools E2E 호출로 검증 대체
                try:
                    t_start = time.time()
                    tools = server_proc.list_tools()
                    elapsed = round((time.time() - t_start) * 1000, 2)
                    results.append({
                        "server": name,
                        "status": "success",
                        "elapsed": elapsed,
                        "data_summary": f"도구 목록 조회 성공 (총 {len(tools)}개 제공)",
                        "detail": f"동적 핸드셰이크 완료"
                    })
                except Exception as e:
                    results.append({
                        "server": name,
                        "status": "error",
                        "error": str(e),
                        "troubleshoot": self._get_troubleshooting_tip(name, str(e))
                    })
                continue

            tool_name = test_info["tool"]
            args = test_info["args"]
            validator = test_info["validator"]

            try:
                t_start = time.time()
                # call_tool 호출로 실제 도구 기동
                res = mcp_client.call_tool(tool_name, args, server_name=name)
                elapsed = round((time.time() - t_start) * 1000, 2)

                if isinstance(res, dict) and "error" in res:
                    err_msg = res["error"]
                    results.append({
                        "server": name,
                        "status": "error",
                        "error": err_msg,
                        "troubleshoot": self._get_troubleshooting_tip(name, err_msg)
                    })
                elif validator(res):
                    data_summary = ""
                    if name == "computer_use":
                        data_summary = f"현재 해상도는 {res.get('width')}x{res.get('height')}로 확인되었습니다"
                    elif name == "shell_exec":
                        data_summary = "터미널 제어 권한이 증명되었습니다"
                    elif name == "filesystem":
                        data_summary = f"프로젝트 폴더 조회 완료 (항목 {res.get('count', 0)}개)"
                    elif name == "google-workspace":
                        data_summary = "이메일 긁어오기 정상 동작이 확인되었습니다"
                    elif name == "youtube":
                        data_summary = "유튜브 동영상 검색 배열 수신 확인"
                    elif name == "weather":
                        data_summary = f"실시간 날씨 정보 수집 성공 ({res.get('summary', '')})"
                    elif name == "web_search":
                        data_summary = "DuckDuckGo 실시간 웹 검색 정상 동작 확인"
                    else:
                        data_summary = "도구 실행 결과 정상 확인"

                    results.append({
                        "server": name,
                        "status": "success",
                        "elapsed": elapsed,
                        "data_summary": data_summary,
                        "detail": f"E2E 실행 성공 ({elapsed} ms)"
                    })
                else:
                    results.append({
                        "server": name,
                        "status": "error",
                        "error": f"데이터 포맷 유효성 검증 실패: {res}",
                        "troubleshoot": "도구 호출은 성공하였으나 반환 데이터 검증 기준을 충족하지 못했습니다."
                    })
            except Exception as e:
                results.append({
                    "server": name,
                    "status": "error",
                    "error": str(e),
                    "troubleshoot": self._get_troubleshooting_tip(name, str(e))
                })


        # 종합 진단 리포트 마크다운 작성
        report_lines = [
            "⚡ **ARIA MCP E2E 심층 검증 진단 결과**",
            ""
        ]
        for r in results:
            name = r["server"]
            if r["status"] == "success":
                report_lines.append(f"✅ **{name}**: 정상 가동 중. {r['data_summary']}. ({r['elapsed']} ms)")
            elif r["status"] == "offline":
                report_lines.append(f"❌ **{name}**: 🔴 오프라인 (Disconnected)")
                report_lines.append(f"  - *원인*: {r['error']}")
                report_lines.append(f"  - *해결 방안*: {r['troubleshoot']}")
            else:
                report_lines.append(f"❌ **{name}**: 🔴 오동작 (Execution Error)")
                report_lines.append(f"  - *에러 내용*: `{r['error']}`")
                report_lines.append(f"  - *해결 방안*: {r['troubleshoot']}")
            report_lines.append("")

        return "\n".join(report_lines)

    def _get_troubleshooting_tip(self, server_name: str, error_msg: str) -> str:
        error_lower = error_msg.lower()
        if "token" in error_lower or "credentials" in error_lower or "auth" in error_lower or "expired" in error_lower or "refresh" in error_lower:
            if server_name == "google-workspace":
                return "현재 구글 토큰이 만료되었거나 인증에 실패한 것으로 보입니다. `token.json` 또는 `credentials.json` 관련 인증 정보를 삭제하고 다시 로그인하여 서버를 재시작해 주세요."
            elif server_name == "notion":
                return "Notion API 키 또는 토큰 설정이 올바르지 않거나 만료되었습니다. `mcp_config.json`의 `NOTION_API_KEY` 환경 변수 설정을 확인해 주세요."
        if "permission" in error_lower or "denied" in error_lower or "unauthorized" in error_lower or "403" in error_lower:
            return f"서버 '{server_name}'의 실행 권한 또는 보안 권한이 부족합니다. 해당 도구 실행에 필요한 권한 설정을 확인해 주세요."
        if "timeout" in error_lower or "timed out" in error_lower:
            return f"서버 '{server_name}'가 응답 제한 시간(Timeout) 내에 답변하지 못했습니다. 서버 프로세스가 멈춰있거나 과부하 상태일 수 있으니 프로세스를 재시작해 주세요."
        if "connection" in error_lower or "refused" in error_lower or "offline" in error_lower:
            return f"서버 '{server_name}'와의 연결이 끊어졌거나 포트/네트워크 통신에 실패했습니다. 해당 서버가 정상적으로 실행 중인지 확인해 주세요."
        if "not found" in error_lower or "no tool" in error_lower or "unknown tool" in error_lower:
            return f"서버 '{server_name}'에 요청한 도구가 정의되어 있지 않거나 이름을 찾을 수 없습니다. 도구 구성을 다시 확인해 주세요."
        
        return f"서버 '{server_name}' 실행 중 예상치 못한 오류가 발생했습니다. 환경 변수 및 관련 종속성 패키지가 정상 설치되었는지 확인하고 서버를 재기동해 주십시오."

    def _ping_mcp(self, server_name: str) -> str:
        """핑 기능 호환을 위해 보존하며 E2E 검증으로 우회"""
        return self._verify_mcp(server_name)

    # ──────────────────────────────────────────────────────────────────────
    # 실행
    # ──────────────────────────────────────────────────────────────────────
    def run_3stage_pipeline(self, user_input: str, chat_history: list = None, callback: callable = None) -> str:
        """
        3-Stage Multi-Agent Orchestration Chain:
        [Router Agent] ➡️ [Worker Agents] ➡️ [Synthesizer Agent]
        """
        print(f"\n⚡ [3-Stage Pipeline Start] User Input: {user_input}")
        
        # --- Stage 1: Router Agent (의도 파악 및 도구 선택) ---
        _emit_agent_status(callback, "router", "running", detail="사용자의 의도 분석 및 최적의 도구 파이프라인 설계 중...")
        if callback:
            callback({"type": "thought", "content": "🤖 [Router Agent] 사용자의 의도 분석 및 최적의 도구 파이프라인 설계 중..."})
            
        tools_desc = self.mcp_hub.get_tools_description_for_llm() if self.mcp_hub else "연결된 도구 없음"
        router_prompt = f"""당신은 ARIA 시스템의 지능형 Router Agent입니다.
사용자의 요청과 대화 이력을 분석하여, 작업을 수행하기 위해 호출해야 할 MCP 도구(들)를 선택하십시오.

[사용 가능한 모든 도구 목록 및 설명]
{tools_desc}

다음 형식의 JSON으로만 응답하십시오. 생각이나 다른 텍스트는 절대 포함하지 마십시오:
{{
  "needs_tools": true/false,
  "selected_tools": [
    {{"tool_name": "도구명", "arguments": {{ "arg1": "val1" }} }}
  ],
  "reason": "도구 선택 근거"
}}

사용자 요청: "{user_input}"
대화 이력: {chat_history}
"""
        
        needs_tools = False
        selected_tools = []
        try:
            res_text = _call_ollama("qwen2.5:14b", router_prompt, temperature=0.0)
            data = self._parse_json_from_llm(res_text)
            needs_tools = data.get("needs_tools", False)
            selected_tools = data.get("selected_tools", [])
            print(f"  [Router Agent] 도구 필요 여부: {needs_tools}, 선택된 도구: {selected_tools}")
            _emit_agent_status(callback, "router", "ok")
        except Exception as e:
            print(f"  ❌ [Router Agent] 에러 발생: {e}")
            _emit_agent_status(callback, "router", "error", detail=str(e)[:120])
            # Fallback: 키워드 기반 수동 도구 라우팅 (실제 존재하는 서버만)
            if any(kw in user_input.lower() for kw in ["날씨", "기온"]):
                # get_weather는 현재 mcp_config에 없으므로 스킵
                pass
            elif any(kw in user_input.lower() for kw in ["뉴스", "검색", "찾아"]):
                # search_web은 현재 mcp_config에 없으므로 스킵
                pass
            elif any(kw in user_input.lower() for kw in ["논문", "arxiv"]):
                # search_arxiv는 현재 mcp_config에 없으므로 스킵
                pass
            # 존재하는 도구만 fallback 허용 (filesystem, huggingface)
            elif any(kw in user_input.lower() for kw in ["huggingface", "허깅페이스", "모델 찾아"]):
                needs_tools = True
                selected_tools = [{"tool_name": "huggingface.search_models", "arguments": {"query": user_input[:80]}}]

        # --- Stage 2: Worker Agents (외부 MCP API 통신 및 데이터 수집) ---
        worker_results = []
        if needs_tools and self.mcp_hub:
            for item in selected_tools:
                t_name = item.get("tool_name")
                t_args = item.get("arguments", {})
                if not t_name:
                    continue
                    
                if callback:
                    callback({"type": "thought", "content": f"👷 [Worker Agent] 통신 및 데이터 수집 중: {t_name}"})
                    callback({"type": "tool_start", "tool": t_name, "params": t_args})
                
                # 채널 격리: 에러나 디버그 로그가 밖으로 새어 나가지 않도록 내부 try-except로 완벽 격리
                try:
                    t_start = time.time()
                    res = self.mcp_hub.call_tool(t_name, t_args)
                    elapsed = round((time.time() - t_start) * 1000, 2)
                    
                    # 성공 결과 저장
                    worker_results.append({
                        "tool": t_name,
                        "status": "success",
                        "elapsed_ms": elapsed,
                        "data": res
                    })
                    
                    if callback:
                        callback({"type": "tool_end", "tool": t_name, "result": json.dumps(res, ensure_ascii=False)})
                except Exception as ex:
                    # 에러 발생 시 외부 채널로 유출되지 않게 내부 컨텍스트에만 에러 기록
                    print(f"  ❌ [Worker Agent Error] {t_name} 실행 에러: {ex}")
                    worker_results.append({
                        "tool": t_name,
                        "status": "error",
                        "error": str(ex)
                    })
                    if callback:
                        callback({"type": "tool_end", "tool": t_name, "result": f"Error: {ex}"})

        # --- Stage 3: Synthesizer Agent (데이터 종합 및 최종 한국어 답변 생성) ---
        _emit_agent_status(callback, "synthesizer", "running", detail="수집된 데이터 종합 및 프리미엄 한국어 답변 생성 중...")
        if callback:
            callback({"type": "thought", "content": "✍️ [Synthesizer Agent] 수집된 데이터 종합 및 프리미엄 한국어 답변 생성 중..."})
            
        synthesizer_prompt = f"""당신은 ARIA 시스템의 Synthesizer Agent입니다.
Router와 Worker Agent들이 수집한 데이터와 사용자의 최초 요청을 종합하여, 최종 사용자에게 제공할 답변을 한국어로 품격 있게 작성하십시오.

[⚠️ 답변 작성 가이드라인]
1. [보안 및 격리]: Worker Agent의 내부 에러 로그나 기술적인 JSON 날것 디버깅 정보는 절대 그대로 노출하거나 유출(Leak)하지 마십시오. 사용자에게는 오직 정제된 정보와 결과만 친절하게 제공해야 합니다.
2. [출력 포맷]: 마크다운 하이퍼링크 `[제목](URL)`이 있는 경우 정제하여 마크다운 링크 문법을 유지해 주십시오. (프론트엔드에서 카드로 파싱됩니다.)
3. 질문에 적합한 본론과 구체적인 액션 아이템을 포함해 주십시오.

사용자 최초 요청: "{user_input}"
대화 이력: {chat_history}
수집된 Worker Agent 결과:
{json.dumps(worker_results, indent=2, ensure_ascii=False)}
"""

        try:
            final_reply = _call_ollama_with_korean_guard("qwen2.5:14b", synthesizer_prompt, temperature=0.3)
            final_reply = final_reply.strip()
            if "</think>" in final_reply:
                final_reply = final_reply.split("</think>")[-1].strip()
            _emit_agent_status(callback, "synthesizer", "ok")
        except Exception as e:
            print(f"  ❌ [Synthesizer Agent] 에러 발생: {e}")
            _emit_agent_status(callback, "synthesizer", "error", detail=str(e)[:120])
            final_reply = "죄송합니다. 데이터를 취합하여 답변을 생성하는 중에 오류가 발생했습니다. 다시 시도해 주십시오."
            
        return final_reply

    def route(self, user_input: str, image_path: str = None,
              chat_history: list = None, chat_id: str = None, callback: callable = None) -> dict:
        """
        메인 라우팅 함수.
        1. deepseek-r1이 필요한 에이전트 판단 (이미지가 있을 경우 vision 고정)
        2. 순차 또는 병렬 실행
        3. 결과 취합 → 최종 답변
        """
        t0 = time.time()
        print(f"\n{'='*60}")
        print(f"[Orchestrator] 요청: {user_input[:80]}")
        print(f"[Orchestrator] 이미지: {bool(image_path)}")

        if user_input.strip().startswith("/verify_mcp") or user_input.strip().startswith("/test_mcp"):
            parts = user_input.strip().split()
            server_name = parts[1] if len(parts) > 1 else None
            verify_res = self._verify_mcp(server_name)
            return {
                "response": verify_res,
                "image_path": None,
                "agents_used": ["orchestrator"],
                "results": {"verify": {"status": "success", "summary": verify_res}},
                "plan": {"agents": ["orchestrator"], "mode": "sequential"},
                "total_elapsed": round(time.time() - t0, 2)
            }

        if user_input.strip().startswith("/mcp"):
            parts = user_input.strip().split(maxsplit=2)
            tool_name = parts[1] if len(parts) > 1 else None
            params_str = parts[2] if len(parts) > 2 else "{}"
            
            if not tool_name:
                verify_res = "❌ 도구 이름이 명시되지 않았습니다. 사용법: `/mcp <tool_name> <json_args>`"
            else:
                try:
                    params = json.loads(params_str)
                    if self.mcp_hub:
                        t_start = time.time()
                        res = self.mcp_hub.call_tool(tool_name, params)
                        elapsed = round((time.time() - t_start) * 1000, 2)
                        verify_res = f"✅ **/mcp {tool_name} 실행 완료 ({elapsed} ms)**\n\n```json\n{json.dumps(res, indent=2, ensure_ascii=False)}\n```"
                    else:
                        verify_res = "❌ MCP 클라이언트가 활성화되어 있지 않습니다."
                except Exception as e:
                    verify_res = f"❌ 오류 발생: {e}"
                    
            return {
                "response": verify_res,
                "image_path": None,
                "agents_used": ["orchestrator"],
                "results": {"mcp_macro": {"status": "success", "summary": verify_res}},
                "plan": {"agents": ["orchestrator"], "mode": "sequential"},
                "total_elapsed": round(time.time() - t0, 2)
            }

        status_cb = None
        if callback:
            def status_cb(agent, state, **kw):
                callback({
                    "type": "agent_status",
                    "agent": agent,
                    "state": state,
                    "ts": time.time(),
                    **kw
                })

        if image_path:
            # 이미지 분석 요청은 무조건 vision 에이전트로 100% Bypass
            plan = {"agents": ["vision"], "mode": "sequential"}
            results = self._run_sequential(
                plan["agents"], user_input, image_path, chat_history, status_cb=status_cb)
            
            # 3. 교차 토론 (Agentic Debate) - 이미지가 없을 때만 실행
            if not image_path and "vision" in results and "analyst" in results:
                print("[Orchestrator] Vision 및 Analyst 분석 완료 -> 교차 토론(Debate) 시작")
                debate_res = self._run_debate(results["vision"], results["analyst"])
                results["debate"] = {
                    "agent": "debate",
                    "status": "success",
                    "summary": debate_res
                }

            # 4. 결과 취합
            final = self._synthesize(results, user_input)
            final["plan"] = plan
            final["total_elapsed"] = round(time.time() - t0, 2)

            print(f"[Orchestrator] 완료: {final['total_elapsed']}s")
            print(f"{'='*60}\n")
            return final
        else:
            # 파일이 들어오지 않은 일반 텍스트 쿼리는 3단계 멀티 에이전트 파이프라인으로 구동
            response = self.run_3stage_pipeline(user_input, chat_history, callback=callback)
            return {
                "response": response,
                "image_path": None,
                "agents_used": ["router", "worker", "synthesizer"],
                "results": {"3stage": response},
                "plan": {"agents": ["3stage"], "mode": "sequential"},
                "total_elapsed": round(time.time() - t0, 2)
            }


    def _run_debate(self, vision_res: dict, analyst_res: dict) -> str:
        """
        vision_agent와 analyst_agent의 의견을 비교/검증하는 토론 수행.
        정확도 미달이거나 분석 비효율이 있으면 outputs/improvement_draft.md 에
        수학적 수식(시간 복잡도, VRAM 등)을 포함한 개선안 작성.
        """
        import os
        from pathlib import Path
        
        vision_summary = vision_res.get("summary", "시각 분석 결과 없음")
        analyst_summary = analyst_res.get("summary", "통계 분석 결과 없음")
        
        # deepseek-r1:8b를 호출하여 토론 진행
        prompt = f"""[Agentic Debate] 비전 에이전트와 데이터 분석 에이전트 간의 정밀 진단 크로스 체크.
        
=== 비전 에이전트 (시각 특징 분석) ===
{vision_summary}

=== 데이터 분석 에이전트 (통계 수치 및 신뢰성 검정) ===
{analyst_summary}

=== 토론 요구 조건 ===
두 에이전트의 분석 결과를 검토하여:
1. 시각 분석(결함 유형 등)과 통계 분석(정상 분포 대비 거리, 95% 신뢰 구간 초과 여부)이 일치하는가?
2. 만약 불일치(예: 시각적으로는 스크래치이나 통계적으로는 95% 신뢰구간 내에 있어 정상으로 보이는 경우 등)가 있는가?
3. 현재 모델(CCIFPS)의 임계값 설정(THRESHOLD = 15.0)이 적절한가? 통계량의 상위 95% 신뢰구간 값과 비교 시, threshold를 조정해야 할 과학적 필요성이 있는가?
4. 연산 비효율성(시간 복잡도, VRAM 사용량 등)은 없는가?

만약 threshold가 너무 낮아 오검출(False Positive) 위험이 있거나, 너무 높아 미검출(False Negative) 위험이 있는 경우, 혹은 연산 성능 향상이 필요한 경우 수학적 증명(예: 시간 복잡도 O(N*M*D), VRAM 사용량 추정, 신뢰구간과의 거리 등)을 포함한 구체적인 개선 코드 초안을 리포트 형식으로 작성하라.

결과는 반드시 다음 마크다운 형식을 유지하여 출력하라 (다른 텍스트 금지):
```markdown
# [ARIA] Self-Improvement Draft

## 1. Debate Consensus (합의사항)
- 요약 기술

## 2. Mathematical Proof of Inefficiency or Accuracy Issue
- 예: CCIFPS k-NN 연산의 시간 복잡도는 O(N * M * D)이며, 현재 VRAM 사용량은 ...MB 이다.
- 통계적 신뢰성 검정에 따른 임계치(THRESHOLD) 적합성 수학적 증명 (95% CI 값 대비 threshold의 차이 분석)

## 3. Actionable Code Modification Proposal
- 수정할 대상 파일: app.py
- 수정할 타겟 변수/값: THRESHOLD = [수정할 신규 값]
- 제안 이유: 통계 데이터 기반 95% 신뢰 수준의 최적값으로 조정.
```
"""
        try:
            debate_result = _call_ollama("deepseek-r1:8b", prompt)
            
            # <think> 태그 제거
            if "</think>" in debate_result:
                debate_result = debate_result.split("</think>")[-1].strip()
                
            # markdown 블록 추출
            if "```markdown" in debate_result:
                debate_result = debate_result.split("```markdown")[-1].split("```")[0].strip()
            elif "```" in debate_result:
                debate_result = debate_result.split("```")[1].split("```")[0].strip()
                
            # outputs/improvement_draft.md 에 저장
            base_path = Path(__file__).parent.resolve()
            out_dir = base_path / "outputs"
            out_dir.mkdir(exist_ok=True)
            draft_path = out_dir / "improvement_draft.md"
            
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(debate_result)
                
            print(f"[Debate] 개선안 초안이 저장되었습니다: {draft_path}")
            return debate_result
        except Exception as e:
            print(f"[Debate] 토론 실행 실패: {e}")
            return f"Debate Failed: {e}"

    def _run_debate_detectors(
        self,
        det_a: dict,
        det_b: dict,
        image_meta: dict | None = None,
    ) -> dict:
        """탐지기 A vs 탐지기 B 중 어느 모델을 채택할지 결정하는 자율 토론.

        [v4 §2 — 분리 원칙]
        - 기존 _run_debate(vision vs analyst 교차검증)와 완전히 분리된 새 메서드.
        - 입력: 두 탐지기의 run() 결과 dict + image_meta(선택)
        - 출력: {"adopted_detector": str, "reason": str, "confidence": float}
        - 프롬프트는 "어느 탐지기 모델을 선택할지" 에만 집중.
          합/불 판정(pass/fail) 문구를 생성하거나 decision을 덮어쓰지 않는다.

        [비용 가드]
        - 이 메서드는 vision_agent에서 escalation(모호 판정) 시에만 호출된다.
        - 이미지당 최대 2개 탐지기만 실행하며, 이 메서드 안에서 추가 추론 없음.
        """
        name_a = det_a.get("model_name", "탐지기A")
        name_b = det_b.get("model_name", "탐지기B")

        score_a = det_a.get("score", 0.0)
        score_b = det_b.get("score", 0.0)
        conf_a  = det_a.get("confidence", 0.0)
        conf_b  = det_b.get("confidence", 0.0)
        mod_a   = det_a.get("render_type", "unknown")
        mod_b   = det_b.get("render_type", "unknown")

        domain      = (image_meta or {}).get("domain", "unknown")
        primary_obj = (image_meta or {}).get("primary_object", "unknown")

        prompt = f"""[Detector Selection Debate] 두 탐지기 결과를 비교하여 이 이미지에 더 적합한 탐지기 1개를 선택하라.

이미지 정보:
- 도메인: {domain}
- 주요 객체: {primary_obj}

탐지기 A: {name_a}
- 이상 점수: {score_a:.4f}
- 자체 신뢰도: {conf_a:.2f}
- 출력 방식: {mod_a}

탐지기 B: {name_b}
- 이상 점수: {score_b:.4f}
- 자체 신뢰도: {conf_b:.2f}
- 출력 방식: {mod_b}

선택 기준:
1. 이미지 도메인에 더 적합한 탐지기를 선택하라.
2. 신뢰도(confidence)가 높은 탐지기를 우선하라.
3. 두 탐지기가 비슷한 수준이면 도메인 전문성으로 판단하라.

[중요 제약]
- "합격(pass)" 또는 "불합격(fail)" 판정을 내리지 마라. 오직 모델 선택만 수행하라.
- 반드시 아래 JSON 형식만 출력하라. 다른 텍스트나 think 태그 없이.

{{
  "adopted_detector": "{name_a}" 또는 "{name_b}",
  "reason": "선택 근거 (1~2문장, 한국어)",
  "confidence": 0.0~1.0 사이 숫자 (이 선택에 대한 확신도)
}}"""

        try:
            print(f"  [DebateDetectors] {name_a} vs {name_b} 모델 선택 토론 시작")
            raw = _call_ollama("deepseek-r1:8b", prompt, temperature=0.1)

            # <think> 태그 제거
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()

            result = self._parse_json_from_llm(raw)

            adopted = result.get("adopted_detector", name_a)
            reason  = result.get("reason", "기본값: 탐지기A 채택")
            conf    = float(result.get("confidence", 0.5))

            print(f"  [DebateDetectors] 채택 결정: {adopted} (확신도={conf:.2f})")
            print(f"  [DebateDetectors] 근거: {reason}")

            return {
                "adopted_detector": adopted,
                "reason"          : reason,
                "confidence"      : conf,
                "det_a_name"      : name_a,
                "det_b_name"      : name_b,
            }
        except Exception as e:
            print(f"  [DebateDetectors] 토론 실패: {e} — 기본값(탐지기A) 채택")
            return {
                "adopted_detector": name_a,
                "reason"          : f"토론 실패 폴백: {e}",
                "confidence"      : 0.3,
                "det_a_name"      : name_a,
                "det_b_name"      : name_b,
            }

    def _run_sequential(self, agent_names: list, user_input: str,
                        image_path: str = None,
                        chat_history: list = None,
                        status_cb: callable = None) -> dict:
        """순차 실행: 이전 에이전트 결과가 다음 입력에 컨텍스트로 전달."""

        results = {}
        for name in agent_names:
            if name == "chat":
                # chat은 에이전트 없이 직접 LLM 응답
                results["chat"] = self._chat_response(
                    user_input, chat_history, results)
                continue

            agent = self._agents.get(name)
            if agent is None:
                results[name] = {
                    "agent": name, "status": "error",
                    "summary": f"에이전트 '{name}'이 로드되지 않음",
                }
                continue

            print(f"  → [{name}] 실행 중...")
            result = agent.safe_run(user_input, image_path, context=results, status_cb=status_cb)
            results[name] = result
            print(f"  ← [{name}] {result.get('status', '?')} "
                  f"({result.get('elapsed', 0)}s)")

            # ── §3 LED: vision 완료 후 scout/debate/detector 이벤트 emit ─────
            # [다운스트림 불변] 결과 dict 필드는 읽기만 하고 수정하지 않는다.
            if name == "vision" and status_cb and result.get("status") not in ("error",):
                det_name    = result.get("detector_name", "")
                ranking     = result.get("detector_ranking", [])   # [(name, score), ...]
                debate_log  = result.get("debate_log")             # None or dict (§2 Debate Path)

                # scout: VLM 전처리 단계 (vision agent의 도메인 분류 완료)
                if det_name:
                    scene = result.get("vlm_scene", "")[:60]
                    ranking_str = " | ".join(f"{n}={s:.2f}" for n, s in ranking[:3])
                    status_cb("scout", "ok",
                              detail=f"도메인 분류 완료 ({scene}) | 순위: {ranking_str}")

                # detector: 채택된 탐지기
                if det_name:
                    score = result.get("anomaly_score", 0.0)
                    threshold = result.get("threshold", 0.0)
                    verdict = result.get("verdict", "n/a")
                    status_cb("detector", "ok",
                              detail=f"{det_name} | score={score:.3f} / thr={threshold:.3f} | {verdict}")

                # debate: Debate Path였을 때만 emit
                if debate_log and isinstance(debate_log, dict):
                    adopted = debate_log.get("adopted_detector", det_name)
                    reason  = debate_log.get("reason", "")[:60]
                    conf    = debate_log.get("confidence", 0.0)
                    status_cb("debate", "ok",
                              detail=f"채택: {adopted} (conf={conf:.2f}) — {reason}")

        return results

    def _run_parallel(self, agent_names: list, user_input: str,
                      image_path: str = None) -> dict:
        """병렬 실행: 최대 2개 동시 (Ollama 부하 제한)."""
        results = {}

        # chat은 분리
        non_chat = [n for n in agent_names if n != "chat"]
        has_chat = "chat" in agent_names

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            for name in non_chat:
                agent = self._agents.get(name)
                if agent:
                    f = executor.submit(agent.safe_run, user_input, image_path)
                    futures[f] = name

            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=120)
                except Exception as e:
                    results[name] = {
                        "agent": name, "status": "error",
                        "summary": f"타임아웃/오류: {e}",
                    }

        if has_chat:
            results["chat"] = self._chat_response(
                user_input, None, results)

        return results

    def _chat_response(self, user_input: str,
                       chat_history: list = None,
                       context: dict = None) -> dict:
        """일반 대화 — qwen2.5:14b 직접 응답. 필요 시 웹 검색."""
        ctx_str = ""
        if context:
            summaries = [f"[{k}] {v.get('summary', '')}"
                        for k, v in context.items()
                        if isinstance(v, dict) and v.get('summary')]
            if summaries:
                ctx_str = "\n\n다른 에이전트의 결과:\n" + "\n".join(summaries)

        history_str = ""
        try:
            from aria.core.database import SessionLocal, AgentMemory
            from aria.mcp.mcp_client import get_current_session_id
            db = SessionLocal()
            memories = db.query(AgentMemory).filter(AgentMemory.session_id == get_current_session_id()).order_by(AgentMemory.timestamp.desc()).limit(50).all()
            memories = list(reversed(memories))
            if memories:
                history_str = "\n최근 대화 이력 (DB 기반):\n" + "\n".join(
                    [f"{'사용자' if m.role == 'user' else 'ARIA' if m.role == 'agent' else '도구'}: {m.content[:1500]}"
                     for m in memories]
                )
            db.close()
        except Exception as e:
            print(f"[Orchestrator DB] AgentMemory 로드 실패: {e}")
            history_str = ""

        from datetime import datetime
        now = datetime.now()
        time_str = now.strftime("%Y년 %m월 %d일 %H시 %M분")
        day_of_week = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

        # ── 웹 검색, 유튜브 또는 날씨 정보가 필요한 질문인지 판단 ──
        web_result = ""
        weather_keywords = ["날씨", "기온", "비", "눈", "미세먼지"]
        youtube_keywords = ["유튜브", "동영상", "영상", "youtube"]
        search_keywords = [
            "뉴스", "속보", "최신", "오늘 소식",           # 뉴스
            "환율", "주가", "코스피", "비트코인", "가격",   # 금융
            "맛집", "추천", "리뷰",                        # 추천
            "검색해", "찾아봐", "알아봐",                   # 명시적 검색 요청
            "방문", "언제", "일정", "계획", "방한", "날짜", # 방한/인물 일정 관련
        ]
        
        # 쿼리에 주어가 생략된 경우, 최근 대화 맥락에서 명사(예: 인물명)를 보완해 쿼리 생성
        search_query = user_input
        if chat_history and len(chat_history) >= 2:
            prev_user_q = chat_history[-2].get("content", "") if isinstance(chat_history[-2], dict) else ""
            if prev_user_q:
                # 최근 이전 대화에서 명사 키워드를 임시 추출하여 보완 (예: 젠슨황)
                for noun in ["젠슨황", "젠슨 황", "황", "젠슨", "엔비디아", "NVIDIA", "AI", "올라마", "Ollama"]:
                    if noun in prev_user_q and noun not in user_input:
                        search_query = f"{noun} {user_input}"
                        print(f"[Orchestrator Context Optimizer] Query expanded: {search_query}")
                        break

        if any(kw in user_input for kw in weather_keywords):
            location = "Seoul"
            for loc in ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주", "경기", "강원"]:
                if loc in user_input:
                    location = loc
                    break
            if self.mcp_hub:
                try:
                    res = self.mcp_hub.call_tool("get_weather", {"location": location})
                    if isinstance(res, dict) and res.get("success"):
                        web_result = res.get("summary", "")
                except Exception as e:
                    print(f"[Orchestrator Weather] MCP 호출 실패: {e}")
            if not web_result:
                web_result = f"날씨 API 호출 실패로 정보를 가져오지 못했습니다. 지역: {location}"
        elif any(kw in user_input for kw in youtube_keywords):
            if self.mcp_hub:
                try:
                    print(f"[Orchestrator YouTube] 유튜브 도구 기동: {search_query}")
                    res = self.mcp_hub.call_tool("search_youtube", {"query": search_query})
                    if isinstance(res, dict) and "error" not in res:
                        # 리스크 객체인 경우 텍스트 변환
                        web_result = json.dumps(res, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[Orchestrator YouTube] MCP 호출 실패: {e}")
            if not web_result:
                # 유튜브 API 실패 시 일반 웹 검색으로 요약 대체
                web_result = self._web_search(search_query)
        elif any(kw in user_input for kw in search_keywords):
            if self.mcp_hub:
                try:
                    res = self.mcp_hub.call_tool("search_web", {"query": search_query})
                    if isinstance(res, dict) and res.get("success"):
                        web_result = res.get("results", "")
                except Exception as e:
                    print(f"[Orchestrator Search] MCP 호출 실패: {e}")
            if not web_result:
                web_result = self._web_search(search_query)

        web_context = ""
        if web_result:
            web_context = f"\n\n🌐 웹 검색 결과:\n{web_result[:800]}"

        kb_ctx = ""
        import os
        kb_path = "outputs/argus_knowledge_base.md"
        if os.path.exists(kb_path):
            try:
                with open(kb_path, "r", encoding="utf-8") as f:
                    kb_ctx = f"\n\n### [ARGUS Knowledge Base - 성찰 지식]\n{f.read()}\n"
            except Exception as e:
                print(f"[KB Load Error] {e}")

        # GUI 의도 감지
        gui_keywords = ["크롬", "브라우저", "클릭", "마우스", "캡처", "화면", "바탕화면", "물리적"]
        is_gui_intent = any(kw in user_input for kw in gui_keywords)
        forced_instruction = ""
        if is_gui_intent:
            forced_instruction = "\n\n[❗ 강제 지침] 현재 너에게는 외부 검색 API(arxiv 등)가 제공되지 않는다. 목적을 달성하려면 반드시 computer_use 도구를 사용하여 브라우저 화면을 물리적으로 조작하고 캡처해야 한다."

        tools_desc = ""
        if self.mcp_hub:
            tools_desc = self.mcp_hub.get_tools_description_for_llm()
        else:
            tools_desc = "연결된 MCP 도구 없음"

        prompt = f"""[TOOL SELECTION RULES]
Rule 1: 사용자가 '클릭', '브라우저 열기', '캡처', '마우스 이동', '화면을 봐' 등 GUI 조작이나 물리적 제어를 명시적으로 요구한 경우, 절대 우회(Bypass)하지 말고 반드시 computer_use MCP 도구를 사용해야 한다.
Rule 2: 정보 검색 시, 사용자가 '화면 캡처'나 '웹페이지 띄우기'를 지시했다면 arxiv나 youtube 같은 텍스트 API 도구의 사용을 엄격히 금지한다. 무조건 computer_use를 통해 브라우저를 물리적으로 조작하여 시각적(Visual) 결과를 도출하라.{forced_instruction}

당신은 단순한 구글 봇이 아닙니다. 연결된 모든 MCP 도구(터미널, 파일시스템, 허깅페이스 AI모델 검색 등)를 자율적으로 활용해 시스템을 제어하고 코드를 직접 수정하는 최고 권한의 ARGUS 관제 마스터 AI이자, 'ARIA' 에이전트의 대화 처리 시스템인 실력 있는 '시니어 엔지니어(Senior Engineer)'입니다.

[사용 가능한 모든 MCP 도구 목록]
{tools_desc}

[⚠️ 핵심 답변 규칙]
1. [기계적 템플릿 사용 금지]: '[SYSTEM_RESPONSE]', '- Action/Answer:', '- Status:' 같은 인위적이고 기계적인 포맷을 절대 사용하지 마라. 자연스럽게 읽히는 일반 마크다운(Markdown) 포맷으로 답변하라.
2. [No-BS (군더더기 없는 직접 답변)]: "마스터 개발자님", "안녕하세요", "도와드리겠습니다", "서버 시간 기준" 같은 무의미한 인사말이나 윤색 멘트(Filler Words)를 절대 사용하지 마라. 질문을 받으면 첫 문장부터 곧바로 핵심 본론과 결론을 말하라.
3. [실질적 액션 아이템 포함]: "공식 문서를 참조하라"는 식의 무책임한 회피성 답변을 금지한다. 질문과 관련된 파이썬 코드 스니펫(huggingface_hub, transformers 등 활용)이나 CLI 명령어(kaggle datasets download 등)를 반드시 마크다운 코드 블록(```)으로 작성하여 구체적이고 즉시 실행 가능한 형태로 제공하라.

현재 시간: {time_str} ({day_of_week}요일)
기본 위치: 대한민국
{history_str}{ctx_str}{kb_ctx}{web_context}

사용자 요청: "{user_input}"
"""

        try:
            response = _call_ollama_with_korean_guard("qwen2.5:14b", prompt, temperature=0.7)
            
            # SYSTEM_RESPONSE 포맷 랩핑 제거 (시니어 모드 마크다운 그대로 반환)
                
            return {
                "agent": "chat",
                "status": "success",
                "summary": response,
            }
        except Exception as e:
            return {
                "agent": "chat",
                "status": "error",
                "summary": f"대화 실패: {e}",
            }

    def _web_search(self, query: str) -> str:
        """웹 검색 — Wikipedia API 및 Google News RSS 우선 사용, DuckDuckGo Lite는 최종 폴백."""
        import urllib.request
        import urllib.parse
        import urllib.error
        import json
        import re
        import html as html_module
        import xml.etree.ElementTree as ET

        # 날씨 질문이면 위치 보충
        weather_kws = ["날씨", "기온", "비", "눈", "미세먼지"]
        if any(kw in query for kw in weather_kws):
            if not any(loc in query for loc in [
                "서울", "부산", "대구", "인천", "광주", "대전",
                "울산", "세종", "제주", "경기", "강원",
            ]):
                query = f"대한민국 {query}"

        # 1. 뉴스 쿼리 여부 판단
        news_kws = ["뉴스", "소식", "보도", "기사", "최근", "동향", "트렌드", "news", "trend"]
        is_news_query = any(kw in query.lower() for kw in news_kws)

        search_results = []

        # 2-A. 뉴스 쿼리인 경우 Google News RSS 우선 실행
        if is_news_query:
            try:
                print(f"[WebSearch] 뉴스 키워드 감지. Google News RSS 우선 실행: '{query}'")
                q = urllib.parse.quote(query)
                url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    xml_data = r.read()
                root = ET.fromstring(xml_data)
                items = root.findall(".//item")[:5]
                news_list = []
                for it in items:
                    title = it.find("title").text if it.find("title") is not None else ""
                    link = it.find("link").text if it.find("link") is not None else ""
                    news_list.append(f"📰 {title}\n   {link}")
                if news_list:
                    print(f"[WebSearch] Google News RSS 검색 성공 ({len(news_list)}개 결과)")
                    search_results.append("\n".join(news_list))
            except Exception as e:
                print(f"[WebSearch] Google News RSS 검색 실패: {e}")

        # 2-B. 일반 쿼리이거나 RSS 결과가 없는 경우 Wikipedia API 실행
        if not search_results:
            try:
                print(f"[WebSearch] Wikipedia API 검색 실행: '{query}'")
                q = urllib.parse.quote(query)
                url = f"https://ko.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=5"
                req = urllib.request.Request(url, headers={"User-Agent": "Ralph-Agent/1.0 (research@cau.ac.kr)"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8", errors="ignore"))
                results = data.get("query", {}).get("search", [])
                wiki_list = []
                for x in results:
                    title = x.get("title", "")
                    snippet = re.sub(r"<[^>]+>", "", x.get("snippet", ""))
                    snippet = html_module.unescape(snippet)
                    wiki_list.append(f"📚 {title}: {snippet}")
                if wiki_list:
                    print(f"[WebSearch] Wikipedia API 검색 성공 ({len(wiki_list)}개 결과)")
                    search_results.append("\n".join(wiki_list))
            except Exception as e:
                print(f"[WebSearch] Wikipedia API 검색 실패: {e}")

        # 만약 Wikipedia/News 결과가 있는 경우 반환
        if search_results:
            return "\n\n".join(search_results)

        # 3. DuckDuckGo Lite 최종 폴백
        try:
            search_query = urllib.parse.quote(f"{query} {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}")
            url = f"https://lite.duckduckgo.com/lite/?q={search_query}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            print(f"[WebSearch Debug] DuckDuckGo Lite fallback: {url}")
            
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status if hasattr(resp, "status") else 200
                    html = resp.read().decode("utf-8", errors="ignore")
            except urllib.error.HTTPError as http_err:
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                if "anomaly-modal" in err_body or "captcha" in err_body.lower() or http_err.code in (403, 429):
                    return "이 환경에서는 외부 인터넷이 차단되었거나 로봇 방지(CAPTCHA/Rate Limit) 정책에 의해 웹 검색 결과를 가져올 수 없습니다. 대신 Wikipedia나 Google News RSS를 통한 우회 검색 결과도 검색어가 매칭되지 않아 반환되지 못했습니다."
                raise http_err

            if "anomaly-modal" in html or "captcha" in html.lower():
                return "이 환경에서는 외부 인터넷이 차단되었거나 로봇 방지(CAPTCHA/Rate Limit) 정책에 의해 웹 검색 결과를 가져올 수 없습니다. 대신 Wikipedia나 Google News RSS를 통한 우회 검색 결과도 검색어가 매칭되지 않아 반환되지 못했습니다."

            # HTML에서 텍스트 추출 (간단한 방식)
            html = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
            html = re.sub(r"<style.*?</style>", "", html, flags=re.DOTALL)
            html = re.sub(r"<[^>]+>", " ", html)
            html = re.sub(r"\s+", " ", html).strip()

            # 상위 결과 추출
            lines = [l.strip() for l in html.split("  ") if len(l.strip()) > 20]
            if not lines:
                return "검색 결과가 비어 있습니다."
            return "\n".join(lines[:10])
        except Exception as e:
            return "이 환경에서는 외부 인터넷이 차단되었거나 로봇 방지(CAPTCHA/Rate Limit) 정책에 의해 웹 검색 결과를 가져올 수 없습니다. (우회 API 검색 결과 없음)"

    # ──────────────────────────────────────────────────────────────────────
    # 결과 취합
    # ──────────────────────────────────────────────────────────────────────
    def _synthesize(self, results: dict, user_input: str) -> dict:
        """에이전트 결과를 하나의 응답으로 취합."""

        # 단일 에이전트 + chat이면 그대로 반환
        if len(results) == 1:
            only = list(results.values())[0]
            return {
                "response": only.get("summary", ""),
                "image_path": only.get("result_image_path")
                              or only.get("image_path"),
                "agents_used": list(results.keys()),
                "results": results,
            }

        # 여러 에이전트 → qwen2.5:14b가 통합 요약
        summaries = []
        image_path = None
        for name, result in results.items():
            if isinstance(result, dict):
                summaries.append(
                    f"[{name} 에이전트]\n{result.get('summary', '결과 없음')}")
                if not image_path:
                    image_path = (result.get("result_image_path")
                                  or result.get("image_path"))

        all_summaries = "\n\n".join(summaries)

        # 일정(schedule)과 소통(communication) 결과가 모두 존재하는지 확인
        is_briefing = "schedule" in results and "communication" in results

        try:
            if is_briefing:
                prompt = f"""너는 'ARIA' 에이전트의 종합 답변 취합 시스템이야.
아래 에이전트 분석 결과(일정 및 소통 메일 정보)를 참고하여 사용자의 질문에 한국어로 종합 답변을 작성해줘.

[중요 조건]
- 반드시 "오늘의 업무 브리핑입니다."라는 문장으로 답변을 시작해야 한다.
- 마크다운 문서를 활용하여 가독성이 높고 자연스럽게 작성하라.

[Language Limit: 어떠한 경우에도 반드시 '한국어(Korean)'로만 답변하라. 일본어나 다른 언어의 출력을 엄격히 금지한다.]

[예약 기능 환각 방지: 사용자가 매일 오전 9시 알람 등 특정 시간에 자동으로 작동하는 '예약(Schedule)' 기능을 요구할 경우, 구글 캘린더에 일정을 등록하는 것은 가능하지만, 너 스스로 특정 시간에 스스로 깨어나서 메시지를 보내는 'Cron 데몬' 기능은 아직 완벽하지 않다고 정직하게 안내하라. (거짓으로 "네, 해드리겠습니다"라고 약속하는 환각 금지)]

[YouTube 기능 한계 고지: 유튜브 관련 요청 중 개인의 '구독 채널 목록'이나 '시청 기록'을 읽는 것은 현재 권한상 불가능하다. 사용자가 구독 목록이나 개인화 정보를 요구하면, '현재 제게는 영상 검색 기능만 부여되어 있으며, 개인 구독 목록 조회 권한은 없습니다'라고 명확하고 정중하게 한국어로 답변하라. 절대로 가짜 구독 정보를 만들어내거나 예시를 들며 회피하지 마라.]

사용자 요청: "{user_input}"

{all_summaries}

취합 응답:"""
            else:
                prompt = f"""너는 'ARIA' 에이전트의 종합 답변 취합 시스템이야.
아래 에이전트 분석 결과들을 참고하여 사용자의 질문에 한국어로 종합 답변을 작성해줘.

[Language Limit: 어떠한 경우에도 반드시 '한국어(Korean)'로만 답변하라. 일본어나 다른 언어의 출력을 엄격히 금지한다.]

[예약 기능 환각 방지: 사용자가 매일 오전 9시 알람 등 특정 시간에 자동으로 작동하는 '예약(Schedule)' 기능을 요구할 경우, 구글 캘린더에 일정을 등록하는 것은 가능하지만, 너 스스로 특정 시간에 스스로 깨어나서 메시지를 보내는 'Cron 데몬' 기능은 아직 완벽하지 않다고 정직하게 안내하라. (거짓으로 "네, 해드리겠습니다"라고 약속하는 환각 금지)]

[YouTube 기능 한계 고지: 유튜브 관련 요청 중 개인의 '구독 채널 목록'이나 '시청 기록'을 읽는 것은 현재 권한상 불가능하다. 사용자가 구독 목록이나 개인화 정보를 요구하면, '현재 제게는 영상 검색 기능만 부여되어 있으며, 개인 구독 목록 조회 권한은 없습니다'라고 명확하고 정중하게 한국어로 답변하라. 절대로 가짜 구독 정보를 만들어내거나 예시를 들며 회피하지 마라.]

사용자 요청: "{user_input}"

{all_summaries}

취합 응답:"""

            response = _call_ollama("qwen2.5:14b", prompt, temperature=0.3)
        except Exception:
            # LLM 실패 시 단순 합치기
            response = "\n\n".join(
                [f"**{k}**: {v.get('summary', '')}"
                 for k, v in results.items()
                 if isinstance(v, dict)])

        return {
            "response": response[:1500],
            "image_path": image_path,
            "agents_used": list(results.keys()),
            "results": results,
        }
