"""Veroku sqlite-backed database with pointer support."""

import json
import logging
import os
import sqlite3
import threading
import typing

from .pointers import PointerDict, PointerList

logger = logging.getLogger(__name__)

JSONSerializable = typing.Any


class Database:
    """Json sqlite storage with auto-save pointers."""

    def __init__(self, path: str):
        self._path = os.path.abspath(path)
        self._db: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._synchronized = False

        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._cursor = self._connection.cursor()

        try:
            self._cursor.execute(
                "SELECT value FROM veroku WHERE key = 'veroku-internal'"
            )
        except sqlite3.OperationalError:
            self._cursor.execute(
                "CREATE TABLE veroku(key TEXT PRIMARY KEY, value TEXT)"
            )
            self._connection.commit()

        try:
            (db,) = self._cursor.execute(
                "SELECT value FROM veroku WHERE key = 'veroku-internal'"
            ).fetchone()
            self._db = json.loads(db)
        except (sqlite3.OperationalError, TypeError, json.JSONDecodeError):
            self._init_empty()

        self._synchronized = True

    def _init_empty(self):
        self._db = {}
        self._save()

    def get(
        self,
        owner: str,
        key: str,
        default: typing.Any = None,
    ) -> typing.Any:
        with self._lock:
            if owner not in self._db:
                return self._checkpoint_pointer(
                    owner,
                    self._db.setdefault(owner, {}),
                    key,
                    default,
                )
            return self._checkpoint_pointer(owner, self._db[owner], key, default)

    def _checkpoint_pointer(self, owner, data, key, default):
        result = data.get(key, default)
        if isinstance(result, dict):
            return PointerDict(self, owner, key, result)
        if isinstance(result, list):
            return PointerList(self, owner, key, result)
        return result

    def set(self, owner: str, key: str, value: JSONSerializable) -> None:
        with self._lock:
            if owner not in self._db:
                self._db[owner] = {}
            self._db[owner][key] = value
            self._save()

    def pointer(self, owner: str, key: str, default: JSONSerializable = None):
        return self.get(owner, key, default)

    def _get_raw(self, owner: str, key: str, default: typing.Any = None) -> typing.Any:
        return self._db.get(owner, {}).get(key, default)

    def _save(self) -> None:
        if not self._synchronized:
            return
        with self._lock:
            self._cursor.execute(
                "INSERT OR REPLACE INTO veroku VALUES (?, ?)",
                ("veroku-internal", json.dumps(self._db)),
            )
            self._connection.commit()

    def close(self) -> None:
        self._save()
        self._connection.close()

    def __getitem__(self, owner: str) -> PointerDict:
        return self.get(owner, "_", {}) or PointerDict(self, owner, "_", {})

    def __setitem__(self, owner: str, value: dict) -> None:
        self._db[owner] = value
        self._save()

    def __delitem__(self, owner: str) -> None:
        del self._db[owner]
        self._save()
