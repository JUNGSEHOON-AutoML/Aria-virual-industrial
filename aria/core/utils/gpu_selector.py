import subprocess

def pick_gpus():
    """여유 VRAM 기준으로 LLM용/비전용 GPU 자동 배정."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0 or not r.stdout.strip():
            # nvidia-smi 실행 오류 시 기본값 반환
            return {"llm": 0, "vision": 1}
            
        gpus = []
        for l in r.stdout.strip().split("\n"):
            parts = l.split(",")
            if len(parts) >= 2:
                gpus.append((int(parts[0].strip()), int(parts[1].strip())))
                
        gpus = sorted(gpus, key=lambda x: -x[1])  # 여유 많은 순
        
        if len(gpus) >= 2 and gpus[1][1] > 8000:
            # GPU 2개 다 여유 → 분리
            return {"llm": gpus[0][0], "vision": gpus[1][0]}
        elif len(gpus) >= 1:
            # 1개만 여유 → 공유
            return {"llm": gpus[0][0], "vision": gpus[0][0]}
        else:
            return {"llm": 0, "vision": 0}
    except Exception:
        # 시스템 에러 시 기본값
        return {"llm": 0, "vision": 1}
