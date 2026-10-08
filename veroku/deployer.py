"""Veroku one-shot deployer: VNC login + station dash tunnel, used only when auth is needed.

Patched for COSMETIC STATION terminal:
  * the station dashboard runs for the WHOLE VNC login session (not a 5s flash);
  * the live noVNC feed is embedded into the dashboard (VNC STREAM panel);
  * after the web token appears the dash shows "TOKEN ACQUIRED" and shuts down.

Changes vs the original file:
  * _dash_ephemeral -> _dash_session + _dash_shutdown
  * deploy_login wires vnc_url/vnc_password into make_handler(...)
Everything else is untouched.
"""

import contextlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time

DEFAULT_DEPLOY_DIR = os.path.expanduser("~/.veroku_deployer")

DASH_PORT = 18900


def _dash_session(cloudflared: str, vnc_url: str = "", vnc_password: str = ""):
    """Start the station dashboard (VNC stream embedded) + one-shot tunnel."""
    import socketserver
    import threading

    from .dash_page import make_handler

    try:
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        handler_cls = make_handler(vnc_url=vnc_url, vnc_password=vnc_password)
        server = socketserver.ThreadingTCPServer(("127.0.0.1", DASH_PORT), handler_cls)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()

        tun, url = _tunnel(cloudflared, DASH_PORT)
        _log("STATION DASH URL: " + url)
        _log("Open it — the VNC stream is embedded in the UPLINK panel.")
        _log("The station shuts down automatically when login completes.")
        return {"server": server, "tun": tun, "url": url, "handler": handler_cls}
    except Exception:
        _log("station dash failed to start (login flow continues)")
        return None


def _dash_shutdown(sess, hold: float = 8.0) -> None:
    """Give the operator a moment, then tear the dash tunnel + server down."""
    if not sess:
        return
    try:
        if hold > 0:
            time.sleep(hold)
        sess["tun"].terminate()
        with contextlib.suppress(Exception):
            sess["tun"].wait(timeout=5)
        threading.Thread(target=sess["server"].shutdown, daemon=True).start()
    except Exception:
        pass


def _find_free_port(start: int) -> int:
    import socket

    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port")


def _log(msg: str) -> None:
    print(f"[veroku] {msg}", file=sys.stderr, flush=True)


def _ensure_cloudflared(deploy_dir: str) -> str:
    """Locate or download the cloudflared binary into deploy dir."""
    os.makedirs(deploy_dir, exist_ok=True)
    local = os.path.join(deploy_dir, "cloudflared")
    found = shutil.which("cloudflared")
    if found:
        return found
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    arch = "amd64" if sys.maxsize > 2**32 and "aarch" not in os.uname().machine else "arm64"
    url = (
        f"https://github.com/cloudflare/cloudflared/releases/latest/download/"
        f"cloudflared-linux-{arch}"
    )
    _log("downloading cloudflared")
    subprocess.run(
        ["curl", "-fsSL", "-o", local, url],
        check=True,
        timeout=300,
    )
    os.chmod(local, 0o755)
    return local


def _ensure_novnc(deploy_dir: str) -> str | None:
    root = os.path.join(deploy_dir, "novnc-root")
    share = os.path.join(root, "usr", "share", "novnc")
    if os.path.isdir(share):
        return share
    vnclocal = os.path.expanduser("~/vnclocal/novnc-root/usr/share/novnc")
    if os.path.isdir(vnclocal):
        return vnclocal
    return None


