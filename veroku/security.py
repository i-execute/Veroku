"""Veroku security: bitmask (OWNER/SUDO/...) checks like Feroku."""

import logging
import typing

from .client import VerokuMessage

logger = logging.getLogger(__name__)

OWNER = 1 << 0
SUDO = 1 << 1
GROUP_OWNER = 1 << 3
GROUP_ADMIN = 1 << 10
GROUP_MEMBER = 1 << 11
PM = 1 << 12
EVERYONE = 1 << 13

BITMAP = {
    "OWNER": OWNER,
    "GROUP_OWNER": GROUP_OWNER,
    "GROUP_ADMIN": GROUP_ADMIN,
    "GROUP_MEMBER": GROUP_MEMBER,
    "PM": PM,
    "SUDO": SUDO,
    "EVERYONE": EVERYONE,
}

STRING_BITMASKS = {
    OWNER: "OWNER",
    SUDO: "SUDO",
    GROUP_OWNER: "GROUP_OWNER",
    GROUP_ADMIN: "GROUP_ADMIN",
    GROUP_MEMBER: "GROUP_MEMBER",
    PM: "PM",
    EVERYONE: "EVERYONE",
}


class SecurityManager:
    """Feroku-style security with bitmasks."""

    def __init__(self, db, client=None):
        self._db = db
        self._client = client
        self._owner = db.get("veroku", "owner", None)
        self._sudo = db.get("veroku", "sudo", [])

    @property
    def owner(self):
        return self._owner

    def check(self, user_id: int, level: int = EVERYONE) -> bool:
        """True if the user has the required security level."""
        if user_id == self._owner:
            return True
        if level & SUDO and user_id in self._sudo:
            return True
        if level & (OWNER | SUDO):
            return False
        return bool(level & EVERYONE)

    def check_command(
        self, user_id: int, func: typing.Callable
    ) -> bool:
        level = getattr(func, "security", 0)
        if level == 0:
            level = EVERYONE
        return self.check(user_id, level)

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
