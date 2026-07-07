import time
try:
    import psutil
except Exception:
    psutil = None
try:
    import pynvml
    pynvml.nvmlInit()
    _NVML = True
except Exception:
    _NVML = False
try:
    import torch
    _CUDA = torch.cuda.is_available()
except Exception:
    _CUDA = False

def get_snapshot() -> dict:
    """읽기전용 하드웨어 스냅샷. GPU/pynvml 없으면 gpus=[]로 안전 폴백."""
    gpus = []
    if _NVML:
        try:
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                name = pynvml.nvmlDeviceGetName(h)
                gpus.append({
                    "index": i,
                    "name": name.decode() if isinstance(name, bytes) else name,
                    "util_pct": util.gpu,
                    "vram_used_mb": mem.used // 1048576,
                    "vram_total_mb": mem.total // 1048576,
                    "temp_c": pynvml.nvmlDeviceGetTemperature(h, 0),
                })
        except Exception:
            pass
    cpu = psutil.cpu_percent(interval=None) if psutil else None
    vm = psutil.virtual_memory() if psutil else None
    return {
        "ts": time.time(),
        "cuda_available": _CUDA,
        "gpus": gpus,
        "cpu_pct": cpu,
        "ram_used_mb": (vm.used // 1048576) if vm else None,
        "ram_total_mb": (vm.total // 1048576) if vm else None,
    }
