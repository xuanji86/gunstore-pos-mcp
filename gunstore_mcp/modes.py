"""Server modes — the cpa read-only gate.

`GUNSTORE_MCP_MODE=cpa` turns the server into an accountant-facing, read-only
surface with three independent defence layers (each fails closed on its own):

  1. Registration (this module's FilteredMCP + CPA_TOOL_NAMES): only the
     18 allowlisted tools exist in tools/list — the write surface is
     physically absent, not merely guarded.
  2. Client (frappe_client.py): every mutating client method refuses in cpa
     mode, and dotted methods are checked against CPA_METHOD_ALLOWLIST —
     names listed one by one, NO prefix wildcards, NO HTTP-verb heuristics
     (run_report rides POST-adjacent /api/method GET; verbs prove nothing).
  3. Settings reads: the 8 integration Settings doctypes refuse get/list in
     cpa mode — Password masking is a framework behaviour, not this repo's
     guarantee, and the config surface has no accounting purpose.

Allowlist caliber authority: runs/2026-07-16-mcp-cpa-mode/cpa-review.md §4
(9 curated reads kept, 6 cut — available_serials excluded because its
exclude_unavailable=True default silently drops consigned/held guns, which is
exactly wrong in a stock-count/audit context).
"""
from __future__ import annotations

import os

from .config import _load_env

FULL_MODE = "full"
CPA_MODE = "cpa"
_VALID_MODES = (FULL_MODE, CPA_MODE)


class CpaModeRefused(RuntimeError):
    """Raised when cpa (read-only) mode blocks an operation."""


# Layer 1 — the EXACT cpa tools/list (asserted by set equality in tests;
# 4 generic + 9 curated read-only + 5 CPA reports = 18).
CPA_TOOL_NAMES: frozenset[str] = frozenset({
    # generic reads (frappe_run_method deliberately absent: reads and writes
    # are statically indistinguishable through it)
    "frappe_list_documents",
    "frappe_get_document",
    "frappe_describe_doctype",
    "frappe_run_report",
    # curated read-only
    "find_item",
    "item_stock",
    "firearms_in_stock",
    "pending_orders",
    "pending_web_orders",
    "consignment_queue",
    "consignment_dealers",
    "consignment_serials",
    "consignment_dealer_orders",
    # CPA report pack (tools/reports.py)
    "sales_report",
    "gl_entries",
    "financial_statement",
    "tax_liability",
    "ar_ap_summary",
})

# Layer 2 — dotted methods callable in cpa mode. One name per line, verified
# read-only server-side; prefix wildcards are a forbidden construct here.
CPA_METHOD_ALLOWLIST: frozenset[str] = frozenset({
    "frappe.desk.query_report.run",
    "ffl_core.api.receive_goods.search_items",
    "ffl_core.api.item_admin.get_item_stock",
    "ffl_core.api.manual_order.list_pending_dispositions",
    "ffl_woo_sync.woocommerce.fulfillment.list_pending_web_orders",
    "ffl_core.api.consignment_out.list_consignment_queue",
    "ffl_core.api.consignment_out.list_consignment_dealers",
    "ffl_core.api.consignment_out.available_serials_for_consignment",
    "ffl_core.api.consignment_orders.list_dealer_orders",
})

# Layer 3 — integration Settings doctypes whose get/list reads are refused in
# cpa mode (config surface, no accounting purpose).
CPA_SETTINGS_READ_BLOCKLIST: frozenset[str] = frozenset({
    "FFL Settings",
    "FastBound Settings",
    "RSR Settings",
    "Payroc Settings",
    "WooCommerce Settings",
    "Dealer WooCommerce Settings",
    "ShipStation Settings",
    # Holds the GunBroker DevKey and the seller account password. Reading it has
    # no accounting purpose, and Password masking is a framework behaviour rather
    # than a guarantee this repo makes.
    "GunBroker Settings",
})


def get_mode() -> str:
    """Resolve the server mode from GUNSTORE_MCP_MODE (default: full).

    Unknown values fail closed with a RuntimeError instead of silently
    running full — a typo'd 'cpa' must never yield a writable server."""
    _load_env()  # honour .env the same way credentials do
    raw = (os.environ.get("GUNSTORE_MCP_MODE") or FULL_MODE).strip().lower()
    if raw not in _VALID_MODES:
        raise RuntimeError(
            f"GUNSTORE_MCP_MODE must be one of {_VALID_MODES} (got {raw!r}) — "
            "refusing to guess a mode."
        )
    return raw


class FilteredMCP:
    """Registration-time filter: only allowlisted tool names reach the real
    MCP; everything else is silently skipped (the tool never exists)."""

    def __init__(self, mcp, allow) -> None:
        self._mcp = mcp
        self._allow = frozenset(allow)

    def tool(self, *args, **kwargs):
        real = self._mcp.tool(*args, **kwargs)

        def deco(fn):
            if fn.__name__ in self._allow:
                return real(fn)
            return fn

        return deco
