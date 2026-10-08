"""Veroku core module: settings (prefix, addalias, delalias, verinfo)."""

import time

from ..utils import answer as _a
from ..types import Module, command
from ..utils.args import get_args_raw
from ..utils.git import get_commit_url, get_git_status
from ..utils.other import get_platform, get_uptime_string
from ..utils.veroku import get_version_raw

START_TS = time.time()


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class Settings(Module):
    """Control core userbot settings."""

    strings = {
        "name": "settings",
        "what_prefix": "<b>What should the prefix be set to?</b>",
        "prefix_incorrect": "<b>Prefix must be one symbol in length</b>",
        "prefix_set": (
            "<b>Command prefix updated</b>\n"
            "<b>Current:</b> <code>{newprefix}</code>\n"
            "<b>Restore:</b> <code>{newprefix}prefix {oldprefix}</code>"
        ),
        "alias_created": "<b>Alias created. Access it with</b> <code>{}</code>",
        "aliases_created": "<b>Added {count} aliases:</b>\n{}",
        "aliases_created_line": "{} for {}",
        "no_command": "<b>Command</b> <code>{}</code> <b>does not exist</b>",
        "alias_exists": (
            "<b>Alias</b> <code>{alias}</code> "
            "<b>already exists for command</b> <code>{command}</code>"
        ),
        "alias_args": "<b>You must provide a command and the alias for it</b>",
        "delalias_args": "<b>You must provide the alias name</b>",
        "alias_removed": "<b>Alias</b> <code>{}</code> <b>removed</b>.",
        "aliases_removed": "<b>Removed {count} aliases:</b>\n{}",
        "aliases_cleared": "<b>All aliases removed</b>.",
        "no_alias": "<b>Alias</b> <code>{}</code> <b>does not exist</b>",
        "verinfo": (
            "<b>Veroku</b> v{}\n"
            "Uptime: {}\n"
            "Platform: {}\n"
            "Commit: {}\n"
            "Repo status: {}"
        ),
        "_cls_doc": "Control core userbot settings",
        "_cmd_doc_prefix": "<prefix> - Set the command prefix",
        "_cmd_doc_addalias": "Set an alias for a command",
        "_cmd_doc_delalias": "<alias|-c|--clear> - Remove an alias or clear all",
        "_cmd_doc_verinfo": " - Show version info",
    }

    @command
    async def prefix(self, message, args: str):
        """Set the command prefix."""
        if not args:
            await _a(message, self.strings["what_prefix"])
            return

        new_prefix = args.split()[0]
        if len(new_prefix) != 1 or new_prefix.isspace():
            await _a(message, self.strings["prefix_incorrect"])
            return

        old_prefix = _escape(self.get_prefix())
        self._db.set("veroku", "command_prefix", new_prefix)
        await _a(
            message,
            self.strings["prefix_set"].format(
                newprefix=_escape(new_prefix),
                oldprefix=old_prefix,
            ),
        )

    @command
    async def addalias(self, message, args: str):
        """Set an alias for a command."""
        args_raw = get_args_raw(message).strip()
        if not args_raw:
            await _a(message, self.strings["alias_args"])
            return

        parsed_lines = []
        for line in args_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                continue
            alias, command_part = parts[0].lower(), parts[1].strip()
            cmd = command_part.split(maxsplit=1)[0]
            rest = (
                command_part.split(maxsplit=1)[1]
                if len(command_part.split(maxsplit=1)) > 1
                else None
            )
            parsed_lines.append((alias, cmd, rest))

        if not parsed_lines:
            await _a(message, self.strings["alias_args"])
            return

        added = []
        skipped = []
        stored = {**self.get("aliases", {})}

        for alias, cmd, rest in parsed_lines:
            target = f"{cmd} {rest}" if rest else cmd
            if alias in self.allmodules.aliases:
                skipped.append(
                    self.strings["alias_exists"].format(
                        alias=_escape(alias),
                        command=_escape(
                            self.allmodules.aliases[alias]
                        ),
                    )
                )
                continue
            if not self.allmodules.add_alias(alias, cmd, rest):
                await _a(
                    message,
                    self.strings["no_command"].format(_escape(cmd)),
                )
                return
            stored[alias] = target
            added.append((alias, target))

        if added:
            self.set("aliases", stored)

        if len(added) == 1 and not skipped:
            await _a(
                message,
                self.strings["alias_created"].format(_escape(added[0][0])),
            )
            return

        response = []
        if added:
            response.append(
                self.strings["aliases_created"].format(
                    count=len(added),
                    aliases="\n".join(
                        self.strings["aliases_created_line"].format(
                            _escape(alias), _escape(target)
                        )
                        for alias, target in added
                    ),
                )
            )
        response.extend(skipped)
        await _a(message, "\n\n".join(response))

    @command
    async def delalias(self, message, args: str):
        """Remove an alias or clear all."""
        args_raw = get_args_raw(message).strip()
        if not args_raw:
            await _a(message, self.strings["delalias_args"])
            return

        if args_raw in {"-c", "--clear"}:
            self.allmodules.aliases.clear()
            self.set("aliases", {})
            await _a(message, self.strings["aliases_cleared"])
            return

        aliases = [
            a.lower().strip()
            for a in args_raw.replace(",", " ").split()
            if a.strip()
        ]

        removed = []
        missed = []
        current = self.get("aliases", {})

        for alias in aliases:
            if not self.allmodules.remove_alias(alias):
                missed.append(alias)
                continue
            current.pop(alias, None)
            removed.append(alias)

        if removed:
            self.set("aliases", current)

        if len(removed) == 1 and not missed:
            await _a(
                message,
                self.strings["alias_removed"].format(_escape(removed[0])),
            )
            return

        response = []
        if removed:
            response.append(
                self.strings["aliases_removed"].format(
                    count=len(removed),
                    aliases=_escape(", ".join(removed)),
                )
            )
        response.extend(
            self.strings["no_alias"].format(_escape(a)) for a in missed
        )
        await _a(message, "\n\n".join(response))

    @command
    async def verinfo(self, message, args: str):
        """Show version info."""
        await _a(
            message,
            self.strings["verinfo"].format(
                get_version_raw(),
                get_uptime_string(START_TS),
                get_platform(),
                get_commit_url(),
                get_git_status(),
            ),
        )
