"""Veroku dashboard page + metrics handlers (used by one-shot login dash).

COSMETIC STATION // VEROKU-1 — SYSMON terminal (dark chassis / amber phosphor).

Drop-in replacement for the old dash_page.py:

  * same entry points: ``DASH_PAGE`` and ``make_handler()`` — works with the
    unpatched deployer.py;
  * NEW: ``make_handler(vnc_url=..., vnc_password=...)`` embeds the live VNC
    stream (noVNC) into the dashboard — used by the patched deployer.py;
  * login/password RANDOMLY GENERATED on the backend at startup, printed to
    stderr when the handler is created (env DASH_USER / DASH_PASS to pin);
  * sessions: POST /api/login -> token, GET /api (Bearer) -> metrics JSON
    {mem, disk, load, procs, event};
  * Handler.emit("TOKEN ACQUIRED") flips the station event banner.
"""

import http.server
import json
import os
import secrets
import sys
import threading
import time

# ---------------------------------------------------------------- credentials
OPERATOR = os.environ.get("DASH_USER") or ("OP-" + secrets.token_hex(8))
PASSCODE = os.environ.get("DASH_PASS") or secrets.token_urlsafe(16)

_sessions = {}          # token -> ts
_sessions_lock = threading.Lock()
_failed = {}            # ip -> [fails, locked_until]
_failed_lock = threading.Lock()
_STATE = {"event": "STANDBY"}    # deployer can flip this via Handler.emit()

MAX_FAILS = 5
LOCK_SECS = 30


def _announce():
    line = "=" * 58
    print("", file=sys.stderr, flush=True)
    print("   " + line, file=sys.stderr, flush=True)
    print("    COSMETIC STATION // VEROKU-1 — SYSMON TERMINAL", file=sys.stderr, flush=True)
    print("   " + line, file=sys.stderr, flush=True)
    print("    DASH LOGIN    " + OPERATOR, file=sys.stderr, flush=True)
    print("    DASH PASSCODE " + PASSCODE, file=sys.stderr, flush=True)
    print("   " + line, file=sys.stderr, flush=True)
    print("    Credentials generated at startup (env DASH_USER / DASH_PASS to pin).",
          file=sys.stderr, flush=True)


def emit_event(event: str):
    _STATE["event"] = event


def _throttled(ip):
    with _failed_lock:
        a = _failed.get(ip)
        return bool(a and a[1] > time.time())


def _register_fail(ip):
    with _failed_lock:
        a = _failed.get(ip, [0, 0.0])
        a[0] += 1
        if a[0] >= MAX_FAILS:
            a[0] = 0
            a[1] = time.time() + LOCK_SECS
        _failed[ip] = a


def _verify(login, password):
    return secrets.compare_digest(str(login), OPERATOR) and \
        secrets.compare_digest(str(password), PASSCODE)


# ---------------------------------------------------------------- metrics
def _meminfo():
    d = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            d[k] = int(v.strip().split()[0]) * 1024  # kB -> bytes
    total = d["MemTotal"]
    avail = d["MemAvailable"]
    swap_t = d.get("SwapTotal", 0)
    swap_f = d.get("SwapFree", 0)
    return {
        "total": total,
        "used": total - avail,
        "avail": avail,
        "pct": round((total - avail) * 100 / total, 1),
        "swap_total": swap_t,
        "swap_used": swap_t - swap_f,
        "swap_pct": round((swap_t - swap_f) * 100 / swap_t, 1) if swap_t else 0,
    }


def _diskinfo():
    st = os.statvfs("/")
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - free
    return {
        "total": total,
        "used": used,
        "free": free,
        "pct": round(used * 100 / total, 1),
    }


def _load():
    with open("/proc/loadavg") as f:
        p = f.read().split()
    return {"1": float(p[0]), "5": float(p[1]), "15": float(p[2])}


def _top_procs(n=10):
    page = os.sysconf("SC_PAGE_SIZE")
    procs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/statm") as f:
                rss = int(f.read().split()[1]) * page
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
            except OSError:
                cmd = ""
            if not cmd:
                try:
                    with open(f"/proc/{pid}/comm") as f:
                        cmd = "[" + f.read().strip() + "]"
                except OSError:
                    continue
            procs.append((rss, pid, cmd[:100]))
        except (OSError, IndexError, ValueError):
            pass
    procs.sort(reverse=True)
    return [{"pid": p, "cmd": c, "mb": round(r / 1048576, 1)} for r, p, c in procs[:n]]


def _snapshot():
    return {
        "mem": _meminfo(),
        "disk": _diskinfo(),
        "load": _load(),
        "procs": _top_procs(),
        "event": _STATE.get("event", "STANDBY"),
    }


DASH_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="dark light">
<title>COSMETIC STATION // VEROKU-1 — SYSMON</title>
<style>/* ============================================================
   COSMETIC STATION // VEROKU-1 — dark chassis, amber phosphor
   Palette (committed): gunmetal panels, warm near-black screens,
   amber accent #ff6a00, warm grey text #c8b89a. Color only in LEDs.
   ============================================================ */
:root {
  --bg-1: #16140f;
  --bg-2: #0c0b08;
  --metal-1: #2c2822;
  --metal-2: #211d17;
  --metal-3: #17140f;
  --metal-edge: #3d372c;
  --metal-hi: rgba(255, 255, 255, 0.07);
  --etch: #6e6252;
  --label: #8a8072;
  --screen-bg: #0a0a08;
  --phosphor: #c8b89a;
  --phosphor-bright: #e8d8b8;
  --phosphor-dim: #7a7060;
  --phosphor-faint: #4a4438;
  --amber: #ff6a00;
  --amber-2: #e05c00;
  --amber-dim: #a04800;
  --amber-glow: rgba(255, 106, 0, 0.35);
  --led-ok: #4a7c59;
  --led-warn: #a07818;
  --led-crit: #cc2200;
  --mono: 'Cascadia Mono', 'SF Mono', 'Consolas', 'Share Tech Mono',
    'Courier New', ui-monospace, monospace;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg-1: #e8e4da;
    --bg-2: #d6d2c6;
    --metal-1: #f0ece2;
    --metal-2: #e4e0d4;
    --metal-3: #d8d4c8;
    --metal-edge: #b0a894;
    --metal-hi: rgba(255, 255, 255, 0.6);
    --etch: #8a8072;
    --label: #7a7060;
    --screen-bg: #f4f1e8;
    --phosphor: #4a4438;
    --phosphor-bright: #2a2418;
    --phosphor-dim: #7a7060;
    --phosphor-faint: #b0a894;
    --amber: #c74e00;
    --amber-2: #a04400;
    --amber-dim: #c74e00;
    --amber-glow: rgba(199, 78, 0, 0.2);
    --led-ok: #3a7c49;
    --led-warn: #9a7818;
    --led-crit: #cc2200;
  }
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
  font-family: var(--mono);
  color: var(--phosphor);
  background-color: var(--bg-2);
  background-image:
    repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.012) 0 1px, transparent 1px 3px),
    repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.12) 0 1px, transparent 1px 3px),
    radial-gradient(ellipse at 50% -10%, var(--bg-1) 0%, var(--bg-2) 60%, #060504 100%);
  background-attachment: fixed;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}

.label {
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--label);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.6);
  user-select: none;
}
.label.dim { opacity: 0.55; }

