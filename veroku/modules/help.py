"""Veroku core module: help (Feroku-style listing)."""

import difflib

from ..utils.messages import answer as _a
from ..types import Module, command

CORE_EMOJI = "🔵"
PLAIN_EMOJI = "▫"
COMMAND_EMOJI = "→"


class Help(Module):
    """Shows help for modules and commands."""

    strings = {
        "name": "help",
        "undoc": "No docs",
        "all_header": "<b>Available {} modules</b>",
        "no_module": "<b>Module not found</b>",
        "not_exact": "<i>An exact command match was not found.</i>",
        "core_notice": "<i>Core commands</i>",
        "partial_load": "<i>Modules are still loading.</i>",
        "_cmd_doc_help": "[module] - Show help for modules and commands",
        "_cls_doc": "Shows help for modules and commands",
    }

    def _module_emoji(self, module) -> str:
        return CORE_EMOJI if self._is_core(module) else PLAIN_EMOJI

    def _is_core(self, module) -> bool:
        return str(getattr(module, "__origin__", "")).startswith(
            self.allmodules.module_dir
        ) or str(getattr(module, "__origin__", "")).startswith("<core")

    def find_aliases(self, command: str) -> list:
        aliases = []
        _command = self.allmodules.commands.get(command)
        if _command is None:
            return []
        if getattr(_command, "alias", None) and not (
            aliases := getattr(_command, "aliases", None)
        ):
            aliases = [_command.alias]
        return aliases or []

    @command
    async def help(self, message, args: str):
        """Show help."""
        prefix = self.get_prefix()

        only_core = False
        if "-c" in args:
            args = args.replace(" -c", "").replace("-c", "")
            only_core = True

        if args:
            await self._modhelp(message, args.strip(), prefix)
            return

        core_ = []
        plain_ = []
        for module in self.allmodules.modules:
            name = module.strings.get("name", module.name)
            core = self._is_core(module)
            commands = list(
                self.allmodules.get_module_commands(module)
            )
            if not commands:
                (core_ if core else plain_).append(
                    f"{self._module_emoji(module)} <code>{name}</code>"
                )
                continue
            tmp = f"{self._module_emoji(module)} <code>{name}</code>"
            tmp += ": ( " + " | ".join(commands) + " )"
            (core_ if core else plain_).append(tmp)

        core_.sort(key=str.lower)
        plain_.sort(key=str.lower)
        entries = (core_ + plain_) if only_core else (core_ + plain_)

        await _a(
            message,
            self.strings["all_header"].format(len(entries))
            + "\n"
            + "\n".join(entries),
        )

    async def _modhelp(self, message, args: str, prefix: str) -> None:
        """Help for one module or command."""
        target = args.split()[0].lower()

        module = self.allmodules.lookup(target)
        if module is True or not module:
            module = None
        exact = bool(module)

        if not module:
            resolved, func = self.allmodules.dispatch(target)
            if func:
                module = getattr(func, "__self__", None)

        if not module:
            modules = sorted(
                [m.strings.get("name", m.name) for m in self.allmodules.modules],
                key=lambda x: difflib.SequenceMatcher(
                    None, target, x.lower()
                ).ratio(),
            )
            if modules:
                candidate = self.allmodules.lookup(modules[-1])
                if candidate is not True and candidate:
                    module = candidate
            exact = False

        if not module:
            await _a(message, self.strings["no_module"])
            return

        name = module.strings.get("name", module.name)
        reply = f"<b>{name}</b>:"
        if module.__class__.__doc__:
            reply += f"\n<i>{module.__class__.__doc__.strip()}</i>\n"

        lines = []
        for cmd_name, func in self.allmodules.get_module_commands(module).items():
            aliases = self.find_aliases(cmd_name)
            alias_txt = (
                " ({})".format(
                    ", ".join(
                        f"<code>{prefix}{a}</code>" for a in aliases
                    )
                )
                if aliases
                else ""
            )
            doc = module.strings.get(
                f"_cmd_doc_{cmd_name}"
            ) or (func.__doc__ or self.strings["undoc"]).strip()
            lines.append(
                f"{COMMAND_EMOJI} <code>{prefix}{cmd_name}</code>"
                f"{alias_txt} {doc}"
            )

        reply += "\n" + "\n".join(lines)
        if self._is_core(module):
            reply += f"\n{self.strings['core_notice']}"
        if not exact:
            reply += f"\n{self.strings['not_exact']}"
        await _a(message, reply)
