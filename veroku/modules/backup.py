"""Veroku core module: backup (db + modules zip to logs group)."""

import datetime
import io
import json
import os
import zipfile

from ..utils.messages import answer as _a
from ..types import Module, command

LOGS_PEER = 2000000039


class Backup(Module):
    """Backup db and modules to the logs group."""

    strings = {
        "name": "backup",
        "backupall_info": (
            "<b>🦊 Backup</b>\n"
            "🕰 <b>Date:</b> <code>{date}</code>\n"
            "📌 <b>Modules:</b> <code>{modules} pcs</code>\n"
            "💾 <b>Size:</b> <code>{size}</code>\n"
            "✍️ <b>Prefix:</b> <code>{prefix}</code>"
        ),
        "backups_on": "<b>🦊 Automatic backup activated</b>",
        "backups_off": "<b>🦊 Automatic backup deactivated</b>",
        "_cmd_doc_backup": "Make a backup of db and modules",
        "_cls_doc": "Backup db and modules",
    }

    def _build_archive(self) -> str:
        database_file = io.BytesIO(
            json.dumps(
                self._db._db if hasattr(self._db, "_db") else dict(self._db),
                indent=2,
            ).encode()
        )
        modules_file = io.BytesIO()
        with zipfile.ZipFile(modules_file, "w", zipfile.ZIP_DEFLATED) as archive:
            for root, _, files in os.walk(self.allmodules.loaded_modules_dir):
                for filename in files:
                    if filename.endswith(".py"):
                        with open(os.path.join(root, filename), "rb") as f:
                            archive.writestr(filename, f.read())
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("db.json", database_file.getvalue())
            archive.writestr("mods.zip", modules_file.getvalue())
        path = "/tmp/veroku.backup"
        with open(path, "wb") as f:
            f.write(result.getvalue())
        return path

    def _modules_count(self) -> int:
        return sum(
            1
            for _, _, files in os.walk(self.allmodules.loaded_modules_dir)
            for fn in files
            if fn.endswith(".py")
        )

    @command
    async def backup(self, message, args: str):
        """Make a backup of db and modules."""
        path = self._build_archive()
        size = os.path.getsize(path)
        caption = self.strings["backupall_info"].format(
            date=f"{datetime.datetime.now():%d-%m-%Y %H-%M}",
            modules=self._modules_count(),
            size=f"{size / 1024:.1f} KB",
            prefix=self.get_prefix(),
        )
        sent = self._client.vk.upload_doc_request(
            LOGS_PEER, path, caption=caption
        )
        os.remove(path)
        self.set("last_backup", round(datetime.datetime.now().timestamp()))
        await _a(message, "✅")
