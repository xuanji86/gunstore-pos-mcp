"""Distributor (RSR Direct Connect) tools — the drop-ship read surface plus the
human confirmation queue.

Every method below was checked against gunstore-pos `origin/develop` before being
wrapped, per this repo's standing rule: the MCP is a thin wrapper and its tests are
fully mocked, so a signature drift would NOT surface here — it would surface as a
runtime error against a live POS.

Split by consequence, because "queue operations" spans a wide range:

* **reads** — catalog/quote/queue/order lists. Two of them (`check_availability`,
  `precheck_fds`) reach the distributor over HTTP; they change nothing, but they are
  not free, so they say so.
* **queue actions** — these move a Distributor Order through the v1 human-confirmed
  gate. ``confirm`` is required on all of them, and it is not ceremony:
  `confirm_order` transitions Draft → Queued **and enqueues the placement worker**,
  i.e. it is the moment a real purchase from RSR becomes inevitable. RSR has no
  cancel API, so there is no undo after that.

Deliberately NOT exposed: direct placement, settings writes, and anything outside the
metabox's clientele.

`fulfillment_options_for_order` (gunstore-pos #258, merged) IS wrapped. Its payload is
three-valued in two places, which is the one thing a consumer here is likely to get
wrong: a null means "not determined yet", never "fine". See that tool's docstring —
an agent that reads it as falsy will report an unchecked destination as shippable,
which is the same fail-open the POS side was just fixed for.
"""
from __future__ import annotations

from typing import Any

from ..frappe_client import get_client
from ..safety import require_confirm, require_reason

_API = "ffl_integrations.distributor.api."
_ROUTER = "ffl_integrations.distributor.router."
_OPTIONS = "ffl_integrations.distributor.options."


