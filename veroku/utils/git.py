"""Veroku utils: git info for .verinfo."""

import logging
import subprocess

logger = logging.getLogger(__name__)


def get_git_hash() -> str | bool:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd="/home/forget/Veroku",
        ).stdout.strip()
    except Exception:
        return False


def get_commit_url() -> str:
    hash_ = get_git_hash()
    if not hash_:
        return "Unknown"
    return f"https://github.com/i-execute/Veroku/commit/{hash_}"


def get_git_status() -> str:
    try:
        process = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if process.returncode != 0:
            return "Not a Git repo"
        output = process.stdout.strip()
        if not output:
            return "Clean"
        count = len(output.splitlines())
        return f"{count} file{'s' if count != 1 else ''} modified"
    except Exception:
        return "Unknown"
