"""Veroku utils: veroku package info."""

import os


def get_version_raw() -> str:
    from .. import version

    return ".".join(map(str, list(version.__version__)))


def get_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def get_dir(mod: str) -> str:
    return os.path.dirname(os.path.abspath(mod))


version = get_version_raw
