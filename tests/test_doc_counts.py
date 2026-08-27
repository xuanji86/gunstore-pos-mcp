"""Documentation-vs-code drift on TOOL COUNTS.

Why this file exists: the tool total has now been wrong or under-tracked THREE times
(the meta-note said it was pinned in 3 places, then 5, then 6 — each time because a
new spot quoted the number and nobody knew). Hand-maintained lists of "places to
update" decay by construction; the fix is to make the count self-checking.

Two layers, because they fail differently:

* **exact claims** — the canonical sentence in each doc must equal the live count,
  bucket by bucket. If a doc is rephrased so the regex no longer matches, that is a
  FAILURE, not a silent pass: a drift test that quietly finds nothing is exactly the
  blanket-stub trap (a check that cannot fail proves nothing).
* **the sweep** — ANY "<N> tools" / "<N> 工具" claim anywhere in the package, the
  docs, or the tests must be a number that is actually true of the surface. This is
  what catches stale prose far from the pins: `server.py` still advertised a
  "67-tool surface" and a test docstring still said "67 tools", neither of which any
  per-file pin was ever going to notice.
"""
from __future__ import annotations

import os
import pathlib
import re
import unittest
from unittest.mock import patch

from gunstore_mcp.modes import CPA_TOOL_NAMES
from gunstore_mcp.tools import curated, distributor, generic, reports

ROOT = pathlib.Path(__file__).resolve().parent.parent
SELF = pathlib.Path(__file__).name


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


_GATES = (distributor.ACTIONS_ENV, curated.GUNBROKER_ACTIONS_ENV)


def _names(module, *, actions: str | None = None,
           gb_actions: str | None = None) -> frozenset:
    # Both registration gates are cleared first, then set explicitly. A stray
    # GUNSTORE_MCP_* in the developer's shell must not be able to decide what
    # "the live surface" is, or these counts would differ per machine.
    env = {k: v for k, v in os.environ.items() if k not in _GATES}
    if actions is not None:
        env[distributor.ACTIONS_ENV] = actions
    if gb_actions is not None:
        env[curated.GUNBROKER_ACTIONS_ENV] = gb_actions
    mcp = _FakeMCP()
    # _load_env stubbed for the same reason as in test_distributor: a developer's own
    # mcp/.env must not be able to decide what "the live surface" is here, or this
    # guard would pass or fail depending on whose machine it runs on.
    with patch.dict(os.environ, env, clear=True), \
            patch.object(distributor, "_load_env", lambda: None), \
            patch.object(curated, "_load_env", lambda: None):
        module.register(mcp)
    return frozenset(mcp.tools)


def _count(module, **kw) -> int:
    return len(_names(module, **kw))


def _live() -> dict:
    generic_n = _count(generic)
    reports_n = _count(reports)
    cur_on_names = _names(curated, gb_actions="1")
    cur_off_names = _names(curated, gb_actions=None)
    cur_on, cur_off = len(cur_on_names), len(cur_off_names)
    dist_on = _count(distributor, actions="1")
    dist_off = _count(distributor, actions=None)
    return {
        "generic": generic_n,
        "curated": cur_on,
        "curated_default": cur_off,
        "gb_actions": cur_on - cur_off,
        # the GunBroker reads, which are NOT gated. Counted off the surface, not
        # written down as "<total gb tools> minus the writes": that literal was a
        # hand-maintained number in the one file whose whole purpose is to abolish
        # them, and adding gb_pull_orders in PR-4b silently made it wrong.
        "gb_readonly": sum(1 for n in cur_off_names if n.startswith("gb_")),
        "reports": reports_n,
        "distributor": dist_on,
        "distributor_default": dist_off,
        "actions": dist_on - dist_off,
        "total": generic_n + cur_on + dist_on + reports_n,
        "default": generic_n + cur_off + dist_off + reports_n,
        "cpa_surface": len(CPA_TOOL_NAMES),
    }


