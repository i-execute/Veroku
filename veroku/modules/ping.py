import time

from veroku.types import Module, command, watcher


class Ping(Module):
    """Ping."""

    strings = {"name": "ping", "_cls_doc": "Check bot responsiveness"}

    @command
    async def ping(self, message, args: str):
        start = time.time()
        await message.answer()
        await message.reply(f"pong: {(time.time() - start) * 1000:.0f}ms")
