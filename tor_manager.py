"""
tor_manager.py
==============
Automatically installs and launches Tor as a subprocess.
Works on Streamlit Cloud (Linux) and locally.
Uses stem.process.launch_tor_with_config to start a Tor process
without needing a pre-configured torrc.
"""

import subprocess
import socket
import time
import shutil
import os
import sys

_tor_process = None


def _is_tor_running(port=9050, timeout=2):
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def _find_tor():
    """Find tor binary path."""
    # Check common paths
    for path in ["/usr/bin/tor", "/usr/local/bin/tor", "/opt/homebrew/bin/tor"]:
        if os.path.isfile(path):
            return path
    # Use shutil
    found = shutil.which("tor")
    return found


def ensure_tor_running(log_fn=print):
    """
    Ensure Tor is running on 127.0.0.1:9050.
    If not already running, launches it via stem.
    Returns True on success, False on failure.
    """
    global _tor_process

    # Already running?
    if _is_tor_running():
        log_fn("Tor already running on port 9050", "ok")
        return True

    # Find tor binary
    tor_bin = _find_tor()
    if not tor_bin:
        log_fn("Tor binary not found. Is 'tor' in packages.txt?", "err")
        return False

    log_fn(f"Found Tor at: {tor_bin}")
    log_fn("Launching Tor process (this takes ~30s)...")

    try:
        import stem.process

        def _handle_init(line):
            log_fn(f"  Tor: {line}")

        _tor_process = stem.process.launch_tor_with_config(
            tor_cmd=tor_bin,
            config={
                "SocksPort": "9050",
                "ControlPort": "9051",
                "DataDirectory": "/tmp/tor-data",
                "Log": "notice stdout",
            },
            init_msg_handler=_handle_init,
            timeout=120,
            take_ownership=True,
        )

        # Verify it's up
        for attempt in range(20):
            if _is_tor_running():
                log_fn("Tor connected and ready!", "ok")
                return True
            time.sleep(2)

        log_fn("Tor launched but not responding on port 9050", "err")
        return False

    except Exception as e:
        log_fn(f"Failed to launch Tor: {e}", "err")

        # Fallback: try launching directly via subprocess
        log_fn("Trying direct subprocess fallback...")
        try:
            os.makedirs("/tmp/tor-data", exist_ok=True)
            proc = subprocess.Popen(
                [tor_bin, "--SocksPort", "9050", "--DataDirectory", "/tmp/tor-data"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _tor_process = proc
            # Wait up to 60s for bootstrap
            for attempt in range(30):
                if _is_tor_running():
                    log_fn("Tor ready (fallback mode)!", "ok")
                    return True
                time.sleep(2)
                log_fn(f"  Waiting for Tor... ({(attempt+1)*2}s)")

            log_fn("Tor did not start in time", "err")
            return False
        except Exception as e2:
            log_fn(f"Subprocess fallback also failed: {e2}", "err")
            return False


def stop_tor():
    global _tor_process
    if _tor_process:
        try:
            _tor_process.kill()
        except Exception:
            pass
        _tor_process = None
