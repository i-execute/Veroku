"""Veroku deployer: one-shot cloudflared tunnel + noVNC login for first auth."""

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

DEFAULT_DEPLOY_DIR = os.path.join(os.path.expanduser("~"), ".veroku_deployer")


def _find_free_port(start: int) -> int:
    for p in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("no free port")


def _log(msg: str) -> None:
    print(f"[veroku-deploy] {msg}", flush=True)


def _ensure_cloudflared(deploy_dir: str) -> str:
    """Locate or download the cloudflared binary into deploy dir."""
    os.makedirs(deploy_dir, exist_ok=True)
    local = os.path.join(deploy_dir, "cloudflared")
    found = shutil.which("cloudflared")
    if found:
        if not os.path.exists(local):
            shutil.copy2(found, local)
        return local
    if os.path.exists(local):
        return local
    url = ("https://github.com/cloudflare/cloudflared/releases/latest/download/"
           "cloudflared-linux-amd64")
    subprocess.run(["curl", "-fsSL", "-o", local, url], check=True)
    os.chmod(local, 0o755)
    return local


def _ensure_novnc(deploy_dir: str) -> str | None:
    """Locate a noVNC web root, else return None."""
    for path in ("/usr/share/novnc", "/opt/novnc",
                 os.path.join(os.path.expanduser("~"), "vnclocal/novnc-root/usr/share/novnc")):
        if os.path.isfile(os.path.join(path, "vnc.html")):
            return path
    return None


def _xvfb(display: int, w: int = 1280, h: int = 800) -> subprocess.Popen:
    return subprocess.Popen(
        ["Xvfb", f":{display}", "-screen", 0, f"{w}x{h}x24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _x11vnc(display: int, rfbport: int, password: str) -> subprocess.Popen:
    vn = shutil.which("x11vnc")
    if not vn:
        vn = os.path.join(os.path.expanduser("~"),
                          "vnclocal/x11vnc-root/usr/bin/x11vnc")
    env = dict(os.environ)
    libdir = os.path.join(os.path.expanduser("~"),
                          "vnclocal/x11vnc-root/usr/lib/x86_64-linux-gnu")
    if os.path.isdir(libdir):
        env["LD_LIBRARY_PATH"] = libdir
    return subprocess.Popen(
        [vn, "-display", f":{display}", "-rfbport", str(rfbport),
         "-passwd", password, "-forever", "-shared", "-noxdamage"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )


def _websockify(wsport: int, rfbport: int, web_root: str | None) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "websockify", "--web", web_root or "",
           str(wsport), f"localhost:{rfbport}"]
    if not web_root:
        cmd = [sys.executable, "-m", "websockify", str(wsport), f"localhost:{rfbport}"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _tunnel(cloudflared: str, port: int) -> tuple[subprocess.Popen, str]:
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
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
            cand = os.path.join(mc, d, "chrome-linux", "chrome")
            if os.path.isfile(cand):
                chromium = cand
                break
            cand = os.path.join(mc, d, "chrome-linux64", "chrome")
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
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_token(profile_dir: str, timeout: int = 600) -> dict:
    """Poll profile localStorage via headless playwright until web token appears."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            profile_dir, headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://vk.ru/", wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + 30
            while time.time() < deadline:
                keys = page.evaluate("() => Object.keys(localStorage)")
                for k in keys:
                    if "web_token" in k:
                        v = page.evaluate(f'() => localStorage.getItem("{k}")')
                        try:
                            return json.loads(v)
                        except (ValueError, TypeError):
                            pass
                time.sleep(2)
            raise RuntimeError("web token not found in localStorage")
        finally:
            ctx.close()


def deploy_login(
    profile_dir: str,
    token_file: str,
    deploy_dir: str = DEFAULT_DEPLOY_DIR,
) -> dict:
    """Spin up Xvfb+VNC+noVNC+cloudflared; user logs in; write token; tear down."""
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

        login_url = f"{url}/vnc.html?autoconnect=1&resize=scale" if web_root else url
        _log("LOGIN URL: " + login_url)
        _log("VNC PASSWORD: " + vnc_password)
        _log("Open the URL on your phone, enter the password, log in to VK.")
        _log("This window will close automatically when login completes.")

        browser = _run_login_browser(display, profile_dir)

        _log("waiting for web token (up to 10 min)...")
        try:
            token_data = _wait_token(profile_dir, timeout=600)
        finally:
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
