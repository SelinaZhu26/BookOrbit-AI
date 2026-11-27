"""BiometricEngine (YOLO) - face detection, enrolment and verification.

Spec item 4: "a simply yolo-based procedure to train and classify human faces".

Pipeline
  1. Detection: YOLOv8n-face (ONNX, run with OpenCV DNN). It returns face
     boxes and five landmarks (eyes, nose, mouth corners).
  2. Alignment + embedding: the landmarks align the face; SFace turns the
     aligned crop into a 128-number embedding.
  3. Training (enrolment): the template of a user is the normalised mean of
     the embeddings of his/her enrolment samples, saved to
     data/biometrics/<user_ID>_face.npy (we keep embeddings, never raw photos).
  4. Classification (sign-in): cosine similarity between the live embedding
     and the stored template; accepted when >= threshold.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..errors import BiometricError

try:                                   # hide OpenCV's informational DNN warnings
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except AttributeError:
    pass


@dataclass
class Face:
    box: tuple[float, float, float, float]          # x, y, w, h
    landmarks: np.ndarray                           # 5 x 2
    score: float

    def as_sface_row(self) -> np.ndarray:
        """SFace.alignCrop expects the YuNet layout: box, 5 landmarks, score.
        Order: image-left eye, image-right eye, nose, image-left mouth, image-right mouth."""
        lm = self.landmarks.copy()
        eyes = lm[:2][np.argsort(lm[:2, 0])]
        mouth = lm[3:5][np.argsort(lm[3:5, 0])]
        ordered = np.vstack([eyes, lm[2:3], mouth])
        return np.array([*self.box, *ordered.reshape(-1), self.score], dtype=np.float32)


class BiometricEngine:
    INPUT = 640
    REG_MAX = 16

    def __init__(self, models_dir: Path, detector_file: str, embedder_file: str,
                 threshold: float = 0.40, conf: float = 0.45):
        self.models_dir = Path(models_dir)
        self.detector_path = self.models_dir / detector_file
        self.embedder_path = self.models_dir / embedder_file
        self.threshold = threshold
        self.conf = conf
        self._net = None
        self._sface = None
        self._lock = threading.Lock()
        self.load_error: str | None = None
        self._load()

    # ------------------------------------------------------------------ setup
    def _load(self) -> None:
        try:
            if not self.detector_path.exists() or not self.embedder_path.exists():
                raise FileNotFoundError(
                    "Face models missing - run `python tools/download_models.py`")
            self._net = cv2.dnn.readNetFromONNX(str(self.detector_path))
            self._sface = cv2.FaceRecognizerSF.create(str(self.embedder_path), "")
            self._anchors = {}
            for stride in (8, 16, 32):
                n = self.INPUT // stride
                xs, ys = np.meshgrid(np.arange(n) + 0.5, np.arange(n) + 0.5)
                self._anchors[stride] = np.stack([xs, ys], axis=-1).reshape(-1, 2)
            self._project = np.arange(self.REG_MAX, dtype=np.float32)
        except Exception as exc:          # pragma: no cover - depends on install
            self._net = self._sface = None
            self.load_error = str(exc)

    @property
    def available(self) -> bool:
        return self._net is not None and self._sface is not None

    def status_text(self) -> str:
        return "YOLOv8-face + SFace ready" if self.available else f"Face models unavailable ({self.load_error})"

    # ------------------------------------------------------------- detection
    def detect(self, image: np.ndarray) -> list[Face]:
        if not self.available:
            raise BiometricError("Face recognition is not available on this computer.", "MODELS")
        h, w = image.shape[:2]
        scale = min(self.INPUT / h, self.INPUT / w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        padh, padw = (self.INPUT - nh) // 2, (self.INPUT - nw) // 2
        canvas = np.full((self.INPUT, self.INPUT, 3), 114, dtype=np.uint8)
        canvas[padh:padh + nh, padw:padw + nw] = cv2.resize(image, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (self.INPUT, self.INPUT), swapRB=True)
        with self._lock:
            self._net.setInput(blob)
            outs = self._net.forward(self._net.getUnconnectedOutLayersNames())

        boxes, scores, kpts_all = [], [], []
        for pred in outs:
            stride = self.INPUT // pred.shape[2]
            p = pred.transpose(0, 2, 3, 1).reshape(-1, pred.shape[1])
            cls = 1 / (1 + np.exp(-p[:, 64]))
            keep = cls > self.conf
            if not keep.any():
                continue
            p, cls = p[keep], cls[keep]
            anchors = self._anchors[stride][keep]
            dist = p[:, :64].reshape(-1, 4, self.REG_MAX)
            dist = np.exp(dist - dist.max(axis=-1, keepdims=True))
            dist = (dist / dist.sum(axis=-1, keepdims=True)) @ self._project
            x1y1 = (anchors - dist[:, :2]) * stride
            x2y2 = (anchors + dist[:, 2:]) * stride
            kp = p[:, 65:80].reshape(-1, 5, 3)
            kx = (kp[..., 0] * 2.0 + (anchors[:, :1] - 0.5)) * stride
            ky = (kp[..., 1] * 2.0 + (anchors[:, 1:2] - 0.5)) * stride
            for i in range(len(cls)):
                bx1, by1 = (x1y1[i] - [padw, padh]) / scale
                bx2, by2 = (x2y2[i] - [padw, padh]) / scale
                boxes.append([float(bx1), float(by1), float(bx2 - bx1), float(by2 - by1)])
                scores.append(float(cls[i]))
                kpts_all.append(np.stack([(kx[i] - padw) / scale, (ky[i] - padh) / scale], axis=-1))
        if not boxes:
            return []
        idx = cv2.dnn.NMSBoxes(boxes, scores, self.conf, 0.5)
        idx = np.array(idx).reshape(-1)
        faces = [Face(tuple(boxes[i]), kpts_all[i].astype(np.float32), scores[i]) for i in idx]
        # ignore tiny background faces (< 4% of the largest one)
        if faces:
            big = max(f.box[2] * f.box[3] for f in faces)
            faces = [f for f in faces if f.box[2] * f.box[3] >= 0.04 * big]
        return sorted(faces, key=lambda f: -f.box[2] * f.box[3])

    # ------------------------------------------------------------- embedding
    def embed(self, image: np.ndarray, face: Face) -> np.ndarray:
        aligned = self._sface.alignCrop(image, face.as_sface_row())
        with self._lock:
            feat = self._sface.feature(aligned)
        v = np.asarray(feat, dtype=np.float32).reshape(-1)
        return v / (np.linalg.norm(v) + 1e-9)

    def single_face_embedding(self, image: np.ndarray) -> np.ndarray:
        """Exactly one face is required (UC-01 step 5)."""
        faces = self.detect(image)
        if not faces:
            raise BiometricError("No face found - look at the camera and try again.", "NO_FACE")
        if len(faces) > 1:
            raise BiometricError("More than one face found - make sure only your face is visible.", "MULTI_FACE")
        return self.embed(image, faces[0])

    # ---------------------------------------------------- train / classify
    @staticmethod
    def build_template(embeddings: list[np.ndarray]) -> np.ndarray:
        t = np.mean(np.stack(embeddings), axis=0)
        return t / (np.linalg.norm(t) + 1e-9)

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        a = a / (np.linalg.norm(a) + 1e-9)
        b = b / (np.linalg.norm(b) + 1e-9)
        return float(np.dot(a, b))

    def verify(self, template: np.ndarray, image: np.ndarray) -> float:
        """Returns the cosine similarity of the live sample (raises if no face)."""
        faces = self.detect(image)
        if not faces:
            raise BiometricError("No face detected - please capture again.", "NO_FACE")
        # The largest face is the person in front of the camera.
        return self.similarity(template, self.embed(image, faces[0]))


def decode_image(data: bytes) -> np.ndarray:
    """Bytes of a JPG/PNG -> BGR image. Raises BiometricError for unreadable files."""
    arr = np.frombuffer(data or b"", dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR) if arr.size else None
    if img is None:
        raise BiometricError("Please choose a JPG or PNG image.", "BAD_IMAGE")
    return img
