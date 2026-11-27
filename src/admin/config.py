"""Read local settings; diagnostics never return credential values."""
import io
import os
import re
from pathlib import Path
from dotenv import dotenv_values

SETTINGS = {"ADMIN_PASSWORD", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ADMIN_HOST",
            "ADMIN_DB_PATH", "USER_DATA_TOKEN", "ADMIN_EXTRACTION_MODE", "JINA_API_KEY",
            "ARTICLE_READER_ENABLED", "ARTICLE_READER_TRANSPORT", "ADMIN_MODEL_TRANSPORT"}


def load_project_config(root, *, override=False, model_only=False):
    root = Path(root)
    path = next((root / n for n in (".env", ".env.txt") if (root / n).is_file()), None)
    error = None
    if path:
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
            values = dotenv_values(stream=io.StringIO(text), interpolate=False)
            if model_only and override:
                for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
                    os.environ.pop(name, None)
            for name, value in values.items():
                if name not in SETTINGS or value is None:
                    continue
                if model_only and name not in {"OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ADMIN_EXTRACTION_MODE"}:
                    continue
                if override or not os.environ.get(name, "").strip():
                    os.environ[name] = value.strip()
        except (OSError, UnicodeError):
            error = "无法读取配置文件，请用记事本另存为 UTF-8 编码。"
    missing = [n for n in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL") if not os.getenv(n, "").strip()]
    model = os.getenv("OPENROUTER_MODEL", "").strip()
    display_model = model if re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.:/-]+", model) else ""
    if model and not display_model:
        error = "模型 ID 格式应为 提供商/模型名，请检查 OPENROUTER_MODEL。"
    return {"file": path.name if path else None, "directory": str(root), "missing": missing,
            "model": display_model, "ready": not missing and error is None,
            "error": error, "note": "就绪仅表示配置已读取，未验证密钥、余额和模型服务连接。"}


def configuration_status(root):
    local = os.getenv("ADMIN_LOCAL_CONFIG_RELOAD") == "1"
    return load_project_config(root, override=local, model_only=True)
