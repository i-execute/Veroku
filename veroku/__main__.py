"""Veroku __main__: dependency check, version check, boot."""

import hashlib
import os
import re
import sys
from pathlib import Path

from ._internal import restart

REQUIREMENTS = Path(__file__).parent.parent / "requirements.txt"
REQUIREMENTS_HASH = ".requirements_hash"


def get_data_root() -> Path:
    for index, arg in enumerate(sys.argv):
        if arg == "--data-root" and index + 1 < len(sys.argv):
            return Path(sys.argv[index + 1]).expanduser()
        if arg.startswith("--data-root="):
            return Path(arg.split("=", maxsplit=1)[1]).expanduser()
    return Path.home() / ".veroku"


def get_file_hash(filename: str) -> str | None:
    hasher = hashlib.sha256()
    try:
        with open(filename, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()
    except FileNotFoundError:
        return None


def deps():
    import subprocess

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "-q",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "-r",
            str(REQUIREMENTS),
        ],
        check=True,
        timeout=600,
        capture_output=True,
    )
    with open(REQUIREMENTS_HASH, "w") as f:
        f.write(get_file_hash(str(REQUIREMENTS)) or "")


if sys.version_info < (3, 10, 0):
    print("Error: you must use at least Python version 3.10.0")
elif __package__ != "veroku":
    print("Error: you cannot run this as a script; you must execute as a package")
else:
    try:
        import vkover  # noqa: F401
    except ImportError:
        print("Installing dependencies...")
        deps()
        restart()

    try:
        from . import log

        log.setup_logging()
        from .main import main
    except ImportError as e:
        print(f"{e}\nAttempting dependencies installation... Just wait ")
        deps()
        restart()

    prev_hash = None
    if os.path.exists(REQUIREMENTS_HASH):
        with open(REQUIREMENTS_HASH) as f:
            prev_hash = f.read().strip()

    current_hash = get_file_hash(str(REQUIREMENTS))
    if REQUIREMENTS.exists() and prev_hash != current_hash:
        print("Detected changes in requirements.txt, updating dependencies...")
        deps()
        restart()

    main()
