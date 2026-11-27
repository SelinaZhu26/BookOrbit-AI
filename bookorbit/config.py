"""Application configuration.

Every value can be overridden with an environment variable so the same code
runs on a team laptop, in the tests and in the demo without edits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(_env("BOOKORBIT_DATA_DIR", str(PROJECT_ROOT / "data"))))
    models_dir: Path = field(default_factory=lambda: Path(_env("BOOKORBIT_MODELS_DIR", str(PROJECT_ROOT / "models"))))
    seed_texts_dir: Path = PROJECT_ROOT / "seed_texts"

    # --- Local LLM (Ollama) -------------------------------------------------
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.2:1b"))
    llm_timeout_s: float = 30.0          # UC-12: "does not answer within 30 seconds"

    # --- Biometrics (UC-01 / UC-02) ----------------------------------------
    face_detector_file: str = "yolov8n-face.onnx"                 # YOLO face detector
    face_embedder_file: str = "face_recognition_sface_2021dec.onnx"  # face embedding
    face_threshold: float = field(default_factory=lambda: float(_env("BOOKORBIT_FACE_THRESHOLD", "0.40")))
    face_detect_conf: float = 0.45
    register_max_tries: int = 3
    login_max_failures: int = 3
    login_lock_minutes: int = 5
    camera_index: int = field(default_factory=lambda: int(_env("BOOKORBIT_CAMERA", "0")))

    # --- Business rules (spec items 6, 7, 8) -------------------------------
    fine_amount: str = "1.00"
    vip_discount: str = "0.10"
    vip_min_purchases: int = 3      # promoted when purchases  > 3
    vip_min_spent: str = "200.00"   # ... or when amount spent > $200
    rc_max_warnings: int = 2        # suspended when warnings > 2
    taboo_block_over: int = 3       # blocked when taboo words > 3
    list_min_ratings: int = 3       # order lists need > 3 ratings
    no_order_below: float = 2.0
    to_order_above: float = 4.0
    buyer_weight: float = 2.0
    max_deposit: str = "10000.00"
    max_comment_len: int = 1000

    # --- Catalog / search ---------------------------------------------------
    page_size: int = 12
    cover_top_k: int = 5
    cover_min_similarity: float = 0.25

    # --- Web/GUI ------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = field(default_factory=lambda: int(_env("BOOKORBIT_PORT", "5050")))
    secret_key: str = field(default_factory=lambda: _env("BOOKORBIT_SECRET", "bookorbit-local-dev-key"))

    @property
    def covers_dir(self) -> Path:
        return self.data_dir / "covers"

    @property
    def texts_dir(self) -> Path:
        return self.data_dir / "texts"

    @property
    def biometrics_dir(self) -> Path:
        return self.data_dir / "biometrics"

    @property
    def store_info_path(self) -> Path:
        return self.data_dir / "policies.txt"
