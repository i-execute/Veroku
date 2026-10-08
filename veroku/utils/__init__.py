"""Veroku utils: text, peers, ids, misc helpers for modules."""

import re
import time


def get_args_raw(message) -> str:
    """Arguments of a command message, verbatim."""
    text = message.text or ""
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def get_args(message) -> list[str]:
    """Arguments of a command message, split."""
    return get_args_raw(message).split()


def chunks(text: str, size: int = 4000) -> list[str]:
    """Split text into chunks under the VK message limit."""
    return [text[i:i + size] for i in range(0, len(text), size)]


def mention(user_id: int, name: str = "") -> str:
    """VK @mention string."""
    return f"[id{user_id}|{name or user_id}]"


def peer_from_chat(chat_id: int) -> int:
    """Convert chat_id to peer_id."""
    return 2000000000 + int(chat_id)


def chat_from_peer(peer_id: int) -> int | None:
    """Convert peer_id to chat_id if it is a group chat."""
    return peer_id - 2000000000 if peer_id > 2000000000 else None


def is_user_peer(peer_id: int) -> bool:
    """True if the peer is a DM with a user."""
    return 0 < peer_id < 2000000000


def fmt_time(ts: float) -> str:
    """Human uptime/duration from seconds."""
    m, s = divmod(int(ts), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    out = []
    if d:
        out.append(f"{d}d")
    if h or d:
        out.append(f"{h}h")
    if m or h or d:
        out.append(f"{m}m")
    out.append(f"{s}s")
    return " ".join(out)


def rand_id() -> int:
    """Random id for messages.send."""
    return int(time.time() * 1000) % 2**31


def sanitize_html(text: str) -> str:
    """Escape VK html-ish markup characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