# (file, regex with ONE capture group, which live count it must equal)
CLAIMS = [
    ("README.md", r"(\d+) tools total", "total"),
    ("README.md", r"(\d+) generic", "generic"),
    ("README.md", r"(\d+) curated", "curated"),
    # anchored on the trailing " +" so it cannot latch onto the prose phrase
    # "the 4 distributor queue actions" — a cost of matching EVERY occurrence
    # rather than the first: loose patterns start colliding with sentences.
    ("README.md", r"(\d+) distributor \+", "distributor"),
    ("README.md", r"(\d+) CPA reports", "reports"),
    ("README.md", r"(\d+) register by default", "default"),
    ("CLAUDE.md", r"\((\d+) 工具", "total"),
    ("CLAUDE.md", r"(\d+) 个通用 Frappe CRUD", "generic"),
    ("CLAUDE.md", r"(\d+) 个业务工具", "curated"),
    ("CLAUDE.md", r"(\d+) 个分销商工具", "distributor"),
    ("CLAUDE.md", r"(\d+) 个 CPA 报表工具", "reports"),
    ("CLAUDE.md", r"默认注册 (\d+) 个", "default"),
    ("CLAUDE.md", r"恰 (\d+) 工具", "cpa_surface"),
    ("TOOLS.md", r"工具总数 (\d+)", "total"),
    ("TOOLS.md", r"(\d+) 个通用 \+", "generic"),
    ("TOOLS.md", r"(\d+) 个专用", "curated"),
    # anchored on the trailing " +" so it cannot latch onto "4 个分销商队列动作"
    ("TOOLS.md", r"(\d+) 个分销商 \+", "distributor"),
    ("TOOLS.md", r"(\d+) 个报表", "reports"),
    ("TOOLS.md", r"全部 (\d+) 工具", "total"),
    ("TOOLS.md", r"默认注册 (\d+)", "default"),
    ("TOOLS.md", r"恰注册其中 (\d+) 个", "cpa_surface"),
    ("TOOLS.md", r"只读 (\d+)", "distributor_default"),
    ("TOOLS.md", r"动作 (\d+)", "actions"),
    # GunBroker buckets. Deliberately NOT phrased "只读 N" / "动作 N": those two
    # patterns match every occurrence in the file, so reusing the wording in §2b
    # would make the GunBroker numbers get checked against the distributor's.
    ("TOOLS.md", r"GunBroker 只读工具 (\d+)", "gb_readonly"),
    ("TOOLS.md", r"GunBroker 写工具 (\d+)", "gb_actions"),
    # The size of each opt-in SET, as the three intro paragraphs phrase it —
    # "the 3 GunBroker write actions" / "3 个 GunBroker 写动作", and the same for
    # the distributor's 4. Five sites quote the GunBroker number and until now
    # exactly one of them was pinned.
    #
    # The sweep below does not cover this, and cannot be made to: it only asks
    # whether a quoted number is SOME live bucket size, and 2 is one (gb_readonly).
    # Measured, not assumed — with these four rows absent, editing all four
    # unpinned sites from 3 back to 2 left the suite entirely green. A count is
    # only guarded where something knows which count it is.
    ("README.md", r"(\d+) GunBroker write actions", "gb_actions"),
    ("CLAUDE.md", r"(\d+) 个 GunBroker 写动作", "gb_actions"),
    ("TOOLS.md", r"(\d+) 个 GunBroker 写动作", "gb_actions"),
    # …and the distributor's, which has the identical hole and has simply never
    # moved. Anchored on 队列动作 so it cannot collide with "(\d+) 个分销商 \+".
    ("README.md", r"(\d+) distributor queue actions", "actions"),
    ("CLAUDE.md", r"(\d+) 个分销商队列动作", "actions"),
    ("TOOLS.md", r"(\d+) 个分销商队列动作", "actions"),
]

