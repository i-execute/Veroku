"""Veroku security: owner/sudo checks for commands."""

import logging

logger = logging.getLogger(__name__)


class SecurityManager:
    """Checks whether a user may execute commands."""

    def __init__(self, db):
        self._db = db
        self._owner = db.get("veroku", "owner", None)
        self._sudo = db.get("veroku", "sudo", [])

    def check(self, user_id: int) -> bool:
        """True if the user is owner or sudo."""
        return user_id == self._owner or user_id in self._sudo

    def set_owner(self, user_id: int) -> None:
        self._owner = user_id
        self._db.set("veroku", "owner", user_id)

    def add_sudo(self, user_id: int) -> None:
        if user_id not in self._sudo:
            self._sudo.append(user_id)
            self._db.set("veroku", "sudo", self._sudo)

    def remove_sudo(self, user_id: int) -> None:
        if user_id in self._sudo:
            self._sudo.remove(user_id)
            self._db.set("veroku", "sudo", self._sudo)
