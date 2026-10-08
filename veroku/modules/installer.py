"""Veroku core module: .lm/.dlm/.ulm/.rst module manager (no inline)."""

import logging

import httpx

from ..utils.messages import answer as _a
from ..types import Module, command
from ..utils.args import get_args_raw

logger = logging.getLogger(__name__)


class Installer(Module):
    """Load, download, unload and restart-with-modules."""

    strings = {
        "name": "installer",
        "_cls_doc": "Manage modules",
        "_cmd_doc_lm": "[reply to source] - Load module from replied text",
        "_cmd_doc_dlm": "[url] - Load module from URL",
        "_cmd_doc_ulm": "<module> - Unload module",
        "_cmd_doc_rst": "<module> [args] - Set command alias",
        "_cmd_doc_ullm": "Unload all non-core modules",
        "loading": "Loading module...",
        "loaded": "<b>Loaded</b> {}",
        "no_class": "<b>Specify module to unload</b>",
        "not_found": "<b>Module not found</b>",
        "unloaded": "<b>Unloaded</b> {}",
        "no_source": "<b>Reply to module source code</b>",
        "bad_source": "<b>Source contains no module</b>",
        "no_url": "<b>Specify URL</b>",
        "no_module": "<b>Module not found at URL</b>",
        "core_protected": "<b>Core module, can't unload</b>",
        "unloaded_all": "<b>Unloaded</b> <code>{}</code> modules",
        "alias_saved": "<b>Alias</b> <code>{}</code> → <code>{}</code>",
        "alias_removed": "<b>Alias</b> <code>{}</code> removed",
        "alias_bad": "<b>Can't create alias</b>",
        "alias_not_found": "<b>Alias not found</b>",
        "no_alias_args": "<b>Usage: .rst <alias> <command> [args]</b>",
    }

    @command
    async def lm(self, message, args: str):
        """Load module from replied message text."""
        if message.reply_text:
            source = message.reply_text
        elif args:
            source = args
        else:
            await _a(message, self.strings["no_source"])
            return

        await _a(message, self.strings["loading"])
        try:
            module = await self.allmodules.load_source(source)
            await _a(message, self.strings["loaded"].format(module.name))
        except Exception as e:
            await _a(message, f"{self.strings['bad_source']}: {e}")

    @command
    async def dlm(self, message, args: str):
        """Load module from URL."""
        url = get_args_raw(message).strip()
        if not url or not url.startswith("http"):
            await _a(message, self.strings["no_url"])
            return

        await _a(message, self.strings["loading"])
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                source = resp.text
        except Exception as e:
            await _a(message, f"{self.strings['no_module']}: {e}")
            return

        try:
            module = await self.allmodules.load_source(source, origin=url)
            await _a(message, self.strings["loaded"].format(module.name))
        except Exception as e:
            await _a(message, f"{self.strings['bad_source']}: {e}")

    @command
    async def ulm(self, message, args: str):
        """Unload module by name."""
        if not args:
            await _a(message, self.strings["no_class"])
            return

        module_name = args.split()[0]
        module = self.lookup(module_name)
        if not module or module is True:
            await _a(message, self.strings["not_found"])
            return

        origin = getattr(module, "__origin__", "")
        if origin and "veroku/modules" in str(origin):
            await _a(message, self.strings["core_protected"])
            return

        try:
            await self.allmodules.unload_module(module.name)
            await _a(message, self.strings["unloaded"].format(module.name))
        except Exception as e:
            await _a(message, f"Error: {e}")

    @command
    async def ullm(self, message, args: str):
        """Unload all non-core modules."""
        removed = 0
        for module in list(self.allmodules.modules):
            origin = str(getattr(module, "__origin__", ""))
            if "veroku/modules" in origin or origin.startswith("<core"):
                continue
            try:
                await self.allmodules.unload_module(module.name)
                removed += 1
            except Exception:
                logger.exception("unload failed")
        await _a(message, self.strings["unloaded_all"].format(removed))

    @command
    async def rst(self, message, args: str):
        """Set or remove a command alias."""
        parts = (args or "").split()
        if not parts:
            await _a(message, self.strings["no_alias_args"])
            return

        alias = parts[0].lower().strip(self.get_prefix())
        if len(parts) == 1:
            if self.allmodules.remove_alias(alias):
                await _a(
                    message, self.strings["alias_removed"].format(alias)
                )
            else:
                await _a(message, self.strings["alias_not_found"])
            return

        cmd = parts[1].lstrip(self.get_prefix()).lower()
        extra = " ".join(parts[2:]) or None
        if self.allmodules.add_alias(alias, cmd, extra):
            await _a(
                message,
                self.strings["alias_saved"].format(
                    alias, f"{cmd} {extra}".strip()
                ),
            )
        else:
            await _a(message, self.strings["alias_bad"])
