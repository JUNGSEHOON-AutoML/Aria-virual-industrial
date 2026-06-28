import base64
import io
import json
import random
from pathlib import Path
from PIL import Image
from aria.simulation.defects import synth_defect

def save_sim_dataset(images_b64: list, work_dir: str,
                     defect_ratio: float = 0.3, defect_type: str = "scratch") -> dict:
    base = Path(work_dir)
    good_dir, def_dir = base / "good", base / "defect"
    good_dir.mkdir(parents=True, exist_ok=True)
    def_dir.mkdir(parents=True, exist_ok=True)
    good_paths, def_paths = [], []
    for i, data in enumerate(images_b64):
        raw = base64.b64decode(data.split(",", 1)[-1])
        # 모든 이미지는 일단 정상(good) 데이터셋에 저장
        gp = good_dir / f"{i:04d}.png"
        gp.write_bytes(raw)
        good_paths.append(str(gp))
        
        # defect_ratio 확률로 스크래치 결함을 덧입혀 결함(defect) 데이터셋에 저장
        if random.random() < defect_ratio:
            img = Image.open(io.BytesIO(raw))
            dp = def_dir / f"{i:04d}.png"
            synth_defect(img, defect_type).save(dp)
            def_paths.append(str(dp))
            
    all_paths = good_paths + def_paths
    manifest = {                              # ★ 6A 포맷과 동일 → 학습이 그대로 소비
        "n_images": len(all_paths),
        "classes": {"good": len(good_paths), "defect": len(def_paths)},
        "images": all_paths[:200],
        "work_dir": str(base),
        "source": "sim",
    }
    with open(base / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest
