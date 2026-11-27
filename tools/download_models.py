"""Download the two face models into models/ (about 50 MB in total).

    python tools/download_models.py

  yolov8n-face.onnx                      YOLOv8-nano face detector (boxes + 5 landmarks)
  face_recognition_sface_2021dec.onnx    SFace face embedding model (OpenCV Zoo)
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = {
    "yolov8n-face.onnx": (
        "https://raw.githubusercontent.com/hpc203/yolov8-face-landmarks-opencv-dnn/main/weights/yolov8n-face.onnx",
        "d22820ff253677420e56562f8351955f741bfed7ab4960cf74aed543f52afeb5"),
    "face_recognition_sface_2021dec.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/"
        "face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    ok = True
    for name, (url, digest) in MODELS.items():
        target = out / name
        if target.exists() and sha256(target) == digest:
            print(f"{name}: already present")
            continue
        print(f"Downloading {name} ...")
        tmp = target.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        if sha256(tmp) != digest:
            tmp.unlink()
            print(f"  checksum mismatch for {name}")
            ok = False
            continue
        tmp.replace(target)
        print("  done")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
