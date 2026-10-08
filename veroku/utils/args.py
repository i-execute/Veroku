"""Veroku utils: shlex args parsing, like Feroku."""

import shlex


def get_args_raw(message) -> str:
    """Arguments of a command message, verbatim."""
    text = getattr(message, "text", message)
    if not text:
        return ""
    return text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""


def get_args(message) -> list[str]:
    """Arguments of a command message, split with shlex."""
    raw = get_args_raw(message)
    if not raw:
        return []
    try:
        return [x for x in shlex.split(raw) if x]
    except ValueError:
        return [raw]


def get_args_split(message, maxsplit: int = -1) -> list[str]:
    """Arguments split by whitespace only."""
    raw = get_args_raw(message)
    if not raw:
        return []
    return raw.split(maxsplit=maxsplit)
