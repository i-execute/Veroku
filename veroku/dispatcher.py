"""Veroku dispatcher: routes VK messages to module commands/watchers."""

import asyncio
import collections
import logging
import re
import time
import traceback

from .client import VerokuMessage
from .security import SecurityManager

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Routes incoming messages to module commands with ratelimit."""

    def __init__(self, modules, client, db):
        self._modules = modules
        self._client = client
        self.client = client
        self._db = db

        self._ratelimit_storage_user = collections.defaultdict(int)
        self._ratelimit_storage_chat = collections.defaultdict(int)
        self._ratelimit_max_user = db.get(__name__, "ratelimit_max_user", 30)
        self._ratelimit_max_chat = db.get(__name__, "ratelimit_max_chat", 100)

        self.security = SecurityManager(db)
        self.check_security = self.security.check
        self._me = self._client.vk_id

    def _ratelimit_exceeded(self, message: VerokuMessage) -> bool:
        user = self._ratelimit_storage_user[message.from_id]
        chat = self._ratelimit_storage_chat[message.peer_id]

        if user > self._ratelimit_max_user or chat > self._ratelimit_max_chat:
            return True

        self._ratelimit_storage_user[message.from_id] += 1
        self._ratelimit_storage_chat[message.peer_id] += 1

        asyncio.get_event_loop().call_later(
            60,
            lambda: self._ratelimit_storage_user.__setitem__(
                message.from_id,
                max(0, self._ratelimit_storage_user[message.from_id] - 1),
            ),
        )
        asyncio.get_event_loop().call_later(
            60,
            lambda: self._ratelimit_storage_chat.__setitem__(
                message.peer_id,
                max(0, self._ratelimit_storage_chat[message.peer_id] - 1),
            ),
        )
        return False

    async def handle_message(self, message: VerokuMessage) -> None:
        try:
            await self._handle_watcher(message)
        except Exception:
            logger.exception("watcher failed")

        prefix = self._modules.get_prefix()
        if not message.text.startswith(tuple(self._modules.get_prefixes())):
            return

        text = message.text
        for p in self._modules.get_prefixes():
            if text.startswith(p):
                text = text[len(p):]
                break

        command = text.split()[0].lower() if text.split() else ""
        args = text[len(command):].strip() if command else ""

        resolved, func = self._modules.dispatch(command)
        if not func:
            return
        command = resolved

        if self._ratelimit_exceeded(message):
            return

        try:
            await func(message, args)
        except Exception:
            logger.exception("command %s failed", command)
            traceback.print_exc()

    async def _handle_watcher(self, message: VerokuMessage) -> None:
        for watcher in self._modules.watchers:
            try:
                await watcher(message)
            except Exception:
                logger.exception("watcher %s failed", getattr(watcher, "__name__", "?"))
