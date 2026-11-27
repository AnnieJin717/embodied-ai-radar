"""Native HTTPS fallback, restricted to the public reader service."""
import os
from pathlib import Path
import shutil
import subprocess
import json
from urllib.error import HTTPError
from urllib.request import getproxies


def native_reader(url, headers):
    if not url.startswith("https://r.jina.ai/"):
        raise ValueError("Only the fixed reader service is accepted")
    return _native_https(url, headers)


def native_model(payload, key):
    return json.loads(_native_https("https://openrouter.ai/api/v1/chat/completions", {
        "Content-Type": "application/json", "Authorization": "Bearer " + key}, payload))


def _native_https(url, headers, payload=None):
    system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "curl.exe"
    executable = str(system) if os.name == "nt" and system.is_file() else shutil.which("curl")
    if not executable:
        raise OSError("Native HTTPS transport unavailable")
    config = []
    # urllib discovers Windows system proxies as well as environment settings.
    proxy = getproxies().get("https")
    if proxy:
        if any(c in proxy for c in "\r\n\0"):
            raise ValueError("Invalid HTTPS proxy configuration")
    for name, value in headers.items():
        line = f"{name}: {value}"
        if any(c in line for c in "\r\n\0"):
            raise ValueError("Invalid reader header configuration")
        config.append('header = "' + line.replace('\\', '\\\\').replace('"', '\\"') + '"')
    if payload is not None:
        serialized = json.dumps(payload, ensure_ascii=False)
        config.append('data-binary = "' + serialized.replace('\\', '\\\\').replace('"', '\\"') + '"')
    # Header credentials go through stdin only; no shell or redirect following.
    command = [executable, "--config", "-", "--silent", "--show-error", "--proto", "=https",
               "--connect-timeout", "8", "--max-time", "65" if payload is not None else "25", "--max-filesize", "1500000",
               "--write-out", "\n%{http_code}", url]
    routes = [config + ['noproxy = "*"']]
    if proxy:
        escaped_proxy = proxy.replace('\\', '\\\\').replace('"', '\\"')
        routes.append(config + ['proxy = "' + escaped_proxy + '"', 'noproxy = ""'])
    for route in routes:
        try:
            result = subprocess.run(command, input=("\n".join(route) + "\n").encode(),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=68 if payload is not None else 28,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            if payload is not None:
                raise TimeoutError("Model request timed out")
            continue
        if result.returncode:
            if payload is not None and result.returncode == 28:
                raise TimeoutError("Model request timed out")
            continue
        body, _, status = result.stdout.rpartition(b"\n")
        if status != b"200":
            if payload is not None:
                raise HTTPError(url, int(status or b"502"), "Model service rejected request", {}, None)
            raise ValueError("阅读服务返回 HTTP " + status.decode("ascii", errors="replace"))
        if len(body) > 1_500_000:
            raise ValueError("阅读服务响应超过大小限制")
        return body
    raise OSError("Native reader could not connect directly or through the configured proxy")
