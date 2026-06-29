"""YOLO 학습 데이터 생성기 (ARIA_Vision_Inspection_Node_Spec 신규3).

MVTec ground_truth 마스크 → connected components → bbox, class=결함폴더명.
YOLO 포맷(images/ + labels/*.txt + data.yaml) 생성.

핵심 문제: MVTec `train/`은 good만 → 결함 라벨 부족.
해결: **합성 증강** — test 결함+마스크를 good 위에 컴포지트 + 도메인 랜덤화로 라벨 대량 생성.

학습(별도, ultralytics 필요):
    from ultralytics import YOLO
    YOLO("yolo26n.pt").train(data="data.yaml", epochs=100, imgsz=640)   # 안정성 우선 시 yolo11n.pt

cv2/PIL/numpy만으로 데이터 생성·검증 가능(ultralytics 불필요).
"""
from __future__ import annotations

import os
import glob
import shutil
import random
from pathlib import Path
from typing import Optional

import numpy as np
import cv2


# ─────────────────────────── 마스크 → bbox ───────────────────────────
def mask_to_boxes(mask: np.ndarray, min_area: int = 20):
    """이진 마스크 → connected components → [(x,y,w,h) 픽셀]."""
    binary = (mask > 127).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    boxes = []
    for i in range(1, n):                      # 0=배경 제외
        x, y, w, h, area = stats[i]
        if area >= min_area:
            boxes.append((int(x), int(y), int(w), int(h)))
    return boxes


def _to_yolo(box, img_w: int, img_h: int):
    """(x,y,w,h) 픽셀 → (cx,cy,w,h) 정규화."""
    x, y, w, h = box
    return ((x + w / 2) / img_w, (y + h / 2) / img_h, w / img_w, h / img_h)


# ─────────────────────────── 합성 증강 ───────────────────────────
def synth_composite(good_bgr: np.ndarray, defect_bgr: np.ndarray, mask: np.ndarray,
                    rng: random.Random):
    """good 이미지 위에 결함 영역(마스크)을 알파 컴포지트 + 도메인 랜덤화.

    반환: (합성 이미지 BGR, [(x,y,w,h) 픽셀 박스들])."""
    H, W = good_bgr.shape[:2]
    out = good_bgr.copy()
    binary = (mask > 127).astype(np.uint8)

    boxes = mask_to_boxes(mask)
    if not boxes:
        return out, []

    # 위치 지터(±결함 크기의 일부) + 밝기 랜덤화(도메인 랜덤화)
    max_shift = 0.08
    dx = int(rng.uniform(-max_shift, max_shift) * W)
    dy = int(rng.uniform(-max_shift, max_shift) * H)

    M = np.float32([[1, 0, dx], [0, 1, dy]])
    shifted_mask = cv2.warpAffine(binary, M, (W, H))
    shifted_def = cv2.warpAffine(defect_bgr, M, (W, H))

    # 부드러운 경계(알파 페더링)
    alpha = cv2.GaussianBlur((shifted_mask * 255).astype(np.uint8), (5, 5), 0).astype(np.float32) / 255.0
    alpha = alpha[..., None]
    out = (shifted_def.astype(np.float32) * alpha + out.astype(np.float32) * (1 - alpha)).astype(np.uint8)

    # 전역 밝기 지터
    beta = rng.uniform(-18, 18)
    out = np.clip(out.astype(np.float32) + beta, 0, 255).astype(np.uint8)

    new_boxes = [(max(0, x + dx), max(0, y + dy), w, h) for (x, y, w, h) in boxes]
    return out, new_boxes


# ─────────────────────────── 데이터셋 빌드 ───────────────────────────
def _defect_classes(category_dir: str):
    gt = Path(category_dir) / "ground_truth"
    return sorted([d.name for d in gt.iterdir() if d.is_dir()]) if gt.is_dir() else []


def _gt_pairs(category_dir: str, cls: str):
    """(test 이미지 경로, 마스크 경로) 쌍 — 000.png ↔ 000_mask.png."""
    cat = Path(category_dir)
    pairs = []
    for mp in sorted((cat / "ground_truth" / cls).glob("*_mask.png")):
        stem = mp.name.replace("_mask.png", "")
        img = cat / "test" / cls / f"{stem}.png"
        if img.exists():
            pairs.append((str(img), str(mp)))
    return pairs


