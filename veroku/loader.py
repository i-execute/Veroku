"""Veroku module loader: discovers, registers and manages modules."""

import importlib
import importlib.util
import inspect
import logging
import os
import pkgutil
import re
import sys

from .types import (
    Module,
    StringLoader,
    Strings,
    get_commands,
    get_watchers,
)

logger = logging.getLogger(__name__)

MODULES_NAME = "modules"
LOADED_MODULES_NAME = "loaded_modules"


def _iter_module_files(dirname: str) -> list[str]:
    if not os.path.isdir(dirname):
        return []
    return sorted(
        os.path.join(dirname, entry.name)
        for entry in os.scandir(dirname)
        if entry.is_file()
        and entry.name.endswith(".py")
        and not entry.name.startswith("_")
    )


def save_module_source(source: str, classname: str) -> str:
    """Save external module source to loaded_modules dir."""
    dirname = os.path.join(
        os.environ.get("VEROKU_ROOT", os.path.expanduser("~/.veroku")),
        LOADED_MODULES_NAME,
    )
    os.makedirs(dirname, exist_ok=True)
    path = os.path.join(dirname, f"{classname}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    return path


class Modules:
    """Module registry: load, register, lookup, aliases, commands."""

    def __init__(self, db, client, root: str):
        self.db = db
        self.client = client
        self.root = root

        self.commands = {}
        self.aliases = {}
        self.modules: list[Module] = []
        self.watchers = []
        self._core_commands = []

        self.module_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), MODULES_NAME
        )
        self.loaded_modules_dir = os.path.join(root, LOADED_MODULES_NAME)
        self.user_modules_dir = os.path.join(root, "Modules")
        os.makedirs(self.loaded_modules_dir, exist_ok=True)

    async def initialize(self) -> list[Module]:
        loaded = []
        core_pkg = f"{__package__}.{MODULES_NAME}"
        for _, name, _ in pkgutil.iter_modules(
            [self.module_dir]
        ):
            try:
                mod = importlib.import_module(f"{core_pkg}.{name}")
                for _, obj in inspect.getmembers(mod, inspect.isclass):
                    if issubclass(obj, Module) and obj is not Module:
                        loaded.append(
                            await self.register(obj, name, self.module_dir)
                        )
                        break
            except Exception:
                logger.exception("failed to load core module %s", name)
        loaded += await self._register_modules(
            _iter_module_files(self.loaded_modules_dir)
        )
        loaded += await self._register_modules(
            _iter_module_files(self.user_modules_dir)
        )
        return loaded

    async def _register_modules(self, paths: list[str]) -> list[Module]:
        loaded = []
        for path in paths:
            try:
                loaded.append(await self.register_module(path))
            except Exception:
                logger.exception("failed to load module %s", path)
        return loaded

    async def register_module(self, path: str) -> Module:
        name = os.path.basename(path)[:-3]
        core = self.module_dir in os.path.abspath(path)
        spec = importlib.util.spec_from_file_location(
            f"veroku_modules.{name}", path
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Module) and obj is not Module:
                instance = await self.register(obj, name, path)
                return instance
        raise ValueError(f"no Module subclass in {name}")

    async def load_source(
        self, source: str, origin: str = "<string>", save_fs: bool = True
    ) -> Module:
        """Load module from source string (dlm/lm)."""
        classname_match = re.search(
            r"class\s+(\w+)\s*\(\s*(?:veroku\.types\.)?Module\s*\)", source
        )
        if not classname_match:
            raise ValueError("no Module subclass found in source")

        spec = importlib.util.spec_from_loader(
            f"veroku_modules.{classname_match.group(1)}",
            StringLoader(source, origin),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Module) and obj is not Module:
                if save_fs:
                    save_module_source(source, obj.__name__)
                return await self.register(obj, obj.__name__, origin)

        raise ValueError("no Module subclass found in source")

    async def register(
        self, cls: type, name: str, origin: str
    ) -> Module:
        core = str(origin).startswith(self.module_dir)

        old = next(
            (m for m in self.modules if m.__class__ is cls), None
        )
        if old is not None:
            await self.unload_module(old.name)

        instance = cls()
        instance.name = name
        instance.__origin__ = origin
        instance.strings_obj = Strings(instance)
        instance.allmodules = self
        instance.internal_init()
        await instance.client_ready()
        instance.config_complete()

        self.modules.append(instance)
        self.register_commands(instance)
        self.register_watchers(instance)

        if core:
            self._core_commands += list(
                map(lambda x: x.lower(), instance.commands)
            )

        return instance

    def register_commands(self, instance: Module) -> None:
        for cmd_name, func in get_commands(instance).items():
            self.commands[cmd_name.lower()] = func

    def register_watchers(self, instance: Module) -> None:
        for _, func in get_watchers(instance).items():
            self.watchers.append(func)

    def add_aliases(self, aliases: dict) -> None:
        self.aliases.update(aliases)

    async def unload_module(self, classname: str) -> Module:
        module = self.lookup(classname)
        await module.on_unload()
        self.modules.remove(module)

        for cmd_name in list(self.commands):
            if getattr(self.commands[cmd_name], "__self__", None) is module:
                del self.commands[cmd_name]

        self.watchers = [
            w
            for w in self.watchers
            if getattr(w, "__self__", None) is not module
        ]
        return module

    def lookup(self, name: str) -> Module:
        for module in self.modules:
            if name in (module.name, module.__class__.__name__):
                return module
        raise KeyError(f"module {name} not found")

    def get_module_commands(self, module: Module) -> dict:
        return get_commands(module)

    def get_prefix(self) -> str:
        prefixes = self.get_prefixes()
        return prefixes[0] if prefixes else "."

    def get_prefixes(self) -> list[str]:
        pref = self.db.get("veroku", "command_prefix", ".")
        return list(pref) if isinstance(pref, str) else pref or ["."]

    def dispatch(self, command: str):
        """Resolve command name (with alias) to (cmd, func)."""
        cmd = command.split()[0].lower() if command else ""
        if cmd in self.commands:
            return (cmd, self.commands[cmd])

        alias = self.aliases.get(cmd)
        if alias:
            target = alias.split(maxsplit=1)[0].lower()
            if target in self.commands:
                return (target, self.commands[target])

        return (command, None)
