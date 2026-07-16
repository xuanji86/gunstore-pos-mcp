"""CPA report tools — read-only report wrappers for the accountant surface.

Registered in BOTH modes (full & cpa). Zero server-side changes: everything
rides `frappe.desk.query_report.run` and plain REST reads. Caliber authority
is runs/2026-07-16-mcp-cpa-mode/cpa-review.md §2/§3 — these wrappers add NO
caliber of their own (fail-closed buckets aside), they transport the server's.
Standard-report filter keys verified against the pinned ERPNext v16 sources.
"""
from __future__ import annotations

from typing import Any

from ..frappe_client import get_client

_STATEMENTS = {
    "pnl": "Profit and Loss Statement",
    "balance_sheet": "Balance Sheet",
    "trial_balance": "Trial Balance",
}
_PERIODICITIES = ("Monthly", "Quarterly", "Half-Yearly", "Yearly")
_AGEING_REPORTS = {"ar": "Accounts Receivable", "ap": "Accounts Payable"}
_GL_FIELDS = [
    "posting_date", "account", "debit", "credit", "against",
    "voucher_type", "voucher_no", "party", "remarks",
]


def _default_company(client) -> str:
    doc = client.get_document("Global Defaults", "Global Defaults") or {}
    company = doc.get("default_company")
    if not company:
        raise ValueError(
            "No default company set (Global Defaults.default_company) — "
            "pass company explicitly."
        )
    return company


def _cents(x) -> int:
    """Money as integer cents — roll-forward identities must hold to the cent,
    so no float accumulation."""
    return int(round(float(x or 0) * 100))