def build_yolo_dataset(category_dir: str, out_dir: str,
                       synth_per_defect: int = 4, val_ratio: float = 0.2,
                       seed: int = 0) -> dict:
    """MVTec 카테고리 → YOLO 데이터셋(images/labels/{train,val} + data.yaml).

    - 실 라벨: ground_truth 마스크 → bbox.
    - 합성 라벨: 각 결함을 good 위에 synth_per_defect회 컴포지트(도메인 랜덤화).
    """
    rng = random.Random(seed)
    classes = _defect_classes(category_dir)
    cls_id = {c: i for i, c in enumerate(classes)}
    out = Path(out_dir)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    good_imgs = sorted(glob.glob(os.path.join(category_dir, "test", "good", "*.png"))) + \
        sorted(glob.glob(os.path.join(category_dir, "train", "good", "*.png")))

    samples = []   # (image_ndarray_or_path, [(cls_id,cx,cy,w,h)], stem)

    # 1) 실측 GT 라벨
    n_real = 0
    for cls in classes:
        for img_path, mask_path in _gt_pairs(category_dir, cls):
            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            img = cv2.imread(img_path)
            if mask is None or img is None:
                continue
            H, W = img.shape[:2]
            labels = [(cls_id[cls], *_to_yolo(b, W, H)) for b in mask_to_boxes(mask)]
            if labels:
                samples.append((img_path, labels, f"real_{cls}_{Path(img_path).stem}"))
                n_real += 1

    # 2) 합성 증강 (good 위에 결함 컴포지트)
    n_synth = 0
    if good_imgs:
        for cls in classes:
            pairs = _gt_pairs(category_dir, cls)
            for k in range(synth_per_defect * max(1, len(pairs) // 4)):
                if not pairs:
                    break
                img_path, mask_path = rng.choice(pairs)
                good = cv2.imread(rng.choice(good_imgs))
                defect = cv2.imread(img_path)
                mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                if good is None or defect is None or mask is None:
                    continue
                if good.shape[:2] != defect.shape[:2]:
                    good = cv2.resize(good, (defect.shape[1], defect.shape[0]))
                comp, boxes = synth_composite(good, defect, mask, rng)
                H, W = comp.shape[:2]
                labels = [(cls_id[cls], *_to_yolo(b, W, H)) for b in boxes]
                if labels:
                    samples.append((comp, labels, f"synth_{cls}_{k:04d}"))
                    n_synth += 1

    # 3) train/val split + 파일 쓰기
    rng.shuffle(samples)
    n_val = int(len(samples) * val_ratio)
    for i, (img, labels, stem) in enumerate(samples):
        split = "val" if i < n_val else "train"
        img_dst = out / "images" / split / f"{stem}.png"
        if isinstance(img, str):
            shutil.copy(img, img_dst)
        else:
            cv2.imwrite(str(img_dst), img)
        with open(out / "labels" / split / f"{stem}.txt", "w") as f:
            for (c, cx, cy, w, h) in labels:
                f.write(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")

    # 4) data.yaml
    yaml_path = out / "data.yaml"
    with open(yaml_path, "w") as f:
        f.write(f"path: {out.resolve()}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(classes)}\n")
        f.write("names:\n")
        for c in classes:
            f.write(f"  {cls_id[c]}: {c}\n")

    return {
        "data_yaml": str(yaml_path),
        "classes": classes,
        "n_real": n_real,
        "n_synth": n_synth,
        "n_total": len(samples),
        "n_train": len(samples) - n_val,
        "n_val": n_val,
    }


def train(data_yaml: str, model: str = "yolo11n.pt", epochs: int = 100,
          imgsz: int = 640, **kw):
    """YOLO 학습 (ultralytics 필요). 모델 무관(yolo11/yolov8/yolo26 등)."""
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise ImportError("ultralytics 미설치 — `pip install ultralytics`") from e
    m = YOLO(model)
    return m.train(data=data_yaml, epochs=epochs, imgsz=imgsz, **kw)


# ─────────────────────────── 검증/증명 ───────────────────────────
def _verify():
    out_dir = "outputs/yolo_dataset/bottle"
    print("=" * 74)
    print("YOLO 데이터셋 빌드 검증 — MVTec bottle (ground_truth → bbox + 합성증강)")
    print("=" * 74)
    info = build_yolo_dataset("data/bottle", out_dir, synth_per_defect=4, val_ratio=0.2, seed=0)
    print(f"  classes        : {info['classes']}")
    print(f"  실측 GT 라벨    : {info['n_real']}장")
    print(f"  합성 증강 라벨  : {info['n_synth']}장")
    print(f"  총 / train / val: {info['n_total']} / {info['n_train']} / {info['n_val']}")
    print(f"  data.yaml       : {info['data_yaml']}")

    # 포맷 검증: 라벨 1개 읽어 정규화 범위 확인
    sample_lbls = sorted(glob.glob(os.path.join(out_dir, "labels", "train", "*.txt")))
    ok_fmt = True
    if sample_lbls:
        with open(sample_lbls[0]) as f:
            for line in f:
                parts = line.split()
                if len(parts) != 5:
                    ok_fmt = False
                    break
                c = int(parts[0]); vals = [float(v) for v in parts[1:]]
                if not (0 <= c < len(info["classes"]) and all(0 <= v <= 1 for v in vals)):
                    ok_fmt = False
        # 이미지-라벨 짝 확인
        img0 = sample_lbls[0].replace("labels", "images").replace(".txt", ".png")
        pair_ok = os.path.exists(img0)
    else:
        ok_fmt = pair_ok = False

    passed = info["n_real"] > 0 and info["n_total"] > info["n_real"] and ok_fmt and pair_ok
    print("-" * 74)
    print(f"  포맷 검증: 라벨 정규화 OK={ok_fmt} · 이미지-라벨 짝 OK={pair_ok}")
    print(f"\n  [{'PASS' if passed else 'FAIL'}] YOLO 데이터셋 생성(실측+합성) + 포맷 유효 (학습은 ultralytics 설치 후)")
    print("=" * 74)
    return passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if _verify() else 1)
