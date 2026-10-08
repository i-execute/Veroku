"""Veroku core module: .lm/.dlm/.ulm module manager (no inline)."""

import logging
import re

from ..types import Module, command
from ..utils.args import get_args_raw

logger = logging.getLogger(__name__)


class InstallerMod(Module):
    """Load, download and unload modules."""

    strings = {
        "name": "Installer",
        "_cls_doc": "Manage modules",
        "_cmd_doc_lm": "[reply to source] - Load module from replied text",
        "_cmd_doc_dlm": "[url] - Load module from URL",
        "_cmd_doc_ulm": "<module> - Unload module",
        "loading": "Loading module...",
        "loaded": "<b>Loaded</b> {}",
        "no_class": "<b>Specify module to unload</b>",
        "not_found": "<b>Module not found</b>",
        "unloaded": "<b>Unloaded</b> {}",
        "no_source": "<b>Reply to module source code</b>",
        "bad_source": "<b>Source contains no module</b>",
        "no_url": "<b>Specify URL</b>",
        "no_module": "<b>Module not found at URL</b>",
        "bad_unicode": "<b>Invalid encoding</b>",
        "core_protected": "<b>Core module, can't unload</b>",
    }

    @command
    async def lm(self, message, args: str):
        """Load module from replied message text."""
        if message.reply_text:
            source = message.reply_text
        elif args:
            source = args
        else:
            await message.reply(self.strings["no_source"])
            return

        await message.reply(self.strings["loading"])
        try:
            module = await self.allmodules.load_source(source)
            await message.reply(
                self.strings["loaded"].format(module.name)
            )
        except Exception as e:
            await message.reply(f"{self.strings['bad_source']}: {e}")

    @command
    async def dlm(self, message, args: str):
        """Load module from URL."""
        import httpx

        url = get_args_raw(message).strip()
        if not url or not url.startswith("http"):
            await message.reply(self.strings["no_url"])
            return

        await message.reply(self.strings["loading"])
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                source = resp.text
        except Exception as e:
            await message.reply(f"{self.strings['no_module']}: {e}")
            return

        try:
            module = await self.allmodules.load_source(source, origin=url)
            await message.reply(
                self.strings["loaded"].format(module.name)
            )
        except Exception as e:
            await message.reply(f"{self.strings['bad_source']}: {e}")

    @command
    async def ulm(self, message, args: str):
        """Unload module by name."""
        if not args:
            await message.reply(self.strings["no_class"])
            return

        module_name = args.split()[0]
        try:
            module = self.lookup(module_name)
        except KeyError:
            await message.reply(self.strings["not_found"])
            return

        origin = getattr(module, "__origin__", "")
        if origin and "veroku/modules" in str(origin):
            await message.reply(self.strings["core_protected"])
            return

        try:
            await self.allmodules.unload_module(module.name)
            await message.reply(
                self.strings["unloaded"].format(module.name)
            )
        except Exception as e:
            await message.reply(f"Error: {e}")