def register(mcp: Any) -> None:
    # ------------------------------------------------------------------ reads

    @mcp.tool()
    def distributor_orders(
        status: str | None = None, distributor: str | None = None, limit: int = 50
    ) -> Any:
        """List Distributor Orders (drop-ship / restock purchase orders to RSR).
        status: Draft | Queued | Placed | Acknowledged | Hold | Partially Shipped |
        Complete | Cancelled | Error (empty = all). Read-only."""
        return get_client().call_method(
            _API + "list_orders",
            {"status": status, "distributor": distributor, "limit": limit},
        )

    @mcp.tool()
    def distributor_route_queue(limit: int = 50) -> Any:
        """The human confirmation queue: Draft Distributor Orders awaiting an
        operator, plus web orders PARKED before routing (unpaid, missing/expired
        buyer FFL, incomplete address) with the reason and the destination FFL's
        expiry. This is the list to read before confirming anything. Read-only."""
        return get_client().call_method(_ROUTER + "route_queue", {"limit": limit})

    @mcp.tool()
    def distributor_catalog_search(
        query: str, limit: int = 10, distributor: str | None = None
    ) -> Any:
        """Typeahead the distributor's catalog by keyword / stock # / UPC / MFG #.
        Reads the locally-synced catalog, not live stock — use
        distributor_check_availability before acting on a quantity. Read-only."""
        return get_client().call_method(
            _API + "search",
            {"query": query, "limit": limit, "distributor": distributor},
        )

    @mcp.tool()
    def distributor_quote(
        item_code: str | None = None, sku: str | None = None,
        distributor: str | None = None,
    ) -> Any:
        """Per-item economics: cost, MAP, MSRP, suggested sell price (the same
        pricing chain the storefront listing publishes), last-known catalog qty,
        restricted states, and the block flags. Pass item_code for a stocked item or
        sku for a raw catalog row. The quantity is the CACHED catalog figure — its
        freshness is not asserted here. Read-only, no HTTP to the distributor."""
        return get_client().call_method(
            _API + "quote",
            {"item_code": item_code, "sku": sku, "distributor": distributor},
        )

    @mcp.tool()
    def distributor_check_availability(
        lines: list[dict], distributor: str | None = None
    ) -> Any:
        """LIVE quantity/price re-confirm straight from the distributor for the given
        lines ([{sku, qty}, …]). Changes nothing, but unlike distributor_quote it
        does reach RSR over HTTP — use it to second-check before confirming an order,
        not to browse."""
        return get_client().call_method(
            _API + "check_availability",
            {"lines": lines, "distributor": distributor},
        )

    @mcp.tool()
    def distributor_precheck_fds(do_name: str) -> Any:
        """Ask the distributor whether the transfer dealer named on this FDS order
        accepts drop-shipped firearms — the cheapest way to avoid an FDS Hold.
        Reaches RSR over HTTP; changes nothing."""
        return get_client().call_method(_ROUTER + "precheck_fds", {"do_name": do_name})

    @mcp.tool()
    def distributor_fulfillment_options(woo_online_order: str) -> Any:
        """Everything needed to decide how to fill ONE web order: per line, the
        distributor candidates (cheapest first), a LOCAL stock comparison row, and a
        verdict. Read-only — it plans nothing and orders nothing.

        THREE-VALUED FIELDS. `if not x` is WRONG on both of these; null means "not
        determined yet", never "fine":

        * `verdict.fulfillable` — true / false / **null**. Null carries a `reason`:
          `unknown_destination` (the destination state is not captured yet — the
          NORMAL state while an order sits in Pending Route or before the buyer's FFL
          is on file) or `stale_feed` (the only quantity that could cover the line
          came off a feed past its refresh window).
        * `restricted_state` — true / false / **null**, same null meaning.

        Treat null as HOLD: report the line as undetermined and quote the `reason`.
        Never state that such a line can ship — a restricted item to an unresolved
        destination is exactly the case this must not wave through.

        CANDIDATE FLAGS: `not_carried` = that distributor has no catalog row for the
        item (listed rather than dropped, so it is not misread as out-of-stock);
        `blocked` = carried but unbuyable (distributor block / vendor approval);
        `stale` = quantity from an aged feed. Unbuyable rows sort to the BOTTOM, so
        the first candidate is the actionable one.

        MONEY: `unit_landed` is PER UNIT and goods-only. Freight does not exist until
        the order is placed, so `shipping` is null with `shipping_known` false. Do not
        present `unit_landed` as a landed cost, and do not multiply it by quantity and
        call the result final."""
        return get_client().call_method(
            _OPTIONS + "fulfillment_options_for_order",
            {"woo_online_order": woo_online_order},
        )

    # --------------------------------------------------------- queue actions

    @mcp.tool()
    def distributor_confirm_order(do_name: str, confirm: bool = False) -> Any:
        """Confirm a DRAFT Distributor Order: Draft → Queued, then the placement
        worker runs.

        ⚠ This is the point of no return. It causes a REAL purchase from the
        distributor, and RSR has **no cancel API** — after placement, undoing it is a
        phone call and a return, not a status change. A counter-sourced order is also
        gated on its invoice being paid in full and will refuse otherwise.
        Read distributor_route_queue first. Requires confirm=true."""
        require_confirm(f"confirm distributor order {do_name} (places a real order)",
                        confirm)
        return get_client().call_method(_API + "confirm_order", {"do_name": do_name})

    @mcp.tool()
    def distributor_cancel_order(
        do_name: str, reason: str, confirm: bool = False
    ) -> Any:
        """Cancel a Distributor Order. Safe only BEFORE placement (Draft/Queued): the
        server will still mark a live order Cancelled but alerts operations, because
        the goods are already moving and the distributor has no cancel API — the
        return is a manual process. Requires a reason and confirm=true."""
        reason = require_reason(f"cancel distributor order {do_name}", reason)
        require_confirm(f"cancel distributor order {do_name}", confirm)
        return get_client().call_method(
            _API + "cancel_order", {"do_name": do_name, "reason": reason}
        )

    @mcp.tool()
    def distributor_reroute(woo_online_order: str, confirm: bool = False) -> Any:
        """Re-run routing for a web order parked in the queue, after fixing whatever
        parked it (payment, the buyer's FFL, the shipping address). Creates DRAFT
        orders only — it never places anything — but it does create documents, so it
        asks for confirm=true. Idempotent: an order that already has live distributor
        orders gains no duplicates."""
        require_confirm(f"re-route {woo_online_order}", confirm)
        return get_client().call_method(
            _ROUTER + "reroute", {"woo_online_order": woo_online_order}
        )

    @mcp.tool()
    def distributor_update_order_ffl(
        do_name: str, ffl_license: str, confirm: bool = False
    ) -> Any:
        """Attach or replace the transfer FFL on a placed FDS order — the standard
        way to release an FDS Hold. The new licence is re-validated through the same
        canonical chain the counter uses (unexpired, complete premise address) BEFORE
        the distributor is called, so an expired licence is refused rather than
        released onto. Calls RSR. Requires confirm=true."""
        require_confirm(f"update transfer FFL on {do_name} to {ffl_license}", confirm)
        return get_client().call_method(
            _ROUTER + "update_order_ffl",
            {"do_name": do_name, "ffl_license": ffl_license},
        )
