"""Veroku core module: .help with modules and per-command docs."""

import logging

from ..types import Module, command
from ..utils.args import get_args_raw

logger = logging.getLogger(__name__)


class HelpMod(Module):
    """Show help for modules and commands."""

    strings = {
        "name": "Help",
        "_cls_doc": "Shows help for modules and commands",
        "_cmd_doc_help": "[command] - Show help for modules and commands",
        "no_module": "<b>Module not found</b>",
        "commands": "<b>Commands:</b>",
        "core": "Core",
        "external": "External",
        "modules": "<b>Veroku modules</b>",
    }

    @command
    async def help(self, message, args: str):
        """Show help."""
        prefix = self.get_prefix()

        if args:
            await self._modhelp(message, args, prefix)
            return

        lines = []
        for module in self.allmodules.modules:
            name = module.strings.get("name", module.name)
            commands = [
                f"{prefix}{cmd}"
                for cmd in self.allmodules.get_module_commands(module)
            ]
            if commands:
                lines.append(
                    f"▫️ <b>{name}</b> — {', '.join(commands)}"
                )

        await message.reply(
            self.strings["modules"] + "\n\n" + "\n".join(lines)
        )

    async def _modhelp(self, message, args: str, prefix: str) -> None:
        """Help for one command or module."""
        target = args.split()[0].lower().removesuffix(prefix)

        for module in self.allmodules.modules:
            for cmd_name, func in self.allmodules.get_module_commands(
                module
            ).items():
                if cmd_name.lower() == target:
                    doc = self.strings.get(
                        f"_cmd_doc_{cmd_name}"
                    ) or (func.__doc__ or "No description").strip()
                    module_name = module.strings.get("name", module.name)
                    await message.reply(
                        f"<b>{prefix}{cmd_name}</b>\n"
                        f"<b>Module:</b> {module_name}\n\n{doc}"
                    )
                    return

        for module in self.allmodules.modules:
            name = (
                module.strings.get("name", module.name).lower()
            )
            if name == target or module.name.lower() == target:
                cmds = self.allmodules.get_module_commands(module)
                docs = []
                for cmd_name in cmds:
                    doc = module.strings.get(
                        f"_cmd_doc_{cmd_name}"
                    ) or (cmds[cmd_name].__doc__ or "").strip()
                    docs.append(
                        f"<code>{prefix}{cmd_name}</code> — {doc or 'No doc'}"
                    )
                await message.reply(
                    f"<b>{module.strings.get('name', module.name)}</b>\n"
                    f"{module.strings.get('_cls_doc', '')}\n\n"
                    + "\n".join(docs)
                )
                return

        await message.reply(self.strings["no_module"])