/* ---------- dark metal panel ---------- */
.panel {
  position: relative;
  background:
    repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.015) 0 1px, rgba(0, 0, 0, 0.06) 1px 2px, transparent 2px 4px),
    linear-gradient(180deg, var(--metal-1) 0%, var(--metal-2) 22%, var(--metal-3) 100%);
  border: 1px solid var(--metal-edge);
  border-radius: 3px;
  box-shadow:
    inset 0 1px 0 var(--metal-hi),
    inset 0 -1px 0 rgba(0, 0, 0, 0.5),
    0 2px 8px rgba(0, 0, 0, 0.55);
}
.panel::before {
  content: '';
  position: absolute;
  inset: 5px;
  pointer-events: none;
  opacity: 0.9;
  background-image:
    radial-gradient(circle at 4px 4px, #0d0b08 0 2.2px, #4a4236 2.2px 3px, transparent 3px),
    radial-gradient(circle at calc(100% - 4px) 4px, #0d0b08 0 2.2px, #4a4236 2.2px 3px, transparent 3px),
    radial-gradient(circle at 4px calc(100% - 4px), #0d0b08 0 2.2px, #4a4236 2.2px 3px, transparent 3px),
    radial-gradient(circle at calc(100% - 4px) calc(100% - 4px), #0d0b08 0 2.2px, #4a4236 2.2px 3px, transparent 3px);
  background-repeat: no-repeat;
}

/* ---------- phosphor screen ---------- */
.screen {
  position: relative;
  background:
    radial-gradient(ellipse at 50% 0%, #14100a 0%, var(--screen-bg) 62%, #050403 100%);
  border: 1px solid #000;
  border-radius: 2px;
  overflow: hidden;
  color: var(--phosphor);
  box-shadow:
    inset 0 0 0 1px rgba(255, 106, 0, 0.06),
    inset 0 2px 16px rgba(0, 0, 0, 0.9),
    0 1px 0 rgba(255, 255, 255, 0.05);
}
.screen::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 5;
  background-image:
    repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.03) 0 1px, transparent 1px 3px),
    radial-gradient(ellipse at center, transparent 52%, rgba(0, 0, 0, 0.55) 100%);
  animation: screen-flicker 7s infinite steps(1);
}
.screen-text { color: var(--phosphor-bright); text-shadow: 0 0 7px var(--amber-glow); }
.screen-dim { color: var(--phosphor-dim); }
.amber { color: var(--amber); text-shadow: 0 0 8px var(--amber-glow); }

/* ---------- LEDs ---------- */
.led {
  display: inline-block;
  width: 9px; height: 9px; min-width: 9px;
  border-radius: 50%;
  background: #3a352c;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.8), 0 1px 0 rgba(255, 255, 255, 0.06);
  vertical-align: middle;
}
.led.ok {
  background: var(--led-ok);
  box-shadow: 0 0 8px rgba(74, 124, 89, 0.8), inset 0 1px 1px rgba(255, 255, 255, 0.2);
  animation: led-pulse 2.6s ease-in-out infinite;
}
.led.warn {
  background: var(--led-warn);
  box-shadow: 0 0 8px rgba(160, 120, 24, 0.75), inset 0 1px 1px rgba(255, 255, 255, 0.18);
  animation: led-pulse 1.8s ease-in-out infinite;
}
.led.crit {
  background: var(--led-crit);
  box-shadow: 0 0 9px rgba(204, 34, 0, 0.85), inset 0 1px 1px rgba(255, 255, 255, 0.15);
  animation: led-pulse 1s ease-in-out infinite;
}
.led.amberled {
  background: var(--amber-2);
  box-shadow: 0 0 9px var(--amber-glow), inset 0 1px 1px rgba(255, 255, 255, 0.2);
  animation: led-pulse 2s ease-in-out infinite;
}

/* ---------- physical keys ---------- */
.key-btn {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--phosphor);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.7);
  cursor: pointer;
  user-select: none;
  background:
    repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.02) 0 1px, transparent 1px 3px),
    linear-gradient(180deg, #3a352c 0%, #2c2822 45%, #211d17 100%);
  border: 1px solid var(--metal-edge);
  border-radius: 2px;
  padding: 12px 18px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.1),
    inset 0 -1px 0 rgba(0, 0, 0, 0.5),
    0 2px 0 #0e0c09,
    0 4px 8px rgba(0, 0, 0, 0.5);
  transition: transform 0.07s ease, box-shadow 0.07s ease, filter 0.15s ease;
}
.key-btn:hover { filter: brightness(1.15); }
.key-btn:active, .key-btn.pressed {
  transform: translateY(2px) scale(0.97);
  box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.6), inset 0 -1px 0 rgba(255, 255, 255, 0.05), 0 0 0 #0e0c09;
}
.key-btn.danger { color: #e07050; border-color: #5a2a18; }
.key-btn.engaged {
  background: linear-gradient(180deg, #4a2c10 0%, #3a220c 55%, #2a1808 100%);
  border-color: var(--amber-dim);
  color: var(--amber);
  text-shadow: 0 0 8px var(--amber-glow);
}

/* ---------- dark input ---------- */
.field {
  width: 100%;
  font-family: var(--mono);
  font-size: 15px;
  letter-spacing: 0.28em;
  color: var(--amber);
  caret-color: var(--amber);
  background: #0c0a07;
  border: 1px solid #3d372c;
  border-radius: 2px;
  padding: 12px 14px;
  box-shadow: inset 0 2px 9px rgba(0, 0, 0, 0.9), 0 1px 0 rgba(255, 255, 255, 0.05);
  outline: none;
}
.field:focus {
  border-color: var(--amber-dim);
  box-shadow: inset 0 2px 9px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(255, 106, 0, 0.35), 0 0 12px rgba(255, 106, 0, 0.12);
}
.field::placeholder { color: var(--phosphor-faint); letter-spacing: 0.18em; }

/* ---------- segmented gauges ---------- */
.gauge-track {
  display: block;
  position: relative;
  height: 14px;
  background: #070604;
  border: 1px solid #000;
  border-radius: 1px;
  box-shadow: inset 0 1px 6px rgba(0, 0, 0, 0.95);
  overflow: hidden;
}
.gauge-fill {
  display: block;
  height: 100%;
  background: linear-gradient(180deg, #ff8c2a 0%, var(--amber-2) 55%, #8a3c00 100%);
  box-shadow: 0 0 10px var(--amber-glow);
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
  position: relative;
}
.gauge-fill::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(90deg, transparent 0 5px, rgba(0, 0, 0, 0.9) 5px 7px);
}
.gauge-fill.warn { background: linear-gradient(180deg, #d8b060 0%, #a07818 55%, #6a4c08 100%); }
.gauge-fill.crit { background: linear-gradient(180deg, #e06040 0%, var(--led-crit) 55%, #701808 100%); box-shadow: 0 0 12px rgba(204, 34, 0, 0.5); }

/* ---------- keyframes ---------- */
@keyframes led-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }
@keyframes screen-flicker { 0%, 100% { opacity: 1; } 3% { opacity: 0.8; } 3.6% { opacity: 1; } 77% { opacity: 0.9; } 77.5% { opacity: 1; } }
@keyframes blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
@keyframes line-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
@keyframes shake { 0%, 100% { transform: translateX(0); } 20% { transform: translateX(-7px); } 40% { transform: translateX(6px); } 60% { transform: translateX(-4px); } 80% { transform: translateX(2px); } }
@keyframes boot-sweep { 0% { transform: translateY(-100%); } 100% { transform: translateY(100%); } }
@keyframes boot-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes stream-scan { 0% { background-position: 0 -100%; } 100% { background-position: 0 200%; } }

::selection { background: var(--amber-dim); color: var(--phosphor-bright); }

/* ============================================================
   LAYOUT
   ============================================================ */
#viewport { min-height: 100vh; padding: 22px; display: flex; justify-content: center; align-items: flex-start; }
#shell {
  width: 100%;
  max-width: 1240px;
  transform-origin: top center;
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
  display: flex;
  flex-direction: column;
  gap: 14px;
}
#grid { display: grid; grid-template-columns: 370px 1fr; gap: 14px; align-items: stretch; }
.col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.pnl { padding: 16px 18px 14px; display: flex; flex-direction: column; gap: 12px; }
.pnl-head { display: flex; justify-content: space-between; align-items: baseline; padding: 0 4px; }
.pnl-foot { display: flex; justify-content: space-between; align-items: center; padding: 2px 4px 0; }

/* ---------- header ---------- */
#hdr { display: grid; grid-template-columns: 1.15fr auto 1.1fr; align-items: center; gap: 18px; padding: 14px 22px; }
.brand { display: flex; flex-direction: column; gap: 7px; }
.brand .nameRow { display: flex; align-items: center; gap: 12px; }
.brand .name {
  font-size: 17px; font-weight: 700; letter-spacing: 0.38em;
  color: var(--phosphor); text-shadow: 0 1px 0 rgba(0, 0, 0, 0.8); white-space: nowrap;
}
.clock-screen { display: flex; align-items: center; gap: 18px; padding: 10px 22px; }
.clock-date { font-size: 12px; letter-spacing: 0.28em; }
.clock-time { font-size: 24px; letter-spacing: 0.18em; line-height: 1; }
.colon { animation: blink 1s steps(1) infinite; margin: 0 1px; color: var(--amber); }
.hdr-meta { justify-self: end; display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
.hdr-meta .row { display: flex; align-items: center; gap: 8px; }
.meta-screen {
  font-size: 11px; letter-spacing: 0.22em;
  background: var(--screen-bg); padding: 2px 10px;
  border: 1px solid #000; border-radius: 1px;
  box-shadow: inset 0 1px 5px rgba(0, 0, 0, 0.9);
  min-width: 90px; text-align: center;
}

/* ---------- subsystem select ---------- */
.mod-rows { display: flex; flex-direction: column; gap: 8px; }
.mod-row {
  display: grid;
  grid-template-columns: 18px 106px 1fr 54px;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  cursor: pointer;
  text-align: left;
  font-family: var(--mono);
  border: 1px solid var(--metal-edge);
  border-radius: 2px;
  background: linear-gradient(180deg, #353028 0%, #2a251e 55%, #211d17 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 2px 0 #0e0c09, 0 4px 8px rgba(0, 0, 0, 0.45);
  transition: transform 0.07s ease, box-shadow 0.12s ease, filter 0.15s ease;
}
.mod-row:hover { filter: brightness(1.12); }
.mod-row:active { transform: translateY(2px) scale(0.985); }
.mod-row.active {
  background: linear-gradient(180deg, #3c2610 0%, #2c1c0a 55%, #1c1206 100%);
  border-color: var(--amber-dim);
  box-shadow: inset 0 1px 0 rgba(255, 180, 90, 0.12), 0 0 16px rgba(255, 106, 0, 0.15), 0 2px 0 #0e0c09;
}
.mod-row.active .mod-label, .mod-row.active .mod-pct { color: var(--amber); text-shadow: 0 0 8px var(--amber-glow); }
.mod-row .led { justify-self: center; }
.mod-label { font-size: 11px; letter-spacing: 0.22em; color: var(--phosphor); white-space: nowrap; }
.mod-pct { font-size: 11px; letter-spacing: 0.12em; text-align: right; color: var(--phosphor-dim); font-variant-numeric: tabular-nums; }
.channel {
  font-size: 10px; letter-spacing: 0.3em; padding: 3px 12px;
  background: var(--screen-bg); color: var(--amber);
  border: 1px solid #000; border-radius: 1px;
  box-shadow: inset 0 1px 5px rgba(0, 0, 0, 0.9), 0 0 8px rgba(255, 106, 0, 0.12);
  text-shadow: 0 0 8px var(--amber-glow);
}

/* ---------- task queue ---------- */
.queue-panel { flex: 1; min-height: 300px; }
.queue-screen { flex: 1; display: flex; flex-direction: column; padding: 10px 6px 6px; min-height: 220px; }
.queue-colhead {
  display: grid; grid-template-columns: 58px 54px 1fr; gap: 8px;
  padding: 2px 10px 8px;
  border-bottom: 1px solid rgba(255, 106, 0, 0.15);
  font-size: 9px; letter-spacing: 0.3em;
}
.queue-rows { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; padding: 6px 0; max-height: 320px; }
.queue-row {
  display: grid; grid-template-columns: 58px 54px 1fr; gap: 8px;
  align-items: baseline; padding: 5px 10px;
  font-family: var(--mono); font-size: 11.5px; letter-spacing: 0.05em; text-align: left;
  background: transparent; border: 1px solid transparent; border-radius: 1px;
  cursor: pointer; color: var(--phosphor);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.queue-row:hover { background: rgba(255, 106, 0, 0.06); border-color: rgba(255, 106, 0, 0.15); }
.queue-row.sel {
  background: rgba(255, 106, 0, 0.09);
  border-color: rgba(255, 106, 0, 0.4);
  box-shadow: 0 0 12px rgba(255, 106, 0, 0.12), inset 0 0 14px rgba(255, 106, 0, 0.05);
}
.queue-row .mb { text-align: right; font-variant-numeric: tabular-nums; color: var(--amber); text-shadow: 0 0 6px var(--amber-glow); }
.queue-row .pid { text-align: right; font-variant-numeric: tabular-nums; color: var(--phosphor-dim); }
.queue-row .cmd { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--phosphor); }
.queue-row.sel .pid, .queue-row.sel .cmd { color: var(--amber); text-shadow: 0 0 8px var(--amber-glow); }
.queue-empty { padding: 28px 10px; text-align: center; font-size: 10px; letter-spacing: 0.28em; }

/* ---------- VNC stream ---------- */
.stream-panel { flex: 1; min-height: 460px; }
.stream-screen { flex: 1; display: flex; flex-direction: column; min-height: 420px; }
.stream-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 106, 0, 0.15);
  flex-wrap: wrap;
}
.stream-toolbar .grow { flex: 1; }
.stream-toolbar .key-btn { padding: 8px 14px; font-size: 10px; }
.stream-frame-wrap { position: relative; flex: 1; min-height: 380px; background: #000; }
.stream-frame-wrap iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: #000; }
.stream-off {
  position: absolute; inset: 0; z-index: 3;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px;
  background:
    repeating-linear-gradient(0deg, rgba(255, 106, 0, 0.03) 0 1px, transparent 1px 4px),
    radial-gradient(ellipse at 50% 40%, #100c07 0%, #060503 100%);
}
.stream-off .big { font-size: 15px; letter-spacing: 0.4em; color: var(--amber); text-shadow: 0 0 12px var(--amber-glow); animation: led-pulse 2.4s ease-in-out infinite; }
.stream-off .sub { font-size: 9px; letter-spacing: 0.3em; color: var(--phosphor-dim); }
.stream-badge {
  font-size: 9px; letter-spacing: 0.26em; padding: 3px 12px;
  border: 1px solid rgba(255, 106, 0, 0.3); border-radius: 1px;
  color: var(--amber); text-shadow: 0 0 8px var(--amber-glow);
  background: rgba(255, 106, 0, 0.06);
}
.stream-badge.ok { border-color: rgba(74, 124, 89, 0.5); color: #7ab08f; }

/* ---------- telemetry ---------- */
.tele-screen { padding: 18px 22px 12px; display: flex; flex-direction: column; gap: 14px; }
.tele-row { display: grid; grid-template-columns: 12px 118px 1fr 62px 180px; align-items: center; gap: 14px; padding: 2px 0; }
.tele-row .t-label { font-size: 10px; letter-spacing: 0.28em; white-space: nowrap; color: var(--phosphor-dim); }
.tele-row.active .t-label { color: var(--amber); text-shadow: 0 0 8px var(--amber-glow); }
.tele-row .t-track .gauge-track { height: 17px; }
.tele-row .t-pct { font-size: 13px; letter-spacing: 0.12em; text-align: right; font-variant-numeric: tabular-nums; color: var(--amber); text-shadow: 0 0 6px var(--amber-glow); }
.tele-row .t-text { font-size: 10px; letter-spacing: 0.12em; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--phosphor-dim); }

/* ---------- detail readout (full width strip) ---------- */
.detail-screen { display: flex; align-items: stretch; gap: 0; min-height: 168px; }
.detail-lines { flex: 1; display: flex; flex-direction: column; gap: 7px; padding: 16px 22px; }
.detail-line {
  font-size: 12.5px; letter-spacing: 0.14em; white-space: pre-wrap; word-break: break-word;
  opacity: 0; animation: line-in 0.22s ease forwards;
}
.detail-cursor-row { display: flex; gap: 8px; margin-top: 4px; font-size: 12.5px; letter-spacing: 0.14em; }
.detail-cursor { animation: blink 0.9s steps(1) infinite; width: fit-content; color: var(--amber); }
.detail-side {
  width: 230px; min-width: 230px;
  border-left: 1px solid rgba(255, 106, 0, 0.15);
  padding: 16px 18px;
  display: flex; flex-direction: column; gap: 10px; justify-content: center;
}
.detail-side .s-row { display: flex; align-items: center; gap: 10px; }
.detail-side .s-label { font-size: 9px; letter-spacing: 0.28em; color: var(--phosphor-dim); }
.detail-side .s-stamp { font-size: 8.5px; letter-spacing: 0.24em; color: var(--phosphor-faint); margin-top: auto; }

/* ---------- action bar ---------- */
#actions { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 14px 20px; flex-wrap: wrap; }
.agroup { display: flex; align-items: center; gap: 10px; }
.zoom-screen {
  min-width: 74px; text-align: center; font-size: 12px; letter-spacing: 0.22em;
  background: var(--screen-bg); border: 1px solid #000; border-radius: 1px; padding: 8px 6px;
  box-shadow: inset 0 1px 6px rgba(0, 0, 0, 0.95);
  font-variant-numeric: tabular-nums; color: var(--amber); text-shadow: 0 0 6px var(--amber-glow);
}

/* ============================================================
   AUTH GATE
   ============================================================ */
#auth-wrap { min-height: calc(100vh - 44px); display: flex; align-items: center; justify-content: center; }
#auth-plate { width: 100%; max-width: 640px; padding: 18px; display: flex; flex-direction: column; gap: 14px; }
.auth-row { display: flex; justify-content: space-between; gap: 12px; padding: 2px 6px; flex-wrap: wrap; }
#auth-screen { padding: 30px 30px 22px; }
#auth-screen.shake { animation: shake 0.45s ease; }
.crest { display: flex; align-items: center; gap: 18px; margin-bottom: 26px; }
.crest-ring {
  width: 52px; height: 52px; min-width: 52px;
  border: 1px solid var(--amber-dim); border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 16px rgba(255, 106, 0, 0.2);
  animation: led-pulse 3.2s ease-in-out infinite;
}
.crest-core {
  width: 18px; height: 18px; border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #ffb060 0%, var(--amber-2) 55%, #6a2c00 100%);
  box-shadow: 0 0 12px var(--amber-glow);
}
.crest .title { font-size: 19px; letter-spacing: 0.32em; text-transform: uppercase; }
.crest .sub { margin-top: 8px; font-size: 10px; letter-spacing: 0.22em; }
.auth-form { display: flex; flex-direction: column; gap: 8px; }
.auth-form .flabel { font-size: 10px; letter-spacing: 0.3em; margin-top: 10px; color: var(--phosphor-dim); }
.auth-actions { display: flex; gap: 12px; margin-top: 24px; }
.auth-actions .key-btn { flex: 1; }
.auth-status { display: flex; align-items: center; gap: 10px; margin-top: 26px; padding-top: 14px; border-top: 1px solid rgba(255, 106, 0, 0.15); }
.auth-status .st { font-size: 11px; letter-spacing: 0.26em; }
.auth-hint { margin-top: 12px; font-size: 8.5px; letter-spacing: 0.18em; line-height: 1.9; opacity: 0.75; color: var(--phosphor-dim); }

/* ============================================================
   BOOT + KEYPAD
   ============================================================ */
#boot {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
  background:
    repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.02) 0 1px, transparent 1px 3px),
    radial-gradient(ellipse at 50% 40%, #120e08 0%, #060503 70%);
  animation: boot-in 0.2s ease;
}
#boot .sweep {
  position: absolute; left: 0; right: 0; height: 120px;
  background: linear-gradient(180deg, transparent 0%, rgba(255, 106, 0, 0.05) 50%, transparent 100%);
  animation: boot-sweep 1.6s linear infinite;
}
#boot .lines { width: min(560px, 86vw); display: flex; flex-direction: column; gap: 7px; }
#boot .bl { font-size: 13px; letter-spacing: 0.16em; white-space: pre; overflow: hidden; text-overflow: ellipsis; opacity: 0; animation: line-in 0.18s ease forwards; }
#boot .bcur { font-size: 13px; margin-top: 6px; animation: blink 0.85s steps(1) infinite; width: fit-content; color: var(--amber); }

#keypad {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 150;
  transform: translateY(110%);
  transition: transform 0.38s cubic-bezier(0.22, 1, 0.36, 1);
  pointer-events: none;
  display: flex; justify-content: center; padding: 0 12px 12px;
}
#keypad.open { transform: translateY(0); pointer-events: auto; }
.kb-plate {
  width: min(760px, 100%);
  border: 1px solid var(--metal-edge);
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  background:
    repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.015) 0 1px, rgba(0, 0, 0, 0.06) 1px 2px, transparent 2px 4px),
    linear-gradient(180deg, var(--metal-1) 0%, var(--metal-2) 22%, var(--metal-3) 100%);
  box-shadow: inset 0 1px 0 var(--metal-hi), 0 -10px 34px rgba(0, 0, 0, 0.65);
  padding: 10px 12px 16px;
}
.kb-grip { display: flex; align-items: center; gap: 14px; padding: 4px 4px 12px; }
.kb-grip .bar { display: inline-block; width: 44px; height: 4px; border-radius: 2px; background: #0e0c09; box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.8); }
.kb-grip .label { flex: 1; }
.kb-grip .key-btn { padding: 8px 16px; font-size: 10px; }
.kb-keys { display: flex; flex-direction: column; gap: 8px; }
.kb-row { display: flex; gap: 6px; justify-content: center; }
.kb-key { flex: 1 1 0; min-width: 0; padding: 14px 4px; font-size: 13px; letter-spacing: 0.08em; text-align: center; }
.kb-key.wide { flex: 1.6 1 0; font-size: 10px; letter-spacing: 0.22em; }
.kb-key.space { flex: 4 1 0; font-size: 10px; letter-spacing: 0.32em; }

@media (max-width: 1024px) {
  #grid { grid-template-columns: 1fr; }
  #viewport { padding: 12px; }
  #hdr { grid-template-columns: 1fr; justify-items: center; text-align: center; }
  .hdr-meta { justify-self: center; align-items: center; }
  .brand .name { letter-spacing: 0.22em; font-size: 14px; }
  .tele-row { grid-template-columns: 12px 106px 1fr 56px; }
  .tele-row .t-text { display: none; }
  .detail-side { display: none; }
}
@media (max-width: 720px) {
  .kb-key { padding: 11px 2px; font-size: 11px; }
  .kb-row { gap: 4px; }
  .stream-panel { min-height: 360px; }
}
</style>
</head>
<body>
<div id="root"></div>
<script>window.__VNC_CFG__ = __VNC_CFG_JSON__;</script>
<script>(()=>{var X,E,De,rt,L,Ce,Me,Ie,re,z,F,Le,ie,le,ae,lt,Q={},Z=[],at=/acit|ex(?:s|g|n|p|$)|rph|grid|ows|mnc|ntw|ine[ch]|zoo|^ord|itera/i,J=Array.isArray;function I(e,t){for(var n in t)e[n]=t[n];return e}function ce(e){e&&e.parentNode&&e.parentNode.removeChild(e)}function it(e,t,n){var o,a,r,i={};for(r in t)r=="key"?o=t[r]:r=="ref"?a=t[r]:i[r]=t[r];if(arguments.length>2&&(i.children=arguments.length>3?X.call(arguments,2):n),typeof e=="function"&&e.defaultProps!=null)for(r in e.defaultProps)i[r]===void 0&&(i[r]=e.defaultProps[r]);return G(e,i,o,a,null)}function G(e,t,n,o,a){var r={type:e,props:t,key:n,ref:o,__k:null,__:null,__b:0,__e:null,__c:null,constructor:void 0,__v:a==null?++De:a,__i:-1,__u:0};return a==null&&E.vnode!=null&&E.vnode(r),r}function U(e){return e.children}function q(e,t){this.props=e,this.context=t}function x(e,t){if(t==null)return e.__?x(e.__,e.__i+1):null;for(var n;t<e.__k.length;t++)if((n=e.__k[t])!=null&&n.__e!=null)return n.__e;return typeof e.type=="function"?x(e):null}function ct(e){if(e.__P&&e.__d){var t=e.__v,n=t.__e,o=[],a=[],r=I({},t);r.__v=t.__v+1,E.vnode&&E.vnode(r),_e(e.__P,r,t,e.__n,e.__P.namespaceURI,32&t.__u?[n]:null,o,n==null?x(t):n,!!(32&t.__u),a),r.__v=t.__v,r.__.__k[r.__i]=r,$e(o,r,a),t.__e=t.__=null,r.__e!=n&&Ue(r)}}function Ue(e){if((e=e.__)!=null&&e.__c!=null)return e.__e=e.__c.base=null,e.__k.some(function(t){if(t!=null&&t.__e!=null)return e.__e=e.__c.base=t.__e}),Ue(e)}function Ne(e){(!e.__d&&(e.__d=!0)&&L.push(e)&&!j.__r++||Ce!=E.debounceRendering)&&((Ce=E.debounceRendering)||Me)(j)}function j(){try{for(var e,t=1;L.length;)L.length>t&&L.sort(Ie),e=L.shift(),t=L.length,ct(e)}finally{L.length=j.__r=0}}function xe(e,t,n,o,a,r,i,c,u,_,p){var v,l,d,b,k,m,f=o&&o.__k||Z,h=t.length;for(u=_t(n,t,f,u,h),v=0;v<h;v++)(d=n.__k[v])!=null&&(l=d.__i!=-1&&f[d.__i]||Q,d.__i=v,m=_e(e,d,l,a,r,i,c,u,_,p),b=d.__e,d.ref&&l.ref!=d.ref&&(l.ref&&ue(l.ref,null,d),p.push(d.ref,d.__c||b,d)),k==null&&b!=null&&(k=b),4&d.__u?(u=Pe(d,u,e),l.__e&&(l.__e=null)):typeof d.type=="function"&&m!==void 0?u=m:b&&(u=b.nextSibling),d.__u&=-7);return n.__e=k,u}function _t(e,t,n,o,a){var r,i,c,u,_,p=n.length,v=p,l=0;for(e.__k=new Array(a),r=0;r<a;r++)(i=t[r])!=null&&typeof i!="boolean"&&typeof i!="function"?(typeof i=="string"||typeof i=="number"||typeof i=="bigint"||i.constructor==String?i=e.__k[r]=G(null,i,null,null,null):J(i)?i=e.__k[r]=G(U,{children:i},null,null,null):i.constructor===void 0&&i.__b>0?i=e.__k[r]=G(i.type,i.props,i.key,i.ref?i.ref:null,i.__v):e.__k[r]=i,u=r+l,i.__=e,i.__b=e.__b+1,c=null,(_=i.__i=ut(i,n,u,v))!=-1&&(v--,(c=n[_])&&(c.__u|=2)),c==null||c.__v==null?(_==-1&&(a>p?l--:a<p&&l++),typeof i.type!="function"&&(i.__u|=4)):_!=u&&(_==u-1?l--:_==u+1?l++:(_>u?l--:l++,i.__u|=4))):e.__k[r]=null;if(v)for(r=0;r<p;r++)(c=n[r])!=null&&!(2&c.__u)&&(c.__e==o&&(o=x(c)),Fe(c,c));return o}function Pe(e,t,n){var o,a;if(typeof e.type=="function"){for(o=e.__k,a=0;o&&a<o.length;a++)o[a]&&(o[a].__=e,t=Pe(o[a],t,n));return t}e.__e!=t&&(t&&e.type&&!t.parentNode&&(t=x(e)),t=n.insertBefore(e.__e,t||null));do t=t&&t.nextSibling;while(t!=null&&t.nodeType==8);return t}function ut(e,t,n,o){var a,r,i,c=e.key,u=e.type,_=t[n],p=_!=null&&(2&_.__u)==0;if(_===null&&c==null||p&&c==_.key&&u==_.type)return n;if(o>(p?1:0)){for(a=n-1,r=n+1;a>=0||r<t.length;)if((_=t[i=a>=0?a--:r++])!=null&&!(2&_.__u)&&c==_.key&&u==_.type)return i}return-1}function Re(e,t,n){t[0]=="-"?e.setProperty(t,n==null?"":n):e[t]=n==null?"":typeof n!="number"||at.test(t)?n:n+"px"}function V(e,t,n,o,a){var r,i;e:if(t=="style")if(typeof n=="string")e.style.cssText=n;else{if(typeof o=="string"&&(e.style.cssText=o=""),o)for(t in o)n&&t in n||Re(e.style,t,"");if(n)for(t in n)o&&n[t]==o[t]||Re(e.style,t,n[t])}else if(t[0]=="o"&&t[1]=="n")r=t!=(t=t.replace(Le,"$1")),i=t.toLowerCase(),t=i in e||t=="onFocusOut"||t=="onFocusIn"?i.slice(2):t.slice(2),e.l||(e.l={}),e.l[t+r]=n,n?o?n[F]=o[F]:(n[F]=ie,e.addEventListener(t,r?ae:le,r)):e.removeEventListener(t,r?ae:le,r);else{if(a=="http://www.w3.org/2000/svg")t=t.replace(/xlink(H|:h)/,"h").replace(/sName$/,"s");else if(t!="width"&&t!="height"&&t!="href"&&t!="list"&&t!="form"&&t!="tabIndex"&&t!="download"&&t!="rowSpan"&&t!="colSpan"&&t!="role"&&t!="popover"&&t in e)try{e[t]=n==null?"":n;break e}catch{}typeof n=="function"||(n==null||n===!1&&t[4]!="-"?e.removeAttribute(t):e.setAttribute(t,t=="popover"&&n==1?"":n))}}function we(e){return function(t){if(this.l){var n=this.l[t.type+e];if(t[z]==null)t[z]=ie++;else if(t[z]<n[F])return;return n(E.event?E.event(t):t)}}}function _e(e,t,n,o,a,r,i,c,u,_){var p,v,l,d,b,k,m,f,h,y,w,N,g,S,W,oe,M=t.type;if(t.constructor!==void 0)return null;128&n.__u&&(u=!!(32&n.__u),r=[c=t.__e=n.__e]),(p=E.__b)&&p(t);e:if(typeof M=="function"){v=i.length;try{if(h=t.props,y=M.prototype&&M.prototype.render,w=(p=M.contextType)&&o[p.__c],N=p?w?w.props.value:p.__:o,n.__c?f=(l=t.__c=n.__c).__=l.__E:(y?t.__c=l=new M(h,N):(t.__c=l=new q(h,N),l.constructor=M,l.render=dt),w&&w.sub(l),l.state||(l.state={}),l.__n=o,d=l.__d=!0,l.__h=[],l._sb=[]),y&&l.__s==null&&(l.__s=l.state),y&&M.getDerivedStateFromProps!=null&&(l.__s==l.state&&(l.__s=I({},l.__s)),I(l.__s,M.getDerivedStateFromProps(h,l.__s))),b=l.props,k=l.state,l.__v=t,d)y&&M.getDerivedStateFromProps==null&&l.componentWillMount!=null&&l.componentWillMount(),y&&l.componentDidMount!=null&&l.__h.push(l.componentDidMount);else{if(y&&M.getDerivedStateFromProps==null&&h!==b&&l.componentWillReceiveProps!=null&&l.componentWillReceiveProps(h,N),t.__v==n.__v||!l.__e&&l.shouldComponentUpdate!=null&&l.shouldComponentUpdate(h,l.__s,N)===!1){t.__v!=n.__v&&(l.props=h,l.state=l.__s,l.__d=!1),t.__e=n.__e,t.__k=n.__k,t.__k.some(function($){$&&($.__=t)}),Z.push.apply(l.__h,l._sb),l._sb=[],l.__h.length&&i.push(l),c=x(n);break e}l.componentWillUpdate!=null&&l.componentWillUpdate(h,l.__s,N),y&&l.componentDidUpdate!=null&&l.__h.push(function(){l.componentDidUpdate(b,k,m)})}if(l.context=N,l.props=h,l.__P=e,l.__e=!1,g=E.__r,S=0,y)l.state=l.__s,l.__d=!1,g&&g(t),p=l.render(l.props,l.state,l.context),Z.push.apply(l.__h,l._sb),l._sb=[];else do l.__d=!1,g&&g(t),p=l.render(l.props,l.state,l.context),l.state=l.__s;while(l.__d&&++S<25);l.state=l.__s,l.getChildContext!=null&&(o=I(I({},o),l.getChildContext())),y&&!d&&l.getSnapshotBeforeUpdate!=null&&(m=l.getSnapshotBeforeUpdate(b,k)),W=p!=null&&p.type===U&&p.key==null?He(p.props.children):p,c=xe(e,J(W)?W:[W],t,n,o,a,r,i,c,u,_),l.base=t.__e,t.__u&=-161,l.__h.length&&i.push(l),f&&(l.__E=l.__=null)}catch($){if(i.length=v,t.__v=null,u||r!=null){if($.then){for(t.__u|=u?160:128;c&&c.nodeType==8&&c.nextSibling;)c=c.nextSibling;r!=null&&(r[r.indexOf(c)]=null),t.__e=c}else if(r!=null)for(oe=r.length;oe--;)ce(r[oe])}else t.__e=n.__e;t.__k==null&&(t.__k=n.__k||[]),$.then||Ke(t),E.__e($,t,n)}}else r==null&&t.__v==n.__v?(t.__k=n.__k,t.__e=n.__e):c=t.__e=pt(n.__e,t,n,o,a,r,i,u,_);return(p=E.diffed)&&p(t),128&t.__u?void 0:c}function Ke(e){e&&(e.__c&&(e.__c.__e=!0),e.__k&&e.__k.some(Ke))}function $e(e,t,n){for(var o=0;o<n.length;o++)ue(n[o],n[++o],n[++o]);E.__c&&E.__c(t,e),e.some(function(a){try{e=a.__h,a.__h=[],e.some(function(r){r.call(a)})}catch(r){E.__e(r,a.__v)}})}function He(e){return typeof e!="object"||e==null||e.__b>0?e:J(e)?e.map(He):e.constructor!==void 0?null:I({},e)}function pt(e,t,n,o,a,r,i,c,u){var _,p,v,l,d,b,k,m=n.props||Q,f=t.props,h=t.type;if(h=="svg"?a="http://www.w3.org/2000/svg":h=="math"?a="http://www.w3.org/1998/Math/MathML":a||(a="http://www.w3.org/1999/xhtml"),r!=null){for(_=0;_<r.length;_++)if((d=r[_])&&"setAttribute"in d==!!h&&(h?d.localName==h:d.nodeType==3)){e=d,r[_]=null;break}}if(e==null){if(h==null)return document.createTextNode(f);e=document.createElementNS(a,h,f.is&&f),c&&(E.__m&&E.__m(t,r),c=!1),r=null}if(h==null)m===f||c&&e.data==f||(e.data=f);else{if(r=h=="textarea"&&f.defaultValue!=null?null:r&&X.call(e.childNodes),!c&&r!=null)for(m={},_=0;_<e.attributes.length;_++)m[(d=e.attributes[_]).name]=d.value;for(_ in m)d=m[_],_=="dangerouslySetInnerHTML"?v=d:_=="children"||_ in f||_=="value"&&"defaultValue"in f||_=="checked"&&"defaultChecked"in f||V(e,_,null,d,a);for(_ in f)d=f[_],_=="children"?l=d:_=="dangerouslySetInnerHTML"?p=d:_=="value"?b=d:_=="checked"?k=d:c&&typeof d!="function"||m[_]===d||V(e,_,d,m[_],a);if(p)c||v&&(p.__html==v.__html||p.__html==e.innerHTML)||(e.innerHTML=p.__html),t.__k=[];else if(v&&(e.innerHTML=""),xe(t.type=="template"?e.content:e,J(l)?l:[l],t,n,o,h=="foreignObject"?"http://www.w3.org/1999/xhtml":a,r,i,r?r[0]:n.__k&&x(n,0),c,u),r!=null)for(_=r.length;_--;)ce(r[_]);c&&h!="textarea"||(_="value",h=="progress"&&b==null?e.removeAttribute("value"):b!=null&&(b!==e[_]||h=="progress"&&!b||h=="option"&&b!=m[_])&&V(e,_,b,m[_],a),_="checked",k!=null&&k!=e[_]&&V(e,_,k,m[_],a))}return e}function ue(e,t,n){try{if(typeof e=="function"){var o=typeof e.__u=="function";o&&e.__u(),o&&t==null||(e.__u=e(t))}else e.current=t}catch(a){E.__e(a,n)}}function Fe(e,t,n){var o,a;if(E.unmount&&E.unmount(e),(o=e.ref)&&(o.current&&o.current!=e.__e||ue(o,null,t)),(o=e.__c)!=null){if(o.componentWillUnmount)try{o.componentWillUnmount()}catch(r){E.__e(r,t)}o.base=o.__P=o.__n=null}if(o=e.__k)for(a=0;a<o.length;a++)o[a]&&Fe(o[a],t,n||typeof e.type!="function");n||ce(e.__e),e.__c=e.__=e.__e=void 0}function dt(e,t,n){return this.constructor(e,n)}function Be(e,t,n){var o,a,r,i;t==document&&(t=document.documentElement),E.__&&E.__(e,t),a=(o=typeof n=="function")?null:n&&n.__k||t.__k,r=[],i=[],_e(t,e=(!o&&n||t).__k=it(U,null,[e]),a||Q,Q,t.namespaceURI,!o&&n?[n]:a?null:t.firstChild?X.call(t.childNodes):null,r,!o&&n?n:a?a.__e:t.firstChild,o,i),$e(r,e,i),e.props.children=null}X=Z.slice,E={__e:function(e,t,n,o){for(var a,r,i;t=t.__;)if((a=t.__c)&&!a.__)try{if((r=a.constructor)&&r.getDerivedStateFromError!=null&&(a.setState(r.getDerivedStateFromError(e)),i=a.__d),a.componentDidCatch!=null&&(a.componentDidCatch(e,o||{}),i=a.__d),i)return a.__E=a}catch(c){e=c}throw e}},De=0,rt=function(e){return e!=null&&e.constructor===void 0},q.prototype.setState=function(e,t){var n;n=this.__s!=null&&this.__s!=this.state?this.__s:this.__s=I({},this.state),typeof e=="function"&&(e=e(I({},n),this.props)),e&&I(n,e),e!=null&&this.__v&&(t&&this._sb.push(t),Ne(this))},q.prototype.forceUpdate=function(e){this.__v&&(this.__e=!0,e&&this.__h.push(e),Ne(this))},q.prototype.render=U,L=[],Me=typeof Promise=="function"?Promise.prototype.then.bind(Promise.resolve()):setTimeout,Ie=function(e,t){return e.__v.__b-t.__v.__b},j.__r=0,re=Math.random().toString(8),z="__d"+re,F="__a"+re,Le=/(PointerCapture)$|Capture$/i,ie=0,le=we(!1),ae=we(!0),lt=0;var B,A,pe,Ye,Y=0,je=[],O=E,We=O.__b,Ve=O.__r,ze=O.diffed,Ge=O.__c,qe=O.unmount,Qe=O.__;function fe(e,t){O.__h&&O.__h(A,e,Y||t),Y=0;var n=A.__H||(A.__H={__:[],__h:[]});return e>=n.__.length&&n.__.push({}),n.__[e]}function R(e){return Y=1,me(et,e)}function me(e,t,n){var o=fe(B++,2);if(o.t=e,!o.__c&&(o.__=[n?n(t):et(void 0,t),function(c){var u=o.__N?o.__N[0]:o.__[0],_=o.t(u,c);u!==_&&(o.__N=[_,o.__[1]],o.__c.setState({}))}],o.__c=A,!A.__f)){var a=function(c,u,_){if(!o.__c.__H)return!0;var p=!1,v=o.__c.props!==c;if(o.__c.__H.__.some(function(d){if(d.__N){p=!0;var b=d.__[0];d.__=d.__N,d.__N=void 0,b!==d.__[0]&&(v=!0)}}),r){var l=r.call(this,c,u,_);return p?l||v:l}return!p||v};A.__f=!0;var r=A.shouldComponentUpdate,i=A.componentWillUpdate;A.componentWillUpdate=function(c,u,_){if(this.__e){var p=r;r=void 0,a(c,u,_),r=p}i&&i.call(this,c,u,_)},A.shouldComponentUpdate=a}return o.__N||o.__}function C(e,t){var n=fe(B++,3);!O.__s&&Je(n.__H,t)&&(n.__=e,n.u=t,A.__H.__h.push(n))}function D(e){return Y=5,Xe(function(){return{current:e}},[])}function Xe(e,t){var n=fe(B++,7);return Je(n.__H,t)&&(n.__=e(),n.__H=t,n.__h=e),n.__}function P(e,t){return Y=8,Xe(function(){return e},t)}function ft(){for(var e;e=je.shift();){var t=e.__H;if(e.__P&&t)try{t.__h.some(ee),t.__h.some(de),t.__h=[]}catch(n){t.__h=[],O.__e(n,e.__v)}}}O.__b=function(e){A=null,We&&We(e)},O.__=function(e,t){e&&t.__k&&t.__k.__m&&(e.__m=t.__k.__m),Qe&&Qe(e,t)},O.__r=function(e){Ve&&Ve(e),B=0;var t=(A=e.__c).__H;t&&(pe===A?(t.__h=[],A.__h=[],t.__.some(function(n){n.__N&&(n.__=n.__N),n.u=n.__N=void 0})):(t.__h.some(ee),t.__h.some(de),t.__h=[],B=0)),pe=A},O.diffed=function(e){ze&&ze(e);var t=e.__c;t&&t.__H&&(t.__H.__h.length&&(je.push(t)!==1&&Ye===O.requestAnimationFrame||((Ye=O.requestAnimationFrame)||mt)(ft)),t.__H.__.some(function(n){n.u&&(n.__H=n.u,n.u=void 0)})),pe=A=null},O.__c=function(e,t){t.some(function(n){try{n.__h.some(ee),n.__h=n.__h.filter(function(o){return!o.__||de(o)})}catch(o){t.some(function(a){a.__h&&(a.__h=[])}),t=[],O.__e(o,n.__v)}}),Ge&&Ge(e,t)},O.unmount=function(e){qe&&qe(e);var t,n=e.__c;n&&n.__H&&(n.__H.__.some(function(o){try{ee(o)}catch(a){t=a}}),n.__H=void 0,t&&O.__e(t,n.__v))};var Ze=typeof requestAnimationFrame=="function";function mt(e){var t,n=function(){clearTimeout(o),Ze&&cancelAnimationFrame(t),setTimeout(e)},o=setTimeout(n,35);Ze&&(t=requestAnimationFrame(n))}function ee(e){var t=A,n=e.__c;typeof n=="function"&&(e.__c=void 0,n()),A=t}function de(e){var t=A;e.__c=e.__(),A=t}function Je(e,t){return!e||e.length!==t.length||t.some(function(n,o){return n!==e[o]})}function et(e,t){return typeof t=="function"?t(e):t}var vt=0,Rt=Array.isArray;function s(e,t,n,o,a,r){t||(t={});var i,c,u=t;if("ref"in u)for(c in u={},t)c=="ref"?i=t[c]:u[c]=t[c];var _={type:e,props:u,key:n,ref:i,__k:null,__:null,__b:0,__e:null,__c:null,constructor:void 0,__v:--vt,__i:-1,__u:0,__source:a,__self:r};if(typeof e=="function"&&(i=e.defaultProps))for(c in i)u[c]===void 0&&(u[c]=i[c]);return E.vnode&&E.vnode(_),_}function ve({onLogin:e,error:t,busy:n,onKeypad:o}){let a=D(null),r=D(null),[i,c]=R(!1),u=D(null);return C(()=>{if(t&&u.current!==t){u.current=t,c(!0);let p=setTimeout(()=>c(!1),450);return()=>clearTimeout(p)}},[t]),s("div",{id:"auth-wrap",children:s("div",{className:"panel",id:"auth-plate",children:[s("div",{className:"auth-row",children:[s("span",{class:"label",children:"COSMETIC STATION"}),s("span",{class:"label dim",children:"UNIT VEROKU-1 // ACCESS GATE"})]}),s("div",{className:`screen ${i?"shake":""}`,id:"auth-screen",children:[s("div",{className:"crest",children:[s("div",{className:"crest-ring",children:s("div",{className:"crest-core"})}),s("div",{children:[s("div",{class:"screen-text title",children:"IDENTIFICATION REQUIRED"}),s("div",{class:"screen-dim sub",children:"SYSMON TERMINAL 04 \xB7 SESSION CREDENTIALS MANDATORY"})]})]}),s("form",{class:"auth-form",onSubmit:p=>{var d,b,k,m;p.preventDefault();let v=(b=(d=a.current)==null?void 0:d.value)!=null?b:"",l=(m=(k=r.current)==null?void 0:k.value)!=null?m:"";if(!v||!l){c(!0),setTimeout(()=>c(!1),450);return}e(v,l),r.current&&(r.current.value="")},children:[s("label",{class:"flabel",for:"op-id",children:"OPERATOR ID"}),s("input",{id:"op-id",class:"field",type:"text",autocomplete:"off",spellcheck:"false",placeholder:"\u2014\u2014\u2014\u2014",ref:a,disabled:n}),s("label",{class:"flabel",for:"op-pass",children:"PASSCODE"}),s("input",{id:"op-pass",class:"field",type:"password",autocomplete:"off",placeholder:"\xB7\xB7\xB7\xB7\xB7\xB7\xB7\xB7",ref:r,disabled:n}),s("div",{class:"auth-actions",children:[s("button",{type:"submit",class:"key-btn",id:"btn-auth",disabled:n,children:n?"VERIFYING\u2026":"AUTHORIZE"}),s("button",{type:"button",class:"key-btn",onClick:o,children:"KEYPAD"})]})]}),s("div",{class:"auth-status",children:[s("span",{class:`led ${t?"crit":"ok"}`}),s("span",{class:"screen-text st",children:t||(n?"CHECKING CREDENTIALS\u2026":"GATE READY")})]}),s("div",{class:"auth-hint",children:"ACCESS CREDENTIALS ARE GENERATED BY CONTROL AT START \u2014 CHECK SERVER CONSOLE / LOG."})]}),s("div",{class:"auth-row",children:[s("span",{class:"label dim",children:"NO TERMINAL ACCESS BEYOND THIS GATE"}),s("span",{class:"label dim",children:"PRESS ENTER TO AUTHORIZE"})]})]})})}var ht=["COSMETIC STATION // UNIT VEROKU-1","SYSMON TERMINAL 04 \u2014 COLD START","\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014","MEM CORE ........................ OK","SWAP BANK ....................... OK","DISK ARRAY ...................... OK","BUS LOAD ........................ OK","PHOSPHOR LINK ................... OK","UPLINK STREAM ................... ARMED","IDENT CONFIRMED ................. {OP}","ACCESS GRANTED"];function he({operator:e,onDone:t}){return C(()=>{let n=setTimeout(t,2500);return()=>clearTimeout(n)},[t]),s("div",{id:"boot",children:[s("div",{class:"sweep"}),s("div",{class:"lines",children:[ht.map((n,o)=>s("div",{class:"screen-text bl",style:{animationDelay:`${o*.16}s`},children:n.replace("{OP}",e||"UNKNOWN")})),s("div",{class:"screen-text bcur",children:"\u2588"})]})]})}var K=e=>String(e).padStart(2,"0");function tt(){let[e,t]=R(()=>new Date);return C(()=>{let n=setInterval(()=>t(new Date),1e3);return()=>clearInterval(n)},[]),{date:`${e.getFullYear()}-${K(e.getMonth()+1)}-${K(e.getDate())}`,hh:K(e.getHours()),mm:K(e.getMinutes()),ss:K(e.getSeconds())}}function nt(e,t){let[n,o]=R(null),[a,r]=R(null),[i,c]=R(null),u=D(t);u.current=t;let _=P(async()=>{var p;if(e)try{let v=await fetch("/api",{headers:{Authorization:`Bearer ${e}`}});if(v.status===401){r("SESSION LOST"),(p=u.current)==null||p.call(u);return}let l=await v.json();o(l),r(null),c(new Date)}catch{r("LINK DOWN")}},[e]);return C(()=>{if(!e)return;o(null),_();let p=setInterval(_,5e3);return()=>clearInterval(p)},[e,_]),{data:n,error:a,lastUpdate:i,refresh:_}}function T(e){if(e==null||isNaN(e))return"--";let t=e/1048576;return t>=1024?`${(t/1024).toFixed(2)} GB`:`${t.toFixed(1)} MB`}function H(e){return e==null?"led":e>85?"led crit":e>70?"led warn":"led ok"}function te(e){return e==null?"gauge-fill":e>85?"gauge-fill crit":e>70?"gauge-fill warn":"gauge-fill"}function ne(e){return e==null?"--":e>85?"THRESHOLD EXCEEDED":e>70?"ELEVATED":"NOMINAL"}function st(e){if(e==null)return"--";let t=Math.floor(e/86400),n=Math.floor(e%86400/3600),o=Math.floor(e%3600/60);return`${t}D ${K(n)}H ${K(o)}M`}function Ee({operator:e,zoom:t,lastUpdate:n,linkError:o,event:a}){let r=tt(),i=!o;return s("header",{class:"panel",id:"hdr",children:[s("div",{class:"brand",children:[s("div",{class:"nameRow",children:[s("span",{class:`led ${i?"ok":"crit"}`}),s("span",{class:"name",children:"COSMETIC STATION"})]}),s("span",{class:"label dim",children:"UNIT VEROKU-1 // SYSMON TERMINAL 04"})]}),s("div",{children:s("div",{class:"screen clock-screen",children:[s("span",{class:"screen-text clock-date",children:r.date}),s("span",{class:"screen-text clock-time",children:[r.hh,s("span",{class:"colon",children:":"}),r.mm,s("span",{class:"colon",children:":"}),r.ss]})]})}),s("div",{class:"hdr-meta",children:[s("div",{class:"row",children:[s("span",{class:"label dim",children:"OPERATOR"}),s("span",{class:"screen-text meta-screen",children:e||"\u2014"})]}),s("div",{class:"row",children:[s("span",{class:"label dim",children:"ZOOM"}),s("span",{class:"screen-text meta-screen",children:[Math.round(t*100),"%"]})]}),s("div",{class:"row",children:[s("span",{class:`led ${i?"ok":"crit"}`}),s("span",{class:`led ${a==="TOKEN ACQUIRED"?"amberled":"ok"}`}),s("span",{class:"label dim",children:[a||(i?"LINK \xB7 AUTO 5S":"LINK DOWN"),n?` \xB7 UPD ${String(n.getHours()).padStart(2,"0")}:${String(n.getMinutes()).padStart(2,"0")}`:""]})]})]})]})}var Et=e=>{var n,o;if(!e)return[{id:"mem",label:"MEM CORE",pct:null},{id:"swap",label:"SWAP BANK",pct:null},{id:"disk",label:"DISK ARRAY",pct:null},{id:"load",label:"BUS LOAD",pct:null},{id:"procs",label:"TASK QUEUE",pct:null}];let t=Math.min(100,e.load[1]/Math.max(1,e.cpus)*100);return[{id:"mem",label:"MEM CORE",pct:e.mem.pct},{id:"swap",label:"SWAP BANK",pct:e.mem.swap_pct},{id:"disk",label:"DISK ARRAY",pct:e.disk.pct},{id:"load",label:"BUS LOAD",pct:t},{id:"procs",label:"TASK QUEUE",pct:((o=(n=e.procs)==null?void 0:n.length)!=null?o:0)*10}]};function be({active:e,data:t,onSelect:n}){return s("div",{class:"panel pnl",children:[s("div",{class:"pnl-head",children:[s("span",{class:"label",children:"SUBSYSTEM SELECT"}),s("span",{class:"label dim",children:"TOGGLE // REPORT"})]}),s("div",{class:"mod-rows",children:Et(t).map(o=>{var a;return s("button",{type:"button",class:`mod-row ${e===o.id?"active":""}`,"aria-pressed":e===o.id,onClick:()=>n(o.id),children:[s("span",{class:H(o.pct)}),s("span",{class:"mod-label",children:o.label}),s("span",{children:s("span",{class:"gauge-track",children:s("span",{class:te(o.pct),style:{width:`${Math.min(100,(a=o.pct)!=null?a:0)}%`}})})}),s("span",{class:"mod-pct",children:[o.pct==null?"--.-":o.pct.toFixed(1),"%"]})]})})}),s("div",{class:"pnl-foot",children:[s("span",{class:"label dim",children:"ACTIVE CHANNEL MARKED"}),s("span",{class:"channel",children:e.toUpperCase()})]})]})}function ye({procs:e,selected:t,onSelect:n}){return s("div",{class:"panel pnl queue-panel",children:[s("div",{class:"pnl-head",children:[s("span",{class:"label",children:"TASK QUEUE"}),s("span",{class:"label dim",children:"TOP MEMORY CONSUMERS"})]}),s("div",{class:"screen queue-screen",children:[s("div",{class:"queue-colhead",children:[s("span",{class:"screen-dim",style:"text-align:right",children:"MEM"}),s("span",{class:"screen-dim",style:"text-align:right",children:"PID"}),s("span",{class:"screen-dim",children:"TASK"})]}),s("div",{class:"queue-rows",children:[e.length===0&&s("div",{class:"screen-dim queue-empty",children:"\u2014 NO TASK DATA // AWAITING LINK \u2014"}),e.map((o,a)=>s("button",{type:"button",class:`queue-row ${a===t?"sel":""}`,onClick:()=>n(a),children:[s("span",{class:"mb",children:o.mb.toFixed(1)}),s("span",{class:"pid",children:o.pid}),s("span",{class:"cmd",children:o.cmd})]}))]})]}),s("div",{class:"pnl-foot",children:[s("span",{class:"label dim",children:"SELECT ROW FOR READOUT"}),s("span",{class:"label dim",children:[e.length," ACTIVE"]})]})]})}function Ae({vncUrl:e,vncPassword:t,event:n}){let[o,a]=R(!1),[r,i]=R(0),[c,u]=R(!1),_=D(null);C(()=>u(!1),[r,e]);let p=e||"",v=!!p,l="";if(v){let d=p.includes("?")?"&":"?";l=`${p}${d}autoconnect=1&resize=scale`,t&&(l+=`&password=${encodeURIComponent(t)}`),o&&(l+="&view_only=1"),l+=`&_=${r}`}return s("div",{class:"panel pnl stream-panel",children:[s("div",{class:"pnl-head",children:[s("span",{class:"label",children:"VNC STREAM // UPLINK-1"}),s("span",{class:`stream-badge ${c?"ok":""}`,children:v?c?"STREAM LIVE":"ACQUIRING SIGNAL\u2026":"NO UPLINK CONFIGURED"})]}),s("div",{class:"screen stream-screen",children:[s("div",{class:"stream-toolbar",children:[s("span",{class:`led ${v?c?"ok":"warn":""}`}),s("span",{class:"label dim",children:"REMOTE OPERATOR VIEW \xB7 CHROMIUM SESSION"}),s("span",{class:"grow"}),s("button",{type:"button",class:`key-btn ${o?"engaged":""}`,onClick:()=>{a(!o),i(r+1)},children:o?"VIEW ONLY":"CONTROL"}),s("button",{type:"button",class:"key-btn",onClick:()=>i(r+1),children:"RECONNECT"}),s("button",{type:"button",class:"key-btn",onClick:()=>v&&window.open(p,"_blank"),children:"OPEN FULL"})]}),s("div",{class:"stream-frame-wrap",ref:_,children:[v&&s("iframe",{src:l,title:"VNC UPLINK",onLoad:()=>u(!0),allow:"clipboard-read; clipboard-write; pointer-lock"},r),(!v||!c)&&s("div",{class:"stream-off",children:[s("div",{class:"big",children:v?"ACQUIRING UPLINK\u2026":"NO UPLINK"}),s("div",{class:"sub",children:v?n==="TOKEN ACQUIRED"?"SESSION COMPLETE // TOKEN ACQUIRED":"REMOTE BROWSER FEED \xB7 AWAITING OPERATOR ACTION":"VNC STREAM AVAILABLE IN DEPLOY MODE (deployer.py)"})]})]})]})]})}function Oe({data:e,activeModule:t}){let n=e?[{id:"mem",label:"MEM CORE",pct:e.mem.pct,text:`${T(e.mem.used)} / ${T(e.mem.total)}`},{id:"swap",label:"SWAP BANK",pct:e.mem.swap_pct,text:`${T(e.mem.swap_used)} / ${T(e.mem.swap_total)}`},{id:"disk",label:"DISK ARRAY /",pct:e.disk.pct,text:`${T(e.disk.used)} / ${T(e.disk.total)}`},{id:"load",label:"BUS LOAD",pct:Math.min(100,e.load[1]/Math.max(1,e.cpus)*100),text:`${e.load[1].toFixed(2)} / ${e.load[5].toFixed(2)} / ${e.load[15].toFixed(2)}`}]:[{id:"mem",label:"MEM CORE",pct:0,text:"\u2014"},{id:"swap",label:"SWAP BANK",pct:0,text:"\u2014"},{id:"disk",label:"DISK ARRAY /",pct:0,text:"\u2014"},{id:"load",label:"BUS LOAD",pct:0,text:"\u2014"}];return s("div",{class:"panel pnl",children:[s("div",{class:"pnl-head",children:[s("span",{class:"label",children:"TELEMETRY"}),s("span",{class:"label dim",children:"LIVE SUBSYSTEM GAUGES // 5S CYCLE"})]}),s("div",{class:"screen tele-screen",children:n.map(o=>s("div",{class:`tele-row ${t===o.id?"active":""}`,children:[s("span",{class:H(o.pct)}),s("span",{class:"t-label",children:o.label}),s("span",{class:"t-track",children:s("span",{class:"gauge-track",children:s("span",{class:te(o.pct),style:{width:`${Math.max(.6,o.pct)}%`}})})}),s("span",{class:"t-pct",children:[o.pct.toFixed(1),"%"]}),s("span",{class:"t-text",children:o.text})]}))})]})}function bt(e,t,n){if(!t)return["> WAITING FOR TELEMETRY\u2026"];let o=t.mem;switch(e){case"swap":return["> MODULE: SWAP BANK",`> STATUS: ${ne(o.swap_pct)}`,`> TOTAL: ${T(o.swap_total)}`,`> USED:  ${T(o.swap_used)} (${o.swap_pct.toFixed(1)}%)`,`> FREE:  ${T(o.swap_total-o.swap_used)}`,o.swap_total===0?"> NOTE: NO SWAP MOUNTED":"> NOTE: PAGED MEMORY RESERVE"];case"disk":return["> MODULE: DISK ARRAY /",`> STATUS: ${ne(t.disk.pct)}`,`> TOTAL: ${T(t.disk.total)}`,`> USED:  ${T(t.disk.used)} (${t.disk.pct.toFixed(1)}%)`,`> FREE:  ${T(t.disk.free)}`,"> NOTE: PRIMARY STORAGE PLATTER"];case"load":return["> MODULE: BUS LOAD",`> LOAD 1M:  ${t.load[1].toFixed(2)}`,`> LOAD 5M:  ${t.load[5].toFixed(2)}`,`> LOAD 15M: ${t.load[15].toFixed(2)}`,`> CORES:    ${t.cpus}`,`> UPTIME:   ${st(t.uptime)}`];case"procs":return n?["> MODULE: TASK QUEUE",`> TASK PID: ${n.pid}`,`> MEM:      ${n.mb.toFixed(1)} MB`,`> CMD:      ${n.cmd}`,"> NOTE: TOP MEMORY CONSUMER"]:["> MODULE: TASK QUEUE","> TASK: NONE SELECTED","> NOTE: SELECT A QUEUE ENTRY"];case"mem":default:return["> MODULE: MEM CORE",`> STATUS: ${ne(o.pct)}`,`> TOTAL: ${T(o.total)}`,`> USED:  ${T(o.used)} (${o.pct.toFixed(1)}%)`,`> AVAIL: ${T(o.avail)}`,`> SWAP:  ${T(o.swap_used)} / ${T(o.swap_total)}`]}}function yt(e,t){if(!t)return 0;switch(e){case"swap":return t.mem.swap_pct;case"disk":return t.disk.pct;case"load":return Math.min(100,t.load[1]/Math.max(1,t.cpus)*100);case"procs":return 0;default:return t.mem.pct}}function Se({module:e,data:t,proc:n,linkError:o}){let a=bt(e,t,n),r=yt(e,t),i=`${e}-${t?"d":"n"}`;return s("div",{class:"panel pnl",children:[s("div",{class:"pnl-head",children:[s("span",{class:"label",children:"DETAIL READOUT"}),s("span",{class:"label dim",children:["MODULE ",e.toUpperCase()," // ",o?"LINK DOWN":"AUTO"]})]}),s("div",{class:"screen detail-screen",children:[s("div",{class:"detail-lines",children:[a.map((c,u)=>s("div",{class:"screen-text detail-line",style:{animationDelay:`${u*110}ms`},children:c})),s("div",{class:"detail-cursor-row",children:[s("span",{class:"screen-text",children:">"}),s("span",{class:"screen-text detail-cursor",children:"\u2588"})]})]},i),s("div",{class:"detail-side",children:[s("div",{class:"s-row",children:[s("span",{class:H(r)}),s("span",{class:"s-label",children:r>85?"CRITICAL THRESHOLD":r>70?"ELEVATED LOAD":"WITHIN OPERATING ENVELOPE"})]}),s("div",{class:"s-row",children:[s("span",{class:"led amberled"}),s("span",{class:"s-label amber",children:"PHOSPHOR LINK OK"})]}),s("div",{class:"s-row",children:s("span",{class:"s-label",children:"REV 7 // CAL 1979"})}),s("div",{class:"s-stamp",children:"STATION TERMINAL 04 \xB7 DIEGETIC BUILD"})]})]})]})}function Te({onRefresh:e,onKeypad:t,keypadOn:n,onZoomIn:o,onZoomOut:a,zoom:r,onLock:i,onOpenUplink:c}){return s("footer",{class:"panel",id:"actions",children:[s("div",{class:"agroup",children:[s("button",{type:"button",class:"key-btn",onClick:e,children:"REFRESH"}),s("button",{type:"button",class:"key-btn",onClick:()=>{let f=document.querySelector("#auth-screen input:not([disabled]),input:focus");f?document.activeElement===f?f.blur():f.focus():alert("NO INPUT FOCUSED")},children:"SYS KBD"})]}),s("div",{class:"agroup",children:[s("button",{type:"button",class:"key-btn",onClick:a,children:"ZOOM \u2212"}),s("div",{class:"screen-text zoom-screen",children:[Math.round(r*100),"%"]}),s("button",{type:"button",class:"key-btn",onClick:o,children:"ZOOM +"})]}),s("div",{class:"agroup",children:[s("button",{type:"button",class:"key-btn",onClick:c,children:"UPLINK"}),s("button",{type:"button",class:"key-btn danger",onClick:i,style:"min-width:170px",children:"LOCK TERMINAL"})]})]})}var At=[["1","2","3","4","5","6","7","8","9","0"],["q","w","e","r","t","y","u","i","o","p"],["a","s","d","f","g","h","j","k","l","@"],["z","x","c","v","b","n","m","-","_","."]];function ke({open:e,onKey:t,onClose:n}){let[o,a]=R(!1),r=i=>{t(i),o&&a(!1)};return s("div",{id:"keypad",class:e?"open":"","aria-hidden":!e,children:s("div",{class:"kb-plate",children:[s("div",{class:"kb-grip",children:[s("span",{class:"bar"}),s("span",{class:"label dim",children:"STATION KEYPAD // INPUT CHANNEL"}),s("button",{type:"button",class:"key-btn",onClick:n,children:"HIDE"})]}),s("div",{class:"kb-keys",children:[At.map(i=>s("div",{class:"kb-row",children:i.map(c=>s("button",{type:"button",class:"key-btn kb-key",onMouseDown:u=>u.preventDefault(),onClick:()=>r(o?c.toUpperCase():c),children:o?c.toUpperCase():c}))})),s("div",{class:"kb-row",children:[s("button",{type:"button",class:`key-btn kb-key wide ${o?"engaged":""}`,onMouseDown:i=>i.preventDefault(),onClick:()=>a(!o),children:"SHIFT"}),s("button",{type:"button",class:"key-btn kb-key space",onMouseDown:i=>i.preventDefault(),onClick:()=>r(" "),children:"SPACE"}),s("button",{type:"button",class:"key-btn kb-key wide",onMouseDown:i=>i.preventDefault(),onClick:()=>r("\b"),children:"DEL"}),s("button",{type:"button",class:"key-btn kb-key wide",onMouseDown:i=>i.preventDefault(),onClick:()=>r(`
`),children:"ENTER"})]})]})]})})}var se=window.__VNC_CFG__||{url:"",password:""},Ot=.8,St=2,ot={phase:"auth",operator:null,token:null,authError:null,authBusy:!1,module:"mem",selectedProc:0,zoom:1,keypad:!1};function Tt(e,t){var n,o;switch(t.type){case"AUTH_BUSY":return{...e,authBusy:!0,authError:null};case"AUTH_FAIL":return{...e,authBusy:!1,authError:t.error};case"AUTH_OK":return{...e,authBusy:!1,authError:null,phase:"boot",operator:t.operator,token:t.token};case"BOOT_DONE":return e.phase==="boot"?{...e,phase:"online"}:e;case"LOCK":return{...ot,zoom:e.zoom,keypad:e.keypad};case"MODULE":return{...e,module:t.module,selectedProc:(n=t.proc)!=null?n:e.selectedProc};case"PROC":return{...e,module:"procs",selectedProc:t.index};case"ZOOM":return{...e,zoom:Math.min(St,Math.max(Ot,Math.round(t.zoom*100)/100))};case"KEYPAD":return{...e,keypad:(o=t.open)!=null?o:!e.keypad};default:return e}}function ge(){var d,b,k;let[e,t]=me(Tt,ot),n=D(null),o=D(null),a=P(()=>{e.token&&fetch("/api/logout",{method:"POST",headers:{Authorization:`Bearer ${e.token}`}}).catch(()=>{}),t({type:"LOCK"})},[e.token]),{data:r,error:i,lastUpdate:c,refresh:u}=nt(e.phase==="auth"?null:e.token,a),_=P(async(m,f)=>{t({type:"AUTH_BUSY"});try{let y=await(await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({login:m,password:f})})).json();y.ok?t({type:"AUTH_OK",operator:y.operator,token:y.token}):t({type:"AUTH_FAIL",error:y.error||"ACCESS DENIED"})}catch{t({type:"AUTH_FAIL",error:"LINK DOWN // SERVER UNREACHABLE"})}},[]),p=P(m=>{t({type:"ZOOM",zoom:Math.round(e.zoom*100)/100+m})},[e.zoom]);C(()=>{let m=f=>{f.ctrlKey&&(f.preventDefault(),t({type:"ZOOM",zoom:e.zoom+(f.deltaY<0?.1:-.1)}))};return window.addEventListener("wheel",m,{passive:!1}),()=>window.removeEventListener("wheel",m)},[e.zoom]),C(()=>{let m=n.current;if(!m)return;let f=0,h=1,y=S=>Math.hypot(S[0].clientX-S[1].clientX,S[0].clientY-S[1].clientY),w=S=>{S.touches.length===2&&(f=y(S.touches),h=e.zoom)},N=S=>{S.touches.length===2&&f&&(S.preventDefault(),t({type:"ZOOM",zoom:h*(y(S.touches)/f)}))},g=()=>{f=0};return m.addEventListener("touchstart",w,{passive:!0}),m.addEventListener("touchmove",N,{passive:!1}),m.addEventListener("touchend",g),()=>{m.removeEventListener("touchstart",w),m.removeEventListener("touchmove",N),m.removeEventListener("touchend",g)}},[e.zoom]),C(()=>{let m=f=>{f.target&&(f.target.tagName==="INPUT"||f.target.tagName==="TEXTAREA")&&(o.current=f.target)};return document.addEventListener("focusin",m),()=>document.removeEventListener("focusin",m)},[]);let v=P(m=>{var h,y,w,N;let f=o.current;if(!(!f||!f.isConnected)){if(f.focus(),m==="\b"){let g=(h=f.selectionStart)!=null?h:f.value.length,S=(y=f.selectionEnd)!=null?y:g;g!==S?f.setRangeText("",g,S,"end"):g>0&&f.setRangeText("",g-1,g,"end")}else if(m===`
`)f.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:!0})),f.form&&f.form.dispatchEvent(new Event("submit",{cancelable:!0,bubbles:!0}));else{let g=(w=f.selectionStart)!=null?w:f.value.length,S=(N=f.selectionEnd)!=null?N:g;f.setRangeText(m,g,S,"end")}f.dispatchEvent(new Event("input",{bubbles:!0}))}},[]);C(()=>{let m=f=>{f.key==="Escape"&&t({type:"KEYPAD",open:!1})};return window.addEventListener("keydown",m),()=>window.removeEventListener("keydown",m)},[]);let l=(r==null?void 0:r.event)||"";return s("div",{id:"viewport",ref:n,style:{"--zoom":e.zoom},children:[s("div",{id:"shell",style:{transform:`scale(${e.zoom})`},children:e.phase==="auth"?s(ve,{onLogin:_,error:e.authError,busy:e.authBusy,onKeypad:()=>t({type:"KEYPAD"})}):s(U,{children:[s(Ee,{operator:e.operator,zoom:e.zoom,lastUpdate:c,linkError:i,event:l}),s("main",{id:"grid",children:[s("section",{class:"col",children:[s(be,{active:e.module,data:r,onSelect:m=>t({type:"MODULE",module:m})}),s(ye,{procs:(d=r==null?void 0:r.procs)!=null?d:[],selected:e.selectedProc,onSelect:m=>t({type:"PROC",index:m})})]}),s("section",{class:"col",children:[s(Ae,{vncUrl:se.url,vncPassword:se.password,event:l}),s(Oe,{data:r,activeModule:e.module})]})]}),s(Se,{module:e.module,data:r,proc:(k=(b=r==null?void 0:r.procs)==null?void 0:b[e.selectedProc])!=null?k:null,linkError:i}),s(Te,{onRefresh:u,onKeypad:()=>t({type:"KEYPAD"}),keypadOn:e.keypad,onZoomIn:()=>p(.15),onZoomOut:()=>p(-.15),zoom:e.zoom,onLock:a,onOpenUplink:()=>se.url&&window.open(se.url,"_blank")}),e.phase==="boot"&&s(he,{operator:e.operator,onDone:()=>t({type:"BOOT_DONE"})})]})}),s(ke,{open:e.keypad,onKey:v,onClose:()=>t({type:"KEYPAD",open:!1})})]})}Be(s(ge,{}),document.getElementById("root"));})();
</script>
</body>
</html>
"""


def make_handler(vnc_url: str = "", vnc_password: str = ""):
    """Build the request handler.

    vnc_url/vnc_password are optional — when set, the VNC STREAM panel embeds
    the live noVNC feed (used by patched deployer.py). Env VNC_URL/VNC_PASS
    work too. Without them the station runs standalone (NO UPLINK plate).
    """
    vnc_url = vnc_url or os.environ.get("VNC_URL", "")
    vnc_password = vnc_password or os.environ.get("VNC_PASS", "")
    vnc_cfg = json.dumps({"url": vnc_url, "password": vnc_password})
    _announce()
    if vnc_url:
        print("    VNC STREAM   " + vnc_url.split("?")[0], file=sys.stderr, flush=True)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            buf = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(buf)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.end_headers()
            self.wfile.write(buf)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj), "application/json")

        def _read_body(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                n = 0
            raw = self.rfile.read(n) if n else b""
            try:
                return json.loads(raw or b"{}")
            except Exception:
                return {}

        def _token(self):
            h = self.headers.get("Authorization", "")
            tok = h[7:] if h.startswith("Bearer ") else self.headers.get("X-Session", "")
            if tok:
                with _sessions_lock:
                    if tok in _sessions:
                        return tok
            return None

        def do_POST(self):
            ip = self.client_address[0] if self.client_address else "?"
            if self.path == "/api/login":
                if _throttled(ip):
                    return self._json(429, {"ok": False, "error": "COOLDOWN — RETRY LATER"})
                body = self._read_body()
                login = str(body.get("login", "")).strip()
                password = str(body.get("password", ""))
                if not login or not password:
                    return self._json(400, {"ok": False, "error": "CREDENTIALS REQUIRED"})
                if _verify(login, password):
                    tok = secrets.token_hex(24)
                    with _sessions_lock:
                        _sessions[tok] = time.time()
                    return self._json(200, {"ok": True, "token": tok, "operator": OPERATOR})
                _register_fail(ip)
                return self._json(401, {"ok": False, "error": "ACCESS DENIED"})

            if self.path == "/api/logout":
                tok = self._token()
                if tok:
                    with _sessions_lock:
                        _sessions.pop(tok, None)
                return self._json(200, {"ok": True})

            return self._json(404, {"ok": False, "error": "NOT FOUND"})

        def do_GET(self):
            if self.path == "/verify":
                self._send(200, b'{"ok": true, "station": "VEROKU-1"}')
                return
            if self.path.startswith("/api"):
                if not self._token():
                    return self._json(401, {"ok": False, "error": "NO SESSION"})
                return self._json(200, _snapshot())

            page = DASH_PAGE.replace("__VNC_CFG_JSON__", vnc_cfg)
            self._send(200, page.encode(), "text/html; charset=utf-8")

        def log_message(self, format, *args):
            return

    Handler.emit = staticmethod(emit_event)
    return Handler
