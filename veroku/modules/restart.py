"""Veroku core module: restart."""

import os
import sys

from ..utils.messages import answer as _a
from ..types import Module, command


class Restart(Module):
    """Restart the userbot."""

    strings = {
        "name": "restart",
        "restarting": "<i>Reiniciando…</i>",
        "restarted": "<b>Successfully restarted!</b>\n<b>Uptime:</b> <code>{uptime}</code>",
        "_cmd_doc_restart": "Restart the userbot",
        "_cls_doc": "Restart the userbot",
    }

    @command
    async def restart(self, message, args: str):
        """Restart the userbot."""
        await _a(message, self.strings["restarting"])
        os.execv(sys.executable, [sys.executable] + sys.argv)
