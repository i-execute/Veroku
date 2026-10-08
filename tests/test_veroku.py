import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veroku.types import Module, command, watcher, ratelimit, tag
from veroku.loader import Modules
from veroku.database import Database
from veroku.dispatcher import CommandDispatcher
from veroku.client import CustomVKClient, VerokuMessage
from veroku.security import SecurityManager, OWNER, SUDO, EVERYONE


class FakeVK:
    def __init__(self):
        self.sent = []

    def send_message_request(self, peer_id, text, **kw):
        self.sent.append((peer_id, text))
        return 1

    def request(self, method, **params):
        return {"chat_id": 7}


class FakeClient:
    def __init__(self):
        self.vk = FakeVK()
        self.vk_id = 42


class FakeMessage:
    def __init__(self, text, peer_id=100, from_id=42):
        self.text = text
        self.peer_id = peer_id
        self.from_id = from_id
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)
        return text


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def modules(db, client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "veroku.loader.Modules.initialize", lambda self: asyncio.sleep(0)
    )
    m = Modules(db, client, str(tmp_path))
    m.commands = {}
    m.aliases = {}
    m.modules = []
    m.watchers = []
    return m


def test_module_commands_discovered(modules):
    class M(Module):
        strings = {"name": "M"}

        @command
        async def hello(self, message, args: str):
            """Say hello"""
            await message.reply("hi")

    mod = M()
    mod.allmodules = modules
    assert "hello" in mod.commands


def test_dispatcher_routes_command(modules, db, client):
    class M(Module):
        strings = {"name": "M"}

        @command
        async def hello(self, message, args: str):
            """Say hello"""
            await message.reply("hello " + args)

    mod = M()
    mod.allmodules = modules
    mod.client = client
    for name, fn in mod.commands.items():
        modules.commands[name] = fn

    dispatcher = CommandDispatcher(modules, client, db)
    msg = FakeMessage(".hello world")
    asyncio.run(dispatcher.handle_message(msg))
    assert msg.replies == ["hello world"]


def test_dispatcher_ignores_no_prefix(modules, db, client):
    dispatcher = CommandDispatcher(modules, client, db)
    msg = FakeMessage("hello world")
    asyncio.run(dispatcher.handle_message(msg))
    assert msg.replies == []


def test_dispatcher_unknown_command(modules, db, client):
    dispatcher = CommandDispatcher(modules, client, db)
    msg = FakeMessage(".nosuch")
    asyncio.run(dispatcher.handle_message(msg))
    assert msg.replies == []


def test_dispatcher_calls_watchers(modules, db, client):
    seen = []

    class M(Module):
        strings = {"name": "M"}

        @watcher
        async def watcher_any(self, message):
            seen.append(message.text)

    mod = M()
    mod.allmodules = modules
    modules.watchers.append(mod.watchers["watcher_any"])

    dispatcher = CommandDispatcher(modules, client, db)
    asyncio.run(dispatcher.handle_message(FakeMessage("anything")))
    assert seen == ["anything"]


def test_prefix_from_db(modules, db):
    db.set("veroku", "command_prefix", "!")
    assert modules.get_prefix() == "!"
    assert modules.get_prefixes() == ["!"]


def test_security_owner(db):
    sec = SecurityManager(db)
    sec.set_owner(42)
    assert sec.check(42, OWNER)
    assert not sec.check(43, OWNER)
    sec.add_sudo(43)
    assert sec.check(43, SUDO)
    assert sec.check(43, EVERYONE)
    sec.remove_sudo(43)
    assert not sec.check(43, SUDO)
    assert sec.check(43, EVERYONE)


def test_database_roundtrip(db):
    db.set("mod", "key", {"a": 1})
    assert db.get("mod", "key") == {"a": 1}
    assert db.get("mod", "missing", 5) == 5
