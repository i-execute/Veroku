"""Veroku core module: security management (owner/sudo)."""

from ..utils.messages import answer as _a
from ..types import Module, command, owner, tag


def _owner_cmd(func):
    func = command(func)
    func = owner(func)
    return func


class Security(Module):
    """Manage owner and sudo users."""

    strings = {
        "name": "security",
        "no_user": "<b>No user id given</b>",
        "added": "<b>Added {} to sudo</b>",
        "removed": "<b>Removed {} from sudo</b>",
        "not_sudo": "<b>{} is not sudo</b>",
        "list": "<b>Sudo users:</b>\n{}",
        "empty": "<b>No sudo users</b>",
        "_cmd_doc_addsudo": "<user_id> - Add a sudo user",
        "_cmd_doc_rmsudo": "<user_id> - Remove a sudo user",
        "_cmd_doc_sudolist": "List sudo users",
        "_cls_doc": "Manage owner and sudo users",
    }

    @_owner_cmd
    async def addsudo(self, message, args: str):
        """Add a sudo user."""
        if not (args and args.strip().isdigit()):
            await _a(message, self.strings["no_user"])
            return
        uid = int(args.strip())
        self._client.dispatcher.security.add_sudo(uid)
        await _a(message, self.strings["added"].format(uid))

    @_owner_cmd
    async def rmsudo(self, message, args: str):
        """Remove a sudo user."""
        if not (args and args.strip().isdigit()):
            await _a(message, self.strings["no_user"])
            return
        uid = int(args.strip())
        if uid not in self._client.dispatcher.security._sudo:
            await _a(message, self.strings["not_sudo"].format(uid))
            return
        self._client.dispatcher.security.remove_sudo(uid)
        await _a(message, self.strings["removed"].format(uid))

    @command
    async def sudolist(self, message, args: str):
        """List sudo users."""
        sudo = self._client.dispatcher.security._sudo
        if not sudo:
            await _a(message, self.strings["empty"])
            return
        await _a(
            message,
            self.strings["list"].format("\n".join(map(str, sudo))),
        )
