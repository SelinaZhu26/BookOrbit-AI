"""AuthService - UC-01 Register an Account, UC-02 Log In Using Biometric Authentication."""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .. import clock
from ..ai.biometric import BiometricEngine
from ..errors import BiometricError, NotFoundError, StorageError, ValidationError
from .base import ServiceBase, Session

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


@dataclass
class LoginResult:
    ok: bool
    message: str
    session: Session | None = None
    attempt: int = 0
    locked: bool = False
    score: float | None = None
    retry_capture: bool = False


class AuthService(ServiceBase):
    def __init__(self, store, config, biometric: BiometricEngine):
        super().__init__(store, config)
        self.bio = biometric

    # ================================================================ UC-01
    def validate_registration(self, full_name: str, username: str, email: str) -> dict[str, str]:
        problems: dict[str, str] = {}
        if not (full_name or "").strip() or len(full_name.strip()) > 60:
            problems["full_name"] = "Enter your full name (1-60 characters)"
        if not USERNAME_RE.match(username or ""):
            problems["username"] = "Use 3-20 letters, digits or underscores"
        elif self.users.by_username(username):
            problems["username"] = "That username is taken"
        if not EMAIL_RE.match((email or "").strip()):
            problems["email"] = "Enter a valid email address"
        return problems

    def face_embeddings(self, images: list[np.ndarray]) -> list[np.ndarray]:
        """Exactly one face per sample; raises BiometricError otherwise (UC-01 step 5)."""
        if not images:
            raise BiometricError("Capture a face photo first.", "NO_IMAGE")
        return [self.bio.single_face_embedding(img) for img in images]

    def register(self, full_name: str, username: str, email: str,
                 images: list[np.ndarray]) -> dict:
        problems = self.validate_registration(full_name, username, email)
        if problems:
            raise ValidationError("Please fix the highlighted fields", problems)
        embeddings = self.face_embeddings(images)           # may raise BiometricError
        template = BiometricEngine.build_template(embeddings)

        with self.store.lock:
            if self.users.by_username(username):            # taken while the user was busy
                raise ValidationError("Please fix the highlighted fields",
                                      {"username": "That username is taken"})
            user_ID = self.store.next_id("users", "user_ID", "U-")
            tpl_path = self.save_template(user_ID, template)
            user = {
                "user_ID": user_ID, "username": username.strip(), "full_Name": full_name.strip(),
                "email": email.strip().lower(), "role": "RC", "status": "ACTIVE",
                "balance": 0.0, "warnings": 0, "purchase_Count": 0, "total_Spent": 0.0,
                "promo_Purchases": 0, "promo_Spent": 0.0, "suspension_Reason": None,
                "created_At": clock.now_iso()}
            try:
                self.store.append("users", user)
                self.store.append("biometrics", self._bio_record(user_ID, tpl_path, len(embeddings)))
            except Exception as exc:                        # no half-created account remains
                tpl_path.unlink(missing_ok=True)
                self.store.delete("users", lambda r: r["user_ID"] == user_ID)
                self.store.delete("biometrics", lambda r: r["user_ID"] == user_ID)
                raise StorageError("Could not create the account. Please try again.") from exc
        return user

    def save_template(self, user_ID: str, template: np.ndarray):
        d = self.config.biometrics_dir
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{user_ID}_face.npy"
        np.save(path, template.astype(np.float32))
        return path

    def _bio_record(self, user_ID: str, path, samples: int) -> dict:
        return {"user_ID": user_ID, "template_Path": f"biometrics/{path.name}",
                "detector": self.config.face_detector_file, "embedder": self.config.face_embedder_file,
                "samples": samples, "created_At": clock.now_iso()}

    def enroll(self, user_ID: str, images: list[np.ndarray]) -> None:
        """(Re-)enrol a face template for an existing account (SU tool / seed)."""
        self.users.get(user_ID)
        template = BiometricEngine.build_template(self.face_embeddings(images))
        path = self.save_template(user_ID, template)
        self.store.delete("biometrics", lambda r: r["user_ID"] == user_ID)
        self.store.append("biometrics", self._bio_record(user_ID, path, len(images)))

    def load_template(self, user_ID: str) -> np.ndarray | None:
        rec = self.store.find("biometrics", user_ID=user_ID)
        if not rec:
            return None
        path = self.config.data_dir / rec["template_Path"]
        return np.load(path) if path.exists() else None

    # ================================================================ UC-02
    def _failures(self, username: str) -> list[dict]:
        """Consecutive failed attempts since the last success, newest first."""
        attempts = sorted(self.store.filter("login_attempts", username=username.lower()),
                          key=lambda a: a["attempt_ID"], reverse=True)
        out = []
        for a in attempts:
            if a["success"]:
                break
            out.append(a)
        return out

    def lock_remaining_s(self, username: str) -> int:
        fails = self._failures(username)
        n = self.config.login_max_failures
        if fails and len(fails) % n == 0:
            elapsed = (clock.now() - clock.parse(fails[0]["created_At"])).total_seconds()
            left = self.config.login_lock_minutes * 60 - elapsed
            return max(0, int(left))
        return 0

    def start_sign_in(self, username: str) -> dict:
        user = self.users.by_username(username)
        if not user:
            raise NotFoundError("No account with that username", field="username")
        if self.lock_remaining_s(user["username"]):
            raise BiometricError("Too many attempts. Try again in 5 minutes.", "LOCKED")
        if self.load_template(user["user_ID"]) is None:
            raise BiometricError("Face template missing - please contact a Super-User.", "NO_TEMPLATE")
        return user

    def verify_sign_in(self, username: str, image: np.ndarray) -> LoginResult:
        user = self.start_sign_in(username)
        template = self.load_template(user["user_ID"])
        try:
            score = self.bio.verify(template, image)
        except BiometricError as exc:
            if exc.code == "NO_FACE":                     # not counted as a failure
                return LoginResult(False, "Please capture again - no face was detected.", retry_capture=True)
            raise
        ok = score >= self.config.face_threshold
        self.store.append("login_attempts", {
            "attempt_ID": self.store.next_id("login_attempts", "attempt_ID", "L-", 6),
            "username": user["username"].lower(), "user_ID": user["user_ID"],
            "score": round(score, 4), "success": ok, "created_At": clock.now_iso()})
        if ok:
            session = Session(user_ID=user["user_ID"], role=user["role"],
                              wallet_only=user["status"] == "SUSPENDED")
            msg = ("Your account is suspended - you are in wallet-only mode."
                   if session.wallet_only else f"Welcome back, {user['full_Name'].split()[0]}")
            return LoginResult(True, msg, session=session, score=score)
        fails = len(self._failures(user["username"]))
        n = self.config.login_max_failures
        attempt = fails % n or n
        if attempt == n:
            return LoginResult(False, "Not recognised. Account locked for 5 minutes.",
                               attempt=attempt, locked=True, score=score)
        return LoginResult(False, f"Not recognised - try again (attempt {attempt} of {n})",
                           attempt=attempt, score=score)

    def refresh_session(self, session: Session) -> Session:
        """Role/status may change (promotion, demotion, suspension, reopening)."""
        if session.user_ID is None:
            return session
        try:
            user = self.users.get(session.user_ID)
        except NotFoundError:
            return Session()
        session.role = user["role"]
        session.wallet_only = user["status"] == "SUSPENDED"
        return session
