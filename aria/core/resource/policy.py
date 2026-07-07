from __future__ import annotations

def choose_device() -> tuple[str, str]:
    """(device, reason) 반환. 라이브 추론이 공통으로 호출하는 단일 진입점."""
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu", "CUDA 미가용(torch가 CPU 빌드이거나 GPU 미감지)"
        best, best_free = 0, -1
        for i in range(torch.cuda.device_count()):
            free, total = torch.cuda.mem_get_info(i)
            if free > best_free:
                best, best_free = i, free
        return f"cuda:{best}", f"GPU {best} 선택(free VRAM 최대 {best_free//1048576}MB)"
    except Exception as e:
        return "cpu", f"디바이스 탐색 실패→CPU ({e})"
