"""Veroku core module: settings (.prefix, .verinfo)."""

import time

from ..types import Module, command
from ..utils.args import get_args_raw
from ..utils.git import get_commit_url, get_git_status
from ..utils.other import get_platform, get_uptime_string
from ..utils.veroku import get_version_raw

START_TS = time.time()


class SettingsMod(Module):
    """Settings and info."""

    strings = {
        "name": "Settings",
        "_cls_doc": "Settings and userbot info",
        "_cmd_doc_prefix": "<prefix> - Set command prefix",
        "_cmd_doc_verinfo": " - Show version info",
        "prefix_set": "<b>Prefix set to</b> {}",
        "prefix_invalid": "<b>Prefix must be a single character</b>",
        "verinfo": (
            "<b>Veroku</b> v{}\n"
            "Uptime: {}\n"
            "Platform: {}\n"
            "Commit: {}\n"
            "Repo status: {}"
        ),
    }

    @command
    async def prefix(self, message, args: str):
        """Set command prefix."""
        new_prefix = get_args_raw(message).strip()
        if not new_prefix or len(new_prefix) != 1:
            await message.reply(self.strings["prefix_invalid"])
            return
        self._db.set("veroku", "command_prefix", new_prefix)
        await message.reply(
            self.strings["prefix_set"].format(new_prefix)
        )

    @command
    async def verinfo(self, message, args: str):
        """Show version info."""
        await message.reply(
            self.strings["verinfo"].format(
                get_version_raw(),
                get_uptime_string(START_TS),
                get_platform(),
                get_commit_url(),
                get_git_status(),
            )
        )
