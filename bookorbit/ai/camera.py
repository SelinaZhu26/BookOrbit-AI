"""Local webcam access for face sign-in (UC-01 / UC-02).

The application runs on the user's own computer, so the Python process reads
the camera directly with OpenCV. The GUI shows a live preview (MJPEG stream)
and asks for snapshots. When no camera is connected, ``available()`` is
False and the screens offer "use a photo file" instead.
"""
from __future__ import annotations

import threading
import time

import cv2
import numpy as np


def _quiet(level_name: str = "LOG_LEVEL_SILENT"):
    """OpenCV prints noisy errors while probing for a camera that is not there."""
    try:
        logging = cv2.utils.logging
        old = logging.getLogLevel()
        logging.setLogLevel(getattr(logging, level_name))
        return lambda: logging.setLogLevel(old)
    except AttributeError:                      # very old OpenCV builds
        return lambda: None


class Camera:
    IDLE_RELEASE_S = 20

    def __init__(self, index: int = 0):
        self.index = index
        self._cap = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._last_use = 0.0
        self._thread: threading.Thread | None = None
        self._probe: tuple[float, bool] = (0.0, False)

    def available(self) -> bool:
        checked, ok = self._probe
        if self._cap is not None and self._cap.isOpened():
            return True
        if time.time() - checked < 10:
            return ok
        restore = _quiet()
        try:
            cap = cv2.VideoCapture(self.index)
            ok = bool(cap is not None and cap.isOpened())
            if cap is not None:
                cap.release()
        finally:
            restore()
        self._probe = (time.time(), ok)
        return ok

    def _open(self) -> bool:
        with self._lock:
            self._last_use = time.time()
            if self._cap is not None and self._cap.isOpened():
                return True
            self._cap = cv2.VideoCapture(self.index)
            if not self._cap.isOpened():
                self._cap = None
                return False
            self._thread = threading.Thread(target=self._reader, daemon=True)
            self._thread.start()
            return True

    def _reader(self) -> None:
        while True:
            with self._lock:
                cap = self._cap
                idle = time.time() - self._last_use > self.IDLE_RELEASE_S
                if cap is None:
                    return
                if idle:
                    cap.release()
                    self._cap = None
                    self._frame = None
                    return
            ok, frame = cap.read()
            if ok:
                self._frame = frame
            else:
                time.sleep(0.05)

    def snapshot(self, wait_s: float = 2.0) -> np.ndarray | None:
        if not self._open():
            return None
        deadline = time.time() + wait_s
        while self._frame is None and time.time() < deadline:
            time.sleep(0.05)
        self._last_use = time.time()
        return None if self._frame is None else self._frame.copy()

    def mjpeg(self):
        if not self._open():
            return
        while True:
            self._last_use = time.time()
            frame = self._frame
            if frame is not None:
                ok, jpg = cv2.imencode(".jpg", cv2.flip(frame, 1), [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
            time.sleep(0.08)
