import random
from PIL import Image, ImageDraw

def synth_defect(img: Image.Image, defect_type: str = "scratch", seed=None) -> Image.Image:
    """정상 이미지에 합성 결함 주입 → 결함 이미지. (seam: 추후 diffusion으로 교체 가능)"""
    rng = random.Random(seed)
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    if defect_type == "scratch":
        for _ in range(rng.randint(1, 3)):
            x1, y1 = rng.randint(0, w), rng.randint(0, h)
            # 흠집 크기는 이미지 크기의 최대 1/3로 제한
            x2 = x1 + rng.randint(-w // 3, w // 3)
            y2 = y1 + rng.randint(-h // 3, h // 3)
            # 경계 제한
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))
            # 어두운 스크래치 색상 (18, 18, 18)
            d.line([(x1, y1), (x2, y2)], fill=(18, 18, 18), width=rng.randint(1, 3))
    else:  # blob 폴백
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(max(2, min(w, h) // 12), max(3, min(w, h) // 6))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 25, 25))
    return out
