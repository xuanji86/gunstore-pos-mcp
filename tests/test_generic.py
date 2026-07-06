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

	def test_verb_in_module_segment_does_not_gate(self):
		# Gating matches the FINAL path segment only — a module named after a
		# verb must not gate an innocuous method inside it.
		self.run_method("ffl_core.disposal.list_rows")
		self.assertEqual(self.client.calls[-1][1], "ffl_core.disposal.list_rows")

	def test_blocked_generic_mutators_refused_even_with_confirm(self):
		with self.assertRaises(WriteRefused):
			self.run_method("frappe.client.set_value", confirm=True)
		self.assertEqual(self.client.calls, [])


if __name__ == "__main__":
	unittest.main()
