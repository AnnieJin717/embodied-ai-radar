"""One FastAPI application for the published client and the authenticated administrator."""
import io
import os
from email.message import Message
from pathlib import Path
from threading import Lock

from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from .admin import store, publication
from .admin.config import load_project_config
from .admin.server import handler_for
from .matching.api import create_app
from .matching.service import MatchingService


class Integration:
    def __init__(self, db, password, config):
        self.db,self.password,self.config=db,password,config
        self.lock=Lock()
        self.version=None

    def initialize(self):
        if not self.password:
            raise RuntimeError("Set ADMIN_PASSWORD before starting the service.")
        with store.database(self.db) as db:
            store.initialize(db)
        with store.database(self.db) as db:
            publication.initialize(db)

    def current(self):
        with self.lock, store.database(self.db) as db:
            version=db.execute("SELECT MAX(id) FROM editions").fetchone()[0]
            if self.version != version:
                entries=list(db.execute(publication.LATEST))
                repo=publication.PublishedRepository(entries)
                self.service=MatchingService(repo,self.config)
                self.version=version
                self.updated=max((e["created"] for e in entries),default=None)
            return self.service,self.updated

    def news(self):
        service,updated=self.current()
        return {"articles":list(service.repository.articles.values()),"fetched_at":updated,"last_batch":None}

    def mount(self,app):
        handler=handler_for(self.db,self.password)

        class AdminRequest(handler):
            def __init__(self,method,path,headers,body):
                self.path=path
                self.headers=Message()
                for key,value in headers.items():
                    self.headers[key]=value
                self.rfile=io.BytesIO(body)
                if method=="GET":
                    self.do_GET()
                else:
                    self.do_POST()

            def send(self,status,body,content_type="application/json; charset=utf-8",headers=None):
                content=body if isinstance(body,bytes) else store.encode(body).encode()
                headers=dict(headers or {})
                if os.getenv("RENDER") and "Set-Cookie" in headers:
                    headers["Set-Cookie"]+="; Secure"
                headers.update({"Content-Type":content_type,"Cache-Control":"no-store","X-Frame-Options":"DENY",
                    "X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"})
                self.response=Response(content,status_code=status,headers=headers)

        @app.middleware("http")
        async def publication_context(request,call_next):
            if request.url.path.startswith("/api/v1/"):
                request.state.service,_=await run_in_threadpool(self.current)
            response=await call_next(request)
            response.headers["Cache-Control"]="no-store"
            return response

        @app.api_route("/admin",methods=["GET"])
        @app.api_route("/admin/{path:path}",methods=["GET","POST"])
        async def administrator(request:Request,path:str=""):
            if path=="api/v1/published":
                return Response(status_code=404)
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>250000:
                    return Response(status_code=413)
            headers=dict(request.headers)
            headers["content-length"]=str(len(body))
            operation=await run_in_threadpool(AdminRequest,request.method,"/"+path,headers,body)
            return operation.response


def build():
    load_project_config(store.ROOT)
    url=os.getenv("DATABASE_URL")
    if os.getenv("RENDER") and not url:
        raise RuntimeError("Render requires persistent DATABASE_URL.")
    path=url or Path(os.getenv("RADAR_DB_PATH") or store.ROOT.parent/"radar-integrated-data"/"radar.sqlite3")
    return create_app(integration=Integration(path,os.getenv("ADMIN_PASSWORD"),dict(os.environ)))

app=build()
