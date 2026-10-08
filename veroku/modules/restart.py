"""Veroku core module: .rst restart."""

from .._internal import restart
from ..types import Module, command


class RestartMod(Module):
    """Restart userbot."""

    strings = {
        "name": "Restart",
        "_cls_doc": "Restart Veroku",
        "_cmd_doc_rst": " - Restart Veroku",
        "restarting": "Restarting Veroku...",
    }

    @command
    async def rst(self, message, args: str):
        """Restart the userbot."""
        await message.reply(self.strings["restarting"])
        restart()
