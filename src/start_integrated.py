import os
import secrets
import socket
import webbrowser
from threading import Timer
import uvicorn
from .admin.config import load_project_config
from .admin.store import ROOT

if __name__=="__main__":
    load_project_config(ROOT)
    os.environ.setdefault("ADMIN_PASSWORD",secrets.token_urlsafe(16))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    url=f"http://127.0.0.1:{port}"
    print(f"Client: {url}/\nAdmin: {url}/admin\nUsername: tester\nPassword: {os.environ['ADMIN_PASSWORD']}",flush=True)
    Timer(2,webbrowser.open,args=(url+"/admin",)).start()
    uvicorn.run("src.integrated:app",host="127.0.0.1",port=port)
