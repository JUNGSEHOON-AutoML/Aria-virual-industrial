"""
system_mcp.py — 시스템 자원 모니터링 FastMCP 서버

노출 도구:
  1. get_gpu_status    — NVIDIA GPU 상태 (nvidia-smi)
  2. get_system_info   — CPU / 메모리 / 디스크 사용량
  3. execute_safe_cmd  — 허용된 명령어만 실행 (화이트리스트)

FastMCP SDK 기반: stdout 오염 없는 안전한 stdio transport
"""

import sys
import asyncio
import subprocess
import shlex
from pathlib import Path

import psutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("system-mcp")

# ── 허용된 명령어 화이트리스트 (쉘 인젝션 방지) ──────────────────
ALLOWED_CMDS = {
    "nvidia-smi", "df", "du", "ls", "pwd", "ps", "top",
    "free", "uptime", "uname", "hostname", "date",
    "cat", "head", "tail", "grep", "find", "wc",
    "echo", "python", "python3", "pip", "pip3",
}


def _is_safe_command(cmd: str) -> bool:
    """첫 번째 토큰이 허용 목록에 있는지 확인."""
    try:
        tokens = shlex.split(cmd)
        if not tokens:
            return False
        return Path(tokens[0]).name in ALLOWED_CMDS
    except Exception:
        return False


@mcp.tool()
async def get_gpu_status() -> dict:
    """
    NVIDIA GPU 상태를 조회합니다 (nvidia-smi).
    GPU 미설치 환경에서는 미지원 메시지를 반환합니다.
    """
    try:
        result = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,"
            "memory.total,memory.used,memory.free,power.draw",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=10)

        if result.returncode != 0:
            return {"success": False, "error": "nvidia-smi 실행 실패 또는 GPU 미설치", "stderr": stderr.decode()}

        gpus = []
        for line in stdout.decode().strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 8:
                gpus.append({
                    "name": parts[0],
                    "temp_c": parts[1],
                    "gpu_util_pct": parts[2],
                    "mem_util_pct": parts[3],
                    "mem_total_mb": parts[4],
                    "mem_used_mb": parts[5],
                    "mem_free_mb": parts[6],
                    "power_w": parts[7],
                })
        return {"success": True, "gpu_count": len(gpus), "gpus": gpus}

    except asyncio.TimeoutError:
        return {"success": False, "error": "nvidia-smi 타임아웃"}
    except FileNotFoundError:
        return {"success": False, "error": "nvidia-smi를 찾을 수 없습니다. NVIDIA GPU가 없거나 드라이버 미설치."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_system_info() -> dict:
    """
    시스템 자원 현황을 반환합니다 (CPU, 메모리, 디스크).
    """
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # 주요 파티션만 (tmpfs 제외)
        disks = []
        for part in psutil.disk_partitions():
            if "tmpfs" in part.fstype or "devtmpfs" in part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "pct": usage.percent,
                })
            except PermissionError:
                continue

        return {
            "success": True,
            "cpu": {
                "usage_pct": cpu_pct,
                "core_count": cpu_count,
                "freq_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
            },
            "memory": {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "used_gb": round(mem.used / (1024 ** 3), 2),
                "available_gb": round(mem.available / (1024 ** 3), 2),
                "usage_pct": mem.percent,
            },
            "swap": {
                "total_gb": round(swap.total / (1024 ** 3), 2),
                "used_gb": round(swap.used / (1024 ** 3), 2),
                "usage_pct": swap.percent,
            },
            "disks": disks,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def execute_safe_cmd(command: str, timeout: int = 15) -> dict:
    """
    허용된 시스템 명령어를 안전하게 실행합니다.

    Args:
        command: 실행할 명령어 (화이트리스트 내 명령만 허용)
        timeout: 최대 실행 시간(초)
    """
    if not _is_safe_command(command):
        return {
            "success": False,
            "error": f"허용되지 않는 명령어입니다. 허용 목록: {', '.join(sorted(ALLOWED_CMDS))}",
        }
    try:
        result = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=timeout)
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": stdout.decode(errors="replace")[:5000],
            "stderr": stderr.decode(errors="replace")[:1000],
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"명령어 타임아웃 ({timeout}초)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    sys.stderr.write("[system-mcp] FastMCP 서버 시작\n")
    mcp.run()
