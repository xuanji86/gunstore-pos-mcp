"""CPA mode tests: the three defence layers.

Layer 1 — registration: GUNSTORE_MCP_MODE=cpa registers EXACTLY the 18-name
allowlist (set equality, per spec acceptance #1 — not merely "no write tools").
Layer 2 — client: mutating client methods + non-allowlisted dotted methods
raise CpaModeRefused before any HTTP.
Layer 3 — the 8 integration Settings doctypes refuse get/list reads in cpa mode.
Full mode must behave exactly as before (no refusals); its size is pinned below and
in tests/test_doc_counts.py rather than restated here in prose, because a number
written into a docstring is exactly the kind that goes stale unnoticed.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from gunstore_mcp import frappe_client as fc_mod
from gunstore_mcp import server
from gunstore_mcp.config import Config
from gunstore_mcp.modes import (
	CPA_METHOD_ALLOWLIST,
	CPA_SETTINGS_READ_BLOCKLIST,
	CpaModeRefused,
	get_mode,
)
from gunstore_mcp.tools import distributor


def _actions(value):
	"""Context manager controlling GUNSTORE_MCP_DISTRIBUTOR_ACTIONS (None = absent).
	_load_env is stubbed so a developer's own mcp/.env cannot flip these assertions."""
	env = {k: v for k, v in os.environ.items() if k != distributor.ACTIONS_ENV}
	if value is not None:
		env[distributor.ACTIONS_ENV] = value
	return _Both(patch.dict(os.environ, env, clear=True),
		patch.object(distributor, "_load_env", lambda: None))


class _Both:
	def __init__(self, *ctxs):
		self._ctxs = ctxs

	def __enter__(self):
		for c in self._ctxs:
			c.__enter__()
		return self

	def __exit__(self, *exc):
		for c in reversed(self._ctxs):
			c.__exit__(*exc)
		return False

# Spelled out independently of modes.py so a drift in EITHER place fails the
# set-equality assertion (the constant can't vouch for itself).
EXPECTED_CPA_TOOLS = {
	# generic (4)
	"frappe_list_documents", "frappe_get_document", "frappe_describe_doctype",
	"frappe_run_report",
	# curated read-only (9)
	"find_item", "item_stock", "firearms_in_stock",
	"pending_orders", "pending_web_orders",
	"consignment_queue", "consignment_dealers", "consignment_serials",
	"consignment_dealer_orders",
	# CPA reports (5)
	"sales_report", "gl_entries", "financial_statement", "tax_liability",
	"ar_ap_summary",
}

EXPECTED_METHOD_ALLOWLIST = {
	"frappe.desk.query_report.run",
	"ffl_core.api.receive_goods.search_items",
	"ffl_core.api.item_admin.get_item_stock",
	"ffl_core.api.manual_order.list_pending_dispositions",
	"ffl_woo_sync.woocommerce.fulfillment.list_pending_web_orders",
	"ffl_core.api.consignment_out.list_consignment_queue",
	"ffl_core.api.consignment_out.list_consignment_dealers",
	"ffl_core.api.consignment_out.available_serials_for_consignment",
	"ffl_core.api.consignment_orders.list_dealer_orders",
}

SETTINGS_DOCTYPES = {
	"FFL Settings", "FastBound Settings", "RSR Settings", "Payroc Settings",
	"WooCommerce Settings", "Dealer WooCommerce Settings", "ShipStation Settings",
	# PR-4a: holds the GunBroker DevKey + seller password (Password fields), and
	# has no accounting purpose — same reasoning as every other row here.
	"GunBroker Settings",
}


class FakeMCP:
	def __init__(self):
		self.tools = {}

	def tool(self, *a, **k):
		def deco(fn):
			self.tools[fn.__name__] = fn
			return fn
		return deco


class RegistrationLayer(unittest.TestCase):
	def test_cpa_mode_registers_exactly_the_18_allowlisted_tools(self):
		mcp = FakeMCP()
		server.register_tools(mcp, mode="cpa")
		self.assertEqual(set(mcp.tools), EXPECTED_CPA_TOOLS)
		self.assertEqual(len(mcp.tools), 18)

	def test_default_full_mode_holds_the_four_queue_actions_back(self):
		"""Default full mode is 79, not 83: the distributor queue actions require an
		explicit opt-in. Pinned separately from the full surface so that turning the
		gate into a no-op would break a test rather than quietly restore the old
		surface."""
		mcp = FakeMCP()
		with _actions(None):
			server.register_tools(mcp, mode="full")
		self.assertEqual(len(mcp.tools), 79)
		for name in ("distributor_confirm_order", "distributor_cancel_order",
				"distributor_reroute", "distributor_update_order_ffl"):
			self.assertNotIn(name, mcp.tools)

	def test_the_actions_flag_cannot_widen_cpa_mode(self):
		"""The two switches are independent, and cpa is the stricter one: opting into
		the queue actions must not add a single tool to the accountant surface."""
		mcp = FakeMCP()
		with _actions("1"):
			server.register_tools(mcp, mode="cpa")
		self.assertEqual(set(mcp.tools), EXPECTED_CPA_TOOLS)
		self.assertEqual(len(mcp.tools), 18)

	def test_full_mode_registers_the_whole_surface_including_the_cpa_18(self):
		mcp = FakeMCP()
		with _actions("1"):
			server.register_tools(mcp, mode="full")
		self.assertEqual(len(mcp.tools), 83)
		self.assertTrue(EXPECTED_CPA_TOOLS <= set(mcp.tools))
		# regression: none of the write faces leaked out of full mode
		for name in ("frappe_run_method", "dispose_order", "receive_goods",
				"cancel_order", "update_settings", "upload_attachment"):
			self.assertIn(name, mcp.tools)

	def test_cpa_mode_excludes_the_write_and_misleading_faces(self):
		mcp = FakeMCP()
		server.register_tools(mcp, mode="cpa")
		for name in (
			"frappe_run_method", "frappe_create_document", "frappe_update_document",
			"frappe_delete_document", "frappe_submit_document", "frappe_cancel_document",
			"upload_attachment", "get_settings", "update_settings",
			"available_serials",  # cpa-review OQ-3: 盘点语境默认剔除,误导
			"rsr_catalog_search",
			"rsr_test_connection", "fastbound_test_connection",
			"woo_test_connection", "shipstation_test_connection",
			# PR-4a: the GunBroker channel is a sales surface, not an accounting one;
			# two of these write to a live marketplace.
			"gb_test_connection", "gb_push_serial", "gb_end_listing", "gb_listing_status",
			"dispose_order", "receive_goods", "cancel_order",
			"ship_consignment_out", "create_consignment_out",
		):
			self.assertNotIn(name, mcp.tools)

	def test_method_allowlist_is_exactly_the_nine_names(self):
		self.assertEqual(set(CPA_METHOD_ALLOWLIST), EXPECTED_METHOD_ALLOWLIST)

	def test_settings_blocklist_is_exactly_the_eight_doctypes(self):
		self.assertEqual(set(CPA_SETTINGS_READ_BLOCKLIST), SETTINGS_DOCTYPES)


