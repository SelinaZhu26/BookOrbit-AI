"""StatusManager - every role/status change goes through here and is written
to status_changes.txt (VIP promotion, VIP demotion, suspension, reopening)."""
from __future__ import annotations

from .. import clock
from .base import ServiceBase


class StatusManager(ServiceBase):
    def _log(self, before: dict, after: dict, reason: str, by: str) -> None:
        self.store.append("status_changes", {
            "change_ID": self.store.next_id("status_changes", "change_ID", "S-"),
            "user_ID": after["user_ID"],
            "from_Role": before["role"], "to_Role": after["role"],
            "from_Status": before["status"], "to_Status": after["status"],
            "reason": reason, "by": by, "created_At": clock.now_iso()})

    def promote_to_vip(self, user: dict, reason: str) -> dict:
        before = dict(user)
        user["role"] = "VC"
        self.users.save(user)
        self._log(before, user, reason, "SYSTEM")
        return user

    def demote_to_rc(self, user: dict, reason: str) -> dict:
        before = dict(user)
        user["role"] = "RC"
        user["promo_Purchases"] = 0        # counters restart after a demotion (UC-11)
        user["promo_Spent"] = 0.0
        self.users.save(user)
        self._log(before, user, reason, "SYSTEM")
        return user

    def suspend(self, user: dict, reason: str, by: str = "SYSTEM") -> dict:
        before = dict(user)
        user["status"] = "SUSPENDED"
        user["suspension_Reason"] = reason
        self.users.save(user)
        self._log(before, user, reason, by)
        return user

    def reopen(self, user: dict, by: str) -> dict:
        before = dict(user)
        user["status"] = "ACTIVE"
        user["warnings"] = 0
        user["suspension_Reason"] = None
        self.users.save(user)
        self._log(before, user, "Reopened by Super-User", by)
        return user

    def history(self, user_ID: str) -> list[dict]:
        return sorted(self.store.filter("status_changes", user_ID=user_ID),
                      key=lambda r: r["created_At"], reverse=True)