def _xvfb(display: int, w: int = 1280, h: int = 800) -> subprocess.Popen:
    return subprocess.Popen(
        ["Xvfb", f":{display}", "-screen", "0", f"{w}x{h}x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _x11vnc(display: int, rfbport: int, password: str) -> subprocess.Popen:
    env = dict(os.environ)
    ld = os.path.expanduser(
        "~/vnclocal/x11vnc-root/usr/lib/x86_64-linux-gnu"
    )
    if os.path.isdir(ld):
        env["LD_LIBRARY_PATH"] = ld
    binary = shutil.which("x11vnc")
    local = os.path.expanduser("~/vnclocal/x11vnc-root/usr/bin/x11vnc")
    if not binary and os.path.isfile(local):
        binary = local
    return subprocess.Popen(
        [
            binary,
            "-display",
            f":{display}",
            "-rfbport",
            str(rfbport),
            "-passwd",
            password,
            "-shared",
            "-forever",
            "-quiet",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _websockify(wsport: int, rfbport: int, web_root: str | None) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "websockify"]
    if web_root:
        cmd.append(f"--web={web_root}")
    cmd += [str(wsport), f"localhost:{rfbport}"]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _tunnel(cloudflared: str, port: int) -> tuple[subprocess.Popen, str]:
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = None
    deadline = time.time() + 60
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if "trycloudflare.com" in line:
            url = line.strip().split()[-1]
            if url.startswith("https://"):
                break
            url = None
        if proc.poll() is not None:
            raise RuntimeError("cloudflared exited early")
        time.sleep(0.2)
    if not url:
        raise RuntimeError("tunnel url not found")
    return proc, url


def _run_login_browser(display: int, profile_dir: str) -> subprocess.Popen:
    """Launch Chromium in the Xvfb display with a persistent profile."""
    chromium = None
    mc = os.path.join(os.path.expanduser("~"), ".cache/ms-playwright")
    if os.path.isdir(mc):
        for d in sorted(os.listdir(mc), reverse=True):
            cand = os.path.join(d, "chrome-linux", "chrome")
            if os.path.isfile(cand):
                chromium = cand
                break
    if not chromium:
        chromium = shutil.which("chromium") or shutil.which("chromium-browser") \
            or shutil.which("google-chrome")
    if not chromium:
        raise RuntimeError("no chromium found; run playwright install chromium")
    env = dict(os.environ)
    env["DISPLAY"] = f":{display}"
    return subprocess.Popen(
        [chromium, "--no-sandbox", "--disable-dev-shm-usage",
         "--user-data-dir=" + profile_dir, "https://vk.ru/"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_token(profile_dir: str, timeout: int = 600) -> dict:
    """Poll profile localStorage via headless playwright until web token appears."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            profile_dir,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            deadline = time.time() + timeout
            token = None
            while time.time() < deadline:
                for page in ctx.pages:
                    try:
                        token = page.evaluate(
                            "() => localStorage.getItem('access_token')"
                        )
                    except Exception:
                        continue
                    if token:
                        break
                if token:
                    break
                time.sleep(3)
            if not token:
                raise RuntimeError("login timed out; no token found")
            return {"access_token": token}
        finally:
            ctx.close()


def deploy_login(
    profile_dir: str,
    token_file: str,
    deploy_dir: str = DEFAULT_DEPLOY_DIR,
) -> dict:
    """Spin up Xvfb+VNC+noVNC+station dash; user logs in; write token; tear down."""
    display = 95
    rfbport = 5995
    wsport = 5996

    vnc_password = secrets.token_urlsafe(8)

    web_root = _ensure_novnc(deploy_dir)
    cloudflared = _ensure_cloudflared(deploy_dir)

    _log("starting Xvfb")
    xvfb = _xvfb(display)
    time.sleep(1)

    try:
        _log("starting x11vnc")
        vnc = _x11vnc(display, rfbport, vnc_password)

        _log("starting websockify/noVNC")
        ws = _websockify(wsport, rfbport, web_root)

        _log("starting tunnel")
        tun, url = _tunnel(cloudflared, wsport)

        vnc_target = (
            f"{url}/vnc.html?autoconnect=1&resize=scale&password={vnc_password}"
            if web_root
            else url
        )
        login_url = vnc_target
        _log("RAW VNC URL: " + login_url)
        _log("VNC PASSWORD: " + vnc_password)

        # station dashboard with the VNC stream embedded — lives for the login session
        dash = _dash_session(cloudflared, vnc_url=vnc_target, vnc_password=vnc_password)

        browser = _run_login_browser(display, profile_dir)

        _log("waiting for web token (up to 10 min)...")
        try:
            token_data = _wait_token(profile_dir, timeout=600)
            if dash:
                with contextlib.suppress(Exception):
                    dash["handler"].emit("TOKEN ACQUIRED")
        finally:
            _dash_shutdown(dash, hold=8)
            _log("shutting down")
            for p in (browser, tun, ws, vnc, xvfb):
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    p.kill()

        with open(token_file, "w", encoding="utf-8") as f:
            json.dump({"access_token": token_data["access_token"]}, f)
        _log(f"token saved to {token_file}")
        return token_data
    except Exception:
        for p in (xvfb,):
            try:
                p.kill()
            except Exception:
                pass
        raise
