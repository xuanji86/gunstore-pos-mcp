"""Curated convenience tools — one call for the frequent settings / sync / report
ops. Thin wrappers over the generic backbone + the apps' whitelisted methods."""
from __future__ import annotations

from typing import Any

from ..frappe_client import get_client
from ..safety import require_confirm, require_reason, strip_passwords, stripped_note

_SETTINGS = {
    "ffl": "FFL Settings",
    "fastbound": "FastBound Settings",
    "rsr": "RSR Settings",
    "payroc": "Payroc Settings",
    "woocommerce": "WooCommerce Settings",
    "dealer": "Dealer WooCommerce Settings",
    "shipstation": "ShipStation Settings",
    "gunbroker": "GunBroker Settings",
}


def _resolve(which: str) -> str:
    key = (which or "").strip().lower()
    if key not in _SETTINGS:
        raise ValueError(
            f"Unknown settings area '{which}'. Use one of: {', '.join(_SETTINGS)}."
        )
    return _SETTINGS[key]


def register(mcp: Any) -> None:
    @mcp.tool()
    def get_settings(which: str) -> Any:
        """Read an integration's Settings. which: ffl | fastbound | rsr | payroc |
        woocommerce | dealer (dealer-portal WooCommerce) | shipstation | gunbroker.
        Password fields are never returned by Frappe."""
        dt = _resolve(which)
        return get_client().get_document(dt, dt)

    @mcp.tool()
    def update_settings(which: str, values: dict) -> Any:
        """Update an integration's Settings. which: ffl | fastbound | rsr | payroc |
        woocommerce | dealer (dealer-portal WooCommerce) | shipstation | gunbroker.
        Credential/password fields are stripped — set those in Desk."""
        dt = _resolve(which)
        clean, stripped = strip_passwords(dt, values)
        return stripped_note(get_client().update_document(dt, dt, clean), stripped)

    @mcp.tool()
    def rsr_sync_catalog() -> Any:
        """Trigger a full RSR catalog sync. Runs in the background — returns once queued."""
        return get_client().call_method("ffl_integrations.rsr.tasks.sync_catalog_now")

    @mcp.tool()
    def rsr_test_connection() -> Any:
        """Probe the RSR FTPS connection + configuration (read-only)."""
        return get_client().call_method("ffl_integrations.rsr.tasks.test_connection")

    @mcp.tool()
    def fastbound_test_connection() -> Any:
        """Probe the FastBound API connection (read-only)."""
        return get_client().call_method("ffl_integrations.fastbound.client_api.test_connection")

    @mcp.tool()
    def woo_test_connection(site: str = "retail") -> Any:
        """Probe a WooCommerce store's API connection (read-only).
        site: retail (main store) | dealer (dealer portal)."""
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.test_connection", {"site": site}
        )

    @mcp.tool()
    def woo_push_item(item_code: str, site: str = "retail", confirm: bool = False) -> Any:
        """Push (create or update) the WooCommerce product(s) for an Item.
        Per-serial firearms push every Active Serial No individually; non-firearm
        and uniform-price firearms push a single item-level product. For ONE gun
        use woo_push_serial instead. site: retail | dealer. Consequential
        — confirm=true."""
        require_confirm(f"woo_push_item {item_code} ({site})", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.push_item_now",
            {"item_code": item_code, "site": site},
        )

    @mcp.tool()
    def woo_delist_item(item_code: str, site: str = "retail", confirm: bool = False) -> Any:
        """Set the WooCommerce product for an Item to Draft + stock 0, hiding it
        from the shop immediately. site: retail | dealer. confirm=true."""
        require_confirm(f"woo_delist_item {item_code} ({site})", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.delist_item_now",
            {"item_code": item_code, "site": site},
        )

    @mcp.tool()
    def woo_reconcile(item_code: str, site: str = "retail", confirm: bool = False) -> Any:
        """Push the item-level product AND all Active Serial Nos for an Item in
        one call. Suitable for the initial listing of a per-serial firearm where
        everything needs to go live at once. site: retail | dealer. confirm=true."""
        require_confirm(f"woo_reconcile {item_code} ({site})", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.reconcile_now",
            {"item_code": item_code, "site": site},
        )

    @mcp.tool()
    def woo_push_serial(serial_no: str, site: str = "retail", confirm: bool = False) -> Any:
        """Push (create or update) the WooCommerce product for ONE firearm Serial No
        — the per-gun listing action (SKU item_code::serial). Prefer this over
        woo_push_item when only specific guns changed: woo_push_item pushes EVERY
        Active serial of that item. site: retail | dealer. confirm=true."""
        require_confirm(f"woo_push_serial {serial_no} ({site})", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.push_serial_now",
            {"serial_no": serial_no, "site": site},
        )

    @mcp.tool()
    def woo_delist_serial(serial_no: str, site: str = "retail", confirm: bool = False) -> Any:
        """Set ONE Serial No's WooCommerce product to Draft + stock 0, hiding that
        gun from the shop immediately. site: retail | dealer. confirm=true."""
        require_confirm(f"woo_delist_serial {serial_no} ({site})", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.delist_serial_now",
            {"serial_no": serial_no, "site": site},
        )

    @mcp.tool()
    def set_serial_title(serial_no: str, title: str) -> Any:
        """Set the per-gun WooCommerce listing title for one firearm (writes
        Serial No.item_name). A per-serial firearm's Woo product name is taken from
        Serial No.item_name, falling back to the shared Item name — so this gives one
        physical gun its own title instead of the model name shared by every serial.
        Not yet live: it takes effect on the next push (woo_push_serial / woo_push_item).
        The field is fetch_if_empty so the value persists once set."""
        return get_client().update_document("Serial No", serial_no, {"item_name": title})

    # ------------------------------------------------- GunBroker channel
    #
    # These reach GunBroker only through the POS: every one calls a whitelisted
    # method in ffl_integrations, which owns the credentials, the listing guards
    # and the sandbox/production choice. Nothing here talks to GunBroker
    # directly, and nothing here can pick an environment — that is
    # `GunBroker Settings.sandbox_mode` on the POS site this MCP is pointed at,
    # and it is the only thing that decides whether a push reaches the real
    # marketplace. Point the MCP at dev.localhost and you are on the sandbox.

    @mcp.tool()
    def gb_test_connection() -> Any:
        """Probe the GunBroker API connection + credentials (read-only).
        Reports which environment answered: the "sandbox" key in the reply is
        true for api.sandbox.gunbroker.com, false for the real marketplace.
        Read that key before doing anything else — it is how you find out which
        GunBroker this POS is wired to."""
        return get_client().call_method(
            "ffl_integrations.gunbroker.client_api.test_connection"
        )

    @mcp.tool()
    def gb_push_serial(serial_no: str, confirm: bool = False) -> Any:
        """List ONE firearm on GunBroker as a fixed-price Buy Now, priced from
        Serial No.sell_price. Publishes a gun for sale on a live marketplace —
        confirm=true.

        A refusal is a normal answer, not an error: guards come back as
        {"ok": false, "skipped": "<reason>", "message": "<why>"} — e.g. the gun
        is not in custody, has no price, is already listed, or is reserved by
        another channel. Read the message and fix the cause; re-calling will not
        change the answer. On success the reply carries "gb_item_id".

        To re-list a gun that somebody ended by hand, use the Serial No form —
        that lift is deliberately not available here."""
        require_confirm(f"gb_push_serial {serial_no}", confirm)
        return get_client().call_method(
            "ffl_integrations.gunbroker.client_api.push_serial_now",
            {"serial_no": serial_no},
        )

    @mcp.tool()
    def gb_end_listing(serial_no: str, confirm: bool = False,
                       reason: str | None = None) -> Any:
        """End ONE gun's GunBroker listing (e.g. it just sold at the counter).
        confirm=true. reason is optional and is recorded on the alert if the
        listing cannot be ended automatically.

        Check "confirmed" in the reply, not "ok". confirmed=true means GunBroker
        was read back and the listing is inactive. Anything else comes with
        "pending_manual": true and a "gb_url": the listing is STILL BUYABLE and a
        person has to end it on the GunBroker site — say so plainly rather than
        reporting the call as done."""
        require_confirm(f"gb_end_listing {serial_no}", confirm)
        return get_client().call_method(
            "ffl_integrations.gunbroker.client_api.end_listing_now",
            {"serial_no": serial_no, "reason": reason},
        )

    @mcp.tool()
    def gb_listing_status(serial_no: str) -> Any:
        """What this POS and GunBroker each think of ONE gun's listing
        (read-only). "state" is the POS view — unlisted | push_pending | listed |
        end_pending | sold | sold_unknown | ended — and "remote" is what
        GunBroker says right now, or null when there is no listing to ask about.
        Use this before pushing or ending anything if the two might disagree."""
        return get_client().call_method(
            "ffl_integrations.gunbroker.client_api.listing_status",
            {"serial_no": serial_no},
        )

    @mcp.tool()
    def atf_verify_ffl(ffl_number: str, confirm: bool = False) -> Any:
        """Live-verify an FFL number via ATF EZ Check and upsert an ATF FFL Record.
        Creates/updates a record, so requires confirm=true."""
        require_confirm(f"atf_verify_ffl {ffl_number}", confirm)
        return get_client().call_method(
            "ffl_integrations.atf.ez_check.lookup_and_create", {"ffl_number": ffl_number}
        )

    @mcp.tool()
    def firearms_in_stock(warehouse: str | None = None, manufacturer: str | None = None) -> Any:
        """Run the 'Firearms In Stock' report — in-stock firearms by serial, with
        acquisition source + FastBound link. Optional warehouse / manufacturer filter."""
        filters: dict[str, Any] = {}
        if warehouse:
            filters["warehouse"] = warehouse
        if manufacturer:
            filters["manufacturer"] = manufacturer
        return get_client().run_report("Firearms In Stock", filters or None)

    @mcp.tool()
    def find_item(query: str, limit: int = 10) -> Any:
        """Typeahead search for Items by barcode / item code / name."""
        return get_client().call_method(
            "ffl_core.api.receive_goods.search_items", {"query": query, "limit": limit}
        )

    # ---- A. read-only queries ------------------------------------------------

    @mcp.tool()
    def item_stock(item_codes: list[str] | str) -> Any:
        """Stock on hand per item: {item_code: qty} summed across all warehouses.
        Accepts a list, a JSON list, or a comma-separated string. Read-only."""
        return get_client().call_method(
            "ffl_core.api.item_admin.get_item_stock", {"item_codes": item_codes}
        )

    @mcp.tool()
    def available_serials(
        item_codes: list[str] | str, exclude_unavailable: bool = True
    ) -> Any:
        """In-stock Serial Nos per firearm item, each with its per-gun sell price:
        {item_code: [{serial, sell_price, ...}]}. Use for 'which units do we have
        of this model + at what price'. By default mirrors the POS picker: held /
        consigned-out / consignment-warehouse guns are EXCLUDED (they're not
        sellable over the counter). Pass exclude_unavailable=false for the RAW
        list — inventory audits that must also see consigned/held guns. Read-only."""
        return get_client().call_method(
            "ffl_core.firearm.available_serials_with_prices",
            {"item_codes": item_codes,
             "exclude_unavailable": 1 if exclude_unavailable else 0},
        )

    @mcp.tool()
    def rsr_catalog_search(query: str, limit: int = 10) -> Any:
        """Search the RSR distributor CATALOG (not local stock) by keyword / RSR
        stock # / UPC / MFG #. Use find_item for items already in this store.
        Read-only. Promote a catalog row to a sellable Item with promote_to_item."""
        return get_client().call_method(
            "ffl_integrations.rsr.search.search", {"query": query, "limit": limit}
        )

    @mcp.tool()
    def boundbook_reconcile(
        apply: bool = False, item_ids: list[str] | None = None, confirm: bool = False
    ) -> Any:
        """Reconcile in-stock firearm Serial Nos against the FastBound bound book —
        find guns FastBound shows as disposed but still Active in our inventory.
        apply=false (default) is a READ-ONLY dry run that just reports them.
        apply=true removes them from stock and requires confirm=true. Optional
        item_ids (FastBound item ids) narrows the scan."""
        if apply:
            require_confirm("boundbook_reconcile apply", confirm)
        return get_client().call_method(
            "ffl_integrations.fastbound.inventory_sync.sync_in_stock_from_boundbook",
            {"dry_run": 0 if apply else 1, "item_ids": item_ids},
        )

    # ---- B. receiving & stock adjustments (writes) ---------------------------

    @mcp.tool()
    def receive_goods(payload: dict, confirm: bool = False) -> Any:
        """Receive stock via the Receive Goods flow: creates + submits a Purchase
        Receipt; for firearms it also creates one FFL Acquisition per serial and
        pushes them to FastBound. payload mirrors the Receive Goods page:
        {supplier, source, warehouse, acquisition_source, items:[{item_code, qty,
        rate, serials:[...], manufacturer, model_name, caliber, firearm_type,
        importer, sell_price, service_need}], ...}. Consequential — confirm=true."""
        require_confirm("receive_goods", confirm)
        return get_client().call_method(
            "ffl_core.api.receive_goods.create_receive", {"payload": payload}
        )

    @mcp.tool()
    def add_stock(
        item_code: str, qty: float, warehouse: str | None = None,
        rate: float | None = None, remarks: str | None = None, confirm: bool = False,
    ) -> Any:
        """Add stock for a NON-serialized item (Material Receipt Stock Entry). Do NOT
        use for serial-tracked firearms — those go through receive_goods so the FFL
        flow runs. confirm=true."""
        require_confirm(f"add_stock {item_code}", confirm)
        return get_client().call_method(
            "ffl_core.api.item_admin.add_stock",
            {"item_code": item_code, "qty": qty, "warehouse": warehouse,
             "rate": rate, "remarks": remarks},
        )

    @mcp.tool()
    def set_stock(
        item_code: str, new_qty: float, warehouse: str | None = None,
        reason: str | None = None, confirm: bool = False,
    ) -> Any:
        """Set a NON-serialized item's on-hand qty to an absolute value via Stock
        Reconciliation (physical count / write-off). reason is recorded in the audit
        trail. confirm=true."""
        require_confirm(f"set_stock {item_code}", confirm)
        return get_client().call_method(
            "ffl_core.api.item_admin.set_stock",
            {"item_code": item_code, "new_qty": new_qty, "warehouse": warehouse,
             "reason": reason},
        )

    @mcp.tool()
    def toggle_service_need(serial: str, value: bool, confirm: bool = False) -> Any:
        """Set a firearm's 'Service Needed' (gunsmith) flag on its Serial No, opening
        or closing the gunsmith ToDo accordingly. confirm=true."""
        require_confirm(f"toggle_service_need {serial}", confirm)
        return get_client().call_method(
            "ffl_core.firearm.toggle_serial_service_need",
            {"serial": serial, "value": 1 if value else 0},
        )

    # ---- C. compliance / FastBound (writes) ----------------------------------

    @mcp.tool()
    def push_serial_to_fastbound(serial: str, confirm: bool = False) -> Any:
        """Push a post-acquisition per-unit correction (manufacturer / importer) for
        one already-booked firearm to FastBound, editing the bound-book item in place
        (PUT /Items/{id}). No-op if the gun isn't in FastBound yet. confirm=true."""
        require_confirm(f"push_serial_to_fastbound {serial}", confirm)
        return get_client().call_method(
            "ffl_integrations.fastbound.tasks.push_serial_to_fastbound", {"serial": serial}
        )

    @mcp.tool()
    def verify_supplier_ffl(supplier_name: str, confirm: bool = False) -> Any:
        """Live ATF EZ Check on a Supplier's FFL and update that supplier's
        verification status/fields. confirm=true (it writes to the Supplier)."""
        require_confirm(f"verify_supplier_ffl {supplier_name}", confirm)
        return get_client().call_method(
            "ffl_integrations.atf.ez_check_api.verify_supplier_ffl",
            {"supplier_name": supplier_name},
        )

    @mcp.tool()
    def reverify_all_ffls(confirm: bool = False) -> Any:
        """Re-run ATF EZ Check for EVERY FFL supplier on file (batch re-verification).
        confirm=true."""
        require_confirm("reverify_all_ffls", confirm)
        return get_client().call_method("ffl_integrations.atf.ez_check.re_verify_all")

    # ---- D. RSR promote (writes) ---------------------------------------------

    @mcp.tool()
    def promote_to_item(payload: dict, confirm: bool = False) -> Any:
        """Promote an RSR catalog row into a sellable Item (manufacturer / model /
        caliber / prices / images flow in from the catalog). payload mirrors the
        promote flow, e.g. {rsr_stock_number, item_code?, item_name?, ...}.
        confirm=true. Find candidates with rsr_catalog_search."""
        require_confirm("promote_to_item", confirm)
        return get_client().call_method(
            "ffl_integrations.rsr.promote.promote_to_item", {"payload": payload}
        )

    @mcp.tool()
    def backfill_from_rsr(
        item_codes: list[str] | str | None = None, confirm: bool = False
    ) -> Any:
        """Backfill manufacturer / model / caliber / etc. on existing Items from the
        RSR catalog (fills only empty fields, never overwrites). item_codes omitted =
        all RSR-linked items. confirm=true."""
        require_confirm("backfill_from_rsr", confirm)
        return get_client().call_method(
            "ffl_integrations.rsr.promote.backfill_from_rsr", {"item_codes": item_codes}
        )

    # ---- E. order / fulfillment queue (the Pending Order page's actions) ------

    @mcp.tool()
    def pending_orders() -> Any:
        """The Pending Order queue, counter + dealer rows: submitted firearm
        shipments that still need disposing, payment, or a ShipStation push.
        Web-shop rows come from pending_web_orders. Consignment fulfillment is
        NOT here — outbound consignments live in their own queue (see
        consignment_queue); this list explicitly excludes consignment invoices.
        Read-only."""
        return get_client().call_method(
            "ffl_core.api.manual_order.list_pending_dispositions"
        )

    @mcp.tool()
    def pending_web_orders() -> Any:
        """Paid WooCommerce web orders awaiting fulfillment — the source='woo'
        rows of the Pending Order page. Read-only."""
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.fulfillment.list_pending_web_orders"
        )

    @mcp.tool()
    def dispose_order(sales_invoice: str, confirm: bool = False) -> Any:
        """Dispose (ship) the firearms on a submitted counter/dealer order: books
        one FFL transfer disposition per not-yet-disposed serial; each disposition's
        on_submit issues the stock-out and pushes FastBound. Server blocks it while
        unpaid or the destination FFL is invalid; idempotent. VERIFY the destination
        FFL and serials first (the UI makes staff tick exactly that). confirm=true."""
        require_confirm(f"dispose_order {sales_invoice}", confirm)
        return get_client().call_method(
            "ffl_core.api.manual_order.dispose_order",
            {"sales_invoice": sales_invoice},
        )

    @mcp.tool()
    def dispose_web_order(woo_online_order: str, confirm: bool = False) -> Any:
        """Dispose the firearms on a paid Woo Online Order (web row). No ShipStation
        push here — the store's own WooCommerce plugin ships web orders. Idempotent
        per {serial, order}. confirm=true."""
        require_confirm(f"dispose_web_order {woo_online_order}", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.fulfillment.dispose_web_order",
            {"woo_online_order": woo_online_order},
        )

    @mcp.tool()
    def record_payment(
        sales_invoice: str, mode_of_payment: str, amount: float | None = None,
        transaction_number: str | None = None, confirm: bool = False,
    ) -> Any:
        """Record a later payment against a submitted, not-fully-paid Sales Invoice
        — books + submits a Payment Entry and returns the new balance. amount
        omitted = the full outstanding; mode_of_payment 'Zelle' requires
        transaction_number. confirm=true."""
        require_confirm(f"record_payment {sales_invoice}", confirm)
        return get_client().call_method(
            "ffl_core.api.manual_order.record_payment",
            {"sales_invoice": sales_invoice, "mode_of_payment": mode_of_payment,
             "amount": amount, "transaction_number": transaction_number},
        )

    @mcp.tool()
    def push_shipment(sales_invoice: str, confirm: bool = False) -> Any:
        """Push a submitted order to ShipStation so staff can buy the label there —
        the Pending Order 'Ship' action. Synchronous, idempotent, fails closed on an
        invalid FFL or unpaid order; independent of the Dispose step. confirm=true."""
        require_confirm(f"push_shipment {sales_invoice}", confirm)
        return get_client().call_method(
            "ffl_integrations.shipstation.api.push_shipment",
            {"sales_invoice": sales_invoice},
        )

    @mcp.tool()
    def mark_shipped_manually(sales_invoice: str, confirm: bool = False) -> Any:
        """Clear a DISPOSED order from the Pending Order queue without a ShipStation
        push (label bought elsewhere / integration off / FFL expired after dispose).
        Refuses while any firearm is undisposed. confirm=true."""
        require_confirm(f"mark_shipped_manually {sales_invoice}", confirm)
        return get_client().call_method(
            "ffl_core.api.manual_order.mark_shipped_manually",
            {"sales_invoice": sales_invoice},
        )

    @mcp.tool()
    def shipstation_test_connection() -> Any:
        """Probe the ShipStation API (GET /v2/carriers; read-only)."""
        return get_client().call_method(
            "ffl_integrations.shipstation.api.test_connection"
        )

    # ---- F. POS 4473 / transfers -----------------------------------------------

    @mcp.tool()
    def start_4473(invoice_name: str, serial_by_item_row: dict, confirm: bool = False) -> Any:
        """Kick off the ATF 4473 for a firearm POS/Sales Invoice: holds the invoice
        in Draft and opens a FastBound 4473 for the cashier to complete.
        serial_by_item_row maps invoice ITEM ROW name -> actual serial, e.g.
        {"a1b2c3d4": "SN123"}. Returns the FastBound URL. confirm=true."""
        require_confirm(f"start_4473 {invoice_name}", confirm)
        return get_client().call_method(
            "ffl_integrations.fastbound.pos_4473.start_4473_for_pos_invoice",
            {"invoice_name": invoice_name, "serial_by_item_row": serial_by_item_row},
        )

    @mcp.tool()
    def manager_override_4473(invoice_name: str, reason: str, confirm: bool = False) -> Any:
        """Manager force-complete a stuck firearm POS sale whose 4473 WAS genuinely
        completed in FastBound but never synced back (edited serial, deleted
        disposition, FastBound down). Mints the Retail Sale disposition(s) marked
        manual_override with WHO + WHY — auditable; does NOT push FastBound, so
        reconcile the bound book separately. reason is required. confirm=true."""
        require_confirm(f"manager_override_4473 {invoice_name}", confirm)
        return get_client().call_method(
            "ffl_integrations.fastbound.pos_4473.manager_override_4473",
            {"invoice_name": invoice_name, "reason": reason},
        )

    @mcp.tool()
    def start_transfer_4473(
        serials: list[str], fee_item: str, fee_amount: float, customer: str,
        pos_profile: str | None = None, invoice_name: str | None = None,
        confirm: bool = False,
    ) -> Any:
        """Start a customer-transfer 4473: builds the transfer POS Invoice server-side
        ($0 line per gun + one Transfer Fee line) and opens the FastBound 4473. Get
        fee_item and the default fee via frappe_run_method
        'ffl_core.firearm.get_transfer_config'. FFL-dealer customers are refused
        server-side (their 4473 gate doesn't apply). confirm=true."""
        require_confirm(f"start_transfer_4473 {customer}", confirm)
        return get_client().call_method(
            "ffl_integrations.fastbound.pos_4473.start_transfer_for_pos_invoice",
            {"serials": serials, "fee_item": fee_item, "fee_amount": fee_amount,
             "customer": customer, "pos_profile": pos_profile,
             "invoice_name": invoice_name},
        )

    # ---- G. consignment out (寄售) — the At Dealer queue's full lifecycle -------

    @mcp.tool()
    def consignment_queue(include_closed: bool = False) -> Any:
        """The outbound-consignment "At Dealer" queue — every unfinished
        Consignment Out (Draft / Shipped) as one card: dealer + shippability,
        ShipStation state, tracking, line pills, and the action gating the
        Dispose/Ship buttons read. An INDEPENDENT queue from pending_orders
        (which excludes consignment invoices). include_closed=true also returns
        Closed/Cancelled history. Read-only."""
        return get_client().call_method(
            "ffl_core.api.consignment_out.list_consignment_queue",
            {"include_closed": 1 if include_closed else 0},
        )

    @mcp.tool()
    def consignment_dealers() -> Any:
        """Every FFL-dealer Customer with its consignment shippability: FFL
        number, eZ-Check status, expiry, plus shippable/block_reason (the same
        gate ship_consignment_out enforces). Use before building a consignment.
        Read-only."""
        return get_client().call_method(
            "ffl_core.api.consignment_out.list_consignment_dealers"
        )

    @mcp.tool()
    def consignment_serials(
        item_code: str | None = None, search: str | None = None, limit: int = 50
    ) -> Any:
        """In-stock (Active) serials pickable for an outbound consignment,
        annotated with settlement/reference prices (cost = dealer price,
        msrp = retail) and — for blocked guns — why they can't be picked
        (blocked rows are returned greyed, not hidden). Filter by item_code
        and/or a search string. Read-only."""
        return get_client().call_method(
            "ffl_core.api.consignment_out.available_serials_for_consignment",
            {"item_code": item_code, "search": search, "limit": limit},
        )

    @mcp.tool()
    def consignment_dealer_orders() -> Any:
        """The post-sale consignment settlement queue: Sold lines whose
        settlement invoice isn't booked yet OR whose invoice isn't paid off.
        Failed rows sort first. Retry a failed settlement invoice with
        retry_consignment_invoice. Read-only."""
        return get_client().call_method(
            "ffl_core.api.consignment_orders.list_dealer_orders"
        )

    @mcp.tool()
    def create_consignment_out(payload: dict, confirm: bool = False) -> Any:
        """Build an outbound consignment to an FFL dealer. payload: {dealer,
        company?, notes?, dispose_now?, lines: [{item_code, serial, cost, msrp}]}.
        dispose_now=0 (default) saves a Draft (guns held, Woo delisted, dispose
        later from the queue); dispose_now=1 also disposes + best-effort
        ShipStation push immediately — if a gate blocks (expired dealer FFL) the
        build still succeeds as Draft with degraded=1. Find candidates with
        consignment_dealers / consignment_serials. Consequential — confirm=true."""
        require_confirm("create_consignment_out", confirm)
        return get_client().call_method(
            "ffl_core.api.consignment_out.create_consignment_out",
            {"payload": payload},
        )

    @mcp.tool()
    def ship_consignment_out(consignment_out: str, confirm: bool = False) -> Any:
        """Dispose (ship) every Draft line of a Consignment Out: books the
        FFL transfer disposition per gun, moves stock to the consignment
        warehouse, pushes FastBound. All lines are validated before any is
        mutated; re-running ships 0 (idempotent). Server blocks on an invalid
        dealer FFL. VERIFY the dealer + serials first. confirm=true."""
        require_confirm(f"ship_consignment_out {consignment_out}", confirm)
        return get_client().call_method(
            "ffl_core.api.consignment_out.ship_consignment_out",
            {"consignment_out": consignment_out},
        )

    @mcp.tool()
    def push_consignment_shipment(consignment_out: str, confirm: bool = False) -> Any:
        """Push a DISPOSED Consignment Out to ShipStation so staff can buy the
        outbound label — the At Dealer queue's Ship action. Synchronous,
        idempotent, persists nothing on API failure (safe to retry). Independent
        of the Dispose step. confirm=true."""
        require_confirm(f"push_consignment_shipment {consignment_out}", confirm)
        return get_client().call_method(
            "ffl_integrations.shipstation.api.push_consignment_shipment",
            {"consignment_out": consignment_out},
        )

    @mcp.tool()
    def mark_consignment_shipped(
        consignment_out: str, tracking_number: str | None = None,
        carrier: str | None = None, confirm: bool = False,
    ) -> Any:
        """Clear a DISPOSED consignment's Ship step without a ShipStation push
        (label bought elsewhere / integration off / dealer FFL expired after
        dispose) — the consignment twin of mark_shipped_manually. Optional
        tracking_number / carrier hand-record the label so the dealer portal
        shows it. confirm=true."""
        require_confirm(f"mark_consignment_shipped {consignment_out}", confirm)
        return get_client().call_method(
            "ffl_core.api.consignment_out.mark_consignment_shipped_manually",
            {"consignment_out": consignment_out,
             "tracking_number": tracking_number, "carrier": carrier},
        )

    @mcp.tool()
    def retry_consignment_invoice(line: str, confirm: bool = False) -> Any:
        """Retry the settlement Sales Invoice for a Sold consignment line whose
        automatic booking failed (error log / total mismatch / dealer FFL
        expired at submit) — the Dealer Orders queue's Retry Invoice action.
        line = the Consignment Out Line name (see consignment_dealer_orders).
        To UNDO a booked settlement, cancel that settlement Sales Invoice
        instead (frappe_cancel_document) — the cancel hook reopens the parent.
        confirm=true."""
        require_confirm(f"retry_consignment_invoice {line}", confirm)
        return get_client().call_method(
            "ffl_core.api.consignment_orders.create_consignment_invoice_now",
            {"line": line},
        )

    @mcp.tool()
    def return_consignment_lines(
        consignment_out: str, lines: list[str],
        to_warehouse: str | None = None, confirm: bool = False,
    ) -> Any:
        """Take unsold consigned guns BACK from the dealer: books a real FFL
        re-acquisition per gun (pushed to FastBound by its own hook) and moves
        stock back to the main (or given) warehouse. lines = Consignment Out
        Line names. confirm=true."""
        require_confirm(f"return_consignment_lines {consignment_out}", confirm)
        return get_client().call_method(
            "ffl_core.api.consignment_out.return_consignment_lines",
            {"consignment_out": consignment_out, "lines": lines,
             "to_warehouse": to_warehouse},
        )

    @mcp.tool()
    def cancel_consignment(
        consignment_out: str, reason: str, line: str | None = None,
        confirm: bool = False,
    ) -> Any:
        """Cancel a consignment that should never have happened. With line:
        cancel ONE shipped line ("the gun never left the store" — undoes the
        disposition; only reachable pre-invoice). Without line: cancel the whole
        DRAFT document (never-shipped staging record; books/moves nothing).
        reason is required and recorded. confirm=true."""
        require_confirm(f"cancel_consignment {consignment_out}", confirm)
        reason = require_reason(f"cancel_consignment {consignment_out}", reason)
        if line:
            return get_client().call_method(
                "ffl_core.api.consignment_out.cancel_consignment_line",
                {"consignment_out": consignment_out, "line": line, "reason": reason},
            )
        return get_client().call_method(
            "ffl_core.api.consignment_out.cancel_consignment_out",
            {"consignment_out": consignment_out, "reason": reason},
        )

    @mcp.tool()
    def update_consignment_prices(
        consignment_out: str, prices: dict, confirm: bool = False,
    ) -> Any:
        """Edit the per-consignment price snapshot on At Dealer lines — the
        queue's "Edit prices" dialog (PR #224). prices: {line_name: {"cost":
        required > 0, "msrp": tri-state}} — omit the "msrp" key to keep the
        stored MSRP, send "" / null to clear it, anything else must be > 0.
        Writes ONLY this shipment's line snapshot ("Dealer Price" + MSRP),
        never Serial No / Item masters; settlement and the dealer portal read
        the same snapshot, so both follow automatically. Server gates: line
        must be At Dealer with no booked settlement invoice; the whole batch
        is validated before anything is written (one bad line rejects all).
        Line names come from consignment_queue. confirm=true."""
        require_confirm(f"update_consignment_prices {consignment_out}", confirm)
        return get_client().call_method(
            "ffl_core.api.consignment_out.update_consignment_line_prices",
            {"consignment_out": consignment_out, "prices": prices},
        )

    # ---- H. counter-order cancel ---------------------------------------------

    @mcp.tool()
    def cancel_order(
        sales_invoice: str, reason: str, refund_mode: str | None = None,
        refund_reference: str | None = None, confirm: bool = False,
    ) -> Any:
        """Cancel a submitted counter/dealer transfer order — the Pending Order
        page's Cancel Order action. Cascades safely: cancels the invoice (its
        hooks reverse the dispositions → stock back in → FastBound delete
        queued), cancels linked Sales Orders, voids the ShipStation order, and
        books a refund Payment Entry for whatever was actually paid
        (refund_mode/refund_reference when a refund is due). reason is required
        and recorded. confirm=true."""
        require_confirm(f"cancel_order {sales_invoice}", confirm)
        reason = require_reason(f"cancel_order {sales_invoice}", reason)
        return get_client().call_method(
            "ffl_core.api.manual_order.cancel_order",
            {"sales_invoice": sales_invoice, "reason": reason,
             "refund_mode": refund_mode, "refund_reference": refund_reference},
        )

    # ---- I. file upload ----------------------------------------------------------

    @mcp.tool()
    def upload_attachment(
        file_path: str, doctype: str | None = None, name: str | None = None,
        fieldname: str | None = None, is_private: bool = True,
    ) -> Any:
        """Upload a LOCAL file to the POS as a File document, optionally attached to
        a document (doctype + name) and/or set into its Attach field (fieldname).
        Returns the File doc incl. file_url. Default is_private=true — product
        photos that WooCommerce must sideload need is_private=false. For bulk
        photo+gallery imports prefer the firearm-listing-import script (it resizes
        images first; oversized originals break the Woo push)."""
        return get_client().upload_file(
            file_path, doctype=doctype, docname=name,
            fieldname=fieldname, is_private=is_private,
        )
