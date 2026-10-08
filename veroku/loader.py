"""Veroku module loader: discovers, registers and manages modules."""

import importlib.util
import inspect
import logging
import os
import sys

from .types import Module, Strings, get_commands, get_watchers

logger = logging.getLogger(__name__)


class Modules:
    """Module registry: load, register, lookup, commands."""

    def __init__(self, db, client, root: str):
        self.db = db
        self.client = client
        self.root = root
        self.module_dir = os.path.join(os.path.dirname(__file__), "..", "modules")
        self.module_dir = os.path.abspath(self.module_dir)

        self.modules: dict[str, Module] = {}
        self._commands: dict[str, object] = {}
        self._watchers: dict[str, object] = {}
        self._strings: dict[str, Strings] = {}

    async def initialize(self) -> None:
        await self.load_all()

    async def load_all(self) -> None:
        if not os.path.isdir(self.module_dir):
            os.makedirs(self.module_dir, exist_ok=True)
        for name in sorted(os.listdir(self.module_dir)):
            if not name.endswith(".py") or name.startswith("_"):
                continue
            try:
                await self.register_module_file(
                    os.path.join(self.module_dir, name), name[:-3]
                )
            except Exception:
                logger.exception("failed to load module %s", name)

    async def register_module_file(self, path: str, name: str) -> Module:
        spec = importlib.util.spec_from_file_location(f"veroku_modules.{name}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Module) and obj is not Module:
                return await self.register(obj, name)
        raise ValueError(f"no Module subclass in {name}")

    async def register(self, cls: type, name: str) -> Module:
        instance = cls()
        instance.name = name
        instance.strings_obj = Strings(instance)
        instance.internal_init()
        instance.allmodules = self
        await instance.client_ready()
        instance.config_complete()

        self.modules[name] = instance
        self._strings[name] = instance.strings_obj

        for cmd_name, func in get_commands(instance).items():
            self._commands[cmd_name] = func
            logger.debug("registered command .%s from %s", cmd_name, name)

        for w_name, func in get_watchers(instance).items():
            self._watchers[f"{name}.{w_name}"] = func

        return instance

    async def unload_module(self, name: str) -> None:
        if name not in self.modules:
            raise ValueError(f"module {name} not loaded")
        mod = self.modules.pop(name)
        await mod.on_unload()

        for cmd_name in list(self._commands):
            if getattr(self._commands[cmd_name], "__self__", None) is mod:
                del self._commands[cmd_name]
        for w_key in list(self._watchers):
            if w_key.startswith(f"{name}."):
                del self._watchers[w_key]

    def lookup(self, name: str) -> Module:
        if name in self.modules:
            return self.modules[name]
        raise KeyError(f"module {name} not found")

    @property
    def commands(self) -> dict:
        return self._commands

    @property
    def watchers(self) -> dict:
        return self._watchers

    @property
    def strings(self) -> dict:
        return self._strings

    def get_prefix(self) -> str:
        return self.get_prefixes()[0]

    def get_prefixes(self) -> list[str]:
        pref = self.db.get("veroku", "prefix", ".")
        return list(pref) if isinstance(pref, str) else pref
