"""Veroku module base: Module, Strings, command/watcher decorators."""

import typing
from dataclasses import dataclass, field

from .pointers import PointerDict, PointerList

if typing.TYPE_CHECKING:
    from .loader import Modules

__all__ = [
    "JSONSerializable",
    "Command",
    "StringLoader",
    "Strings",
    "Module",
    "get_commands",
    "get_watchers",
    "PointerDict",
    "PointerList",
    "command",
    "watcher",
    "ratelimit",
    "tag",
]


class Strings:
    """Localised strings of a module."""

    def __init__(self, module: typing.Any):
        source = module.strings
        self._strings = dict(source) if isinstance(source, dict) else {}

    def __getitem__(self, key: str) -> str:
        return self._strings.get(key, f"Unknown string: {key}")

    def get(self, key: str, default: typing.Any = None) -> typing.Any:
        return self._strings.get(key, default)

    def __call__(self, key: str, _: typing.Any = None) -> str:
        return self[key]

    def __iter__(self):
        return iter(self._strings)

    def __contains__(self, key: str) -> bool:
        return key in self._strings


class Module:
    """Base class for Veroku modules."""

    strings = {"name": "Unknown"}

    def config_complete(self):
        pass

    async def client_ready(self):
        pass

    def internal_init(self):
        self.allmodules: "Modules"
        self.db = self.allmodules.db
        self._db = self.allmodules.db
        self.client = self.allmodules.client
        self._client = self.allmodules.client
        self.lookup = self.allmodules.lookup
        self.get_prefix = self.allmodules.get_prefix
        self.get_prefixes = self.allmodules.get_prefixes
        self.vk_id: int = self._client.vk_id
        self._vk_id: int = self._client.vk_id

    async def on_unload(self):
        pass

    async def invoke(
        self,
        command: str,
        args: str | None = None,
        peer: int | None = None,
    ) -> typing.Any:
        if command not in self.allmodules.commands:
            raise ValueError(f"Command {command} not found")
        if peer is None:
            raise ValueError("peer must be specified")
        cmd = f"{self.get_prefix()}{command} {args or ''}".strip()
        message = await self._client.send_message(peer, cmd)
        await self.allmodules.commands[command](message)
        return message

    @property
    def commands(self) -> dict[str, "Command"]:
        return get_commands(self)

    @property
    def watchers(self) -> dict[str, "Command"]:
        return get_watchers(self)

    @commands.setter
    def commands(self, _):
        pass

    @watchers.setter
    def watchers(self, _):
        pass


Command = typing.Any


def _get_members(mod: Module, marker: str, attr: str, strict: bool = False) -> dict:
    found = {}
    for cls in type(mod).__mro__:
        for name, member in vars(cls).items():
            if callable(member) and hasattr(member, attr) \
                    and (not strict or not name.startswith("_")):
                found[name] = getattr(mod, name)
    return found


def get_commands(mod: Module) -> dict:
    return _get_members(mod, "cmd", "is_command")


def get_watchers(mod: Module) -> dict:
    return _get_members(mod, "watcher", "is_watcher", strict=True)


def _mark_method(mark: str, *args, **kwargs):
    if len(args) == 1 and callable(args[0]) and not kwargs:
        func = args[0]
        setattr(func, mark, True)
        return func

    def decorator(func: Command) -> Command:
        setattr(func, mark, True)
        for arg in args:
            setattr(func, arg, True)
        for kwarg, value in kwargs.items():
            setattr(func, kwarg, value)
        return func
    return decorator


def command(*args, **kwargs):
    return _mark_method("is_command", *args, **kwargs)


def watcher(*args, **kwargs):
    return _mark_method("is_watcher", *args, **kwargs)


def ratelimit(func: Command) -> Command:
    func.ratelimit = True
    return func

def tag(*tags, **kwarg_tags):
    def inner(func: Command) -> Command:
        for _tag in tags:
            setattr(func, _tag, True)
        for _tag, value in kwarg_tags.items():
            setattr(func, _tag, value)
        return func
    return inner


@dataclass
class ConfigValue:
    option: str
    default: typing.Any = None
    doc: str = "No description"
    value: typing.Any = field(default=None)
    validator: typing.Callable | None = None
    on_change: typing.Callable | None = None
    folder: str | None = None

    def __post_init__(self):
        if self.value is None:
            self.value = self.default

    def set_no_raise(self, value: typing.Any) -> bool:
        self.value = value
        return True
