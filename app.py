"""
TDS Onion Auto-Solver — Streamlit App (Fixed)
Fixed:
  1. st.text_input needs non-empty label (was empty string "")
  2. st.session_state not safe from background threads → use plain _shared dict + lock
  3. Tor auto-starts at app launch via background thread (no button click needed)
  4. Auto-refresh every 3s while Tor is starting or scraper is running
"""

import streamlit as st
import json
import re
import time
import threading
import subprocess
import shutil
import os

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="TDS Onion Solver", page_icon="🧅", layout="wide")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@800&display=swap');
html,body,[class*="css"],.stApp{background:#0a0c10!important;color:#e2eaf5;}
[class*="css"]{font-family:'JetBrains Mono',monospace!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:1.5rem 2rem 3rem;max-width:1280px;}

.hero{text-align:center;padding:2rem 1rem 1.5rem;border-bottom:1px solid #1e2733;margin-bottom:1.8rem;}
.hero h1{font-family:'Syne',sans-serif!important;font-size:2.1rem;font-weight:800;color:#00e5a0;letter-spacing:.05em;margin:0 0 .3rem;}
.hero .sub{color:#7a90aa;font-size:.7rem;letter-spacing:.1em;}

.card{background:#0f1318;border:1px solid #1e2733;border-radius:10px;padding:1rem 1.2rem;margin-bottom:.85rem;}
.card-g{border-left:3px solid #00e5a0;}
.card-r{border-left:3px solid #ff4f6d;background:#120a0c;}
.card-o{border-left:3px solid #f5a623;}

.rtable{width:100%;border-collapse:collapse;}
.rtable tr{border-bottom:1px solid #1a2230;}
.rtable tr:last-child{border-bottom:none;}
.rtable td{padding:.42rem .25rem;font-size:.75rem;vertical-align:middle;}
.td-n{color:#4a5f75;width:28px;}
.td-name{color:#94a8bf;}
.td-ans{text-align:right;font-weight:700;color:#00e5a0;}
.td-pend{text-align:right;color:#2a3f52;}
.td-err{text-align:right;color:#ff4f6d;font-size:.66rem;}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.57rem;border:1px solid;margin-left:5px;}
.b-ec{border-color:#3d9fff;color:#3d9fff;}
.b-nw{border-color:#f5a623;color:#f5a623;}
.b-sm{border-color:#b97fff;color:#b97fff;}
.b-fr{border-color:#ff4f6d;color:#ff4f6d;}

.logbox{background:#060809;border:1px solid #1e2733;border-radius:6px;padding:.75rem 1rem;
        font-size:.65rem;line-height:1.75;color:#4a5f75;font-family:'JetBrains Mono',monospace;
        max-height:240px;overflow-y:auto;white-space:pre-wrap;}
.lg{color:#7a90aa;}.lk{color:#00e5a0;}.le{color:#ff4f6d;}.lw{color:#f5a623;}

.jsonbox{background:#060809;border:1px solid #1e2733;border-radius:8px;padding:1rem;
         font-size:.7rem;line-height:1.9;color:#c9d8e8;font-family:'JetBrains Mono',monospace;
         white-space:pre-wrap;word-break:break-all;}
.jk{color:#7fb3d8;}.jf{color:#00e5a0;font-weight:600;}.je{color:#ff4f6d;}

.stProgress>div>div>div{background:#00e5a0!important;border-radius:4px;}
.stProgress>div>div{background:#1a2230!important;border-radius:4px;}

/* Fix label colour (visible on dark bg) */
.stTextInput label{color:#7a90aa!important;font-size:.7rem!important;letter-spacing:.05em;}
.stTextInput input{background:#0f1318!important;border:1px solid #2a3545!important;
    border-radius:7px!important;color:#e2eaf5!important;
    font-family:'JetBrains Mono',monospace!important;}
.stTextInput input:focus{border-color:#00e5a0!important;box-shadow:none!important;}

.stButton>button{background:#00e5a0!important;color:#0a0c10!important;
    font-family:'JetBrains Mono',monospace!important;font-weight:700!important;
    border:none!important;border-radius:7px!important;width:100%;
    padding:.65rem 0!important;font-size:.8rem!important;}
.stButton>button:hover{background:#00c98d!important;}
.stButton>button:disabled{background:#1a2230!important;color:#4a5f75!important;}

.stTextArea label{color:#7a90aa!important;font-size:.68rem!important;}
.stTextArea textarea{background:#060809!important;border:1px solid #1e2733!important;
    border-radius:7px!important;color:#c9d8e8!important;
    font-family:'JetBrains Mono',monospace!important;font-size:.7rem!important;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>🧅 TDS ONION AUTO-SOLVER</h1>
  <div class="sub">IITM · @ds.study.iitm.ac.in · 12 TASKS · FULLY AUTOMATED</div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Thread-safe shared state
# Background threads CANNOT use st.session_state — it raises AttributeError.
# We use a plain dict + threading.Lock instead.
# ══════════════════════════════════════════════════════════════════════════════
_lock = threading.Lock()
_shared = {
    "logs":         [],
    "answers":      {},
    "running":      False,
    "done":         False,
    "tor_ok":       False,
    "tor_starting": False,
}

def _slog(msg, level="info"):
    """Thread-safe log append."""
    cls = {"ok": "lk", "err": "le", "warn": "lw"}.get(level, "lg")
    with _lock:
        _shared["logs"].append(f'<span class="{cls}">{msg}</span>')

def _sset(key, val):
    with _lock:
        _shared[key] = val

def _sget(key):
    with _lock:
        return _shared[key]

def _sanswer(n, val):
    with _lock:
        _shared["answers"][f"task{n}"] = val


# ══════════════════════════════════════════════════════════════════════════════
# Tor auto-launcher
# ══════════════════════════════════════════════════════════════════════════════
def _tor_port_open():
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 9050), timeout=2)
        s.close()
        return True
    except Exception:
        return False


def _launch_tor():
    """Called from a daemon thread. Never touches st.session_state."""
    _sset("tor_starting", True)
    _slog("Searching for tor binary...")

    tor_bin = shutil.which("tor") or "/usr/bin/tor"
    if not os.path.isfile(tor_bin):
        _slog("tor binary not found. Check packages.txt contains 'tor'.", "err")
        _sset("tor_starting", False)
        return

    _slog(f"Found tor at {tor_bin}")
    _slog("Bootstrapping Tor network (30–90s first time)...", "warn")

    # Method 1: stem
    try:
        import stem.process

        stem.process.launch_tor_with_config(
            tor_cmd=tor_bin,
            config={
                "SocksPort": "9050",
                "ControlPort": "9051",
                "DataDirectory": "/tmp/tor-data",
                "Log": "notice stdout",
            },
            init_msg_handler=lambda line: _slog(f"  {line}"),
            timeout=120,
            take_ownership=True,
        )
    except Exception as e:
        _slog(f"stem launch error: {e} — trying subprocess...", "warn")
        try:
            os.makedirs("/tmp/tor-data", exist_ok=True)
            subprocess.Popen(
                [tor_bin, "--SocksPort", "9050", "--DataDirectory", "/tmp/tor-data"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e2:
            _slog(f"subprocess launch failed: {e2}", "err")
            _sset("tor_starting", False)
            return

    # Wait for port to open
    for i in range(45):
        if _tor_port_open():
            _slog("Tor is connected and ready!", "ok")
            _sset("tor_ok", True)
            _sset("tor_starting", False)
            return
        time.sleep(2)
        if i % 5 == 4:
            _slog(f"  Still waiting... {(i+1)*2}s elapsed")

    _slog("Tor did not become ready in 90s. Try clicking Retry.", "err")
    _sset("tor_starting", False)


# Auto-start Tor once at import time (only if not already running/starting)
# Using a module-level flag so multiple Streamlit reruns don't spawn multiple threads.
if not hasattr(st, "_tor_thread_started"):
    st._tor_thread_started = True          # module-level, survives reruns
    if _tor_port_open():
        _sset("tor_ok", True)
        _slog("Tor already running on :9050", "ok")
    else:
        _t = threading.Thread(target=_launch_tor, daemon=True, name="tor-auto")
        _t.start()


# ══════════════════════════════════════════════════════════════════════════════
# Scraper runner
# ══════════════════════════════════════════════════════════════════════════════
def _run_scraper():
    try:
        from scraper import TDSScraper
        scraper = TDSScraper(log_fn=_slog, delay=0.5)
        results = scraper.run_all(progress_cb=_sanswer)
        with _lock:
            for k, v in results.items():
                _shared["answers"][k] = v
        _sset("done", True)
    except Exception as e:
        _slog(f"Fatal scraper error: {e}", "err")
    finally:
        _sset("running", False)


# ══════════════════════════════════════════════════════════════════════════════
# Snapshot shared state for this render cycle
# ══════════════════════════════════════════════════════════════════════════════
with _lock:
    snap = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
            for k, v in _shared.items()}


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
TASKS = [
    (1,  "Apparel total inventory value",    "ec"),
    (2,  "Outdoors highest-review SKU",       "ec"),
    (3,  "Outdoors OOS avg rating",           "ec"),
    (4,  "Tech total internal views",         "nw"),
    (5,  "Michael Clayton article count",     "nw"),
    (6,  "Politics avg internal views",       "nw"),
    (7,  "Verified users total followers",    "sm"),
    (8,  "#coffee posts total likes",         "sm"),
    (9,  "Users in Wrightborough",            "sm"),
    (10, "June 2025 joiners rep sum",         "fr"),
    (11, "Vendor badge reputation total",     "fr"),
    (12, "General board 0-reply threads",     "fr"),
]
BADGE = {
    "ec": ("E-Commerce", "b-ec"),
    "nw": ("News",        "b-nw"),
    "sm": ("Social",      "b-sm"),
    "fr": ("Forum",       "b-fr"),
}

c_left, c_mid, c_right = st.columns([1.05, 1.7, 1.25], gap="large")

# ─── LEFT ─────────────────────────────────────────────────────────────────────
with c_left:
    st.markdown('<div class="card card-g">', unsafe_allow_html=True)
    # FIX: label must be non-empty string
    email = st.text_input(
        "Student Email",
        placeholder="yourname@ds.study.iitm.ac.in",
        key="email_input",
    )
    valid_email = bool(email and email.strip().endswith("@ds.study.iitm.ac.in"))
    if email and not valid_email:
        st.markdown(
            '<p style="color:#ff4f6d;font-size:.7rem;margin-top:4px;">⚠ Must end with @ds.study.iitm.ac.in</p>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # Tor status
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<p style="font-size:.6rem;color:#4a5f75;letter-spacing:.1em;margin-bottom:.5rem;">TOR STATUS</p>', unsafe_allow_html=True)

    if snap["tor_ok"]:
        st.markdown('<p style="color:#00e5a0;font-size:.78rem;">● Connected on :9050 ✓</p>', unsafe_allow_html=True)
    elif snap["tor_starting"]:
        st.markdown('<p style="color:#f5a623;font-size:.78rem;">◌ Bootstrapping Tor network...</p>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:.65rem;color:#4a5f75;">First-time startup takes 30–90s.<br>Page refreshes automatically.</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#ff4f6d;font-size:.78rem;">● Not connected</p>', unsafe_allow_html=True)
        if st.button("⚡ Retry Tor Launch", key="retry_tor"):
            if not _sget("tor_starting"):
                _t = threading.Thread(target=_launch_tor, daemon=True, name="tor-retry")
                _t.start()
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Solve button
    can_run = valid_email and snap["tor_ok"] and not snap["running"]
    if st.button(
        "🚀 Solve All 12 Tasks" if not snap["running"] else "⏳ Solving...",
        disabled=not can_run,
        key="solve_btn",
    ):
        with _lock:
            _shared.update({"answers": {}, "logs": [], "running": True, "done": False})
        _t = threading.Thread(target=_run_scraper, daemon=True, name="scraper")
        _t.start()
        time.sleep(0.3)
        st.rerun()

    # Progress bar
    n_ok = sum(1 for v in snap["answers"].values() if not str(v).startswith("ERROR"))
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f'<p style="font-size:.67rem;color:#7a90aa;text-align:center;margin-bottom:.3rem;">{n_ok} / 12 tasks solved</p>',
        unsafe_allow_html=True,
    )
    st.progress(n_ok / 12)

    if snap["done"]:
        st.markdown(
            '<div class="card card-g" style="text-align:center;margin-top:.8rem;">'
            '<p style="color:#00e5a0;font-size:.8rem;margin:0;">✓ Complete!<br>'
            '<span style="font-size:.65rem;color:#7a90aa;">Copy JSON → paste into exam.</span></p>'
            "</div>", unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="card" style="margin-top:1rem;">'
        '<p style="font-size:.6rem;color:#4a5f75;letter-spacing:.08em;margin-bottom:.4rem;">HOW IT WORKS</p>'
        '<p style="font-size:.67rem;color:#7a90aa;line-height:1.75;">'
        "① Tor auto-starts when app loads<br>"
        "② Enter IITM email<br>"
        "③ Click Solve All 12 Tasks<br>"
        "④ Wait ~5–15 min<br>"
        "⑤ Copy JSON → submit"
        "</p></div>",
        unsafe_allow_html=True,
    )

# ─── CENTER ───────────────────────────────────────────────────────────────────
with c_mid:
    st.markdown('<p style="font-size:.6rem;color:#4a5f75;letter-spacing:.1em;margin-bottom:.7rem;">TASK RESULTS</p>', unsafe_allow_html=True)

    rows = ""
    for n, name, cat in TASKS:
        lbl, bcls = BADGE[cat]
        ans = snap["answers"].get(f"task{n}")
        if ans is None:
            a_html = '<td class="td-pend">—</td>'
        elif str(ans).startswith("ERROR"):
            s = str(ans)[:52] + ("…" if len(str(ans)) > 52 else "")
            a_html = f'<td class="td-err">{s}</td>'
        else:
            a_html = f'<td class="td-ans">{ans}</td>'
        rows += (
            f'<tr><td class="td-n">{str(n).zfill(2)}</td>'
            f'<td class="td-name">{name}<span class="badge {bcls}">{lbl}</span></td>'
            f'{a_html}</tr>'
        )

    st.markdown(f'<div class="card"><table class="rtable">{rows}</table></div>', unsafe_allow_html=True)

    if snap["logs"]:
        st.markdown('<p style="font-size:.6rem;color:#4a5f75;letter-spacing:.1em;margin:.8rem 0 .4rem;">LIVE LOG</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="logbox">{"<br>".join(snap["logs"][-80:])}</div>', unsafe_allow_html=True)

# ─── RIGHT ────────────────────────────────────────────────────────────────────
with c_right:
    st.markdown('<p style="font-size:.6rem;color:#4a5f75;letter-spacing:.1em;margin-bottom:.7rem;">SUBMISSION JSON</p>', unsafe_allow_html=True)

    payload = {f"task{n}": snap["answers"].get(f"task{n}", "") for n in range(1, 13)}
    json_str = json.dumps(payload, indent=2)

    def _cjson(raw):
        out = []
        for line in raw.split("\n"):
            m = re.match(r'(\s*"task\d+":\s*)(".*?")(,?)$', line)
            if m:
                k = m.group(1).replace('"', '<span class="jk">"', 1).replace('":', '"</span>:', 1)
                v, c = m.group(2), m.group(3)
                vc = "je" if "ERROR" in v else ("jf" if v not in ('""', '""') and len(v) > 2 else "")
                vh = f'<span class="{vc}">{v}</span>' if vc else v
                out.append(f"{k} {vh}{c}")
            else:
                out.append(line)
        return "<br>".join(out)

    st.markdown(f'<div class="jsonbox">{_cjson(json_str)}</div>', unsafe_allow_html=True)
    st.text_area("Select all → Copy ↓", value=json_str, height=290, key="json_ta")

    if snap["done"]:
        st.markdown(
            '<div class="card card-g" style="margin-top:.5rem;">'
            '<p style="color:#00e5a0;font-size:.75rem;margin:0;">✓ Paste into exam → click Save.</p>'
            "</div>", unsafe_allow_html=True,
        )

# ── Auto-refresh while active ──────────────────────────────────────────────────
if snap["tor_starting"] or snap["running"]:
    time.sleep(3)
    st.rerun()
