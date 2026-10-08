"""Veroku core module: self-test (ping)."""

import time

from ..utils.messages import answer as _a
from ..types import Module, command


class Tester(Module):
    """Perform operations based on userbot self-testing."""

    strings = {
        "name": "tester",
        "no_module": "<b>Module not found</b>",
        "pong": "🫀 <b>Pong</b>\n<code>{ping} ms</code>",
        "_cmd_doc_ping": "Measure userbot response time",
        "_cls_doc": "Perform operations based on userbot self-testing",
    }

    @command
    async def ping(self, message, args: str):
        """Measure userbot response time."""
        start = time.monotonic()
        await _a(message, self.strings["pong"].format(ping="…"))
        rtt = (time.monotonic() - start) * 1000
        await _a(message, self.strings["pong"].format(
            ping=f"{rtt:.0f}",
        ))
