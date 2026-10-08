"""Veroku entrypoint: config, auth, module loading, long poll loop."""

import argparse
import asyncio
import json
import os
import sys

import vkover

from .client import CustomVKClient
from .database import Database
from .deployer import deploy_login, DEFAULT_DEPLOY_DIR
from .dispatcher import CommandDispatcher
from .loader import Modules
from .log import setup_logging


class Veroku:
    """Veroku userbot: loads modules and runs the VK long poll."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

        self.profile_dir = os.path.join(root, "vk_profile")
        self.token_file = os.path.join(root, "web_token.json")
        self.db = Database(os.path.join(root, "veroku.db"))

        setup_logging()

        self.vk = self._build_vk()
        self.client = CustomVKClient(self.vk)
        self.modules = Modules(self.db, self.client, root)
        self.dispatcher = CommandDispatcher(self.modules, self.client, self.db)

    def _build_vk(self) -> vkover.VKover:
        if not os.path.isfile(self.token_file):
            deploy_login(
                profile_dir=self.profile_dir,
                token_file=self.token_file,
                deploy_dir=DEFAULT_DEPLOY_DIR,
            )
        self.vk = vkover.VKover.from_files(
            self.token_file, profile_dir=self.profile_dir
        )
        return self.vk

    async def run(self) -> None:
        await self.client.authorize()
        await self.modules.initialize()
        loop = asyncio.get_event_loop()
        lp = self.vk.longpoll()

        def worker():
            try:
                from vkover.handlers import NEW_MESSAGE

                for ev in lp.events():
                    if ev.code == NEW_MESSAGE:
                        from .client import VerokuMessage

                        msg = VerokuMessage(
                            self.client, ev.peer_id, ev.message_id, ev.text,
                            out=ev.out, from_id=self.client.vk_id,
                            date=ev.timestamp,
                        )
                        loop.call_soon_threadsafe(
                            lambda m=msg: loop.create_task(
                                self.dispatcher.handle_message(m)
                            ),
                        )
            except Exception:
                import logging
                logging.getLogger(__name__).exception("longpoll worker died")

        import threading
        threading.Thread(target=worker, daemon=True, name="vk-lp").start()
        await asyncio.Event().wait()


def main() -> None:
    ap = argparse.ArgumentParser(description="Veroku userbot")
    ap.add_argument("--root", default=os.path.join(os.path.expanduser("~"), ".veroku"),
                    help="state directory")
    args = ap.parse_args()

    bot = Veroku(args.root)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
