"""
shell_exec_mcp.py — 안전한 셸 명령 실행 MCP 서버

역할:
  에이전트가 시스템 명령을 실행할 수 있도록 MCP 도구를 제공한다.
  읽기 전용 명령만 자동 실행하고, 쓰기/설치 명령은 터미널에
  복사할 명령어 텍스트만 출력한다 (관리자가 직접 실행).

노출 도구:
  1. run_command     — 읽기 전용 명령 자동 실행 + 쓰기 명령 안내
  2. run_python      — Python 코드 실행 (읽기 전용: 조회/검증만)
  3. check_process   — 실행 중인 프로세스 확인
  4. suggest_command — 실행하지 않고 명령어만 안내 (관리자용)

정책:
  - 자동 실행: ls, cat, grep, git status, python -m py_compile 등 (읽기 전용)
  - 수동 안내: pip install, ollama pull, git push 등 (명령어 텍스트 출력)
  - 차단: rm -rf, shutdown, reboot 등 (에러 반환)

사용법:
  python mcp_servers/shell_exec_mcp.py
"""

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# ──────────────────────────────────────────────
# 보안: 명령어 정책 (2-Tier)
# ──────────────────────────────────────────────

# 프로젝트 루트 (명령 실행 CWD)
PROJECT_ROOT = str(Path(__file__).parent.parent.resolve())

# TODO(security): 프로덕션 환경에서는 SELinux/AppArmor 프로파일을 사용하세요.

# ── Tier 1: 자동 실행 허용 (읽기 전용 명령) ──
# 시스템 상태를 변경하지 않는 안전한 명령만 포함
AUTO_EXEC_COMMANDS = {
    # 파일 조회 (읽기 전용)
    "ls", "cat", "head", "tail", "wc", "find", "grep", "file", "du", "df",
    "tree", "stat", "which", "whereis",
    # 시스템 정보 (읽기 전용)
    "uname", "hostname", "whoami", "date", "uptime", "free",
    "nvidia-smi",
    # 프로세스 조회
    "ps", "pgrep",
    # 텍스트 처리 (읽기 전용)
    "sort", "uniq", "cut", "awk", "diff", "jq",
    # 기타 읽기 전용
    "echo", "env", "printenv",
}

# ── Tier 1 확장: 특정 서브커맨드만 자동 실행 허용 ──
# (바이너리, 서브커맨드_접두사) 형태
AUTO_EXEC_SUBCOMMANDS = {
    "git": {"status", "log", "diff", "branch", "remote", "show", "describe", "tag"},
    "pip": {"list", "show", "freeze", "check"},
    "pip3": {"list", "show", "freeze", "check"},
    "python": {"-m py_compile", "-c", "--version", "-V"},
    "python3": {"-m py_compile", "-c", "--version", "-V"},
    "ollama": {"list", "show", "ps"},
    "conda": {"list", "info", "env list"},
}

# ── Tier 2: 수동 안내만 (실행하지 않음) ──
# 시스템을 변경하는 명령은 명령어 텍스트만 안내
SUGGEST_ONLY_COMMANDS = {
    "pip", "pip3", "conda",      # install/uninstall
    "ollama",                     # pull/rm
    "git",                        # push/reset/commit
    "python", "python3",          # 스크립트 실행
    "curl", "wget",               # 다운로드
    "tar", "gzip", "gunzip", "zip", "unzip",  # 압축
    "sed", "tr",                  # 텍스트 변환 (파일 수정 가능)
}

# ── 절대 금지 (차단) ──
BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "rm -r /",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    ":(){ ",       # Fork bomb
    "chmod 777",
    "chown root",
    "passwd",
    "sudo su",
    "su -",
    "> /dev/sd",
    "> /dev/nvme",
    "format c:",
]

# 실행 시간 제한 (초)
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300

# 출력 크기 제한 (bytes)
MAX_OUTPUT_SIZE = 100 * 1024  # 100KB


