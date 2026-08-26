"""Centralized write guards used by every mutating tool.

Concerns kept in one place so generic and curated tools can't diverge:
  - strip_passwords: credentials never transit the MCP / the conversation.
  - require_confirm: destructive/consequential ops need an explicit confirm=true.
  - check_write_allowed: structural/permission doctypes are read-only here.
  - check_fields_writable: some fields are not writable through the MCP at all.
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
#
# `[_-]key\b` is the general arm: it catches `consumer_key`, `dev_key`,
# `sandbox_dev_key` and anything else spelled <thing>_key, while leaving RSR's
# `key_dealer` / `ftp_dir_keydealer` alone (those are a dealer tier, not a
# secret — "key" leads there, and no word boundary follows it). A bare `key`
# would strip both and break legitimate writes. `dev[_-]?key` is spelled out
# separately so the unseparated `devkey` is covered too, the way `apikey` is.
#
# Verified against every Password field in the platform: before this arm,
# `consumer_key` (WooCommerce Settings AND Dealer WooCommerce Settings) already
# escaped the backstop — GunBroker's DevKey was not the first gap, only the one
# that got noticed.
_CREDENTIAL_NAME = re.compile(
    r"(passwd|password|pwd|secret|api[_-]?key|token|webhook|private[_-]?key"
    r"|dev[_-]?key|[_-]key\b|passphrase|credential|\bpin\b)",
    re.I,
)

# Fields the MCP must never write, per doctype. Distinct from the credential
# backstop above in both mechanism and reason: credentials are stripped and
# reported, these REFUSE the whole call.
#
# Refusing rather than stripping is the point. A caller who asks to flip
# `sandbox_mode` and set `page_size` in one call believes both landed; strip the
# first and the write half-applies while the response says it succeeded in a
# note nobody reads. For a field that decides whether a firearm goes on the real
# GunBroker, "you may not do this here" has to be an error, not a footnote.
#
# These belong in the desk UI, done by a person who can see the whole settings
# form, not in a tool call an agent can talk itself into. The MCP instance
# genuinely points at production (see tools/distributor.py:169-177 for the same
# reasoning applied to registration).
MCP_NEVER_WRITES: dict[str, frozenset[str]] = {
    "GunBroker Settings": frozenset({
        # environment — LD-13: sandbox vs the live marketplace is decided on the
        # POS and nowhere else. base_url_override is here because it overrides
        # the base URL outright and so defeats sandbox_mode on its own.
        "enabled", "sandbox_mode", "base_url_override",
        # credentials — also caught by the backstop above; named here so the
        # refusal is explicit rather than a silent strip.
        "dev_key", "sandbox_dev_key", "username", "password",
        # money and irreversibility
        "end_strategy", "check_deposit_account", "card_checkout_enabled",
    }),
}

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


def check_fields_writable(doctype: str, values: dict) -> None:
    """Refuse the whole write if it touches a field the MCP may never set.

    Top level only: the forbidden names are all scalars on the parent doctype,
    and a child row that happens to reuse one of these names (a `category_map`
    row with an `enabled` column, say) is a different field entirely."""
    forbidden = MCP_NEVER_WRITES.get(doctype)
    if not forbidden:
        return
    hit = sorted(k for k in values if k in forbidden)
    if not hit:
        return
    raise WriteRefused(
        f"Refused: {hit} cannot be set through the MCP on '{doctype}'. "
        f"These decide which GunBroker gets contacted, hold the credentials, or "
        f"move money — they are changed in Desk by a person, deliberately, not "
        f"in a tool call. Not writable here: {sorted(forbidden)}."
    )


def require_confirm(action: str, confirm: bool) -> None:
    if not confirm:
        raise WriteRefused(
            f"Refused: '{action}' is destructive/consequential. "
            "Re-call with confirm=true to proceed."
        )


def require_reason(action: str, reason: str | None) -> str:
    """Validate the mandatory reason on cancel-class ops; returns it stripped.

    The server enforces non-empty reasons independently — this is the UX
    front-gate so the refusal happens before any network call, and it lives
    here so curated tools can't diverge on the message."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError(
            f"reason is required for '{action}' — say why (it is recorded "
            "in the audit trail)."
        )
    return reason


def check_write_allowed(doctype: str) -> None:
    if doctype in get_config().write_denylist:
        raise WriteRefused(
            f"Refused: writes to '{doctype}' are blocked (schema/permission doctype). "
            "Change these in Desk or via code/migrations, not the MCP."
        )
