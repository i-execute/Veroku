"""Veroku utils: custom placeholders, like Feroku."""

import typing

custom_placeholders: dict[str, dict] = {}


def register_placeholder(
    placeholder: str,
    callback: typing.Callable,
    description: str | None = None,
):
    module_name = callback.__self__.__class__.__name__
    custom_placeholders[placeholder] = {
        "module_name": module_name,
        "module_instance": callback.__self__,
        "callback": callback,
        "description": description,
        "placeholder_name": placeholder,
    }
    return True


async def get_placeholder(placeholder: str, data: dict | None = None):
    callback = custom_placeholders[placeholder]["callback"]
    try:
        return str(await callback(data))
    except Exception:
        return str(await callback())


async def get_placeholders(data: dict, custom_message: str | None):
    if custom_message is None:
        return data
    for placeholder in custom_placeholders.values():
        if f"{{{placeholder['placeholder_name']}}}" in custom_message:
            data[placeholder["placeholder_name"]] = await get_placeholder(
                placeholder["placeholder_name"], data
            )
    return data


def unregister_placeholders(module_name: str) -> int:
    to_remove = [
        name
        for name, data in custom_placeholders.items()
        if data.get("module_name") == module_name
    ]
    for name in to_remove:
        del custom_placeholders[name]
    return len(to_remove)


def config_placeholders() -> list[str] | None:
    result = [
        f"{{{name}}} - {data.get('description') or 'No docs'}"
        for name, data in custom_placeholders.items()
    ]
    return result or None
