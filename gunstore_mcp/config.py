"""Environment-driven configuration (loaded once, lazily)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Schema / permission doctypes blocked from writes by default. Changing these is
# a code/migration concern, not something to do ad-hoc against production.
DEFAULT_WRITE_DENYLIST = (
    "DocType", "Custom Field", "Property Setter", "Server Script",
    "Client Script", "Role", "DocPerm", "Custom DocPerm", "User",
)


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    api_secret: str
    timeout: int
    write_denylist: frozenset[str]


_config: Config | None = None


def _load_env() -> None:
    # .env sits at the repo root, two levels up from gunstore_mcp/config.py.
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # fall back to process env / cwd .env


def get_config() -> Config:
    global _config
    if _config is not None:
        return _config

    _load_env()
    base_url = (os.environ.get("FRAPPE_BASE_URL") or "").rstrip("/")
    api_key = os.environ.get("FRAPPE_API_KEY") or ""
    api_secret = os.environ.get("FRAPPE_API_SECRET") or ""
    if not (base_url and api_key and api_secret):
        raise RuntimeError(
            "Missing Frappe credentials. Set FRAPPE_BASE_URL, FRAPPE_API_KEY and "
            "FRAPPE_API_SECRET in mcp/.env (see mcp/.env.example)."
        )

    raw = os.environ.get("FRAPPE_WRITE_DENYLIST")
    denylist = (
        frozenset(d.strip() for d in raw.split(",") if d.strip())
        if raw is not None
        else frozenset(DEFAULT_WRITE_DENYLIST)
    )

    raw_timeout = os.environ.get("FRAPPE_TIMEOUT") or "30"
    try:
        timeout = int(raw_timeout)
    except ValueError:
        raise RuntimeError(f"FRAPPE_TIMEOUT must be an integer (got {raw_timeout!r}).")

    _config = Config(
        base_url=base_url,
        api_key=api_key,
        api_secret=api_secret,
        timeout=timeout,
        write_denylist=denylist,
    )
    return _config
