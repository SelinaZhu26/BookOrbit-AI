"""Enrol (train) a face template for an existing account.

    python tools/enroll_face.py alice                 # webcam: takes 3 samples
    python tools/enroll_face.py alice --image me.jpg  # from photo file(s)

Used to give the seeded demo accounts (admin, alice, selina, ...) a face so
they can sign in. New customers enrol themselves on the Registration screen.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from bookorbit.app_context import AppContext  # noqa: E402
from bookorbit.errors import BiometricError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--image", nargs="*", type=Path, help="photo file(s) instead of the webcam")
    ap.add_argument("--samples", type=int, default=3)
    args = ap.parse_args()

    ctx = AppContext()
    if not ctx.biometric.available:
        print("Face models are missing:", ctx.biometric.load_error)
        return 1
    user = ctx.users.by_username(args.username)
    if not user:
        print(f"No account with username '{args.username}'")
        return 1
    images = []
    if args.image:
        for p in args.image:
            img = cv2.imread(str(p))
            if img is None:
                print(f"Cannot read {p}")
                return 1
            images.append(img)
    else:
        if not ctx.camera.available():
            print("No camera found - use --image photo.jpg")
            return 1
        print(f"Look at the camera. Taking {args.samples} samples...")
        for i in range(args.samples):
            time.sleep(0.8)
            frame = ctx.camera.snapshot()
            if frame is not None:
                images.append(frame)
                print(f"  sample {i + 1} captured")
    try:
        ctx.auth.enroll(user["user_ID"], images)
    except BiometricError as exc:
        print("Could not enrol:", exc.message)
        return 1
    print(f"Face template saved for {user['username']} ({user['full_Name']}). They can now sign in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
