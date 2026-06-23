"""Unit tests for the curated MCP tools added for groups A–D.

The tools are thin wrappers over FrappeClient.call_method / run_report. We register
them against a fake MCP, patch the client to a recorder, and assert each tool calls
the correct whitelisted method path + kwargs and enforces its confirm guard. No
network / Frappe needed.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from gunstore_mcp.safety import WriteRefused
from gunstore_mcp.tools import curated


class FakeClient:
	def __init__(self):
		self.calls = []

	def call_method(self, method, kwargs=None):
		self.calls.append(("call_method", method, kwargs or {}))
		return {"ok": True}

	def run_report(self, name, filters=None):
		self.calls.append(("run_report", name, filters))
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


class CuratedTools(unittest.TestCase):
	def setUp(self):
		mcp = FakeMCP()
		curated.register(mcp)
		self.tools = mcp.tools
		self.client = FakeClient()
		self._patch = patch.object(curated, "get_client", return_value=self.client)
		self._patch.start()
		self.addCleanup(self._patch.stop)

	def _last(self):
		return self.client.calls[-1]

	# ---------------------------------------------------------- A: read-only

	def test_item_stock(self):
		self.tools["item_stock"](["A", "B"])
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.item_admin.get_item_stock",
			{"item_codes": ["A", "B"]},
		))

	def test_available_serials(self):
		self.tools["available_serials"]("A")
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.firearm.available_serials_with_prices",
			{"item_codes": "A"},
		))

	def test_rsr_catalog_search(self):
		self.tools["rsr_catalog_search"]("glock", 5)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.rsr.search.search",
			{"query": "glock", "limit": 5},
		))

	def test_boundbook_reconcile_defaults_to_dry_run(self):
		self.tools["boundbook_reconcile"]()
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_integrations.fastbound.inventory_sync.sync_in_stock_from_boundbook",
			{"dry_run": 1, "item_ids": None},
		))

	def test_boundbook_reconcile_apply_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["boundbook_reconcile"](apply=True)
		self.assertEqual(self.client.calls, [])  # refused before any call
		self.tools["boundbook_reconcile"](apply=True, confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_integrations.fastbound.inventory_sync.sync_in_stock_from_boundbook",
			{"dry_run": 0, "item_ids": None},
		))

	# ------------------------------------------------- B: writes (confirm)

	def test_receive_goods_requires_confirm(self):
		payload = {"supplier": "X", "items": []}
		with self.assertRaises(WriteRefused):
			self.tools["receive_goods"](payload)
		self.tools["receive_goods"](payload, confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.receive_goods.create_receive",
			{"payload": payload},
		))

	def test_add_stock(self):
		with self.assertRaises(WriteRefused):
			self.tools["add_stock"]("ITEM", 5)
		self.tools["add_stock"]("ITEM", 5, warehouse="WH", rate=10, remarks="r", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.item_admin.add_stock",
			{"item_code": "ITEM", "qty": 5, "warehouse": "WH", "rate": 10, "remarks": "r"},
		))

	def test_set_stock(self):
		with self.assertRaises(WriteRefused):
			self.tools["set_stock"]("ITEM", 3)
		self.tools["set_stock"]("ITEM", 3, warehouse="WH", reason="count", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.item_admin.set_stock",
			{"item_code": "ITEM", "new_qty": 3, "warehouse": "WH", "reason": "count"},
		))

	def test_toggle_service_need_maps_bool_to_int(self):
		with self.assertRaises(WriteRefused):
			self.tools["toggle_service_need"]("SN1", True)
		self.tools["toggle_service_need"]("SN1", True, confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.firearm.toggle_serial_service_need",
			{"serial": "SN1", "value": 1},
		))
		self.tools["toggle_service_need"]("SN1", False, confirm=True)
		self.assertEqual(self._last()[2]["value"], 0)

	# ------------------------------------ C: compliance / FastBound (confirm)

	def test_push_serial_to_fastbound(self):
		with self.assertRaises(WriteRefused):
			self.tools["push_serial_to_fastbound"]("SN1")
		self.tools["push_serial_to_fastbound"]("SN1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.fastbound.tasks.push_serial_to_fastbound",
			{"serial": "SN1"},
		))

	def test_verify_supplier_ffl(self):
		with self.assertRaises(WriteRefused):
			self.tools["verify_supplier_ffl"]("SUP")
		self.tools["verify_supplier_ffl"]("SUP", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.atf.ez_check_api.verify_supplier_ffl",
			{"supplier_name": "SUP"},
		))

	def test_reverify_all_ffls(self):
		with self.assertRaises(WriteRefused):
			self.tools["reverify_all_ffls"]()
		self.tools["reverify_all_ffls"](confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.atf.ez_check.re_verify_all", {},
		))

	# ------------------------------------------------- D: RSR promote (confirm)

	def test_promote_to_item(self):
		payload = {"rsr_stock_number": "GLK19"}
		with self.assertRaises(WriteRefused):
			self.tools["promote_to_item"](payload)
		self.tools["promote_to_item"](payload, confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.rsr.promote.promote_to_item",
			{"payload": payload},
		))

	def test_backfill_from_rsr(self):
		with self.assertRaises(WriteRefused):
			self.tools["backfill_from_rsr"]()
		self.tools["backfill_from_rsr"](["A"], confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.rsr.promote.backfill_from_rsr",
			{"item_codes": ["A"]},
		))

	# ------------------------------------------------------------- coverage

	def test_all_new_tools_registered(self):
		for name in (
			"item_stock", "available_serials", "rsr_catalog_search", "boundbook_reconcile",
			"receive_goods", "add_stock", "set_stock", "toggle_service_need",
			"push_serial_to_fastbound", "verify_supplier_ffl", "reverify_all_ffls",
			"promote_to_item", "backfill_from_rsr",
		):
			self.assertIn(name, self.tools)


if __name__ == "__main__":
	unittest.main()
