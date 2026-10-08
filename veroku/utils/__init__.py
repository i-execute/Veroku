"""Veroku utils package, structured like Feroku."""

from importlib import import_module

_MODULES = (
    "args",
    "git",
    "messages",
    "other",
    "veroku",
    "placeholders",
)

for _module_name in _MODULES:
    _module = import_module(f"{__name__}.{_module_name}")
    _names = getattr(
        _module,
        "__all__",
        tuple(name for name in vars(_module) if not name.startswith("_")),
    )
    globals().update({name: getattr(_module, name) for name in _names})

del _module_name, _module, _names, import_module
