import logging

from veroku.types import Module, command

logger = logging.getLogger(__name__)


class Logs(Module):
    """Stream logs to a VK chat."""

    strings = {
        "name": "logs",
        "_cls_doc": "Stream logs to a VK chat",
        "usage": (
            "Usage:\n"
            ".logsto - bind logs to this chat\n"
            ".logsoff - stop\n"
            ".logsc - create chat for logs"
        ),
        "no_chat": "Run this in the chat you want logs sent to",
        "enabled": "logs -> this chat",
        "disabled": "logs off",
        "created": "chat created, peer {peer}",
    }

    class _Handler(logging.Handler):
        def __init__(self, mod):
            super().__init__(level=logging.WARNING)
            self.mod = mod
            self.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            ))

        def emit(self, record):
            try:
                peer = self.mod._get_peer()
                if peer:
                    text = self.format(record)
                    self.mod._client.vk.send_message_request(peer, text[:4000])
            except Exception:
                pass

    def __init__(self):
        self._handler = None

    def _get_peer(self) -> int | None:
        return self.db.get("veroku.logs", "peer", None)

    @command
    async def logsto(self, message, args: str):
        """Bind logs to the current chat"""
        self.db.set("veroku.logs", "peer", message.peer_id)
        await _a(message, self.strings["enabled"])

    @command
    async def logsoff(self, message, args: str):
        """Disable log forwarding"""
        self.db.set("veroku.logs", "peer", None)
        await _a(message, self.strings["disabled"])

    @command
    async def logsc(self, message, args: str):
        """Create a group chat for logs"""
        title = args or "veroku logs"
        r = self._client.vk.request("messages.createChat", title=title)
        chat_id = r if isinstance(r, int) else r.get("chat_id", r)
        peer = 2000000000 + int(chat_id)
        self.db.set("veroku.logs", "peer", peer)
        await _a(message, self.strings["created"].format(peer=peer))

    async def client_ready(self):
        if self._handler is None:
            self._handler = self._Handler(self)
            logging.getLogger().addHandler(self._handler)
