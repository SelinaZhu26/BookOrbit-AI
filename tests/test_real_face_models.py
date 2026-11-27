"""Real YOLOv8-face + SFace pipeline. Skipped when the models are not downloaded.

Uses images you provide (no faces are shipped with the project):
    BOOKORBIT_TEST_FACE_A   a photo of person A
    BOOKORBIT_TEST_FACE_B   a photo of a different person B
    BOOKORBIT_TEST_NOFACE   a photo with no face (optional)
"""
import os

import cv2
import numpy as np
import pytest

from bookorbit.ai.biometric import BiometricEngine
from bookorbit.config import Config
from bookorbit.errors import BiometricError

cfg = Config()
engine = BiometricEngine(cfg.models_dir, cfg.face_detector_file, cfg.face_embedder_file, cfg.face_threshold)
A, B, NONE = (os.environ.get(k) for k in ("BOOKORBIT_TEST_FACE_A", "BOOKORBIT_TEST_FACE_B", "BOOKORBIT_TEST_NOFACE"))

pytestmark = pytest.mark.skipif(not engine.available, reason="face models not downloaded")


def test_models_load():
    assert engine.available and "ready" in engine.status_text()


def test_no_face_in_blank_image():
    assert engine.detect(np.full((480, 640, 3), 200, np.uint8)) == []
    with pytest.raises(BiometricError) as e:
        engine.single_face_embedding(np.full((480, 640, 3), 200, np.uint8))
    assert e.value.code == "NO_FACE"


@pytest.mark.skipif(not (A and B), reason="set BOOKORBIT_TEST_FACE_A and _B to run")
def test_same_person_accepted_other_person_rejected():
    a, b = cv2.imread(A), cv2.imread(B)
    template = engine.build_template([engine.single_face_embedding(a)])
    h, w = a.shape[:2]
    rotated = cv2.warpAffine(a, cv2.getRotationMatrix2D((w / 2, h / 2), 6, 0.9), (w, h))
    brighter = cv2.convertScaleAbs(a, alpha=1.15, beta=15)
    assert engine.verify(template, rotated) >= cfg.face_threshold
    assert engine.verify(template, brighter) >= cfg.face_threshold
    assert engine.verify(template, b) < cfg.face_threshold
    two = np.hstack([cv2.resize(a, (512, 512)), cv2.resize(b, (512, 512))])
    with pytest.raises(BiometricError) as e:
        engine.single_face_embedding(two)
    assert e.value.code == "MULTI_FACE"


@pytest.mark.skipif(not NONE, reason="set BOOKORBIT_TEST_NOFACE to run")
def test_photo_without_face():
    assert engine.detect(cv2.imread(NONE)) == []
