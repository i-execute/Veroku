"""Veroku core module: per-module info (.cfg module shows options)."""

from ..utils.messages import answer as _a
from ..types import Module, command


class Config(Module):
    """Command configurator for Veroku modules."""

    strings = {
        "name": "config",
        "args": "<b>Invalid arguments</b>",
        "no_option": "<b>Option not found</b>",
        "configure": "<b>Choose a module to configure</b>\n{}",
        "configuring_mod": "<b>Config options of module</b> <code>{}</code>\n\n{}",
        "no_config": "<b>Module</b> <code>{}</code> <b>has no config options</b>",
        "option_saved": "<b>Option</b> <code>{}</code> <b>of module</b> <code>{}</code><b> saved!</b>\n<b>Current: {}</b>",
        "option_reset": "<b>Option</b> <code>{}</code> <b>of module</b> <code>{}</code> <b>has been reset to default</b>\n<b>Current: {}</b>",
        "configuring_option": "<b>Configuring option</b> <code>{}</code> <b>of module</b> <code>{}</code>\n<i>{}</i>\n\n<b>Default:</b> <code>{}</code>\n<b>Current:</b> <code>{}</code>\n\n<i>Set:</i> <code>.cfg {} {} &lt;value&gt;</code>",
        "_cmd_doc_cfg": "[module] [option] [value] - Show or configure module options",
        "_cls_doc": "Command configurator for Veroku modules",
    }

    @command
    async def cfg(self, message, args: str):
        """Show or configure module options."""
        raw = (args or "").strip()
        if not raw:
            await self._list_modules(message)
            return

        parts = raw.split(maxsplit=2)
        module = self.lookup(parts[0])
        if not module or module is True:
            await self._list_modules(message)
            return

        conf = getattr(module, "config", None)
        if not conf or not hasattr(conf, "__contains__") or not list(conf):
            await _a(
                message,
                self.strings["no_config"].format(module.name),
            )
            return

        if len(parts) == 1:
            await self._list_options(message, module, conf)
            return

        option = parts[1]
        if option not in conf:
            await _a(message, self.strings["no_option"])
            return

        if len(parts) == 2:
            await _a(
                message,
                self.strings["configuring_option"].format(
                    option,
                    module.name,
                    conf.get_doc(option),
                    conf.getdef(option),
                    conf[option],
                    module.name,
                    option,
                ),
            )
            return

        value = parts[2]
        reset = value.lower() in ("reset", "default")
        if reset:
            conf.reset(option)
        else:
            conf[option] = self._coerce(value, conf.getdef(option))

        self._db.set(
            module.__class__.__name__,
            "__config__",
            {k: v.value for k, v in conf.items()},
        )

        await _a(
            message,
            self.strings["option_reset" if reset else "option_saved"].format(
                option, module.name, conf[option]
            ),
        )

    def _coerce(self, value: str, default):
        if isinstance(default, bool):
            return value.lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            try:
                return int(value)
            except ValueError:
                return value
        if isinstance(default, list):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    async def _list_modules(self, message):
        entries = []
        for module in self.allmodules.modules:
            conf = getattr(module, "config", None)
            if conf and hasattr(conf, "__contains__") and list(conf):
                entries.append(f"→ <code>{module.name}</code>")
        await _a(
            message,
            self.strings["configure"].format(
                "\n".join(entries) or "<i>No configurable modules</i>"
            ),
        )

    async def _list_options(self, message, module, conf):
        lines = []
        for option, value in conf.items():
            lines.append(
                f"→ <code>{option}</code> = <code>{value.value}</code>\n  <i>{value.doc}</i>"
            )
        await _a(
            message,
            self.strings["configuring_mod"].format(
                module.name, "\n".join(lines)
            ),
        )
