"""CoverIndex - search books by a picture of their cover (spec item 5).

Each cover is described by SIFT key-points (local features that survive a
phone photo: rotation, scale, perspective, lighting) plus an HSV colour
histogram. A query photo is matched against every cover; the score combines
the number of geometrically consistent matches (RANSAC homography inliers,
relative to the best match) with the colour similarity -> 0..1.
"""
from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np


class CoverIndex:
    HEIGHT = 480

    def __init__(self, index_dir: Path):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._sift = cv2.SIFT_create(nfeatures=600)
        self._matcher = cv2.BFMatcher(cv2.NORM_L2)
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return any(self.index_dir.glob("*.npz"))

    def _features(self, img: np.ndarray):
        h, w = img.shape[:2]
        scale = self.HEIGHT / h
        img = cv2.resize(img, (max(1, int(w * scale)), self.HEIGHT))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        with self._lock:
            kps, desc = self._sift.detectAndCompute(gray, None)
        pts = np.array([k.pt for k in kps], dtype=np.float32) if kps else np.zeros((0, 2), np.float32)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256])
        hist = cv2.normalize(hist, None).flatten()
        if desc is None:
            desc = np.zeros((0, 128), np.float32)
        return pts, desc, hist

    def add(self, book_ID: str, cover_path: Path) -> bool:
        img = cv2.imread(str(cover_path))
        if img is None:
            return False
        pts, desc, hist = self._features(img)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.index_dir / f"{book_ID}.npz", pts=pts, desc=desc, hist=hist)
        self._cache.pop(book_ID, None)
        return True

    def remove(self, book_ID: str) -> None:
        p = self.index_dir / f"{book_ID}.npz"
        if p.exists():
            p.unlink()
        self._cache.pop(book_ID, None)

    def _load(self, book_ID: str) -> dict:
        if book_ID not in self._cache:
            z = np.load(self.index_dir / f"{book_ID}.npz")
            self._cache[book_ID] = {"pts": z["pts"], "desc": z["desc"], "hist": z["hist"]}
        return self._cache[book_ID]

    def _inliers(self, q_pts, q_desc, c_pts, c_desc) -> int:
        if len(q_desc) < 8 or len(c_desc) < 8:
            return 0
        pairs = self._matcher.knnMatch(q_desc, c_desc, k=2)
        good = [m for m, *rest in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * rest[0].distance]
        if len(good) < 8:
            return len(good) // 3
        src = np.float32([q_pts[m.queryIdx] for m in good]).reshape(-1, 1, 2)
        dst = np.float32([c_pts[m.trainIdx] for m in good]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
        return int(mask.sum()) if mask is not None else 0

    def search(self, image: np.ndarray, top_k: int = 5, min_similarity: float = 0.25) -> list[tuple[str, float]]:
        q_pts, q_desc, q_hist = self._features(image)
        raw = []
        for f in sorted(self.index_dir.glob("*.npz")):
            book_ID = f.stem
            c = self._load(book_ID)
            inl = self._inliers(q_pts, q_desc, c["pts"], c["desc"])
            color = max(0.0, float(cv2.compareHist(q_hist.astype(np.float32), c["hist"].astype(np.float32),
                                                   cv2.HISTCMP_CORREL)))
            raw.append((book_ID, inl, color))
        best = max([r[1] for r in raw] or [0])
        results = []
        for book_ID, inl, color in raw:
            geo = inl / max(best, 30)
            results.append((book_ID, round(0.75 * geo + 0.25 * color, 3)))
        results.sort(key=lambda r: -r[1])
        return [r for r in results[:top_k] if r[1] >= min_similarity]
