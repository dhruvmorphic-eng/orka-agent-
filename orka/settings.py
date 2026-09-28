"""Local credentials: gitignored, owner-readable only, never logged."""
import json
import os
import tempfile
from pathlib import Path
from dotenv import dotenv_values


def settings_path():
    return Path(__file__).resolve().parent.parent / "data" / "credentials.json"


def save_credentials(key, model, path=None):
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".credentials-")
    try:
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"ANTHROPIC_API_KEY": key, "ANTHROPIC_MODEL": model}, handle)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_credentials(path=None, env_path=None):
    # Load only documented settings; do not expand shell/environment references.
    if path is None or env_path is not None:
        env_file = Path(env_path) if env_path else Path(__file__).resolve().parent.parent / ".env"
        try:
            values = dotenv_values(env_file, interpolate=False) if env_file.exists() else {}
            for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ORKA_DB"):
                value = values.get(name)
                if value and value.strip():
                    os.environ.setdefault(name, value.strip())
        except (OSError, ValueError):
            raise RuntimeError("Local .env settings could not be read.") from None
    path = Path(path or settings_path())
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
            value = data.get(name)
            if isinstance(value, str) and value.strip():
                # Explicit environment configuration takes priority.
                os.environ.setdefault(name, value.strip())
    except (OSError, ValueError, AttributeError):
        raise RuntimeError("Local AI settings could not be read. Run Configure Orka.command again.") from None
