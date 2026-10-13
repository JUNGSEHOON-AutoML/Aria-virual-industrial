"""O0: inspect the host without creating a CUDA context or changing the system.

Only writes the requested JSON/Markdown reports. Run on the host: a sandbox's
missing NVML access is UNKNOWN, never evidence that a host driver is broken.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VALIDATED = {"570.169", "580.95.05", "595.58.03"}
MIN_DISK = 250_000_000_000  # Requirement uses decimal GB.
MIN_RAM = 16 * 1024**3  # Conservative interpretation; MemAvailable includes cache.


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return {"command": args, "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": args, "returncode": None, "stdout": "", "stderr": str(exc)}


def driver_status(version):
    if version in VALIDATED:
        return "pass"
    try:
        parts = tuple(int(p) for p in version.split("."))
    except (AttributeError, ValueError):
        return "unknown"
    return "unverified" if parts >= (570, 169) else "fail"


def parse_gpus(result):
    if result["returncode"] != 0:
        return None
    try:
        doc = ET.fromstring(result["stdout"])
        version = doc.findtext("driver_version")
        rows = []
        for gpu in doc.findall("gpu"):
            processes = gpu.find("processes")
            known = processes is not None and (processes.text or "").strip() not in {"N/A", "Not Supported"}
            rows.append({
                "model": gpu.findtext("product_name"), "uuid": gpu.findtext("uuid"),
                "driver": version, "driver_status": driver_status(version),
                "free_memory": gpu.findtext("fb_memory_usage/free"),
                "total_memory": gpu.findtext("fb_memory_usage/total"),
                "processes_known": known,
                "processes": [{e.tag: e.text for e in p} for p in gpu.findall("processes/process_info")],
            })
        return rows
    except ET.ParseError:
        return None


def disk_info(path):
    planned = Path(path).absolute()
    existing = planned
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    stat = os.statvfs(existing)
    return {"path": str(planned), "measured_ancestor": str(existing),
            "available_bytes": stat.f_bavail * stat.f_frsize,
            "total_bytes": stat.f_blocks * stat.f_frsize,
            "ancestor_writable": os.access(existing, os.W_OK),
            "meets_capacity": stat.f_bavail * stat.f_frsize >= MIN_DISK}


def gates(gpus, os_info, disk, available_ram, display):
    return {
        "driver": bool(gpus) and all(g["driver_status"] == "pass" for g in gpus),
        # Conservatively require no graphics OR compute process; never reserve it.
        "unused_rtx": bool(gpus) and any("RTX" in (g["model"] or "") and g["processes_known"] and not g["processes"] for g in gpus),
        "kit_storage": disk["available_bytes"] >= MIN_DISK,
        "ram": available_ram >= MIN_RAM,
        "os": os_info.get("ID") == "ubuntu" and os_info.get("VERSION_ID") in {"22.04", "24.04"},
        "display_route": True,  # Absence selects headless streaming; not launched.
    }


def inspect(kit_path):
    os_info = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    os_info = {k: v.strip('"') for k, v in os_info.items()}
    mem = dict(re.findall(r"^(\w+):\s+(\d+) kB$", Path("/proc/meminfo").read_text(), re.M))
    available_ram = int(mem.get("MemAvailable", 0)) * 1024
    gpu_query = command(["nvidia-smi", "-q", "-x"])
    gpus = parse_gpus(gpu_query)
    mounts = command(["findmnt", "--json", "--real", "-o", "TARGET,SOURCE,FSTYPE"])
    candidates = []
    def visit(rows):
        for row in rows:
            if row.get("fstype") in {"ext4", "xfs", "btrfs", "zfs", "nfs", "nfs4"}:
                try:
                    candidates.append({**disk_info(row["target"]), "source": row["source"], "fstype": row["fstype"]})
                except OSError as exc:
                    candidates.append({"path": row["target"], "error": str(exc)})
            visit(row.get("children", []))
    if mounts["returncode"] == 0:
        visit(json.loads(mounts["stdout"])["filesystems"])
    disk = disk_info(kit_path)
    display = os.environ.get("DISPLAY")
    checks = gates(gpus, os_info, disk, available_ram, display)
    return {
        "schema": 1, "milestone": "O0", "checked_at": datetime.now(timezone.utc).isoformat(),
        "read_only_system": True, "gpu_context_created": False,
        "o0_audit_complete": True, "o2_environment_ready": all(checks.values()),
        "o2_authorized": False, "experiment_completion_verified": False,
        "requirements": {"validated_drivers": sorted(VALIDATED), "disk_bytes": MIN_DISK,
                         "ram_available_bytes": MIN_RAM, "source": "BuildSpec 13.1"},
        "gates": checks, "failed": [k for k, v in checks.items() if not v],
        "gpu_query": gpu_query, "gpus": gpus,
        "gpu_note": "Missing NVML/query failure is UNKNOWN. Idle snapshot is not a reservation or experiment completion proof.",
        "os": os_info, "ram_available_bytes": available_ram,
        "free_g": command(["free", "-g"]), "planned_kit_storage": disk,
        "alternative_volumes": candidates, "mount_query": mounts,
        "display": display, "render_route": "desktop" if display else "headless_streaming_deferred_to_O2",
    }


def admin_request(report):
    gpu = report["gpus"] or []
    rows = [
        ("OS", report["os"].get("PRETTY_NAME"), "Ubuntu 22.04 / 24.04"),
        ("Driver", ", ".join(sorted({g["driver"] for g in gpu})) or "UNKNOWN", "570.169 / 580.95.05 / 595.58.03; newer is unverified"),
        ("GPU", f'{len(gpu)} RTX candidates; idle check={report["gates"]["unused_rtx"]}', "Unoccupied RTX; reserve only after experiment completion"),
        ("Kit path", f'{report["planned_kit_storage"]["path"]}: {report["planned_kit_storage"]["available_bytes"]/1e9:.2f} GB free', "250 GB free"),
        ("RAM", f'{report["ram_available_bytes"]/1024**3:.2f} GiB available', "16 GiB available (conservative)"),
        ("Display", report["display"] or "unset", report["render_route"]),
    ]
    lines = ["# Omniverse 관리자 요청서 — O2 보류", "", f'측정: {report["checked_at"]}', "",
             "O0 환경 조건 실패: " + ", ".join(report["failed"]), "",
             "항목 | 현재 값 | 필요한 값", "--- | --- | ---"]
    lines += [" | ".join(map(str, row)) for row in rows]
    lines += ["", "## 다른 볼륨 (할당·쓰기·설치하지 않음)", ""]
    lines += [f'- `{r["path"]}`: {r.get("available_bytes", 0)/1e9:.2f} GB; 250 GB 충족={r.get("meets_capacity", False)}; 쓰기 가능={r.get("ancestor_writable", False)}' for r in report["alternative_volumes"]]
    lines += ["", "공용 서버 드라이버·OS 업그레이드는 다른 사용자 CUDA 작업과 실행 환경에 영향을 준다. 관리자에게 본 실험 및 다른 사용자 작업 종료 후 점검/재부팅 일정을 요청한다. 충분한 용량의 설치·캐시 경로도 관리자가 할당해야 한다.",
              "", "Codex는 드라이버·CUDA·시스템 패키지·GPU 프로세스를 변경하지 않았으며 Kit/Replicator를 설치하거나 실행하지 않았다. GPU 유휴 관측은 본 실험 완료의 근거가 아니다. O2 진입 전에 O0 전체 재검사 및 본 실험 종료 확인이 필요하다. O1은 독립 CPU 작업으로 진행한다.",
              "", "기술 요구사항 확인 출처: https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-path", type=Path, default=ROOT / "outputs/omniverse/kit")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/autopilot/omniverse_preflight.json")
    args = parser.parse_args()
    report = inspect(args.kit_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if not report["o2_environment_ready"]:
        args.output.with_name("omniverse_admin_request.md").write_text(admin_request(report))
    print(json.dumps({k: report[k] for k in ("gates", "failed", "o2_environment_ready")}, ensure_ascii=False))
    return 0 if report["o2_environment_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
