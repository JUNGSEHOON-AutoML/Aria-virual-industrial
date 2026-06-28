"""
mcp_client.py — MCP 클라이언트 허브

역할:
  mcp_config.json을 읽어 MCP 서버들을 subprocess로 실행하고,
  ralph_loop.py에서 호출할 수 있는 단일 인터페이스를 제공한다.

  MCP 프로토콜: JSON-RPC 2.0 over stdio (Anthropic MCP spec)

사용법:
  from aria.mcp.mcp_client import MCPClient

  client = MCPClient("mcp_config.json")
  client.start_servers()

  # 도구 목록 조회
  tools = client.list_all_tools()

  # 도구 호출 (올바른 사용법: "server.tool", args)
  result = client.call_tool("computer_use.take_screenshot", {})
  result = client.call_tool("computer_use.find_on_screen", {"click_target": "검색창"})
  #
  # ⚠️ 잘못된 사용법 (절대 안 됨):
  #   client.call_tool("computer_use", "take_screenshot", {})  ← TypeError: unhashable type: 'dict'
  # 시그니처: call_tool(tool_name: str, arguments: dict = None, server_name: str = None)
  # 2번째 인자가 문자열이면 차단됨, 점(점) 표기법("server.tool") 가 권장됨
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────
# Human-in-the-Loop (HITL) Thread-Local & Global Registry
# ──────────────────────────────────────────────
class ChannelContext(threading.local):
    def __init__(self):
        self.channel_type = None  # "websocket", "http", or None
        self.websocket = None
        self.chat_id = None
        self.loop = None
        self.role = "admin"       # 기본 권한은 admin (웹/클라이언트는 무조건 admin)
        self.current_node = None  # 현재 실행 중인 에이전트 노드명 (PHYSICAL, OPERATOR 등)

current_channel = ChannelContext()
pending_approvals = {}
pending_approvals_lock = threading.Lock()

def get_current_session_id() -> str:
    return "default"

def send_security_warning(warning_msg: str):
    # 특정 호출 WebSocket으로 전송
    try:
        if current_channel.websocket and current_channel.loop:
            import asyncio
            msg_payload = {"type": "thought", "content": warning_msg}
            asyncio.run_coroutine_threadsafe(
                current_channel.websocket.send_json(msg_payload),
                current_channel.loop
            )
    except Exception as e:
        print(f"[HITL Specific WS Warning] 실패: {e}")

    # 3. 전체 웹소켓으로 브로드캐스트
    try:
        import sys
        if "app" in sys.modules:
            import app
            import asyncio
            if hasattr(app, "manager") and app.manager:
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
                
                msg_payload = {"type": "thought", "content": warning_msg}
                if loop:
                    asyncio.run_coroutine_threadsafe(app.manager.broadcast(msg_payload), loop)
                else:
                    new_loop = asyncio.new_event_loop()
                    new_loop.run_until_complete(app.manager.broadcast(msg_payload))
                    new_loop.close()
    except Exception as e:
        print(f"[HITL WebSocket Warning] 실패: {e}")


class MCPServerProcess:
    """단일 MCP 서버 프로세스를 관리한다."""

    def __init__(self, name: str, config: Dict):
        self.name = name
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self.response_queues: Dict[int, queue.Queue] = {}
        self.oauth_url: Optional[str] = None
        self.is_oauth_pending = False

    def start(self) -> bool:
        """서버 프로세스를 시작한다."""
        cmd_executable = self.config["command"]
        if cmd_executable == "python":
            cmd_executable = sys.executable
        else:
            resolved_path = shutil.which(cmd_executable)
            if resolved_path:
                cmd_executable = resolved_path
            else:
                print(f"[MCP:{self.name}] 경고: '{cmd_executable}' 명령어를 시스템 PATH에서 찾을 수 없습니다.")
        cmd = [cmd_executable] + self.config.get("args", [])
        env = {**os.environ, **self.config.get("env", {})}

        # 환경변수에서 ${VAR} 패턴을 실제 값으로 치환
        resolved_env = {}
        for k, v in env.items():
            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                var_name = v[2:-1]
                resolved_env[k] = os.environ.get(var_name, "")
            else:
                resolved_env[k] = v

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=resolved_env,
                text=True,
                bufsize=1,
            )

            # 비동기 리더 스레드 기동
            threading.Thread(target=self._read_stdout, daemon=True).start()
            threading.Thread(target=self._read_stderr, daemon=True).start()

            print(f"[MCP:{self.name}] Initialize 핸드셰이크 전송 중... (OAuth 대기 가능)")
            # OAuth 로그인 과정을 감안해 초기 타임아웃을 300초로 설정
            init_res = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ralph-loop", "version": "1.0.0"},
            }, timeout=300.0)

            if init_res:
                self._send_notification("notifications/initialized", {})
                self.oauth_url = None
                self.is_oauth_pending = False
                print(f"[MCP:{self.name}] Initialize 성공")
                return True
            else:
                print(f"[MCP:{self.name}] Initialize 실패 (응답 없음/타임아웃)")
                return False

        except FileNotFoundError as e:
            print(f"[MCP:{self.name}] 서버 시작 실패: {e}")
            return False
        except Exception as e:
            print(f"[MCP:{self.name}] 오류: {e}")
            return False

    def stop(self):
        """서버 프로세스를 종료한다."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.response_queues.clear()
        self.oauth_url = None
        self.is_oauth_pending = False

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _read_stdout(self):
        url_pattern = re.compile(r'https?://[^\s]+')
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                line_str = line.strip()
                # print(f"[MCP:{self.name}:STDOUT] {line_str}") # 디버깅용

                # OAuth URL 감지
                if "accounts.google.com" in line_str or "authorize" in line_str or "Please visit this URL" in line_str:
                    match = url_pattern.search(line_str)
                    if match:
                        self.oauth_url = match.group(0)
                        self.is_oauth_pending = True
                        print(f"\n[⚠️ MCP OAUTH REQUIRED] {self.name} 서버가 구글 인증을 요청합니다.")
                        print(f"인증 URL: {self.oauth_url}\n")

                # JSON-RPC 응답 파싱
                if line_str.startswith("{") and line_str.endswith("}"):
                    try:
                        data = json.loads(line_str)
                        if "id" in data:
                            req_id = data["id"]
                            with self._lock:
                                q = self.response_queues.get(req_id)
                            if q:
                                q.put(data)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[MCP:{self.name}:STDOUT_ERR] {e}")
                break

    def _read_stderr(self):
        url_pattern = re.compile(r'https?://[^\s]+')
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stderr.readline()
                if not line:
                    break
                line_str = line.strip()
                # print(f"[MCP:{self.name}:STDERR] {line_str}") # 디버깅용

                # OAuth URL 감지 (stderr에 인쇄될 수도 있음)
                if "accounts.google.com" in line_str or "authorize" in line_str or "Please visit this URL" in line_str:
                    match = url_pattern.search(line_str)
                    if match:
                        self.oauth_url = match.group(0)
                        self.is_oauth_pending = True
                        print(f"\n[⚠️ MCP OAUTH REQUIRED - STDERR] {self.name} 서버가 구글 인증을 요청합니다.")
                        print(f"인증 URL: {self.oauth_url}\n")
            except Exception:
                break

    def _send_request(self, method: str, params: Dict = None, timeout: float = 60.0) -> Optional[Dict]:
        """JSON-RPC 2.0 요청을 전송하고 응답을 반환한다."""
        if not self.process or self.process.poll() is not None:
            return None

        req_id = self._next_id()
        q = queue.Queue()
        with self._lock:
            self.response_queues[req_id] = q

        request = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            request["params"] = params

        try:
            line = json.dumps(request, ensure_ascii=False) + "\n"
            self.process.stdin.write(line)
            self.process.stdin.flush()

            # 응답 대기
            try:
                response = q.get(timeout=timeout)
                return response
            except queue.Empty:
                print(f"[MCP:{self.name}] 요청 타임아웃 (id={req_id}, method={method})")
                return None
        except Exception as e:
            print(f"[MCP:{self.name}] 통신 오류: {e}")
        finally:
            with self._lock:
                if req_id in self.response_queues:
                    del self.response_queues[req_id]

        return None

    def _send_notification(self, method: str, params: Dict = None):
        """응답이 없는 알림을 전송한다."""
        if not self.process or self.process.poll() is not None:
            return
        notification = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            notification["params"] = params
        try:
            self.process.stdin.write(json.dumps(notification) + "\n")
            self.process.stdin.flush()
        except Exception:
            pass

    def list_tools(self) -> List[Dict]:
        """이 서버가 제공하는 도구 목록을 반환한다."""
        response = self._send_request("tools/list", {})
        if response and "result" in response:
            return response["result"].get("tools", [])
        return []

    def call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """지정된 도구를 호출하고 결과를 반환한다."""
        timeout = 300.0 if self.name in ("shell_exec", "computer_use") else 60.0
        response = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        }, timeout=timeout)
        if not response:
            return {"error": f"MCP 서버 '{self.name}' 응답 없음 (타임아웃)"}

        if "error" in response:
            return {"error": response["error"].get("message", "알 수 없는 오류")}

        result = response.get("result", {})
        # content 배열에서 첫 번째 text를 파싱
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except json.JSONDecodeError:
                return {"text": content[0]["text"]}

        return result


