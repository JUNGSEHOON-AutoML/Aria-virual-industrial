import os
import zipfile
import tarfile
from pathlib import Path
from PIL import Image

_IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

def scan_dataset(archive_path: str, work_dir: str) -> dict:
    """압축을 해제하고 통계 리포트(이미지 수, 클래스, 포맷, 해상도 분포)를 리턴한다."""
    out = Path(work_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    out_prefix = str(out) + os.sep

    # 1. 압축 해제 (Zip/Tar Slip 방지)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as z:
            for member in z.namelist():
                member_path = (out / member).resolve()
                if not (str(member_path).startswith(out_prefix) or str(member_path) == str(out)):
                    raise ValueError(f"Directory traversal detected in ZIP: {member}")
            z.extractall(out)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as t:
            for member in t.getmembers():
                member_path = (out / member.name).resolve()
                if not (str(member_path).startswith(out_prefix) or str(member_path) == str(out)):
                    raise ValueError(f"Directory traversal detected in TAR: {member.name}")
                if member.issym() or member.islnk():
                    link_target = (out / member.linkname).resolve()
                    if not (str(link_target).startswith(out_prefix) or str(link_target) == str(out)):
                        raise ValueError(f"Directory traversal via link detected in TAR: {member.name}")
            t.extractall(out)
    else:
        raise ValueError("zip/tar 형식이 아님")

    # 2. 통계 계산
    images = []
    classes = {}
    formats = {}
    sizes = []

    for root, _, files in os.walk(out):
        for fn in files:
            ext = Path(fn).suffix.lower()
            if ext in _IMG_EXT:
                p = os.path.join(root, fn)
                images.append(p)
                
                # 클래스명은 이미지가 있는 디렉토리명으로 지정
                cls = Path(root).name
                classes[cls] = classes.get(cls, 0) + 1
                
                formats[ext] = formats.get(ext, 0) + 1
                try:
                    with Image.open(p) as im:
                        sizes.append(im.size)
                except Exception:
                    pass

    resolution = {}
    if sizes:
        ws = [s[0] for s in sizes]
        hs = [s[1] for s in sizes]
        resolution = {"w": [min(ws), max(ws)], "h": [min(hs), max(hs)]}

    return {
        "n_images": len(images),
        "classes": classes,
        "formats": formats,
        "resolution": resolution,
        "images": images[:200],
        "work_dir": str(out)
    }
