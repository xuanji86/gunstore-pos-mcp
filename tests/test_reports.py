"""Unit tests for the CPA report tools (tools/reports.py).

Thin wrappers over run_report / REST reads; caliber authority is
runs/2026-07-16-mcp-cpa-mode/cpa-review.md §2/§3. All mocked — no network.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from gunstore_mcp.tools import reports


class FakeClient:
	"""Recorder + programmable canned responses."""

	def __init__(self):
		self.calls = []
		self.canned = {}

	def run_report(self, name, filters=None):
		self.calls.append(("run_report", name, filters))
		return self.canned.get(("run_report", name),
			{"columns": [], "result": [], "report_summary": [{"label": "x"}]})

	def list_documents(self, doctype, **kw):
		self.calls.append(("list_documents", doctype, kw))
		hit = self.canned.get(("list", doctype))
		return hit(kw) if callable(hit) else (hit if hit is not None else [])

	def get_document(self, doctype, name):
		self.calls.append(("get_document", doctype, name))
		return self.canned.get(("get", doctype, name), {})


class FakeMCP:
	def __init__(self):
		self.tools = {}

	def tool(self, *a, **k):
		def deco(fn):
			self.tools[fn.__name__] = fn
			return fn
		return deco


GLOBAL_DEFAULTS = ("get", "Global Defaults", "Global Defaults")


class ReportTools(unittest.TestCase):
	def setUp(self):
		mcp = FakeMCP()
		reports.register(mcp)
		self.tools = mcp.tools
		self.client = FakeClient()
		self.client.canned[GLOBAL_DEFAULTS] = {"default_company": "Old Steel Arsenal"}
		self._patch = patch.object(reports, "get_client", return_value=self.client)
		self._patch.start()
		self.addCleanup(self._patch.stop)

	# ---------------------------------------------------------- registration

	def test_exactly_six_report_tools(self):
		self.assertEqual(set(self.tools), {
			"sales_report", "inventory_receipts", "gl_entries", "financial_statement",
			"tax_liability", "ar_ap_summary",
		})

	# ---------------------------------------------------- inventory_receipts

	def test_inventory_receipts_passthrough_defaults_to_units(self):
		canned = {"columns": [1], "result": [2], "report_summary": [{"label": "Cost Received"}]}
		self.client.canned[("run_report", "Inventory Receipts")] = canned
		out = self.tools["inventory_receipts"]("2026-08-01", "2026-08-31")
		self.assertIs(out, canned)  # 原样透传,卡片不得丢
		self.assertEqual(self.client.calls[-1], ("run_report", "Inventory Receipts", {
			"from_date": "2026-08-01", "to_date": "2026-08-31", "view": "Units",
		}))

	def test_inventory_receipts_optional_filters_and_include_flags(self):
		self.tools["inventory_receipts"]("2026-08-01", "2026-08-31", view="Summary",
			category="Firearm", receipt_class="Transfer", supplier="RSR Group",
			include_transfers=True, include_custody=True)
		self.assertEqual(self.client.calls[-1][2], {
			"from_date": "2026-08-01", "to_date": "2026-08-31", "view": "Summary",
			"category": "Firearm", "receipt_class": "Transfer", "supplier": "RSR Group",
			"include_transfers": 1, "include_custody": 1,
		})
		# False flags are NOT sent — the server's default (hidden) must not be
		# overridden by an explicit 0 that a later server version might read differently.
		self.tools["inventory_receipts"]("2026-08-01", "2026-08-31")
		self.assertNotIn("include_transfers", self.client.calls[-1][2])

	# ---------------------------------------------------------- sales_report

	def test_sales_report_passthrough_keeps_report_summary(self):
		canned = {"columns": [1], "result": [2], "report_summary": [{"label": "Net"}]}
		self.client.canned[("run_report", "Sales Report")] = canned
		out = self.tools["sales_report"]("2026-07-01", "2026-07-31")
		self.assertIs(out, canned)  # 原样透传,不得丢 report_summary
		self.assertEqual(self.client.calls[-1], ("run_report", "Sales Report", {
			"from_date": "2026-07-01", "to_date": "2026-07-31", "view": "Product",
		}))

	def test_sales_report_optional_filters(self):
		self.tools["sales_report"]("2026-07-01", "2026-07-31", view="Order Detail",
			channel="Web", product_type="Firearms")
		self.assertEqual(self.client.calls[-1][2], {
			"from_date": "2026-07-01", "to_date": "2026-07-31",
			"view": "Order Detail", "channel": "Web", "product_type": "Firearms",
		})

	# ------------------------------------------------------------ gl_entries

	def test_gl_entries_constant_not_cancelled_and_range(self):
		self.client.canned[("list", "GL Entry")] = [{"account": "A"}] * 3
		out = self.tools["gl_entries"]("2026-07-01", "2026-07-31", account="Sales Tax Payable - OSA")
		kind, doctype, kw = self.client.calls[-1]
		self.assertEqual((kind, doctype), ("list_documents", "GL Entry"))
		self.assertIn(["is_cancelled", "=", 0], kw["filters"])
		self.assertIn(["posting_date", ">=", "2026-07-01"], kw["filters"])
		self.assertIn(["posting_date", "<=", "2026-07-31"], kw["filters"])
		self.assertIn(["account", "=", "Sales Tax Payable - OSA"], kw["filters"])
		for f in ("posting_date", "account", "debit", "credit", "against",
				"voucher_type", "voucher_no", "party", "remarks"):
			self.assertIn(f, kw["fields"])
		self.assertEqual(out["truncated"], False)
		self.assertEqual(len(out["rows"]), 3)

	def test_gl_entries_truncation_is_explicit(self):
		# limit+1 rows canned → truncated:true, exactly `limit` rows returned
		self.client.canned[("list", "GL Entry")] = lambda kw: [
			{"n": n} for n in range(kw["limit"])]
		out = self.tools["gl_entries"]("2026-07-01", "2026-07-31", limit=5)
		self.assertEqual(self.client.calls[-1][2]["limit"], 6)  # fetch limit+1
		self.assertTrue(out["truncated"])
		self.assertEqual(len(out["rows"]), 5)

	# ---------------------------------------------------- financial_statement

	def test_financial_statement_pnl_date_range(self):
		self.tools["financial_statement"]("pnl", "2026-01-01", "2026-06-30")
		self.assertEqual(self.client.calls[-1], ("run_report",
			"Profit and Loss Statement", {
				"company": "Old Steel Arsenal",
				"filter_based_on": "Date Range",
				"period_start_date": "2026-01-01",
				"period_end_date": "2026-06-30",
				"periodicity": "Monthly",
			}))

	def test_financial_statement_balance_sheet(self):
		self.tools["financial_statement"]("balance_sheet", "2026-01-01",
			"2026-12-31", periodicity="Yearly")
		name = self.client.calls[-1][1]
		self.assertEqual(name, "Balance Sheet")
		self.assertEqual(self.client.calls[-1][2]["periodicity"], "Yearly")

	def test_financial_statement_trial_balance_resolves_fiscal_year(self):
		self.client.canned[("list", "Fiscal Year")] = [{"name": "2026"}]
		self.tools["financial_statement"]("trial_balance", "2026-01-01", "2026-06-30")
		self.assertEqual(self.client.calls[-1], ("run_report", "Trial Balance", {
			"company": "Old Steel Arsenal", "fiscal_year": "2026",
			"from_date": "2026-01-01", "to_date": "2026-06-30",
		}))

	def test_financial_statement_trial_balance_no_fy_fails_closed(self):
		self.client.canned[("list", "Fiscal Year")] = []
		with self.assertRaises(ValueError):
			self.tools["financial_statement"]("trial_balance", "2025-07-01", "2026-06-30")

	def test_financial_statement_bad_statement_rejected(self):
		with self.assertRaises(ValueError):
			self.tools["financial_statement"]("cashflow", "2026-01-01", "2026-06-30")

	# ---------------------------------------------------------- tax_liability

	def _prime_tax(self, gl_rows):
		self.client.canned[("list", "Sales Taxes and Charges Template")] = [
			{"name": "Texas Sales Tax - OSA"}]
		self.client.canned[("get", "Sales Taxes and Charges Template",
			"Texas Sales Tax - OSA")] = {"taxes": [
				{"account_head": "Sales Tax Payable - OSA"},
				{"account_head": ""},                          # blank dropped
				{"account_head": "Sales Tax Payable - OSA"},   # dupe dropped
			]}
		self.client.canned[("list", "GL Entry")] = gl_rows

	def test_tax_liability_rollforward_and_identity(self):
		self._prime_tax([
			# opening (before from_date): credit 100
			{"posting_date": "2026-06-15", "voucher_type": "Sales Invoice",
			 "voucher_no": "SI-1", "debit": 0, "credit": 100.00},
			# period: SI credit 82.50 (销售计提)
			{"posting_date": "2026-07-03", "voucher_type": "Sales Invoice",
			 "voucher_no": "SI-2", "debit": 0, "credit": 82.50},
			# period: JE credit 5.00 (adjustment, fail-closed 单列)
			{"posting_date": "2026-07-05", "voucher_type": "Journal Entry",
			 "voucher_no": "JE-1", "debit": 0, "credit": 5.00},
			# period: JE debit 100.00 (汇缴)
			{"posting_date": "2026-07-20", "voucher_type": "Journal Entry",
			 "voucher_no": "JE-2", "debit": 100.00, "credit": 0},
			# period: SI debit 2.50 (return/amend 冲销)
			{"posting_date": "2026-07-21", "voucher_type": "Sales Invoice",
			 "voucher_no": "SI-3", "debit": 2.50, "credit": 0},
			# period: Payment Entry debit 1.00 (非常规 voucher → fail-closed 单列)
			{"posting_date": "2026-07-22", "voucher_type": "Payment Entry",
			 "voucher_no": "PE-1", "debit": 1.00, "credit": 0},
		])
		out = self.tools["tax_liability"]("2026-07-01", "2026-07-31")
		self.assertEqual(out["accounts"], ["Sales Tax Payable - OSA"])
		self.assertEqual(out["opening_balance"], 100.00)
		self.assertEqual(out["collected"]["sales_invoices"], 82.50)
		self.assertEqual(out["collected"]["journal_entry_adjustments"], 5.00)
		self.assertEqual(out["collected"]["other"], {})
		self.assertEqual(out["remitted"]["journal_entries"], 100.00)
		self.assertEqual(out["remitted"]["sales_invoice_reversals"], 2.50)
		self.assertEqual(out["remitted"]["other"], {"Payment Entry": 1.00})
		# 恒等式:closing == opening + Σcredit − Σdebit,与工具内部口径独立复算
		self.assertEqual(out["closing_balance"], 100.00 + 87.50 - 103.50)
		self.assertEqual(out["identity_check"], "ok")
		# 模板解析必须按服务端同一规则过滤(is_default=1, disabled=0, company)
		tmpl_call = [c for c in self.client.calls
			if c[0] == "list_documents" and c[1] == "Sales Taxes and Charges Template"][0]
		self.assertIn(["is_default", "=", 1], tmpl_call[2]["filters"])
		self.assertIn(["disabled", "=", 0], tmpl_call[2]["filters"])
		self.assertIn(["company", "=", "Old Steel Arsenal"], tmpl_call[2]["filters"])
		# GL 查询必须 is_cancelled=0
		gl_call = [c for c in self.client.calls
			if c[0] == "list_documents" and c[1] == "GL Entry"][0]
		self.assertIn(["is_cancelled", "=", 0], gl_call[2]["filters"])

	def test_tax_liability_cent_exact_no_float_drift(self):
		self._prime_tax([
			{"posting_date": "2026-07-01", "voucher_type": "Sales Invoice",
			 "voucher_no": f"SI-{i}", "debit": 0, "credit": 0.1} for i in range(3)
		])
		out = self.tools["tax_liability"]("2026-07-01", "2026-07-31")
		self.assertEqual(out["collected"]["sales_invoices"], 0.30)  # not 0.30000000000000004
		self.assertEqual(out["closing_balance"], 0.30)

	def test_tax_liability_no_default_template_fails_closed(self):
		self.client.canned[("list", "Sales Taxes and Charges Template")] = []
		with self.assertRaises(ValueError):
			self.tools["tax_liability"]("2026-07-01", "2026-07-31")

	def test_tax_liability_docstring_names_the_total_taxes_trap(self):
		doc = self.tools["tax_liability"].__doc__
		self.assertIn("Total Taxes and Charges", doc)

	# ---------------------------------------------------------- ar_ap_summary

	def test_ar_summary(self):
		self.tools["ar_ap_summary"]("ar", "2026-07-31")
		self.assertEqual(self.client.calls[-1], ("run_report", "Accounts Receivable", {
			"company": "Old Steel Arsenal", "report_date": "2026-07-31",
			"ageing_based_on": "Posting Date", "range": "30, 60, 90, 120",
		}))

	def test_ap_summary(self):
		self.tools["ar_ap_summary"]("ap", "2026-07-31")
		self.assertEqual(self.client.calls[-1][1], "Accounts Payable")

	def test_ar_ap_bad_kind_rejected(self):
		with self.assertRaises(ValueError):
			self.tools["ar_ap_summary"]("inventory", "2026-07-31")


if __name__ == "__main__":
	unittest.main()
