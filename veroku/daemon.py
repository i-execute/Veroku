"""Veroku daemon: systemd user unit install, Feroku-style self-hosting."""

import contextlib
import logging
import os
import pwd
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _daemon_command(command: list[str], env=None, timeout: int = 30) -> bool:
    try:
        return (
            subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                timeout=timeout,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def install_daemon() -> bool:
    """Install veroku.service as a systemd user unit (rootless) and start it."""
    executable = str(Path(sys.executable).resolve())
    repository = str(Path(__file__).parent.parent.resolve())
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    user_unit = not is_root
    unit_dir = (
        Path("/etc/systemd/system")
        if is_root
        else Path.home() / ".config" / "systemd" / "user"
    )
    unit_path = unit_dir / "veroku.service"
    target = "default.target" if user_unit else "multi-user.target"
    unit = (
        "[Unit]\n"
        "Description=Veroku userbot\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={repository}\n"
        f"ExecStart={executable} -m veroku\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "Environment=PYTHONUNBUFFERED=1\n\n"
        "[Install]\n"
        f"WantedBy={target}\n"
    )

    service_written = False
    try:
        unit_dir.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(unit)
        unit_path.chmod(0o644)
        service_written = True
    except OSError:
        logger.exception("Failed to write %s", unit_path)
        return False

    env = os.environ.copy()
    linger_enabled = not user_unit
    if user_unit and hasattr(os, "getuid"):
        runtime_dir = Path("/run/user") / str(os.getuid())
        if runtime_dir.is_dir():
            env.setdefault("XDG_RUNTIME_DIR", str(runtime_dir))
            env.setdefault(
                "DBUS_SESSION_BUS_ADDRESS",
                f"unix:path={runtime_dir / 'bus'}",
            )
        try:
            username = pwd.getpwuid(os.getuid()).pw_name
            linger_enabled = _daemon_command(
                ["sudo", "-n", "loginctl", "enable-linger", username],
                timeout=5,
            ) or _daemon_command(
                ["loginctl", "enable-linger", username],
                timeout=5,
            )
            linger_enabled = linger_enabled or (
                Path("/var/lib/systemd/linger") / username
            ).exists()
        except (KeyError, OSError):
            linger_enabled = False

    systemctl = ["systemctl", "--user"] if user_unit else ["systemctl"]
    if service_written and _daemon_command(
        systemctl + ["daemon-reload"], env
    ) and _daemon_command(systemctl + ["enable", "veroku.service"], env):
        return _daemon_command(
            systemctl + ["start", "veroku.service"], env
        )
    return False


def daemon_status() -> str:
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    systemctl = ["systemctl", "--user"] if not is_root else ["systemctl"]
    try:
        out = subprocess.run(
            systemctl + ["status", "veroku.service", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout or out.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return f"status failed: {e}"
