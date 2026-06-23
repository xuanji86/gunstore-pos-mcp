"""Curated convenience tools — one call for the frequent settings / sync / report
ops. Thin wrappers over the generic backbone + the apps' whitelisted methods."""
from __future__ import annotations

from typing import Any

from ..frappe_client import get_client
from ..safety import require_confirm, strip_passwords, stripped_note

_SETTINGS = {
    "ffl": "FFL Settings",
    "fastbound": "FastBound Settings",
    "rsr": "RSR Settings",
    "payroc": "Payroc Settings",
    "woocommerce": "WooCommerce Settings",
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
        """Read an integration's Settings. which: ffl | fastbound | rsr | payroc | woocommerce.
        Password fields are never returned by Frappe."""
        dt = _resolve(which)
        return get_client().get_document(dt, dt)

    @mcp.tool()
    def update_settings(which: str, values: dict) -> Any:
        """Update an integration's Settings. which: ffl | fastbound | rsr | payroc | woocommerce.
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
    def woo_test_connection() -> Any:
        """Probe the WooCommerce API connection (read-only)."""
        return get_client().call_method("ffl_woo_sync.woocommerce.client_api.test_connection")

    @mcp.tool()
    def woo_push_item(item_code: str, confirm: bool = False) -> Any:
        """Push (create or update) the WooCommerce product(s) for an Item.
        Per-serial firearms push every Active Serial No individually; non-firearm
        and uniform-price firearms push a single item-level product. Consequential
        — confirm=true."""
        require_confirm(f"woo_push_item {item_code}", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.push_item_now",
            {"item_code": item_code},
        )

    @mcp.tool()
    def woo_delist_item(item_code: str, confirm: bool = False) -> Any:
        """Set the WooCommerce product for an Item to Draft + stock 0, hiding it
        from the shop immediately. confirm=true."""
        require_confirm(f"woo_delist_item {item_code}", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.delist_item_now",
            {"item_code": item_code},
        )

    @mcp.tool()
    def woo_reconcile(item_code: str, confirm: bool = False) -> Any:
        """Push the item-level product AND all Active Serial Nos for an Item in
        one call. Suitable for the initial listing of a per-serial firearm where
        everything needs to go live at once. confirm=true."""
        require_confirm(f"woo_reconcile {item_code}", confirm)
        return get_client().call_method(
            "ffl_woo_sync.woocommerce.client_api.reconcile_now",
            {"item_code": item_code},
        )

    @mcp.tool()
    def set_serial_title(serial_no: str, title: str) -> Any:
        """Set the per-gun WooCommerce listing title for one firearm (writes
        Serial No.item_name). A per-serial firearm's Woo product name is taken from
        Serial No.item_name, falling back to the shared Item name — so this gives one
        physical gun its own title instead of the model name shared by every serial.
        Not yet live: it takes effect on the next push (push_serial_now / woo_push_item).
        The field is fetch_if_empty so the value persists once set."""
        return get_client().update_document("Serial No", serial_no, {"item_name": title})

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
    def available_serials(item_codes: list[str] | str) -> Any:
        """In-stock Serial Nos per firearm item, each with its per-gun sell price:
        {item_code: [{serial, sell_price, ...}]}. Use for 'which units do we have
        of this model + at what price'. Read-only."""
        return get_client().call_method(
            "ffl_core.firearm.available_serials_with_prices", {"item_codes": item_codes}
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
