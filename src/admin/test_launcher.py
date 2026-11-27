"""Loopback-only testing launcher; never exposes the administrator publicly."""
import os
import logging
import secrets
import webbrowser
from threading import Timer

from src.admin.config import load_project_config
from src.admin.server import make_server
from src.admin.store import ROOT


def main():
    log_dir = ROOT / "var"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[
        logging.FileHandler(log_dir / "admin-test.log", encoding="utf-8"),
        logging.StreamHandler(),
    ])
    config = load_project_config(ROOT, override=True)
    os.environ["ADMIN_LOCAL_CONFIG_RELOAD"] = "1"
    print(f"Config file: {config['file'] or 'NOT FOUND'}", flush=True)
    print(f"Config directory: {config['directory']}", flush=True)
    print("Model settings: " + ("present" if config["ready"] else "MISSING: " + ", ".join(config["missing"])), flush=True)
    password = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    # A separate database keeps test edits away from production or existing local data.
    with make_server(("127.0.0.1", 0), ROOT / "var" / "admin-test.sqlite3", password) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print("\nLOCAL ADMIN TEST / only this computer", flush=True)
        print(f"URL: {url}\nUsername: tester\nPassword: {password}", flush=True)
        print("Keep this window open. Ctrl+C stops the server.", flush=True)
        print("No LLM configuration? Article preview and company editing still work.", flush=True)
        print("LLM extraction requires OPENROUTER_API_KEY and OPENROUTER_MODEL in .env.", flush=True)
        print("Use the sign-in form INSIDE the page, not a browser authentication popup.", flush=True)
        print(f"Error log: {log_dir / 'admin-test.log'}", flush=True)
        (log_dir / "open-admin.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>Open administrator</title>'
            f'<p>Keep the CMD window open.</p><a href="{url}">Open administrator / 打开管理员网页</a>',
            encoding="utf-8")

        def open_browser():
            try:
                if not webbrowser.open(url):
                    print("Browser did not open. Copy the URL above into your browser.", flush=True)
            except Exception:
                logging.exception("Could not open browser; the server is still running")
                print("Copy the URL above into your browser.", flush=True)

        Timer(1, open_browser).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Administrator startup failed")
        print("Startup failed. See the error above and var/admin-test.log. The server did not start.", flush=True)
        raise SystemExit(1)
