from veroku.types import Module, command, watcher


class HelpMod(Module):
    """List available commands."""

    strings = {"name": "Help", "_cls_doc": "List available commands"}

    @command
    async def cmdlist(self, message, args: str):
        lines = ["Available commands:"]
        for name, fn in sorted(self.allmodules.commands.items()):
            doc = (fn.__doc__ or "").strip().splitlines()
            desc = doc[0] if doc else ""
            lines.append(f"• {self.get_prefix()}{name} — {desc}" if desc
                         else f"• {self.get_prefix()}{name}")
        await message.reply("\n".join(lines))
