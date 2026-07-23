"""Distributor (RSR Direct Connect) tool surface.

Two things these tests are actually for:

1. **the dotted method names and argument keys** — the MCP is a thin wrapper and its
   client is mocked, so a wrong method path or arg name cannot fail here the way it
   would against a live POS. Pinning the exact call payload is the only local signal.
   (Every path below was checked against gunstore-pos `origin/develop` when written.)
2. **the confirm gates** — `confirm_order` is the moment a real, uncancellable
   purchase from RSR becomes inevitable, so "it refuses without confirm" is a
   safety assertion, not a formality.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from gunstore_mcp.safety import WriteRefused
from gunstore_mcp.tools import distributor


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class FakeClient:
    def __init__(self):
        self.calls = []

    def call_method(self, method, args=None):
        self.calls.append((method, args or {}))
        return {"ok": True}


class DistributorTools(unittest.TestCase):
    def setUp(self):
        mcp = FakeMCP()
        distributor.register(mcp)
        self.tools = mcp.tools
        self.client = FakeClient()
        p = patch.object(distributor, "get_client", return_value=self.client)
        p.start()
        self.addCleanup(p.stop)

    # ---- surface ---------------------------------------------------------

    def test_distributor_tool_count_pinned(self):
        # 7 read + 4 queue actions = 11. TOOLS.md / CLAUDE.md / README quote the
        # TOTAL (79) — if this moves, move all of them too.
        self.assertEqual(len(self.tools), 11)

    def test_every_tool_is_namespaced(self):
        for name in self.tools:
            self.assertTrue(name.startswith("distributor_"),
                            f"{name} breaks the distributor_* namespace")

    def test_placement_and_settings_are_not_exposed(self):
        # The console surface must not grow a direct-place or settings door.
        for forbidden in ("place", "settings", "delete"):
            self.assertFalse([n for n in self.tools if forbidden in n],
                             f"unexpected {forbidden!r} tool in the distributor surface")

    # ---- reads: exact method paths + arg keys ----------------------------

    def test_orders_call(self):
        self.tools["distributor_orders"](status="Draft", limit=5)
        method, args = self.client.calls[0]
        self.assertEqual(method, "ffl_integrations.distributor.api.list_orders")
        self.assertEqual(args, {"status": "Draft", "distributor": None, "limit": 5})

    def test_route_queue_call(self):
        self.tools["distributor_route_queue"](limit=7)
        self.assertEqual(self.client.calls[0],
                         ("ffl_integrations.distributor.router.route_queue", {"limit": 7}))

    def test_catalog_search_call(self):
        self.tools["distributor_catalog_search"](query="glock", limit=3)
        method, args = self.client.calls[0]
        self.assertEqual(method, "ffl_integrations.distributor.api.search")
        self.assertEqual(args, {"query": "glock", "limit": 3, "distributor": None})

    def test_quote_call(self):
        self.tools["distributor_quote"](item_code="ACC-1")
        method, args = self.client.calls[0]
        self.assertEqual(method, "ffl_integrations.distributor.api.quote")
        self.assertEqual(args, {"item_code": "ACC-1", "sku": None, "distributor": None})

    def test_check_availability_call(self):
        self.tools["distributor_check_availability"](lines=[{"sku": "A", "qty": 1}])
        method, args = self.client.calls[0]
        self.assertEqual(method, "ffl_integrations.distributor.api.check_availability")
        self.assertEqual(args["lines"], [{"sku": "A", "qty": 1}])

    def test_precheck_fds_call(self):
        self.tools["distributor_precheck_fds"](do_name="DO-1")
        self.assertEqual(self.client.calls[0],
                         ("ffl_integrations.distributor.router.precheck_fds",
                          {"do_name": "DO-1"}))

    def test_fulfillment_options_call(self):
        self.tools["distributor_fulfillment_options"](woo_online_order="WOO-1")
        self.assertEqual(
            self.client.calls[0],
            ("ffl_integrations.distributor.options.fulfillment_options_for_order",
             {"woo_online_order": "WOO-1"}))

    def test_fulfillment_options_lives_in_the_options_module_not_api(self):
        """It is the ONLY tool served from `distributor.options`. Pinning that here
        because a plausible-looking `...api.fulfillment_options_for_order` would pass
        every other test in this file and only fail against a live POS."""
        self.tools["distributor_fulfillment_options"](woo_online_order="WOO-1")
        method, _ = self.client.calls[0]
        self.assertTrue(method.startswith("ffl_integrations.distributor.options."))

    def test_reads_need_no_confirm(self):
        self.tools["distributor_orders"]()
        self.tools["distributor_route_queue"]()
        self.tools["distributor_fulfillment_options"](woo_online_order="WOO-1")
        self.assertEqual(len(self.client.calls), 3)

    # ---- queue actions: gates fire BEFORE any network call ---------------

    def test_confirm_order_refuses_without_confirm(self):
        with self.assertRaises(WriteRefused):
            self.tools["distributor_confirm_order"](do_name="DO-1")
        self.assertEqual(self.client.calls, [], "refusal must precede the call")

    def test_confirm_order_proceeds_with_confirm(self):
        self.tools["distributor_confirm_order"](do_name="DO-1", confirm=True)
        self.assertEqual(self.client.calls[0],
                         ("ffl_integrations.distributor.api.confirm_order",
                          {"do_name": "DO-1"}))

    def test_cancel_requires_a_reason_and_confirm(self):
        with self.assertRaises(Exception):
            self.tools["distributor_cancel_order"](do_name="DO-1", reason="",
                                                   confirm=True)
        with self.assertRaises(WriteRefused):
            self.tools["distributor_cancel_order"](do_name="DO-1", reason="dup order")
        self.assertEqual(self.client.calls, [])

    def test_cancel_passes_the_stripped_reason(self):
        self.tools["distributor_cancel_order"](do_name="DO-1", reason="  dup  ",
                                               confirm=True)
        method, args = self.client.calls[0]
        self.assertEqual(method, "ffl_integrations.distributor.api.cancel_order")
        self.assertEqual(args, {"do_name": "DO-1", "reason": "dup"})

    def test_reroute_refuses_without_confirm(self):
        with self.assertRaises(WriteRefused):
            self.tools["distributor_reroute"](woo_online_order="WOO-1")
        self.assertEqual(self.client.calls, [])

    def test_reroute_proceeds_with_confirm(self):
        self.tools["distributor_reroute"](woo_online_order="WOO-1", confirm=True)
        self.assertEqual(self.client.calls[0],
                         ("ffl_integrations.distributor.router.reroute",
                          {"woo_online_order": "WOO-1"}))

    def test_update_order_ffl_refuses_without_confirm(self):
        with self.assertRaises(WriteRefused):
            self.tools["distributor_update_order_ffl"](do_name="DO-1",
                                                       ffl_license="1-23")
        self.assertEqual(self.client.calls, [])

    def test_update_order_ffl_call(self):
        self.tools["distributor_update_order_ffl"](do_name="DO-1", ffl_license="1-23",
                                                   confirm=True)
        method, args = self.client.calls[0]
        self.assertEqual(method, "ffl_integrations.distributor.router.update_order_ffl")
        self.assertEqual(args, {"do_name": "DO-1", "ffl_license": "1-23"})


class CpaModeUnchanged(unittest.TestCase):
    """The CPA read-only surface is a security boundary — adding a whole new tool
    module must not widen it by accident."""

    def test_cpa_allowlist_gains_nothing(self):
        from gunstore_mcp import modes

        self.assertEqual(len(modes.CPA_TOOL_NAMES), 18)
        self.assertFalse([n for n in modes.CPA_TOOL_NAMES if n.startswith("distributor_")])


if __name__ == "__main__":
    unittest.main()
