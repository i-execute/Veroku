"""Veroku core module: translate via Google Translate (free endpoint)."""

import json
import urllib.parse
import urllib.request

from ..utils.messages import answer as _a
from ..types import Module, command
from ..utils.args import get_args_raw


def _translate(text: str, source: str, target: str) -> str:
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source or "auto",
        "tl": target,
        "dt": "t",
        "q": text,
    }
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return "".join(part[0] for part in data[0] if part[0])


class Translate(Module):
    """Translate text via Google Translate."""

    strings = {
        "name": "translate",
        "invalid_lang": "<b>Invalid language code</b>",
        "no_text": "<b>No text to translate</b>",
        "translated": "<b>Translated:</b>\n{}",
        "_cmd_doc_tr": "[lang] [text] - Translate text (reply supported)",
        "_cls_doc": "Translate text",
    }

    @command
    async def tr(self, message, args: str):
        """Translate text."""
        target = "ru"
        text = args
        parts = (args or "").split(maxsplit=1)
        if parts and len(parts[0]) <= 5 and parts[0].replace("-", "").isalpha():
            target = parts[0]
            text = parts[1] if len(parts) > 1 else ""
        if not text and message.reply_text:
            text = message.reply_text
        if not text:
            await _a(message, self.strings["no_text"])
            return
        try:
            result = _translate(text, "auto", target)
        except Exception:
            await _a(message, self.strings["invalid_lang"])
            return
        await _a(message, self.strings["translated"].format(result))
