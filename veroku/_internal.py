"""Veroku internal: restart, task tracking."""

import asyncio
import logging
import os
import sys

_background_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> asyncio.Task:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def install_task_tracking():
    loop_cls = asyncio.base_events.BaseEventLoop
    if getattr(loop_cls.create_task, "_veroku_tracked", False):
        return

    original_create_task = loop_cls.create_task

    def create_task(self, coro, **kwargs):
        return _track_task(original_create_task(self, coro, **kwargs))

    create_task._veroku_tracked = True
    loop_cls.create_task = create_task


def restart():
    logging.shutdown()
    os.execv(
        sys.executable,
        [sys.executable, "-m", "veroku", *sys.argv[1:]],
    )
