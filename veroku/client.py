"""Veroku client: wraps vkover into a Hikka-like client with send/edit/reply."""

import asyncio
import logging
import threading
import time

import vkover

logger = logging.getLogger(__name__)


class VerokuMessage:
    """VK message proxy: reply/edit/respond like a Telegram message."""

    def __init__(self, client: "CustomVKClient", peer_id: int, message_id: int,
                 text: str, out: bool = False, from_id: int = 0, date: int = 0,
                 raw: dict | None = None):
        self._client = client
        self.peer_id = peer_id
        self.id = message_id
        self.message_id = message_id
        self.conversation_message_id = 0
        self.text = text
        self.out = out
        self.from_id = from_id
        self.date = date
        self.raw = raw or {}

    async def reply(self, text: str, **kw) -> "VerokuMessage":
        return await self._client.send_message(
            self.peer_id, text, reply_to_cmid=self.conversation_message_id or None,
            **kw,
        )

    async def respond(self, text: str, **kw) -> "VerokuMessage":
        return await self._client.send_message(self.peer_id, text, **kw)

    async def edit(self, text: str, **kw) -> bool:
        return await self._client.edit_message(
            self.peer_id, self.id, text, **kw,
        )

    async def answer(self) -> None:
        await self._client.set_typing(self.peer_id)

    async def delete(self) -> None:
        await self._client.delete_message(self.peer_id, self.id)


class CustomVKClient:
    """High-level VK client for Veroku, wired to the dispatcher loop."""

    def __init__(self, vk: vkover.VKover):
        self.vk = vk
        self.vk_id: int = 0
        self.loop = asyncio.get_event_loop()

    async def authorize(self) -> dict:
        me = self.vk.me
        self.vk_id = me["id"]
        return me

    async def send_message(self, peer_id: int, text: str, **kw) -> VerokuMessage:
        r = await self.loop.run_in_executor(
            None,
            lambda: self.vk.send_message_request(peer_id, text, **kw),
        )
        mid = r if isinstance(r, int) else r.get("response", r)
        return VerokuMessage(self, peer_id, mid if isinstance(mid, int) else 0,
                             text, out=True, from_id=self.vk_id)

    async def edit_message(self, peer_id: int, message_id: int, text: str,
                           **kw) -> bool:
        return await self.loop.run_in_executor(
            None,
            lambda: self.vk.edit_message_request(peer_id, message_id, text, **kw),
        )

    async def delete_message(self, peer_id: int, message_id: int) -> bool:
        return await self.loop.run_in_executor(
            None,
            lambda: self.vk.delete_message_request([message_id]),
        )

    async def set_typing(self, peer_id: int, typing_type: str = "text") -> None:
        await self.loop.run_in_executor(
            None,
            lambda: self.vk.set_typing_request(peer_id, typing_type),
        )

    async def run(self):
        await self.authorize()
        await self.loop.run_in_executor(None, self.vk.run)

