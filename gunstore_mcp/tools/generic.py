"""Generic Frappe backbone tools — these cover EVERY doctype and whitelisted
method, present and future. Curated tools (curated.py) are thin sugar on top."""
from __future__ import annotations

import re
from typing import Any

from ..frappe_client import get_client
from ..safety import (
    WriteRefused,
    check_write_allowed,
    require_confirm,
    strip_passwords,
    stripped_note,
)

# A method is confirm-gated when its FINAL path segment matches a destructive /
# consequential verb (matching the segment, not the whole dotted path, avoids
# gating on a module name). The second row is this domain's own high-consequence
# verbs: dispose (bound-book disposition + stock-out), push (live Woo/FastBound/
# ShipStation writes), charge (card terminal), consolidate (posts stock + SI).
# The third row covers the consignment-out / onboarding lifecycle (#196–#222):
# ship (dispose + stock-out), sold/receive (mark_sold mints the settlement
# invoice; receive also gates create_receive's Purchase-Receipt + FastBound
# push), return (books a real re-acquisition), settle, onboard (creates a
# portal login + customer). Over-gating a rare read (get_receive_sources) is
# the accepted cost — the gate fails safe.
_DESTRUCTIVE_METHOD = re.compile(
    r"(delete|destroy|drop|truncate|wipe|reset|purge|cancel|void|refund"
    r"|force|remove|rename|bulk|import"
    r"|dispose|push|charge|consolidate"
    r"|ship|settle|return|onboard|receive|sold)",
    re.I,
)

# High-consequence whitelisted writes whose LAST path segment carries no
# destructive verb, so the regex above cannot see them (review q2, run
# 2026-07-16-mcp-cpa-mode). Gated by EXACT dotted name — list names one by
# one, no prefixes or wildcards. "update"/"create" are deliberately not regex
# verbs (they would over-gate half of Frappe's read-adjacent surface):
# update_order and update_consignment_line_prices rewrite money fields on
# live orders; create_consignment_out with dispose_now=1 books dispositions
# and moves stock, well beyond what "create" implies.
_ALWAYS_CONFIRM_METHODS = {
    "ffl_core.api.manual_order.update_order",
    "ffl_core.api.consignment_out.update_consignment_line_prices",
    "ffl_core.api.consignment_out.create_consignment_out",
}

# Frappe globally whitelists these generic mutators at /api/method — reaching
# them via frappe_run_method would bypass the structured CRUD guards (denylist,
# password-strip, confirm). Refuse them and point at the guarded tools.
_BLOCKED_GENERIC_METHODS = {
    "frappe.client.set_value",
    "frappe.client.insert",
    "frappe.client.insert_many",
    "frappe.client.save",
    "frappe.client.submit",
    "frappe.client.cancel",
    "frappe.client.delete",
    "frappe.client.delete_doc",
    "frappe.client.bulk_update",
    "frappe.client.rename_doc",
    "frappe.rename_doc.rename_doc",
    "frappe.model.rename_doc.rename_doc",
}


