"""Veroku utils: misc helpers (rand, run_sync, platform)."""

import asyncio
import contextlib
import os
import random
import typing
from datetime import datetime


def rand(size: int) -> str:
    """Random alphanumeric string."""
    return "".join(
        random.choice("abcdefghijklmnopqrstuvwxyz1234567890")
        for _ in range(size)
    )


def run_sync(func, *args, **kwargs):
    """Run blocking function in executor."""
    return asyncio.get_event_loop().run_in_executor(
        None, lambda: func(*args, **kwargs)
    )


def get_platform() -> str:
    """Human-readable platform name."""
    with contextlib.suppress(Exception):
        if os.path.isfile("/proc/device-tree/model"):
            with open("/proc/device-tree/model") as f:
                model = f.read().strip()
                if any(board in model for board in ("Orange", "Raspberry")):
                    return model
    import platform

    return f"{platform.system()} {platform.release()}"


def get_uptime_string(start_ts: float) -> str:
    """Uptime as human string."""
    delta = datetime.now().timestamp() - start_ts
    minutes, seconds = divmod(int(delta), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def array_sum(array: list[list[typing.Any]]) -> list[typing.Any]:
    """Flatten one level of nested lists."""
    return [item for sub in array for item in sub]


def chunks(lst: list, n: int) -> list[list]:
    """Split list into chunks of n."""
    return [lst[i : i + n] for i in range(0, len(lst), n)]
