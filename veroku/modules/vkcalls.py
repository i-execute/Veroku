from veroku.types import Module, command
from veroku.utils import chunks, get_args_raw


class VKCallsMod(Module):
    """VK calls manager: create, list, finish — via local cache."""

    strings = {
        "name": "VKCalls",
        "created": (
            "Call created\n"
            "Call ID: {call_id}\n"
            "Join link: {join_link}\n"
            "Short ID: {short_id}\n"
            "Short password: {short_password}\n"
            "Short link: {short_link}"
        ),
        "failed": "Failed to create call: {error}",
        "finished": "Call finished: {call_id}",
        "unknown": "Unknown call: {call_id}",
        "active": "Active calls ({count}):\n{list}",
        "no_active": "No active calls",
        "usage": (
            "Usage:\n"
            ".vkcall create [group_id]\n"
            ".vkcall list\n"
            ".vkcall kill <call_id>"
        ),
        "no_args": "Usage: .vkcall kill <call_id>",
    }

    def __init__(self):
        self._cache = None

    async def client_ready(self):
        self._cache = self._client.vk.calls(db=self.db)

    @command
    async def vkcall(self, message, args: str):
        """VK calls manager: create/list/kill"""
        if not args:
            await message.reply(self.strings["usage"])
            return

        sub, rest = (args.split(maxsplit=1) + [""])[:2]
        sub = sub.lower()

        if sub == "create":
            await self._create(message, rest)
        elif sub == "list":
            await self._list(message)
        elif sub == "kill":
            await self._kill(message, rest.strip())
        else:
            await message.reply(self.strings["usage"])

    async def _create(self, message, group_arg: str):
        group_id = int(group_arg) if group_arg.strip().isdigit() else None
        try:
            resp = self._client.vk.create_web_call_request(group_id)
            entry = self._cache.add(resp)
        except Exception as e:
            await message.reply(self.strings["failed"].format(error=str(e)[:200]))
            return

        sc = entry["short_credentials"]
        await message.reply(self.strings["created"].format(
            call_id=entry["call_id"],
            join_link=entry["join_link"] or "?",
            short_id=sc.get("id", "N/A"),
            short_password=sc.get("password", "N/A"),
            short_link=sc.get("link_with_password", "N/A"),
        ))

    async def _list(self, message):
        calls = self._cache.all()
        if not calls:
            await message.reply(self.strings["no_active"])
            return
        lines = [
            f"{c['call_id']} — {c['short_credentials'].get('id', c['call_id'][:8])}"
            for c in calls
        ]
        for chunk in chunks(self.strings["active"].format(
                count=len(calls), list="\n".join(lines))):
            await message.reply(chunk)

    async def _kill(self, message, call_id: str):
        if not call_id:
            await message.reply(self.strings["no_args"])
            return
        if self._cache.get(call_id) is None:
            await message.reply(self.strings["unknown"].format(call_id=call_id))
            return
        try:
            self._cache.finish(call_id)
        except Exception as e:
            await message.reply("failed: " + str(e)[:200])
            return
        await message.reply(self.strings["finished"].format(call_id=call_id))