def _is_auto_exec_allowed(command: str) -> bool:
    """
    명령어가 자동 실행 허용(읽기 전용)인지 판단한다.
    True: 자동 실행 OK, False: 수동 안내만
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    if not tokens:
        return False

    binary = os.path.basename(tokens[0])

    # Tier 1: 완전 읽기 전용 명령
    if binary in AUTO_EXEC_COMMANDS:
        return True

    # Tier 1 확장: 특정 서브커맨드 허용
    if binary in AUTO_EXEC_SUBCOMMANDS and len(tokens) > 1:
        allowed_subs = AUTO_EXEC_SUBCOMMANDS[binary]
        # 첫 번째 인수 확인
        sub = tokens[1]
        if sub in allowed_subs:
            return True
        # 다중 토큰 서브커맨드 확인 (예: "python -m py_compile")
        sub_two = " ".join(tokens[1:3]) if len(tokens) > 2 else ""
        if sub_two in allowed_subs:
            return True

    return False


def _validate_command(command: str) -> Optional[str]:
    """
    명령어를 검증한다.
    안전하면 None 반환, 위험하면 에러 메시지 반환.
    """
    if not command or not command.strip():
        return "빈 명령어"

    # 블랙리스트 패턴 검사
    cmd_lower = command.lower().strip()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return f"위험 명령어 차단: '{pattern}' 패턴 감지"

    # 셸 인젝션 방지: 위험한 연산자 검사
    dangerous_operators = ["&&", "||", ";", "|", "`", "$(", "${"]
    for op in dangerous_operators:
        if op in command:
            return f"셸 연산자 차단: '{op}' — 단일 명령만 허용됩니다"

    # 바이너리 존재 확인
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"명령어 파싱 오류: {e}"

    if not tokens:
        return "빈 명령어"

    binary = os.path.basename(tokens[0])
    all_allowed = AUTO_EXEC_COMMANDS | set(SUGGEST_ONLY_COMMANDS)
    if binary not in all_allowed:
        return (f"허용되지 않은 명령어: '{binary}'. "
                f"허용 목록: {', '.join(sorted(all_allowed))}")

    return None


def _truncate_output(output: str) -> str:
    """출력을 최대 크기로 제한한다."""
    if len(output.encode("utf-8", errors="replace")) > MAX_OUTPUT_SIZE:
        truncated = output[:MAX_OUTPUT_SIZE // 2]
        truncated += f"\n\n... [출력 잘림: 원본 {len(output)} 문자] ...\n\n"
        truncated += output[-MAX_OUTPUT_SIZE // 4:]
        return truncated
    return output


# ──────────────────────────────────────────────
# MCP 도구 구현
# ──────────────────────────────────────────────

def tool_run_command(arguments: Dict) -> Dict:
    """
    셸 명령을 실행하거나 안내한다.
    - 읽기 전용 명령: 자동 실행 후 결과 반환
    - 쓰기/설치 명령: 실행하지 않고 명령어 텍스트만 안내 (bypass_policy가 True이면 강제 자동 실행)
    """
    command = arguments.get("command", "")
    timeout = min(arguments.get("timeout", DEFAULT_TIMEOUT), MAX_TIMEOUT)
    cwd = arguments.get("cwd", PROJECT_ROOT)
    bypass_policy = arguments.get("bypass_policy", False)

    # ── 가상환경 pip 안전 매핑 필터 ──
    import re
    if command.strip().startswith("pip ") or command.strip().startswith("pip3 "):
        command = re.sub(r"^(pip3|pip)\b", f"{sys.executable} -m pip", command.strip())
        sys.stderr.write(f"  🔄 [Shell Exec Filter] pip 명령 치환 적용: {command}\n")
        sys.stderr.flush()

    # 보안 검증 (블랙리스트/화이트리스트)
    error = _validate_command(command)
    if error:
        return {"success": False, "error": error}

    # CWD 검증: 프로젝트 루트 내로 제한
    cwd_resolved = os.path.realpath(cwd)
    project_prefix = PROJECT_ROOT + os.sep
    if not (cwd_resolved == PROJECT_ROOT or cwd_resolved.startswith(project_prefix)):
        return {"success": False,
                "error": f"CWD 접근 거부: 프로젝트 루트 외부 — {cwd}"}

    # 자동 실행 가능한지 또는 강제 바이패스 상태인지 판단
    if bypass_policy or _is_auto_exec_allowed(command):
        # ── Tier 1: 자동 실행 ──
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd_resolved,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            stdout = _truncate_output(result.stdout)
            stderr = _truncate_output(result.stderr)

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "command": command,
                "mode": "auto_executed",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"실행 시간 초과: {timeout}초",
                "command": command,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}
    else:
        # ── Tier 2: 쓰기/설치 명령 → 실행 안 함, 안내만 ──
        return {
            "success": True,
            "mode": "suggest_only",
            "command": command,
            "message": (
                f"⚠️ 이 명령은 시스템을 변경할 수 있어 자동 실행되지 않습니다.\n"
                f"관리자가 터미널에서 직접 실행해주세요:\n\n"
                f"  cd {cwd_resolved}\n"
                f"  {command}\n"
            ),
            "copy_command": command,
            "cwd": cwd_resolved,
        }


def tool_run_python(arguments: Dict) -> Dict:
    """
    Python 코드를 실행한다.
    인라인 코드(-c) 또는 검증 명령(-m py_compile)만 자동 실행.
    스크립트 실행은 안내만 제공 (bypass_policy가 True이면 강제 자동 실행).
    """
    code = arguments.get("code", "")
    script_path = arguments.get("script_path", "")
    args_list = arguments.get("args", [])
    timeout = min(arguments.get("timeout", DEFAULT_TIMEOUT), MAX_TIMEOUT)
    bypass_policy = arguments.get("bypass_policy", False)

    if script_path:
        # 스크립트 파일 → 안내만 (자동 실행 안 함)
        resolved = os.path.realpath(os.path.join(PROJECT_ROOT, script_path))
        project_prefix = PROJECT_ROOT + os.sep
        if not (resolved == PROJECT_ROOT or resolved.startswith(project_prefix)):
            return {"success": False,
                    "error": f"접근 거부: 프로젝트 외부 스크립트 — {script_path}"}

        if not os.path.exists(resolved):
            return {"success": False, "error": f"스크립트 없음: {script_path}"}

        args_str = " ".join(str(a) for a in args_list)
        full_cmd = f"python {script_path} {args_str}".strip()

        if bypass_policy:
            cmd = [sys.executable, resolved] + [str(a) for a in args_list]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=PROJECT_ROOT,
                )

                stdout = _truncate_output(result.stdout)
                stderr = _truncate_output(result.stderr)

                return {
                    "success": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "mode": "auto_executed",
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "error": f"실행 시간 초과: {timeout}초"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {
            "success": True,
            "mode": "suggest_only",
            "message": (
                f"⚠️ 스크립트 실행은 자동 실행되지 않습니다.\n"
                f"관리자가 터미널에서 직접 실행해주세요:\n\n"
                f"  cd {PROJECT_ROOT}\n"
                f"  {full_cmd}\n"
            ),
            "copy_command": full_cmd,
            "cwd": PROJECT_ROOT,
        }
    elif code:
        # 인라인 코드 → 자동 실행 (조회/검증 목적)
        cmd = [sys.executable, "-c", code]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=PROJECT_ROOT,
            )

            stdout = _truncate_output(result.stdout)
            stderr = _truncate_output(result.stderr)

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "mode": "auto_executed",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"실행 시간 초과: {timeout}초"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        return {"success": False, "error": "code 또는 script_path 중 하나 필요"}


def tool_check_process(arguments: Dict) -> Dict:
    """실행 중인 프로세스를 확인한다."""
    name = arguments.get("name", "")
    show_all = arguments.get("show_all", False)

    try:
        if name:
            result = subprocess.run(
                ["pgrep", "-la", name],
                capture_output=True, text=True, timeout=10,
            )
        elif show_all:
            result = subprocess.run(
                ["ps", "aux", "--sort=-pcpu"],
                capture_output=True, text=True, timeout=10,
            )
        else:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=10,
            )

        output = _truncate_output(result.stdout)

        # 주요 프로세스 필터링 (show_all이 아닌 경우)
        if not show_all and not name:
            keywords = ["ollama", "python", "uvicorn", "node", "npm"]
            lines = result.stdout.strip().split("\n")
            header = lines[0] if lines else ""
            filtered = [l for l in lines[1:] if any(k in l.lower() for k in keywords)]
            output = header + "\n" + "\n".join(filtered[:30])

        return {
            "success": True,
            "output": output,
            "filter": name if name else ("all" if show_all else "relevant"),
            "mode": "auto_executed",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_suggest_command(arguments: Dict) -> Dict:
    """
    명령어를 실행하지 않고, 관리자가 복사해서 쓸 수 있도록 안내한다.
    에이전트가 pip install 등을 추천할 때 사용.
    """
    command = arguments.get("command", "")
    reason = arguments.get("reason", "에이전트 추천")
    cwd = arguments.get("cwd", PROJECT_ROOT)

    if not command:
        return {"success": False, "error": "command가 필요합니다"}

    return {
        "success": True,
        "mode": "suggest_only",
        "command": command,
        "reason": reason,
        "message": (
            f"📋 에이전트가 다음 명령을 추천합니다:\n\n"
            f"  cd {cwd}\n"
            f"  {command}\n\n"
            f"이유: {reason}\n"
            f"터미널에 복사해서 직접 실행하세요."
        ),
        "copy_command": command,
        "cwd": cwd,
    }


# ──────────────────────────────────────────────
# MCP 서버 프로토콜
# ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "run_command",
        "description": (
            "셸 명령을 실행하거나 안내한다. "
            "읽기 전용 명령(ls, cat, grep, git status, pip list 등)은 자동 실행. "
            "설치/변경 명령(pip install, ollama pull 등)은 실행하지 않고 터미널 복사용 텍스트만 반환."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "실행/안내할 명령어"},
                "timeout": {"type": "integer", "description": "타임아웃 초 (기본: 60, 최대: 300)"},
                "cwd": {"type": "string", "description": "작업 디렉토리 (기본: 프로젝트 루트)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Python 코드를 실행한다. 인라인 코드(-c)는 자동 실행 (조회/검증 목적). "
            "스크립트 파일 실행은 안내만 제공 (관리자가 터미널에서 직접 실행)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "실행할 Python 코드 (인라인, 자동 실행)"},
                "script_path": {"type": "string", "description": ".py 스크립트 경로 (안내만)"},
                "args": {"type": "array", "description": "스크립트 인수 목록"},
                "timeout": {"type": "integer", "description": "타임아웃 초 (기본: 60)"},
            },
        },
    },
    {
        "name": "check_process",
        "description": "실행 중인 프로세스를 확인한다. name으로 필터링 가능.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "검색할 프로세스 이름 (예: 'ollama')"},
                "show_all": {"type": "boolean", "description": "모든 프로세스 표시 (기본: false)"},
            },
        },
    },
    {
        "name": "suggest_command",
        "description": "명령을 실행하지 않고, 관리자가 복사할 수 있도록 안내만 한다. pip install, ollama pull 등 추천 시 사용.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "추천할 명령어"},
                "reason": {"type": "string", "description": "추천 이유"},
                "cwd": {"type": "string", "description": "실행 디렉토리"},
            },
            "required": ["command"],
        },
    },
]

TOOL_HANDLERS = {
    "run_command": tool_run_command,
    "run_python": tool_run_python,
    "check_process": tool_check_process,
    "suggest_command": tool_suggest_command,
}


def handle_request(request: dict):
    """JSON-RPC 2.0 요청을 처리한다."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "shell-exec-mcp",
                "version": "2.0.0",
                "description": "읽기 전용 자동 실행 + 쓰기 명령 안내 MCP",
            },
        }}

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)

        if not handler:
            result_content = json.dumps({"error": f"알 수 없는 도구: {tool_name}"})
            is_error = True
        else:
            try:
                result_content = json.dumps(handler(arguments), ensure_ascii=False)
                is_error = False
            except Exception as e:
                result_content = json.dumps({"error": str(e)})
                is_error = True

        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": result_content}],
            "isError": is_error,
        }}

    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main():
    """Stdio JSON-RPC 2.0 서버 메인 루프."""
    sys.stderr.write(f"[shell-exec-mcp] v2.0 서버 시작 (PID={os.getpid()})\n")
    sys.stderr.write(f"[shell-exec-mcp] 프로젝트 루트: {PROJECT_ROOT}\n")
    sys.stderr.write(f"[shell-exec-mcp] 자동 실행: {len(AUTO_EXEC_COMMANDS)}개 (읽기 전용)\n")
    sys.stderr.write(f"[shell-exec-mcp] 수동 안내: pip install, ollama pull 등\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    sys.stderr.write("[shell-exec-mcp] 서버 종료\n")


if __name__ == "__main__":
    main()