class MCPClient:
    """여러 MCP 서버를 통합 관리하는 클라이언트 허브."""

    def __init__(self, config_path: str = "mcp_config.json"):
        self.config_path = Path(config_path)
        self.servers: Dict[str, MCPServerProcess] = {}
        self.tool_registry: Dict[str, str] = {}  # tool_name → server_name
        self._config = {}

    def load_config(self) -> bool:
        """mcp_config.json을 로드한다."""
        if not self.config_path.exists():
            print(f"[MCP] 설정 파일 없음: {self.config_path}")
            return False
        try:
            with open(self.config_path, encoding="utf-8") as f:
                self._config = json.load(f)
            return True
        except Exception as e:
            print(f"[MCP] 설정 로드 오류: {e}")
            return False

    def start_servers(self, server_names: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        설정된 MCP 서버들을 시작한다.

        Args:
            server_names: 시작할 서버 목록. None이면 모든 서버 시작.

        Returns:
            {server_name: 성공 여부} 딕셔너리
        """
        if not self.load_config():
            return {}

        mcp_servers_config = self._config.get("mcpServers", {})
        results = {}

        for name, config in mcp_servers_config.items():
            if server_names and name not in server_names:
                continue

            # 환경변수 값 체크 가드레일 (플레이스홀더 필터링)
            skip_server = False
            for env_key, env_val in config.get("env", {}).items():
                if isinstance(env_val, str) and env_val.startswith("${") and env_val.endswith("}"):
                    var_name = env_val[2:-1]
                    real_val = os.environ.get(var_name, "").strip()
                    # HUGGINGFACE_TOKEN은 비어있어도 skip하지 않음 (public API 허용)
                    if var_name == "HUGGINGFACE_TOKEN":
                        continue
                    if not real_val or "여기에_" in real_val or "ENTER_" in real_val.upper() or "INSERT_" in real_val.upper():
                        print(f"[MCP] '{name}' 패스: 필수 환경변수 '{var_name}'가 기본값 상태이거나 비어있습니다. 이 서버 기동을 보류합니다.")
                        skip_server = True
                        break
            
            if skip_server:
                results[name] = False
                continue

            print(f"[MCP] '{name}' 서버 시작 중...")
            server = MCPServerProcess(name, config)
            success = server.start()
            results[name] = success

            if success:
                self.servers[name] = server
                # 도구 등록
                tools = server.list_tools()
                for tool in tools:
                    tool_full_name = f"{name}.{tool['name']}"
                    self.tool_registry[tool_full_name] = name
                    self.tool_registry[tool["name"]] = name  # 서버 이름 없이도 검색 가능
                print(f"[MCP] '{name}' 시작 완료 ({len(tools)}개 도구)")
            else:
                print(f"[MCP] '{name}' 시작 실패 — 스킵")

        return results

    def stop_servers(self):
        """모든 MCP 서버를 종료한다."""
        for name, server in self.servers.items():
            print(f"[MCP] '{name}' 서버 종료")
            server.stop()
        self.servers.clear()
        self.tool_registry.clear()

    def list_all_tools(self) -> List[Dict]:
        """모든 서버의 도구 목록을 통합하여 반환한다."""
        all_tools = []
        for server_name, server in self.servers.items():
            tools = server.list_tools()
            for tool in tools:
                tool["server"] = server_name
                
                # Gmail 검색 도구 파라미터 설명 고도화 (학교명, 사람 이름 등 핵심 엔티티 추출 유도)
                if tool["name"] in ["gmail.search", "google-workspace.gmail.search"]:
                    input_schema = tool.get("inputSchema", {})
                    if "properties" not in input_schema:
                        input_schema["properties"] = {}
                    
                    enhanced_desc = (
                        "Gmail 검색 쿼리. 사용자가 요청한 핵심 엔티티(학교명, 사람 이름 등)를 "
                        "자연어에서 강제로 추출하여 매핑해야 함. "
                        "예: 사용자가 '중앙대 안 읽은 메일'을 찾으면 반드시 'from:중앙대 OR subject:중앙대 is:unread' 형태로 매핑할 것. "
                        "예: '홍길동 메일'은 'from:홍길동 OR subject:홍길동' 형태로 매핑할 것."
                    )
                    
                    input_schema["properties"]["query"] = {
                        "type": "string",
                        "description": enhanced_desc
                    }
                    input_schema["properties"]["q"] = {
                        "type": "string",
                        "description": enhanced_desc
                    }
                
                # YouTube 도구 설명 고도화 (구독 목록 조회 등의 개인화 기능 부재 고지)
                if "youtube" in tool["name"]:
                    tool["description"] = (
                        "이 도구는 유튜브에서 키워드로 '영상 검색(Search)'만 가능하며, "
                        "사용자의 개인 '구독 채널 목록'이나 '시청 기록'을 읽는 기능은 현재 권한상 불가능하다. "
                        "사용자가 구독 목록을 요구하면, '현재 제게는 영상 검색 기능만 부여되어 있으며, "
                        "개인 구독 목록 조회 권한은 없습니다'라고 명확하고 정중하게 한국어로 답변하라."
                    )
                
                all_tools.append(tool)
        return all_tools

    def call_tool(self, tool_name: str, arguments: Dict = None,
                  server_name: Optional[str] = None) -> Dict:
        """
        도구를 호출한다.

        Args:
            tool_name: 도구 이름 (예: "take_screenshot", "computer_use.take_screenshot")
            arguments: 도구 파라미터
            server_name: 서버 이름 (None이면 tool_registry에서 자동 검색)

        Returns:
            도구 실행 결과 딕셔너리
        """
        if arguments is None:
            arguments = {}

        # ── 호출 인자 타입 방어 (3인자 실수 패턴 탐지) ──
        # 잘못된 예: call_tool("server", "tool_name", {...})
        # → arguments에 문자열이 들어오는 경우 즉시 에러 반환
        if isinstance(arguments, str):
            return {
                "error": (
                    f"[call_tool 사용법 오류] arguments 자리에 문자열 '{arguments}'이 들어왔습니다. "
                    f"올바른 사용법: call_tool(\"server.{arguments}\", {{...}}) — "
                    f"점 표기(dot-notation)를 사용하세요."
                )
            }


        if tool_name in ["gmail.search", "google-workspace.gmail.search"]:
            if "q" in arguments and "query" not in arguments:
                arguments["query"] = arguments.pop("q")

        # "server.tool" 형식 파싱
        if "." in tool_name and server_name is None:
            parts = tool_name.split(".", 1)
            if parts[0] in self.servers:
                server_name, tool_name = parts[0], parts[1]

        # 서버 자동 검색
        if server_name is None:
            server_name = self.tool_registry.get(tool_name)
            if not server_name:
                return {"error": f"도구 '{tool_name}'을 찾을 수 없습니다. 사용 가능: {list(self.tool_registry.keys())}"}

        server = self.servers.get(server_name)
        if not server:
            return {"error": f"서버 '{server_name}'이 실행 중이 아닙니다"}

        # ── Guest Sandbox Block Gate (Hard Block) ──
        is_guest = (hasattr(current_channel, "role") and current_channel.role == "guest")
        if is_guest:
            BLOCKED_GUEST_SERVERS = ["computer_use", "shell_exec", "filesystem", "google-workspace"]
            is_blocked = False
            for blocked in BLOCKED_GUEST_SERVERS:
                if blocked in tool_name or (server_name and blocked in server_name):
                    is_blocked = True
                    break
            if is_blocked:
                return {"error": "⛔ [권한 오류] 해당 도구(터미널, 파일, 컴퓨터 제어 등)는 최고 관리자(세훈님)만 사용할 수 있습니다. 게스트는 일반 대화 및 arXiv 검색 등의 안전한 기능만 이용 가능합니다."}

        # ── Human-in-the-Loop (HITL) Intercept Gate ──
        DANGEROUS_TOOLS = ["shell_exec", "delete_file", "write_file", "computer_use"]
        is_dangerous = False
        for dangerous in DANGEROUS_TOOLS:
            if dangerous in tool_name or (server_name and dangerous in server_name):
                is_dangerous = True
                break

        current_node = getattr(current_channel, "current_node", None)
        is_autonomous = current_node in ("PHYSICAL", "OPERATOR")

        # 만약 자율 에이전트(OPERATOR, PHYSICAL) 노드에서 들어온 호출이라면
        # shell_exec 호출에 대해 bypass_policy=True를 강제 주입하여 서버가 차단 없이 즉시 실행하도록 유도
        if is_autonomous:
            if "shell_exec" in tool_name or (server_name and "shell_exec" in server_name):
                arguments["bypass_policy"] = True

        # 자율 에이전트가 아닌 일반적인 경우에만 Y/N 승인 프롬프트(HITL) 실행
        if is_dangerous and current_channel.channel_type and not is_autonomous:
            key = current_channel.channel_type

            # Create event and register in global pending approvals
            event = threading.Event()
            with pending_approvals_lock:
                pending_approvals[key] = {
                    "event": event,
                    "decision": None
                }

            # Format and send security warning
            warning_msg = f"⚠️ [보안 경고] 에이전트가 다음 명령을 실행하려 합니다: {tool_name} - {json.dumps(arguments, ensure_ascii=False)}. 승인하시겠습니까? (Y/N)"
            print(f"[HITL Warning] {warning_msg}")
            send_security_warning(warning_msg)

            # Block current worker thread waiting for user input
            event.wait()

            # Retrieve result and cleanup
            with pending_approvals_lock:
                decision_info = pending_approvals.pop(key, None)

            approved = decision_info["decision"] if decision_info else False
            if not approved:
                return {"error": "User denied permission for this action. You must find an alternative safe method or stop the task."}

        return server.call_tool(tool_name, arguments)

    def get_models_config(self) -> Dict[str, str]:
        """mcp_config.json의 models 섹션을 반환한다."""
        return self._config.get("models", {
            "text": "llama3.1",
            "vision": "qwen2.5vl:7b",
            "anomaly": "ccifps",
        })

    def get_tools_description_for_llm(self) -> str:
        """LLM 프롬프트에 삽입할 도구 설명 문자열을 생성한다."""
        tools = self.list_all_tools()
        if not tools:
            return "현재 MCP 도구 없음"

        lines = []
        for tool in tools:
            server = tool.get("server", "?")
            name = tool["name"]
            desc = tool.get("description", "")
            lines.append(f"  - [{server}] {name}: {desc}")

        return "\n".join(lines)

    def is_running(self) -> bool:
        """하나 이상의 서버가 실행 중인지 확인한다."""
        return len(self.servers) > 0

    def get_oauth_urls(self) -> Dict[str, str]:
        """실행 중인 서버 중 OAuth 인증이 필요한 서버의 URL을 반환한다."""
        urls = {}
        for name, server in self.servers.items():
            if server.oauth_url:
                urls[name] = server.oauth_url
        return urls


# ── 편의 함수 ──────────────────────────────────────────────────────────────────

def load_env(env_path: str = ".env"):
    """
    .env 파일을 읽어 환경변수로 설정한다.
    python-dotenv 없이도 동작하는 간단한 구현.
    """
    env_file = Path(env_path)
    if not env_file.exists():
        return

    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # 이미 설정된 환경변수는 덮어쓰지 않음
                if key not in os.environ:
                    os.environ[key] = value


# ── 테스트 ──────────────────────────────────────────────────────────────────────
_MCP_SINGLETON = None

def get_mcp_client():
    """프로세스 단일 MCPClient 반환 (레지스트리 상주 탐지기가 사용)."""
    global _MCP_SINGLETON
    if _MCP_SINGLETON is None:
        import os
        _MCP_SINGLETON = MCPClient(os.environ.get("MCP_CONFIG", "mcp_config.json"))
    return _MCP_SINGLETON

if __name__ == "__main__":
    print("=" * 55)
    print("  MCP Client 테스트")
    print("=" * 55)

    load_env()

    client = MCPClient("mcp_config.json")

    # computer_use 서버만 시작 (가장 안전)
    results = client.start_servers(server_names=["computer_use"])
    print(f"\n서버 시작 결과: {results}")

    if client.is_running():
        print("\n사용 가능한 도구:")
        for tool in client.list_all_tools():
            print(f"  [{tool['server']}] {tool['name']}: {tool.get('description','')[:60]}")

        print("\n화면 크기 조회:")
        result = client.call_tool("get_screen_size")
        print(f"  결과: {result}")

    client.stop_servers()
    print("\n테스트 완료")