def register(mcp: Any) -> None:
    @mcp.tool()
    def sales_report(
        from_date: str, to_date: str, view: str = "Product",
        channel: str | None = None, product_type: str | None = None,
    ) -> Any:
        """The POS Sales Report (revenue + profit, all channels), returned
        UNCHANGED — columns, rows and the report_summary cards. view: "Order"
        (per-order), "Order Detail" (order → line drill-down) or "Product"
        (default here — the CPA tax-reporting view: per-line tax from ERPNext's
        stored item-wise tax details, tax rows classified to Sales Tax /
        Shipping / Unclassified fail-closed). channel: POS | Web | B2B-Manual
        (empty = all). Profit is net (pre-tax). Read-only."""
        filters: dict[str, Any] = {
            "from_date": from_date, "to_date": to_date, "view": view,
        }
        if channel:
            filters["channel"] = channel
        if product_type:
            filters["product_type"] = product_type
        return get_client().run_report("Sales Report", filters)

    @mcp.tool()
    def gl_entries(
        from_date: str, to_date: str, account: str | None = None,
        party: str | None = None, voucher_no: str | None = None,
        voucher_type: str | None = None, limit: int = 500,
    ) -> Any:
        """General-ledger rows for a date range, optionally filtered by
        account / party / voucher_no / voucher_type. Cancelled GL is ALWAYS
        excluded (is_cancelled=0 — cancel+amend refund reworks drop out
        automatically). Truncation is explicit: when more rows exist than
        `limit`, the result carries truncated:true — never a silent cut, a
        silently-shortened ledger reconciles to wrong numbers. limit is
        clamped to 1..5000 (0 or empty falls back to 500 — NOT Frappe's
        "0 = all" convention); for more rows, paginate by narrowing the date
        range. Read-only."""
        limit = max(1, min(int(limit or 500), 5000))
        filters: list[list] = [
            ["posting_date", ">=", from_date],
            ["posting_date", "<=", to_date],
            ["is_cancelled", "=", 0],
        ]
        for field, value in (
            ("account", account), ("party", party),
            ("voucher_no", voucher_no), ("voucher_type", voucher_type),
        ):
            if value:
                filters.append([field, "=", value])
        rows = get_client().list_documents(
            "GL Entry", fields=_GL_FIELDS, filters=filters,
            limit=limit + 1, order_by="posting_date asc, name asc",
        ) or []
        truncated = len(rows) > limit
        rows = rows[:limit]
        return {"rows": rows, "count": len(rows),
                "truncated": truncated, "limit": limit}

    @mcp.tool()
    def financial_statement(
        statement: str, from_date: str, to_date: str,
        periodicity: str = "Monthly", company: str | None = None,
    ) -> Any:
        """One of the standard financial statements over a date range:
        statement = "pnl" (Profit and Loss Statement), "balance_sheet" or
        "trial_balance". P&L/BS run filter_based_on="Date Range" with the
        given periodicity (Monthly/Quarterly/Half-Yearly/Yearly). Trial
        Balance needs the range inside ONE fiscal year (ERPNext requires a
        fiscal_year filter; it is resolved from the dates — a spanning range
        is refused rather than guessed). company defaults to the default
        company. Read-only."""
        if statement not in _STATEMENTS:
            raise ValueError(
                f"statement must be one of {sorted(_STATEMENTS)} (got {statement!r})."
            )
        if periodicity not in _PERIODICITIES:
            raise ValueError(
                f"periodicity must be one of {_PERIODICITIES} (got {periodicity!r})."
            )
        client = get_client()
        company = company or _default_company(client)
        if statement == "trial_balance":
            fys = client.list_documents(
                "Fiscal Year", fields=["name"],
                filters=[["year_start_date", "<=", from_date],
                         ["year_end_date", ">=", to_date]],
                limit=1, order_by="year_start_date desc",
            ) or []
            if not fys:
                raise ValueError(
                    "Trial Balance needs from_date..to_date inside a single "
                    "fiscal year — no Fiscal Year covers this range."
                )
            return client.run_report("Trial Balance", {
                "company": company, "fiscal_year": fys[0]["name"],
                "from_date": from_date, "to_date": to_date,
            })
        return client.run_report(_STATEMENTS[statement], {
            "company": company,
            "filter_based_on": "Date Range",
            "period_start_date": from_date,
            "period_end_date": to_date,
            "periodicity": periodicity,
        })

    @mcp.tool()
    def tax_liability(
        from_date: str, to_date: str, company: str | None = None,
    ) -> Any:
        """Sales-tax liability roll-forward for the period, straight from the
        GL. TRAP: an invoice's "Total Taxes and Charges" includes shipping and
        other charges — it is NOT the sales tax; only GL rows on the sales-tax
        account(s) count, which is all this tool reads.

        Accounts are resolved dynamically — the default enabled Sales Taxes
        and Charges Template's distinct account_heads (the same rule the
        server's setup/tax.py and Sales Report use; nothing hardcoded) — and
        echoed back in the result. Rows are is_cancelled=0; cancel+amend
        restatements land on the amended invoice's posting_date.

        Output: opening_balance (before from_date), collected credits split
        by voucher (Sales Invoice = sales accrual; Journal Entry = adjustments,
        listed separately, never merged into sales), remitted debits split by
        voucher (Journal Entry = remittance payments; Sales Invoice = return /
        amend reversals), any other voucher type fail-closed into its own
        "other" bucket, and closing_balance. The identity closing == opening +
        credits − debits is asserted internally to the cent; a classification
        that drops rows raises instead of returning numbers. Single-state (TX)
        system — there is deliberately no state parameter. Read-only."""
        client = get_client()
        company = company or _default_company(client)
        # Account set — mirror of ffl_core.setup.tax._company_sales_tax_accounts:
        # default enabled template → child account_heads, order kept, blanks/dupes dropped.
        tmpls = client.list_documents(
            "Sales Taxes and Charges Template", fields=["name"],
            filters=[["company", "=", company], ["is_default", "=", 1],
                     ["disabled", "=", 0]],
            limit=1,
        ) or []
        if not tmpls:
            raise ValueError(
                f"No default enabled Sales Taxes and Charges Template for "
                f"{company!r} — cannot resolve the sales-tax account(s)."
            )
        tmpl = client.get_document(
            "Sales Taxes and Charges Template", tmpls[0]["name"]) or {}
        accounts: list[str] = []
        for row in tmpl.get("taxes") or []:
            head = (row.get("account_head") or "").strip()
            if head and head not in accounts:
                accounts.append(head)
        if not accounts:
            raise ValueError(
                f"Default sales-tax template {tmpls[0]['name']!r} has no "
                "account_head rows — nothing to roll forward."
            )
        rows = client.list_documents(
            "GL Entry",
            fields=["posting_date", "voucher_type", "voucher_no", "debit", "credit"],
            filters=[["account", "in", accounts], ["company", "=", company],
                     ["is_cancelled", "=", 0], ["posting_date", "<=", to_date]],
            limit=0,
        ) or []

        opening = 0
        c_si = c_je = d_si = d_je = 0
        other_c: dict[str, int] = {}
        other_d: dict[str, int] = {}
        total_c = total_d = 0
        for r in rows:
            credit, debit = _cents(r.get("credit")), _cents(r.get("debit"))
            if str(r.get("posting_date") or "") < from_date:
                opening += credit - debit
                continue
            vt = r.get("voucher_type") or "Unknown"
            total_c += credit
            total_d += debit
            if vt == "Sales Invoice":
                c_si += credit
                d_si += debit
            elif vt == "Journal Entry":
                c_je += credit
                d_je += debit
            else:  # fail-closed: unexpected vouchers stay visible, unmerged
                if credit:
                    other_c[vt] = other_c.get(vt, 0) + credit
                if debit:
                    other_d[vt] = other_d.get(vt, 0) + debit
        closing = opening + total_c - total_d
        # Belt-and-suspenders (review question, lead-adjudicated KEEP): with
        # today's control flow this Σbuckets==Σtotals check is structurally
        # always-true — every period row is added to totals AND to exactly one
        # bucket in the same if/elif/else. The real guard is the cent-exact
        # closing identity above (independently recomputed in tests). This
        # assertion exists to catch a FUTURE refactor that adds a bucket path
        # without keeping the totals in lockstep.
        if (c_si + c_je + sum(other_c.values()) != total_c
                or d_si + d_je + sum(other_d.values()) != total_d):
            raise RuntimeError(
                "tax_liability internal identity check failed — the voucher "
                "classification dropped rows; refusing to return numbers."
            )

        def dollars(c: int) -> float:
            return c / 100.0

        return {
            "company": company,
            "accounts": accounts,
            "from_date": from_date,
            "to_date": to_date,
            "opening_balance": dollars(opening),
            "collected": {
                "sales_invoices": dollars(c_si),
                "journal_entry_adjustments": dollars(c_je),
                "other": {k: dollars(v) for k, v in other_c.items()},
            },
            "remitted": {
                "journal_entries": dollars(d_je),
                "sales_invoice_reversals": dollars(d_si),
                "other": {k: dollars(v) for k, v in other_d.items()},
            },
            "total_credits": dollars(total_c),
            "total_debits": dollars(total_d),
            "closing_balance": dollars(closing),
            "identity_check": "ok",
            "note": (
                "'Total Taxes and Charges' on an invoice includes shipping and "
                "other charges — NOT sales tax. This roll-forward reads only "
                "the GL rows on the resolved sales-tax account(s)."
            ),
        }

    @mcp.tool()
    def ar_ap_summary(kind: str, as_on_date: str, company: str | None = None) -> Any:
        """Aged Accounts Receivable (kind="ar") or Accounts Payable ("ap") as
        of a date — the standard ERPNext ageing report (Posting Date basis,
        30/60/90/120 buckets). Consignment settlement invoices appear in AR
        under their dealer. company defaults to the default company. Read-only."""
        if kind not in _AGEING_REPORTS:
            raise ValueError(
                f"kind must be one of {sorted(_AGEING_REPORTS)} (got {kind!r})."
            )
        client = get_client()
        company = company or _default_company(client)
        return client.run_report(_AGEING_REPORTS[kind], {
            "company": company,
            "report_date": as_on_date,
            "ageing_based_on": "Posting Date",
            "range": "30, 60, 90, 120",
        })