class ModeEnv(unittest.TestCase):
	def test_default_is_full(self):
		with patch.dict(os.environ, {}, clear=False):
			os.environ.pop("GUNSTORE_MCP_MODE", None)
			self.assertEqual(get_mode(), "full")

	def test_cpa_env(self):
		with patch.dict(os.environ, {"GUNSTORE_MCP_MODE": "CPA"}):
			self.assertEqual(get_mode(), "cpa")

	def test_unknown_mode_fails_closed(self):
		with patch.dict(os.environ, {"GUNSTORE_MCP_MODE": "rw"}):
			with self.assertRaises(RuntimeError):
				get_mode()


def _client(mode: str) -> fc_mod.FrappeClient:
	cfg = Config(base_url="http://test.invalid", api_key="k", api_secret="s",
		timeout=5, write_denylist=frozenset())
	with patch.object(fc_mod, "get_config", return_value=cfg), \
			patch.dict(os.environ, {"GUNSTORE_MCP_MODE": mode}):
		return fc_mod.FrappeClient()


class Recorder:
	def __init__(self):
		self.calls = []

	def __call__(self, method, path, **kw):
		self.calls.append((method, path, kw))
		return {"ok": True}


class ClientLayerCpa(unittest.TestCase):
	def setUp(self):
		self.client = _client("cpa")
		self.rec = Recorder()
		self.client._request = self.rec  # any HTTP that happens is recorded

	def test_document_writes_refused_before_any_http(self):
		with self.assertRaises(CpaModeRefused):
			self.client.create_document("Item", {"item_code": "X"})
		with self.assertRaises(CpaModeRefused):
			self.client.update_document("Item", "X", {"disabled": 1})
		with self.assertRaises(CpaModeRefused):
			self.client.delete_document("Item", "X")
		with self.assertRaises(CpaModeRefused):
			self.client.submit_document("Sales Invoice", "SI-1")
		with self.assertRaises(CpaModeRefused):
			self.client.cancel_document("Sales Invoice", "SI-1")
		with self.assertRaises(CpaModeRefused):
			self.client.upload_file("/tmp/x.jpg")
		self.assertEqual(self.rec.calls, [])

	def test_non_allowlisted_methods_refused_even_reads(self):
		for method in (
			"ffl_core.api.manual_order.dispose_order",       # write
			"ffl_core.api.manual_order.record_payment",      # write
			"ffl_core.firearm.available_serials_with_prices",  # read, 未列名
			"ffl_integrations.rsr.search.search",            # read, 未列名
			"frappe.client.get_list",                        # framework read, 未列名
		):
			with self.assertRaises(CpaModeRefused, msg=method):
				self.client.call_method(method, {})
		self.assertEqual(self.rec.calls, [])

	def test_every_allowlisted_method_passes(self):
		for method in sorted(EXPECTED_METHOD_ALLOWLIST):
			self.client.call_method(method, {})
		self.assertEqual(len(self.rec.calls), len(EXPECTED_METHOD_ALLOWLIST))

	def test_run_report_allowed(self):
		self.client.run_report("Sales Report", {"from_date": "2026-07-01"})
		self.assertEqual(len(self.rec.calls), 1)

	def test_settings_reads_blocked_third_layer(self):
		for dt in sorted(SETTINGS_DOCTYPES):
			with self.assertRaises(CpaModeRefused, msg=dt):
				self.client.get_document(dt, dt)
			with self.assertRaises(CpaModeRefused, msg=dt):
				self.client.list_documents(dt)
		self.assertEqual(self.rec.calls, [])

	def test_ordinary_reads_still_work(self):
		self.client.list_documents("Sales Invoice", limit=5)
		self.client.get_document("GL Entry", "GL-0001")
		self.client.get_document("Global Defaults", "Global Defaults")
		self.assertEqual(len(self.rec.calls), 3)


class ClientLayerFull(unittest.TestCase):
	def test_full_mode_unchanged(self):
		client = _client("full")
		rec = Recorder()
		client._request = rec
		client.create_document("Item", {"item_code": "X"})
		client.call_method("ffl_core.api.manual_order.dispose_order", {})
		client.get_document("RSR Settings", "RSR Settings")
		self.assertEqual(len(rec.calls), 3)


if __name__ == "__main__":
	unittest.main()
