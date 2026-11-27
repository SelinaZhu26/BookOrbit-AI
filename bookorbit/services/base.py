"""Shared helpers for the services: session object, user lookups, logging."""
from __future__ import annotations

from dataclasses import dataclass

from .. import clock
from ..config import Config
from ..errors import NotFoundError, PermissionDenied
from ..persistence.filestore import FileStore

ROLES = ("VS", "RC", "VC", "SU")
ROLE_NAMES = {"VS": "Visitor", "RC": "Registered Customer", "VC": "VIP Customer", "SU": "Super-User"}


@dataclass
class Session:
    """Who is using the application (Section 4.1 Global Data)."""
    user_ID: str | None = None
    role: str = "VS"
    wallet_only: bool = False
    visitor_key: str | None = None   # lets a visitor edit their own review in this session

    @property
    def is_visitor(self) -> bool:
        return self.user_ID is None

    @property
    def is_customer(self) -> bool:
        return self.role in ("RC", "VC")


class Users:
    def __init__(self, store: FileStore):
        self.store = store

    def get(self, user_ID: str) -> dict:
        u = self.store.find("users", user_ID=user_ID)
        if not u:
            raise NotFoundError("Account not found")
        return u

    def by_username(self, username: str) -> dict | None:
        uname = (username or "").strip().lower()
        for u in self.store.read_all("users"):
            if u["username"].lower() == uname:
                return u
        return None

    def save(self, user: dict) -> dict:
        return self.store.update("users", "user_ID", user["user_ID"], dict(user))


def require_role(session: Session, *roles: str) -> None:
    if session.role not in roles:
        raise PermissionDenied("You do not have permission to access this page.")


def log_admin(store: FileStore, admin_ID: str, action: str, target: str, details: str = "") -> None:
    store.append("admin_actions", {
        "action_ID": store.next_id("admin_actions", "action_ID", "A-"),
        "admin_ID": admin_ID, "action": action, "target": target,
        "details": details, "created_At": clock.now_iso()})


class ServiceBase:
    def __init__(self, store: FileStore, config: Config):
        self.store = store
        self.config = config
        self.users = Users(store)
