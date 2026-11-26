"""Launcher started by Start.bat.

Starts the local API on 127.0.0.1:8765 with a fresh per-launch session token and opens
the website with the token in the URL fragment (never sent to the web server). If the
converter is already running, it reopens the browser with the existing session instead
of starting a duplicate backend.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from backend.settings import APP_NAME, DEV_FRONTEND_URL, HOST, PORT, load_config


def _health() -> dict | None:
    try:
        req = urllib.request.Request(f"http://{HOST}:{PORT}/health", headers={"Host": f"{HOST}:{PORT}"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((HOST, PORT)) == 0


def _open(frontend_url: str, token: str) -> None:
    url = f"{frontend_url.split('#')[0]}#token={token}"
    print(f"Opening {frontend_url}")
    webbrowser.open(url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parquet to CSV Converter launcher")
    parser.add_argument("--dev", action="store_true", help=f"use the Next.js dev server at {DEV_FRONTEND_URL}")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    cfg = load_config()
    if args.dev:
        cfg.frontend_url = DEV_FRONTEND_URL
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    health = _health()
    if health and health.get("app") == APP_NAME:
        try:
            session = json.loads(cfg.session_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("The converter is already running but its session file is missing.")
            print("Close the other converter window, then double-click Start.bat again.")
            return 1
        print("The converter is already running. Reopening the website.")
        if not args.no_browser:
            _open(session.get("frontend_url", cfg.frontend_url), session["token"])
        return 0
    if _port_in_use():
        print(f"ERROR: Port {PORT} on {HOST} is used by another program.")
        print("Close that program (or restart the PC), then double-click Start.bat again.")
        return 1

    token = secrets.token_urlsafe(32)
    session = {"token": token, "pid": os.getpid(), "port": PORT, "frontend_url": cfg.frontend_url, "started_at": time.time()}
    cfg.session_file.write_text(json.dumps(session), encoding="utf-8")

    import uvicorn

    from backend.api import create_app

    app = create_app(cfg, token)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", access_log=False))

    def open_when_ready() -> None:
        for _ in range(100):
            if _health():
                print(f"Converter running at http://{HOST}:{PORT}. Keep this window open while you use it.")
                if not args.no_browser:
                    _open(cfg.frontend_url, token)
                return
            time.sleep(0.2)
        print("ERROR: The converter did not respond to its health check. See the messages above.")

    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run()
    finally:
        try:
            if json.loads(cfg.session_file.read_text(encoding="utf-8")).get("pid") == os.getpid():
                cfg.session_file.unlink()
        except (OSError, ValueError):
            pass
    return 0 if server.started else 1


if __name__ == "__main__":
    sys.exit(main())
