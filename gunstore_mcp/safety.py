"""Centralized write guards used by every mutating tool.

Concerns kept in one place so generic and curated tools can't diverge:
  - strip_passwords: credentials never transit the MCP / the conversation.
  - require_confirm: destructive/consequential ops need an explicit confirm=true.
  - check_write_allowed: structural/permission doctypes are read-only here.
  - stripped_note: uniform "field X was not sent" response wrapper.
"""
from __future__ import annotations

import re
import time

from .config import get_config
from .frappe_client import get_client

# Name-based credential backstop — applied to EVERY key at every nesting level,
# even when doctype meta can't be fetched, so a secret can't slip through on a
# transient describe failure. Meta-based Password-type detection is primary.
_CREDENTIAL_NAME = re.compile(
    r"(passwd|password|pwd|secret|api[_-]?key|token|webhook|private[_-]?key"
    r"|passphrase|credential|\bpin\b)",
    re.I,
)

_PW_TTL = 600.0  # re-describe a doctype's Password fields at most every 10 min
_pw_cache: dict[str, tuple[float, frozenset[str]]] = {}


class WriteRefused(RuntimeError):
    """Raised when a write is blocked by a guard (surfaced to the user as-is)."""


def _password_fields(doctype: str) -> frozenset[str]:
    now = time.monotonic()
    hit = _pw_cache.get(doctype)
    if hit and now - hit[0] < _PW_TTL:
        return hit[1]
    fields = get_client().describe_doctype(doctype)
    pw = frozenset(
        f.get("fieldname") for f in fields
        if f.get("fieldtype") == "Password" and f.get("fieldname")
    )
    if fields:  # never cache an empty result from a failed describe
        _pw_cache[doctype] = (now, pw)
    return pw


def _is_credential(key: str, meta_pw: frozenset[str]) -> bool:
    return key in meta_pw or bool(_CREDENTIAL_NAME.search(key))


def _strip(values: dict, meta_pw: frozenset[str], stripped: list[str], prefix: str = "") -> dict:
    clean: dict = {}
    for k, v in values.items():
        path = f"{prefix}{k}"
        if _is_credential(k, meta_pw):
            stripped.append(path)
            continue
        if isinstance(v, dict):
            clean[k] = _strip(v, meta_pw, stripped, f"{path}.")
        elif isinstance(v, list):
            clean[k] = [
                _strip(row, meta_pw, stripped, f"{path}[].") if isinstance(row, dict) else row
                for row in v
            ]
        else:
            clean[k] = v
    return clean


def strip_passwords(doctype: str, values: dict) -> tuple[dict, list[str]]:
    """Return (values with every credential field removed, list of stripped paths).

    Recurses into nested dicts and child-table rows. Credential detection is
    meta-based (Password fieldtype) for the top-level doctype, plus a name-regex
    backstop applied at every nesting level."""
    try:
        meta_pw = _password_fields(doctype)
    except Exception:
        # Fail safe: a describe hiccup must never block a legitimate write, and
        # the name-regex backstop still covers credential-named fields.
        meta_pw = frozenset()
    stripped: list[str] = []
    clean = _strip(values, meta_pw, stripped)
    return clean, stripped


def stripped_note(result, stripped: list[str]):
    """Wrap a write result with a note naming any credential fields not sent."""
    if not stripped:
        return result
    return {
        "result": result,
        "stripped_password_fields": stripped,
        "note": (
            f"credential field(s) {stripped} were NOT sent — set them directly in "
            "Desk; the MCP never transmits credentials."
        ),
    }


def require_confirm(action: str, confirm: bool) -> None:
    if not confirm:
        raise WriteRefused(
            f"Refused: '{action}' is destructive/consequential. "
            "Re-call with confirm=true to proceed."
        )


def check_write_allowed(doctype: str) -> None:
    if doctype in get_config().write_denylist:
        raise WriteRefused(
            f"Refused: writes to '{doctype}' are blocked (schema/permission doctype). "
            "Change these in Desk or via code/migrations, not the MCP."
        )
