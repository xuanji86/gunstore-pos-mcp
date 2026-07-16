"""Unit tests for the generic backbone guards: the destructive-verb confirm
gate on frappe_run_method (incl. the domain verbs dispose/push/charge/
consolidate) and the blocked generic Frappe mutators."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from gunstore_mcp.safety import WriteRefused
from gunstore_mcp.tools import generic


class FakeClient:
	def __init__(self):
		self.calls = []

	def call_method(self, method, kwargs=None):
		self.calls.append(("call_method", method, kwargs or {}))
		return {"ok": True}


class FakeMCP:
	"""Captures @mcp.tool()-decorated functions by name."""
	def __init__(self):
		self.tools = {}

	def tool(self, *a, **k):
		def deco(fn):
			self.tools[fn.__name__] = fn
			return fn
		return deco


class RunMethodGuards(unittest.TestCase):
	def setUp(self):
		mcp = FakeMCP()
		generic.register(mcp)
		self.run_method = mcp.tools["frappe_run_method"]
		self.client = FakeClient()
		self._patch = patch.object(generic, "get_client", return_value=self.client)
		self._patch.start()
		self.addCleanup(self._patch.stop)

	def test_benign_method_needs_no_confirm(self):
		self.run_method("ffl_core.api.manual_order.list_pending_dispositions")
		self.assertEqual(self.client.calls[-1][1],
			"ffl_core.api.manual_order.list_pending_dispositions")

	def test_domain_destructive_verbs_gated(self):
		for method in (
			"ffl_core.api.manual_order.dispose_order",
			"ffl_woo_sync.woocommerce.fulfillment.dispose_web_order",
			"ffl_integrations.shipstation.api.push_shipment",
			"ffl_woo_sync.woocommerce.client_api.push_serial_now",
			"ffl_integrations.payroc.api.charge_pos_invoice",
			"ffl_core.api.pos_consolidate.consolidate_pos_invoice_now",
		):
			with self.assertRaises(WriteRefused, msg=method):
				self.run_method(method)
			self.run_method(method, confirm=True)
			self.assertEqual(self.client.calls[-1][1], method)

	def test_consignment_and_lifecycle_verbs_gated(self):
		# audit 附注 a: the consignment / onboarding whitelisted writes carry
		# verbs (ship / mark_*_shipped / mark_sold / mark_received / return /
		# onboard / receive) that the original regex missed — a bare
		# frappe_run_method call could dispose stock or mint invoices unconfirmed.
		for method in (
			"ffl_core.api.consignment_out.ship_consignment_out",
			"ffl_core.api.consignment_out.mark_consignment_shipped_manually",
			"ffl_core.api.consignment_out.return_consignment_lines",
			"ffl_core.api.consignment_out.cancel_consignment_out",
			"ffl_core.api.consignment_portal.mark_sold",
			"ffl_core.api.consignment_portal.mark_received",
			"ffl_core.api.dealer_onboarding.onboard_dealer",
			"ffl_core.api.receive_goods.create_receive",
			"ffl_core.api.manual_order.mark_shipped_manually",
		):
			with self.assertRaises(WriteRefused, msg=method):
				self.run_method(method)
			self.run_method(method, confirm=True)
			self.assertEqual(self.client.calls[-1][1], method)

	def test_consignment_reads_stay_ungated(self):
		for method in (
			"ffl_core.api.consignment_out.list_consignment_queue",
			"ffl_core.api.consignment_out.list_consignment_dealers",
			"ffl_core.api.consignment_out.available_serials_for_consignment",
			"ffl_core.api.consignment_orders.list_dealer_orders",
		):
			self.run_method(method)
			self.assertEqual(self.client.calls[-1][1], method)

	def test_verb_in_module_segment_does_not_gate(self):
		# Gating matches the FINAL path segment only — a module named after a
		# verb must not gate an innocuous method inside it.
		self.run_method("ffl_core.disposal.list_rows")
		self.assertEqual(self.client.calls[-1][1], "ffl_core.disposal.list_rows")

	def test_blocked_generic_mutators_refused_even_with_confirm(self):
		with self.assertRaises(WriteRefused):
			self.run_method("frappe.client.set_value", confirm=True)
		self.assertEqual(self.client.calls, [])

	def test_generic_tool_count_pinned(self):
		# 10 generic + 52 curated (test_curated_tool_count_pinned) = 62 total.
		# TOOLS.md / CLAUDE.md / README.md quote 62 — move all three if this moves.
		mcp = FakeMCP()
		generic.register(mcp)
		self.assertEqual(len(mcp.tools), 10)


if __name__ == "__main__":
	unittest.main()
