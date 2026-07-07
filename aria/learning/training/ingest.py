import os, json, zipfile, tarfile
from pathlib import Path

_IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

def ingest_zip(zip_path: str, work_dir: str) -> dict:
    """ZIP 또는 TAR 아카이브를 풀고 이미지 수/클래스를 집계해 manifest.json을 쓴다."""
    out = Path(work_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    out_prefix = str(out) + os.sep
    
    if zipfile.is_zipfile(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            for member in z.namelist():
                member_path = (out / member).resolve()
                if not (str(member_path).startswith(out_prefix) or str(member_path) == str(out)):
                    raise ValueError(f"Directory traversal detected in ZIP: {member}")
            z.extractall(out)
    elif tarfile.is_tarfile(zip_path):
        with tarfile.open(zip_path) as t:
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
        raise ValueError(f"지원하지 않는 아카이브 포맷이거나 파일이 손상되었습니다: {zip_path}")

    images, classes = [], {}
    for root, _, files in os.walk(out):
        for fn in files:
            if Path(fn).suffix.lower() in _IMG_EXT:
                images.append(os.path.join(root, fn))
                cls = Path(root).name
                classes[cls] = classes.get(cls, 0) + 1

    manifest = {
        "n_images": len(images),
        "classes": classes,
        "images": images[:200],      # 프리뷰용 일부만 보관
        "work_dir": str(out),
    }
    with open(out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest

