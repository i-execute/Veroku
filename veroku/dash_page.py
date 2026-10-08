"""Veroku dashboard page + metrics handlers (used by one-shot login dash)."""

import http.server
import json
import os


def _meminfo():
    d = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            d[k] = int(v.strip().split()[0])
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
    procs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/statm") as f:
                rss = int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
            if cmd:
                procs.append((rss, pid, cmd[:100]))
        except (OSError, IndexError, ValueError):
            pass
    procs.sort(reverse=True)
    return [{"pid": p, "cmd": c, "mb": round(r / 1048576, 1)} for r, p, c in procs[:n]]


DASH_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veroku Dash</title><style>
body{font-family:system-ui;background:#111;color:#eee;margin:16px;max-width:720px}
.card{background:#1c1c1c;border-radius:10px;padding:14px;margin-bottom:12px}
.bar{background:#333;border-radius:6px;height:18px;overflow:hidden;margin:6px 0}
.fill{height:100%;transition:width .5s}
.ok{background:#3aa757}.warn{background:#d4a017}.crit{background:#c0392b}
table{width:100%;border-collapse:collapse;font-size:13px}
td{padding:3px 6px;border-bottom:1px solid #2a2a2a}
.meta{color:#888;font-size:12px}
</style></head><body>
<h2>Veroku server</h2>
<div class="card"><b>RAM</b><div class="bar"><div class="fill" id="mbar"></div></div>
<div id="mtxt" class="meta"></div>
<b>Swap</b><div class="bar"><div class="fill" id="sbar"></div></div>
<div id="stxt" class="meta"></div></div>
<div class="card"><b>Disk /</b><div class="bar"><div class="fill" id="dbar"></div></div>
<div id="dtxt" class="meta"></div></div>
<div class="card"><b>Load</b><div id="ltxt"></div></div>
<div class="card"><b>Top RAM</b><table id="pt"></table></div>
<div class="meta">auto-refresh 5s</div>
<script>
function cls(p){return p>85?'crit':p>70?'warn':'ok'}
function fmt(b){return (b/1048576).toFixed(1)+' MB'}
async function up(){
try{const d=await (await fetch('/api')).json();
const m=d.mem,di=d.disk,l=d.load;
mbar.style.width=m.pct+'%';mbar.className='fill '+cls(m.pct);
mtxt.textContent=m.pct+'% — '+fmt(m.used)+' / '+fmt(m.total)+' (free '+fmt(m.avail)+')';
sbar.style.width=m.swap_pct+'%';sbar.className='fill '+cls(m.swap_pct);
stxt.textContent=m.swap_pct+'% — '+fmt(m.swap_used)+' / '+fmt(m.swap_total);
dbar.style.width=di.pct+'%';dbar.className='fill '+cls(di.pct);
dtxt.textContent=di.pct+'% — '+fmt(di.used)+' / '+fmt(di.total)+' (free '+fmt(di.free)+')';
ltxt.textContent=l['1']+' / '+l['5']+' / '+l['15'];
pt.innerHTML=d.procs.map(p=>'<tr><td>'+p.mb+' MB</td><td>'+p.pid+'</td><td>'+p.cmd+'</td></tr>').join('');
}catch(e){}}up();setInterval(up,5000);
</script></body></html>"""


def make_handler():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api"):
                data = {
                    "mem": _meminfo(),
                    "disk": _diskinfo(),
                    "load": _load(),
                    "procs": _top_procs(),
                }
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = DASH_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return Handler