# "12 tools", "12-tool", "12 工具", "12 个工具"
_SWEEP = (re.compile(r"(\d+)[ -]tools?\b"), re.compile(r"(\d+)\s*个?工具"))
_SWEPT_FILES = ("README.md", "CLAUDE.md", "TOOLS.md")


class ExactClaims(unittest.TestCase):
    def setUp(self):
        self.live = _live()

    def test_every_documented_count_matches_the_registered_surface(self):
        """EVERY occurrence must be true, not just the first.

        re.search stops at the first hit, which let a stale "只读 6" survive three
        lines below a correct "只读 7" — the guard read the right number and never
        looked further. A doc claim is not "the first place a number appears", it is
        every place it appears."""
        for fname, pattern, key in CLAIMS:
            text = (ROOT / fname).read_text(encoding="utf-8")
            hits = list(re.finditer(pattern, text))
            self.assertTrue(
                hits, f"{fname}: no match for {pattern!r} — the claim was rephrased or "
                "removed, so this pin stopped guarding anything. Restore the wording "
                "or update CLAIMS deliberately.")
            for m in hits:
                line = text.count("\n", 0, m.start()) + 1
                self.assertEqual(
                    int(m.group(1)), self.live[key],
                    f"{fname}:{line} claims {m.group(1)} for {key}, live surface has "
                    f"{self.live[key]}")

    def test_the_buckets_add_up_to_the_total(self):
        L = self.live
        self.assertEqual(
            L["total"], L["generic"] + L["curated"] + L["distributor"] + L["reports"])
        # Two independent registration gates now, so the default surface is the
        # total less BOTH opt-in sets.
        self.assertEqual(L["default"], L["total"] - L["actions"] - L["gb_actions"])
        self.assertEqual(L["curated"], L["curated_default"] + L["gb_actions"])

    def test_both_registration_gates_actually_hold_something_back(self):
        """A gate that gates nothing is the failure mode these counts exist to
        catch: turn either one into a no-op and the arithmetic above still
        balances, because everything would simply always be registered."""
        L = self.live
        self.assertEqual(L["actions"], 4)
        self.assertEqual(L["gb_actions"], 3)
        self.assertEqual(L["gb_readonly"], 2)

    def test_the_gunbroker_buckets_are_read_off_the_surface(self):
        """gb_readonly is derived, so it has to be shown to be derived: every gb_
        tool is in exactly one of the two buckets, and neither is empty. A typo in
        the prefix would otherwise report 0 reads and quietly agree with a doc that
        also said 0."""
        gated = _names(curated, gb_actions="1") - _names(curated, gb_actions=None)
        ungated = {n for n in _names(curated, gb_actions=None) if n.startswith("gb_")}
        self.assertTrue(gated and ungated)
        self.assertTrue(all(n.startswith("gb_") for n in gated), sorted(gated))
        self.assertEqual(len(gated), self.live["gb_actions"])
        self.assertEqual(len(ungated), self.live["gb_readonly"])


class NoStaleCountAnywhere(unittest.TestCase):
    """The sweep. Every tool-count claim in prose must be a number the surface can
    actually produce — this is what catches a stale figure in a module docstring,
    which no per-file pin was ever looking at."""

    def test_no_prose_quotes_a_count_the_surface_cannot_produce(self):
        live = _live()
        legit = set(live.values())
        targets = [ROOT / f for f in _SWEPT_FILES]
        targets += [p for p in (ROOT / "gunstore_mcp").rglob("*.py")]
        targets += [p for p in (ROOT / "tests").glob("*.py") if p.name != SELF]

        bad = []
        for path in targets:
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                for rx in _SWEEP:
                    for m in rx.finditer(line):
                        if int(m.group(1)) not in legit:
                            bad.append(
                                f"{path.relative_to(ROOT)}:{lineno} claims "
                                f"{m.group(0)!r}")
        self.assertEqual(
            bad, [],
            "stale tool counts (legit values: "
            f"{sorted(legit)}):\n  " + "\n  ".join(bad))


if __name__ == "__main__":
    unittest.main()
