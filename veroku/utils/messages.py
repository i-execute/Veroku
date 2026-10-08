"""Veroku utils: message answering like Feroku utils.answer."""

import typing

if typing.TYPE_CHECKING:
    from ..client import VerokuMessage


async def answer(message: "VerokuMessage", text: str, **kw) -> "VerokuMessage":
    """Edit own messages, send new otherwise (Feroku-style)."""
    if getattr(message, "out", False):
        await message.edit(text, **kw)
        return message
    return await message.reply(text, **kw)
