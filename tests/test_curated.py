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

	def update_document(self, doctype, name, values):
		self.calls.append(("update_document", doctype, name, values))
		return {"ok": True}

	def get_document(self, doctype, name):
		self.calls.append(("get_document", doctype, name))
		return {"ok": True}

	def upload_file(self, file_path, *, doctype=None, docname=None, fieldname=None,
			is_private=True, filename=None):
		self.calls.append(("upload_file", file_path, doctype, docname, fieldname,
			is_private, filename))
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

	def test_available_serials_excludes_unavailable_by_default(self):
		# Mirrors the server default (firearm.py available_serials_with_prices
		# exclude_unavailable=True): held / consigned-out guns are dropped.
		self.tools["available_serials"]("A")
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.firearm.available_serials_with_prices",
			{"item_codes": "A", "exclude_unavailable": 1},
		))

	def test_available_serials_can_include_unavailable(self):
		# Inventory-audit callers need the RAW list (consigned/held included).
		self.tools["available_serials"]("A", exclude_unavailable=False)
		self.assertEqual(self._last()[2],
			{"item_codes": "A", "exclude_unavailable": 0})

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

	def test_set_serial_title(self):
		"""Per-gun Woo title write goes to Serial No.item_name (no confirm gate)."""
		self.tools["set_serial_title"]("SN1", "Colt King Cobra .357 Magnum")
		self.assertEqual(self._last(), (
			"update_document", "Serial No", "SN1",
			{"item_name": "Colt King Cobra .357 Magnum"},
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

	# ------------------------------------------ E: settings map additions

	def test_get_settings_shipstation_and_dealer(self):
		self.tools["get_settings"]("shipstation")
		self.assertEqual(self._last(), (
			"get_document", "ShipStation Settings", "ShipStation Settings"))
		self.tools["get_settings"]("dealer")
		self.assertEqual(self._last(), (
			"get_document", "Dealer WooCommerce Settings", "Dealer WooCommerce Settings"))

	# ---------------------------------------------------- F: Woo multi-site

	def test_woo_push_item_defaults_to_retail(self):
		with self.assertRaises(WriteRefused):
			self.tools["woo_push_item"]("ITEM")
		self.tools["woo_push_item"]("ITEM", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.client_api.push_item_now",
			{"item_code": "ITEM", "site": "retail"},
		))

	def test_woo_push_item_dealer_site(self):
		self.tools["woo_push_item"]("ITEM", site="dealer", confirm=True)
		self.assertEqual(self._last()[2], {"item_code": "ITEM", "site": "dealer"})

	def test_woo_delist_item_site(self):
		self.tools["woo_delist_item"]("ITEM", site="dealer", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.client_api.delist_item_now",
			{"item_code": "ITEM", "site": "dealer"},
		))

	def test_woo_reconcile_site(self):
		self.tools["woo_reconcile"]("ITEM", site="dealer", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.client_api.reconcile_now",
			{"item_code": "ITEM", "site": "dealer"},
		))

	def test_woo_test_connection_site(self):
		self.tools["woo_test_connection"]()
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.client_api.test_connection",
			{"site": "retail"},
		))
		self.tools["woo_test_connection"](site="dealer")
		self.assertEqual(self._last()[2], {"site": "dealer"})

	def test_woo_push_serial(self):
		with self.assertRaises(WriteRefused):
			self.tools["woo_push_serial"]("SN1")
		self.tools["woo_push_serial"]("SN1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.client_api.push_serial_now",
			{"serial_no": "SN1", "site": "retail"},
		))

	def test_woo_delist_serial(self):
		with self.assertRaises(WriteRefused):
			self.tools["woo_delist_serial"]("SN1")
		self.tools["woo_delist_serial"]("SN1", site="dealer", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.client_api.delist_serial_now",
			{"serial_no": "SN1", "site": "dealer"},
		))

	# ------------------------------------------- G: order / fulfillment queue

	def test_pending_orders_read_only(self):
		self.tools["pending_orders"]()
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.manual_order.list_pending_dispositions", {},
		))

	def test_pending_orders_docstring_names_consignment_queue(self):
		# #213 split the consignment fulfillment into its own queue; the server
		# list explicitly EXCLUDES consignment SIs. The docstring must route the
		# operator to consignment_queue or they will think consignments vanished.
		self.assertIn("consignment_queue", self.tools["pending_orders"].__doc__)

	def test_pending_web_orders_read_only(self):
		self.tools["pending_web_orders"]()
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_woo_sync.woocommerce.fulfillment.list_pending_web_orders", {},
		))

	def test_dispose_order_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["dispose_order"]("SI-1")
		self.assertEqual(self.client.calls, [])
		self.tools["dispose_order"]("SI-1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.manual_order.dispose_order",
			{"sales_invoice": "SI-1"},
		))

	def test_dispose_web_order_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["dispose_web_order"]("WOO-1")
		self.tools["dispose_web_order"]("WOO-1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_woo_sync.woocommerce.fulfillment.dispose_web_order",
			{"woo_online_order": "WOO-1"},
		))

	def test_record_payment(self):
		with self.assertRaises(WriteRefused):
			self.tools["record_payment"]("SI-1", "Zelle")
		self.tools["record_payment"]("SI-1", "Zelle", amount=100.0,
			transaction_number="Z123", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.manual_order.record_payment",
			{"sales_invoice": "SI-1", "mode_of_payment": "Zelle",
			 "amount": 100.0, "transaction_number": "Z123"},
		))

	def test_push_shipment_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["push_shipment"]("SI-1")
		self.tools["push_shipment"]("SI-1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.shipstation.api.push_shipment",
			{"sales_invoice": "SI-1"},
		))

	def test_mark_shipped_manually_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["mark_shipped_manually"]("SI-1")
		self.tools["mark_shipped_manually"]("SI-1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.manual_order.mark_shipped_manually",
			{"sales_invoice": "SI-1"},
		))

	def test_shipstation_test_connection_read_only(self):
		self.tools["shipstation_test_connection"]()
		self.assertEqual(self._last(), (
			"call_method", "ffl_integrations.shipstation.api.test_connection", {},
		))

	# --------------------------------------------------------- H: POS 4473

	def test_start_4473(self):
		mapping = {"row1": "SN1"}
		with self.assertRaises(WriteRefused):
			self.tools["start_4473"]("POSINV-1", mapping)
		self.tools["start_4473"]("POSINV-1", mapping, confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_integrations.fastbound.pos_4473.start_4473_for_pos_invoice",
			{"invoice_name": "POSINV-1", "serial_by_item_row": mapping},
		))

	def test_manager_override_4473(self):
		with self.assertRaises(WriteRefused):
			self.tools["manager_override_4473"]("POSINV-1", "webhook lost")
		self.tools["manager_override_4473"]("POSINV-1", "webhook lost", confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_integrations.fastbound.pos_4473.manager_override_4473",
			{"invoice_name": "POSINV-1", "reason": "webhook lost"},
		))

	def test_start_transfer_4473(self):
		with self.assertRaises(WriteRefused):
			self.tools["start_transfer_4473"](["SN1"], "TRANSFER-FEE", 25.0, "CUST-1")
		self.tools["start_transfer_4473"](["SN1", "SN2"], "TRANSFER-FEE", 25.0,
			"CUST-1", pos_profile="Main", confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_integrations.fastbound.pos_4473.start_transfer_for_pos_invoice",
			{"serials": ["SN1", "SN2"], "fee_item": "TRANSFER-FEE",
			 "fee_amount": 25.0, "customer": "CUST-1", "pos_profile": "Main",
			 "invoice_name": None},
		))

	# ------------------------------------------------------- I: file upload

	def test_upload_attachment(self):
		self.tools["upload_attachment"]("/tmp/x.jpg", doctype="Serial No",
			name="SN1", is_private=False)
		self.assertEqual(self._last(), (
			"upload_file", "/tmp/x.jpg", "Serial No", "SN1", None, False, None))

	# ------------------------------------------ J: consignment out (寄售) reads

	def test_consignment_queue_read_only(self):
		self.tools["consignment_queue"]()
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.consignment_out.list_consignment_queue",
			{"include_closed": 0},
		))
		self.tools["consignment_queue"](include_closed=True)
		self.assertEqual(self._last()[2], {"include_closed": 1})

	def test_consignment_dealers_read_only(self):
		self.tools["consignment_dealers"]()
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_core.api.consignment_out.list_consignment_dealers", {},
		))

	def test_consignment_serials_read_only(self):
		self.tools["consignment_serials"](item_code="GLK19", search="G19", limit=10)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_core.api.consignment_out.available_serials_for_consignment",
			{"item_code": "GLK19", "search": "G19", "limit": 10},
		))

	def test_consignment_dealer_orders_read_only(self):
		self.tools["consignment_dealer_orders"]()
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_core.api.consignment_orders.list_dealer_orders", {},
		))

	# ----------------------------------------- K: consignment out (寄售) writes

	def test_create_consignment_out_requires_confirm(self):
		payload = {"dealer": "AAA", "lines": [
			{"item_code": "I", "serial": "SN1", "cost": 400, "msrp": 599}]}
		with self.assertRaises(WriteRefused):
			self.tools["create_consignment_out"](payload)
		self.assertEqual(self.client.calls, [])
		self.tools["create_consignment_out"](payload, confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.consignment_out.create_consignment_out",
			{"payload": payload},
		))

	def test_ship_consignment_out_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["ship_consignment_out"]("CONO-0001")
		self.assertEqual(self.client.calls, [])
		self.tools["ship_consignment_out"]("CONO-0001", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.consignment_out.ship_consignment_out",
			{"consignment_out": "CONO-0001"},
		))

	def test_push_consignment_shipment_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["push_consignment_shipment"]("CONO-0001")
		self.tools["push_consignment_shipment"]("CONO-0001", confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_integrations.shipstation.api.push_consignment_shipment",
			{"consignment_out": "CONO-0001"},
		))

	def test_mark_consignment_shipped_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["mark_consignment_shipped"]("CONO-0001")
		self.tools["mark_consignment_shipped"]("CONO-0001",
			tracking_number="1Z999", carrier="UPS", confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_core.api.consignment_out.mark_consignment_shipped_manually",
			{"consignment_out": "CONO-0001", "tracking_number": "1Z999",
			 "carrier": "UPS"},
		))

	def test_retry_consignment_invoice_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["retry_consignment_invoice"]("LINE-1")
		self.tools["retry_consignment_invoice"]("LINE-1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_core.api.consignment_orders.create_consignment_invoice_now",
			{"line": "LINE-1"},
		))

	def test_return_consignment_lines_requires_confirm(self):
		with self.assertRaises(WriteRefused):
			self.tools["return_consignment_lines"]("CONO-0001", ["L1", "L2"])
		self.tools["return_consignment_lines"]("CONO-0001", ["L1", "L2"],
			to_warehouse="Main - OSA", confirm=True)
		self.assertEqual(self._last(), (
			"call_method",
			"ffl_core.api.consignment_out.return_consignment_lines",
			{"consignment_out": "CONO-0001", "lines": ["L1", "L2"],
			 "to_warehouse": "Main - OSA"},
		))

	def test_cancel_consignment_whole_doc(self):
		with self.assertRaises(WriteRefused):
			self.tools["cancel_consignment"]("CONO-0001", "built by mistake")
		self.assertEqual(self.client.calls, [])
		self.tools["cancel_consignment"]("CONO-0001", "built by mistake",
			confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.consignment_out.cancel_consignment_out",
			{"consignment_out": "CONO-0001", "reason": "built by mistake"},
		))

	def test_cancel_consignment_single_line(self):
		self.tools["cancel_consignment"]("CONO-0001", "wrong gun", line="L1",
			confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.consignment_out.cancel_consignment_line",
			{"consignment_out": "CONO-0001", "line": "L1", "reason": "wrong gun"},
		))

	def test_cancel_consignment_blank_reason_rejected(self):
		with self.assertRaises(ValueError):
			self.tools["cancel_consignment"]("CONO-0001", "  ", confirm=True)
		self.assertEqual(self.client.calls, [])

	# --------------------------------------------------- L: counter order cancel

	def test_cancel_order_requires_confirm_and_reason(self):
		with self.assertRaises(WriteRefused):
			self.tools["cancel_order"]("SI-1", "customer backed out")
		with self.assertRaises(ValueError):
			self.tools["cancel_order"]("SI-1", "", confirm=True)
		self.assertEqual(self.client.calls, [])
		self.tools["cancel_order"]("SI-1", "customer backed out",
			refund_mode="Cash", refund_reference="R1", confirm=True)
		self.assertEqual(self._last(), (
			"call_method", "ffl_core.api.manual_order.cancel_order",
			{"sales_invoice": "SI-1", "reason": "customer backed out",
			 "refund_mode": "Cash", "refund_reference": "R1"},
		))

	# ------------------------------------------------------------- coverage

	def test_all_new_tools_registered(self):
		for name in (
			"item_stock", "available_serials", "rsr_catalog_search", "boundbook_reconcile",
			"receive_goods", "add_stock", "set_stock", "toggle_service_need",
			"push_serial_to_fastbound", "verify_supplier_ffl", "reverify_all_ffls",
			"promote_to_item", "backfill_from_rsr", "set_serial_title",
			"woo_push_serial", "woo_delist_serial",
			"pending_orders", "pending_web_orders",
			"dispose_order", "dispose_web_order", "record_payment",
			"push_shipment", "mark_shipped_manually", "shipstation_test_connection",
			"start_4473", "manager_override_4473", "start_transfer_4473",
			"upload_attachment",
			# consignment out lifecycle + counter-order cancel (P1 补齐)
			"consignment_queue", "consignment_dealers", "consignment_serials",
			"consignment_dealer_orders", "create_consignment_out",
			"ship_consignment_out", "push_consignment_shipment",
			"mark_consignment_shipped", "retry_consignment_invoice",
			"return_consignment_lines", "cancel_consignment", "cancel_order",
		):
			self.assertIn(name, self.tools)

	def test_curated_tool_count_pinned(self):
		# 52 curated + 10 generic = 62 total. TOOLS.md / CLAUDE.md / README.md
		# quote this number — if this assertion moves, move all three docs too.
		self.assertEqual(len(self.tools), 52)


if __name__ == "__main__":
	unittest.main()
