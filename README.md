# Veroku

VK-юзербот в стиле Hikka/Feroku на веб-токенах (через [VKover](https://github.com/i-execute/VKover)).

Работает с личного аккаунта: Long Poll v3, команды текстом (префикс `.`), модули, sqlite-стейт, логи в группу.

## Запуск

```bash
pip install -e . && playwright install chromium
veroku --root ~/.veroku
```

При первом запуске `veroku` сам поднимает Xvfb + VNC + noVNC + cloudflared-туннель:
печатает в терминал URL (случайный) и случайный пароль VNC — открываешь с телефона,
логинишься в VK, токен пишется в `~/.veroku/web_token.json`, туннель и браузер
автоматически закрываются. Бинарник cloudflared хранится в `~/.veroku_deployer/`.

Токен протухает — Veroku молча обновляет его через headless-браузер с тем же профилем.

## Модули

| Команда | Описание |
|---|---|
| `.cmdlist` | список команд |
| `.ping` | проверка отклика |
| `.logsto` | привязать логи к текущему чату |
| `.logs_chat_create [title]` | создать групповой чат для логов |
| `.logs_off` | выключить пересылку логов |
| `.vkcall` | создать VK-звонок (ссылка + короткие креды) |
| `.vkcallend <id>` | завершить звонок |

## Свои модули

```python
from veroku.types import Module, command

class MyMod(Module):
    strings = {"name": "My"}

    @command
    async def hello(self, message, args: str):
        """Say hello"""
        await message.reply("hello " + args)
```

Кидай в `veroku/modules/*.py` — подхватится автоматически. Инлайн-режима и ботов
в VK нет, так что весь UX — текстовые команды; `message.reply/edit/respond/delete`
доступны как в Telethon.