def register(mcp: Any) -> None:
    @mcp.tool()
    def frappe_list_documents(
        doctype: str,
        fields: list[str] | None = None,
        filters: list | dict | None = None,
        limit: int = 20,
        start: int = 0,
        order_by: str | None = None,
    ) -> Any:
        """List documents of any doctype.

        filters are Frappe-style: a list of [field, operator, value] (e.g.
        [["is_firearm","=",1],["status","=","Active"]]) or a simple {field: value}
        dict. limit defaults to 20; pass limit=0 for all rows. Call
        frappe_describe_doctype first if unsure of field names."""
        return get_client().list_documents(
            doctype, fields=fields, filters=filters, limit=limit, start=start, order_by=order_by
        )

    @mcp.tool()
    def frappe_get_document(doctype: str, name: str) -> Any:
        """Fetch one document by name. For a Single/Settings doctype, name == doctype
        (e.g. doctype='RSR Settings', name='RSR Settings')."""
        return get_client().get_document(doctype, name)

    @mcp.tool()
    def frappe_describe_doctype(doctype: str) -> Any:
        """List a doctype's fields (custom fields included): fieldname, label,
        fieldtype, options, reqd. Fields flagged is_password=true can never be
        written through this MCP — set those in Desk."""
        out = []
        for f in get_client().describe_doctype(doctype):
            ft = f.get("fieldtype")
            if ft in ("Section Break", "Column Break", "Tab Break", "HTML", "Button"):
                continue
            out.append({
                "fieldname": f.get("fieldname"),
                "label": f.get("label"),
                "fieldtype": ft,
                "options": f.get("options"),
                "reqd": f.get("reqd"),
                "is_password": ft == "Password",
            })
        return out

    @mcp.tool()
    def frappe_create_document(doctype: str, values: dict) -> Any:
        """Create a document. Credential/password fields are stripped automatically."""
        check_write_allowed(doctype)
        clean, stripped = strip_passwords(doctype, values)
        return stripped_note(get_client().create_document(doctype, clean), stripped)

    @mcp.tool()
    def frappe_update_document(doctype: str, name: str, values: dict) -> Any:
        """Update fields on a document. Credential/password fields are stripped
        automatically (set those in Desk)."""
        check_write_allowed(doctype)
        clean, stripped = strip_passwords(doctype, values)
        return stripped_note(get_client().update_document(doctype, name, clean), stripped)

    @mcp.tool()
    def frappe_delete_document(doctype: str, name: str, confirm: bool = False) -> Any:
        """Delete a document. Requires confirm=true. For firearms/Items prefer
        frappe_run_method('ffl_core.api.item_admin.force_delete', ...) which preserves
        the A&D audit trail."""
        check_write_allowed(doctype)
        require_confirm(f"delete {doctype} {name}", confirm)
        get_client().delete_document(doctype, name)
        return {"deleted": name, "doctype": doctype}

    @mcp.tool()
    def frappe_submit_document(doctype: str, name: str, confirm: bool = False) -> Any:
        """Submit a draft document (docstatus 0 -> 1). Requires confirm=true —
        submitting can fire side effects (e.g. a FastBound push on FFL Acquisition)."""
        check_write_allowed(doctype)
        require_confirm(f"submit {doctype} {name}", confirm)
        return get_client().submit_document(doctype, name)

    @mcp.tool()
    def frappe_cancel_document(doctype: str, name: str, confirm: bool = False) -> Any:
        """Cancel a submitted document (docstatus 1 -> 2). Requires confirm=true."""
        check_write_allowed(doctype)
        require_confirm(f"cancel {doctype} {name}", confirm)
        return get_client().cancel_document(doctype, name)

    @mcp.tool()
    def frappe_run_method(method: str, kwargs: dict | None = None, confirm: bool = False) -> Any:
        """Call any whitelisted server method by dotted path, e.g.
        'ffl_integrations.rsr.tasks.sync_catalog_now'. Generic Frappe mutators
        (frappe.client.set_value/insert/save/delete/bulk_update/...) are refused —
        use the structured frappe_*_document tools, which enforce the guards.
        Methods whose name implies a destructive action — or that are on the
        explicit high-consequence list — require confirm=true."""
        if method in _BLOCKED_GENERIC_METHODS:
            raise WriteRefused(
                f"Refused: '{method}' is a generic Frappe mutator that would bypass the "
                "MCP write guards (denylist, password-strip, confirm). Use the structured "
                "tools instead: frappe_create_document / frappe_update_document / "
                "frappe_delete_document / frappe_submit_document / frappe_cancel_document."
            )
        if (method in _ALWAYS_CONFIRM_METHODS
                or _DESTRUCTIVE_METHOD.search(method.rsplit(".", 1)[-1])):
            require_confirm(f"run_method {method}", confirm)
        return get_client().call_method(method, kwargs)

    @mcp.tool()
    def frappe_run_report(report_name: str, filters: dict | list | None = None) -> Any:
        """Run a Script/Query Report (e.g. 'Firearms In Stock') and return its
        columns + result rows."""
        return get_client().run_report(report_name, filters)
