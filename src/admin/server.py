"""Independent administrator service. Run with python -m src.admin.server."""
import base64
import binascii
import hmac
import json
import logging
import os
import secrets
import time
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlsplit
from uuid import uuid4

from src.admin import store, workflow
from src.admin.export import snapshot
from src.admin.config import load_project_config, configuration_status
from src.news_36kr import FetchError, http_get, parse_feed, read_feed

PAGE = Path(__file__).with_name("index.html")
LOGIN_PAGE = Path(__file__).with_name("login.html")
LOGGER = logging.getLogger(__name__)


class AdminHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        LOGGER.exception("Administrator HTTP request failed")


def handler_for(path, password, *, extract=workflow.extract, fetch=workflow.fetch_article):
    taxonomy = {}
    for row in json.loads((store.DATA / "taxonomy.json").read_text(encoding="utf-8")):
        taxonomy.setdefault(row["field"], set()).add(row["label"])

    jobs = {}
    job_lock = Lock()
    article_cache = {}
    cache_lock = Lock()
    sessions = {}
    session_lock = Lock()
    cookie_name = "admin_session_" + secrets.token_hex(6)

    def read_article(request):
        raw_url = request.get("url") or ""
        text = request.get("text") or ""
        published = request.get("published_at") or None
        if not isinstance(raw_url, str) or not isinstance(text, str) or (
                published is not None and not isinstance(published, str)):
            raise ValueError("URL, article text and publication date must be strings.")
        url = workflow.source_url(raw_url) if raw_url else None
        if not text.strip() and url:
            try:
                with cache_lock:
                    cached = article_cache.get(url)
                if cached and time.monotonic() - cached[0] < 300:
                    text, found_date = cached[1:]
                else:
                    text, found_date = fetch(url)
                    with cache_lock:
                        if len(article_cache) >= 32:
                            article_cache.pop(next(iter(article_cache)))
                        article_cache[url] = (time.monotonic(), text, found_date)
            except ValueError:
                raise
            except OSError as exc:
                raise ValueError("Article fetch failed: network or DNS error. Retry or paste its text.") from exc
            published = published or found_date
        return text, url, published

    def run_extraction(job_id, request):
        try:
            if extract is workflow.extract:
                config = configuration_status(store.ROOT)
                if not config["ready"]:
                    raise ValueError((config["error"] or "后台未读取到完整模型配置。缺少：" + ", ".join(config["missing"]))
                                     + "。请查看页面顶部配置检查，确认文件位于启动脚本同一目录。")
            started = time.monotonic()
            with job_lock:
                jobs[job_id]["phase"] = "fetching_article"
            text, url, published = read_article(request)
            fetch_ms = round((time.monotonic() - started) * 1000)
            with job_lock:
                jobs[job_id]["phase"] = "extracting"
            result = extract(text, url, published, taxonomy)
            result["fetch_ms"] = fetch_ms
            result["total_ms"] = round((time.monotonic() - started) * 1000)
            with store.database(path) as db:
                saved = store.save_extraction(db, result)
            update = {"status": "succeeded", "result": saved}
        except Exception as exc:
            LOGGER.warning("admin_job id=%s status=failed error=%s", job_id, type(exc).__name__)
            message = str(exc) if type(exc) is ValueError else "Extraction failed. Check server logs."
            update = {"status": "failed", "error": message}
        with job_lock:
            jobs[job_id].update(update)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            data = body if isinstance(body, bytes) else store.encode(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                             "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            try:
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                LOGGER.info("Client disconnected while receiving an HTTP response")

        def actor(self, *, required=True):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                token_cookie = cookie.get(cookie_name)
                if token_cookie:
                    with session_lock:
                        session = sessions.get(token_cookie.value)
                        if session and session[1] > time.monotonic():
                            return session[0]
                        sessions.pop(token_cookie.value, None)
            except CookieError:
                pass
            scheme, _, token = self.headers.get("Authorization", "").partition(" ")
            try:
                decoded = base64.b64decode(token, validate=True).decode()
                name, separator, supplied = decoded.partition(":")
                if (scheme.lower() == "basic" and separator and name and len(name) <= 80
                        and hmac.compare_digest(supplied.encode(), password.encode())):
                    return name
            except (binascii.Error, UnicodeError):
                pass
            if required:
                # Do not trigger the browser-native Basic-auth prompt on every API failure.
                self.send(401, {"error": "Login required or session expired. Reload this page to sign in."})
            return None

        def login(self, request):
            name = request.get("username")
            supplied = request.get("password")
            if (not isinstance(name, str) or not name.strip() or len(name) > 80
                    or not isinstance(supplied, str)
                    or not hmac.compare_digest(supplied.encode(), password.encode())):
                self.send(401, {"error": "用户名或密码不正确。请使用当前启动窗口中的密码。"})
                return
            token = secrets.token_urlsafe(32)
            now = time.monotonic()
            with session_lock:
                for key in list(sessions):
                    if sessions[key][1] <= now:
                        sessions.pop(key)
                if len(sessions) >= 128:
                    sessions.pop(next(iter(sessions)))
                sessions[token] = (name.strip(), now + 8 * 3600)
            self.send(200, {"ok": True}, headers={
                "Set-Cookie": f"{cookie_name}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
            })

        def do_GET(self):
            if self.path == "/healthz":
                self.send(200, {"status": "ok", "version": "form-login-v2",
                                "revision": os.getenv("RENDER_GIT_COMMIT", "local")})
                return
            route = urlsplit(self.path).path
            if route == "/favicon.ico":
                self.send(204, b"")
                return
            if route == "/" and not self.actor(required=False):
                self.send(200, LOGIN_PAGE.read_bytes(), "text/html; charset=utf-8")
                return
            if route == "/api/v1/published":
                token = os.getenv("USER_DATA_TOKEN", "")
                if not token or not hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode()):
                    self.send(401, {"error": "User-service token required."})
                    return
                with store.database(path) as db:
                    records = [{k: v for k, v in c.items() if k in set(workflow.FIELDS) | {"id", "primary_tracks", "admin_sources", "_updated"}} for c in store.companies(db)]
                    events = [{"company_id": r["company_id"], **json.loads(r["payload"])} for r in db.execute("SELECT company_id,payload FROM events")]
                self.send(200, {"schema_version": "1", "companies": records, "events": events})
                return
            actor = self.actor()
            if not actor:
                return
            if route == "/api/session":
                self.send(200, {"username": actor})
                return
            if route == "/api/config-status":
                self.send(200, configuration_status(store.ROOT))
                return
            if route.startswith("/api/extract/jobs/"):
                job_id = route.rsplit("/", 1)[-1]
                with job_lock:
                    job = jobs.get(job_id)
                    result = ({key: value for key, value in job.items() if key != "actor"}
                              if job and job["actor"] == actor else None)
                if result is None:
                    self.send(404, {"error": "Extraction task is no longer available. Check the review queue."})
                else:
                    self.send(200, result)
                return
            if route == "/":
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                return
            with store.database(path) as db:
                if route == "/api/companies":
                    self.send(200, store.companies(db))
                elif route.startswith("/api/publication/"):
                    from .publication import workspace
                    try:
                        self.send(200, workspace(db, route.rsplit("/", 1)[-1]))
                    except ValueError as exc:
                        self.send(404, {"error": str(exc)})
                elif route == "/api/backup":
                    from .backup import download
                    self.send(200, download(db), "application/octet-stream",
                              {"Content-Disposition": 'attachment; filename="radar-backup.sqlite3"'})
                elif route == "/api/queue":
                    self.send(200, store.queue(db))
                elif route == "/api/candidates":
                    self.send(200, [json.loads(row[0]) for row in db.execute("SELECT payload FROM candidates")])
                elif route.startswith("/api/company/"):
                    company_id = route.rsplit("/", 1)[-1]
                    events = db.execute("SELECT payload FROM events WHERE company_id=?", (company_id,))
                    self.send(200, sorted((json.loads(row[0]) for row in events),
                                          key=lambda row: row["published_at"] or "", reverse=True))
                elif route == "/api/export":
                    try:
                        self.send(200, snapshot(db), "application/zip",
                                  headers={"Content-Disposition": 'attachment; filename="matching_data.zip"'})
                    except ValueError as exc:
                        self.send(400, {"error": str(exc)})
                else:
                    self.send(404, {"error": "Unknown page."})

        def do_POST(self):
            route = urlsplit(self.path).path
            actor = None
            if route != "/api/login":
                actor = self.actor()
                if not actor:
                    return
            try:
                origin = self.headers.get("Origin")
                if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                    raise ValueError("Cross-origin requests are not accepted.")
                size = int(self.headers.get("Content-Length", "0"))
                if (self.headers.get_content_type() != "application/json"
                        or not 0 < size <= 250_000):
                    raise ValueError("Expected a JSON request under 250 KB.")
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict):
                    raise ValueError("Expected a JSON object.")
                if route == "/api/login":
                    self.login(request)
                    return
                route = urlsplit(self.path).path
                if route == "/api/extract":
                    self.start_extraction(request, actor)
                    return
                result = self.process(route, request, actor)
            except (KeyError, TypeError, ValueError, OSError, FetchError) as exc:
                self.send(400, {"error": str(exc) if isinstance(exc, (ValueError, FetchError)) else
                                "Request failed. Check inputs or paste the article text."})
                return
            self.send(200, result)

        def start_extraction(self, request, actor):
            with job_lock:
                busy = any(job["status"] == "running" for job in jobs.values())
                if not busy:
                    while len(jobs) >= 32:
                        jobs.pop(next(iter(jobs)))
                    job_id = uuid4().hex
                    jobs[job_id] = {"actor": actor, "status": "running"}
            if busy:
                self.send(409, {"error": "An extraction is in progress. Wait for it to finish."})
                return
            try:
                Thread(target=run_extraction, args=(job_id, request), daemon=True).start()
            except RuntimeError:
                with job_lock:
                    jobs.pop(job_id)
                self.send(503, {"error": "Could not start extraction. Try again."})
                return
            self.send(202, {"id": job_id})

        def process(self, route, request, actor):
            if route == "/api/article":
                text, url, published = read_article(request)
                if not workflow.usable_article(text):
                    raise ValueError("No readable article body. Try another URL or paste the article text.")
                return {"text": text, "url": url, "published_at": published, "characters": len(text)}
            if route == "/api/feed":
                body, _ = read_feed({"feed": {}}, http_get)
                rows, _ = parse_feed(body)
                with store.database(path) as db:
                    db.executemany("INSERT INTO candidates VALUES (?,?) ON CONFLICT(url) DO UPDATE SET payload=excluded.payload",
                                   [(row["url"], store.encode(row)) for row in rows])
                return rows
            if route == "/api/rules":
                text, url, _ = read_article(request)
                return {"rule_events": workflow.extract_events(
                    url or "", "", text, workflow.funding_fields(text))}
            with store.database(path) as db:
                if route in {"/api/publication/preview","/api/publication/apply"}:
                    from .publication import apply
                    return apply(db, request["changes"], actor, preview=route.endswith("/preview"))
                if route == "/api/company/create":
                    fields = request["fields"]
                    db.execute("BEGIN IMMEDIATE")
                    if store.match_company(db, fields["name"]):
                        raise ValueError("A company with this name already exists.")
                    return store.save_company(db,None,fields,actor,"manual")
                if route == "/api/review":
                    return store.decide(db, request, actor)
                if route == "/api/company":
                    row = db.execute("SELECT * FROM companies WHERE id=?", (request["id"],)).fetchone()
                    if row is None:
                        raise ValueError("Company not found.")
                    return store.save_company(db, row, request["fields"], actor, "manual")
            raise ValueError("Unknown endpoint.")

    return Handler


def make_server(address, path, password, **dependencies):
    if not password:
        raise ValueError("Set ADMIN_PASSWORD before starting the administrator service.")
    with store.database(path) as db:
        store.initialize(db)
    return AdminHTTPServer(address, handler_for(path, password, **dependencies))


if __name__ == "__main__":
    load_project_config(store.ROOT)
    database = Path(os.getenv("ADMIN_DB_PATH", "var/admin.sqlite3"))
    with make_server((os.getenv("ADMIN_HOST", "127.0.0.1"), int(os.getenv("PORT", "8012"))),
                     database, os.getenv("ADMIN_PASSWORD")) as server:
        print(f"Administrator service listening on port {server.server_port}", flush=True)
        server.serve_forever()
