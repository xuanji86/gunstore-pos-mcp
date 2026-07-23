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


def _count(module, *, actions: str | None = None) -> int:
    env = {k: v for k, v in os.environ.items() if k != distributor.ACTIONS_ENV}
    if actions is not None:
        env[distributor.ACTIONS_ENV] = actions
    mcp = _FakeMCP()
    with patch.dict(os.environ, env, clear=True):
        module.register(mcp)
    return len(mcp.tools)


def _live() -> dict:
    generic_n = _count(generic)
    curated_n = _count(curated)
    reports_n = _count(reports)
    dist_on = _count(distributor, actions="1")
    dist_off = _count(distributor, actions=None)
    return {
        "generic": generic_n,
        "curated": curated_n,
        "reports": reports_n,
        "distributor": dist_on,
        "distributor_default": dist_off,
        "actions": dist_on - dist_off,
        "total": generic_n + curated_n + dist_on + reports_n,
        "default": generic_n + curated_n + dist_off + reports_n,
        "cpa_surface": len(CPA_TOOL_NAMES),
    }


# (file, regex with ONE capture group, which live count it must equal)
CLAIMS = [
    ("README.md", r"(\d+) tools total", "total"),
    ("README.md", r"(\d+) generic", "generic"),
    ("README.md", r"(\d+) curated", "curated"),
    ("README.md", r"(\d+) distributor", "distributor"),
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
]

# "12 tools", "12-tool", "12 工具", "12 个工具"
_SWEEP = (re.compile(r"(\d+)[ -]tools?\b"), re.compile(r"(\d+)\s*个?工具"))
_SWEPT_FILES = ("README.md", "CLAUDE.md", "TOOLS.md")


class ExactClaims(unittest.TestCase):
    def setUp(self):
        self.live = _live()

    def test_every_documented_count_matches_the_registered_surface(self):
        for fname, pattern, key in CLAIMS:
            text = (ROOT / fname).read_text(encoding="utf-8")
            m = re.search(pattern, text)
            self.assertIsNotNone(
                m, f"{fname}: no match for {pattern!r} — the claim was rephrased or "
                "removed, so this pin stopped guarding anything. Restore the wording "
                "or update CLAIMS deliberately.")
            self.assertEqual(
                int(m.group(1)), self.live[key],
                f"{fname} claims {m.group(1)} for {key}, live surface has "
                f"{self.live[key]}")

    def test_the_buckets_add_up_to_the_total(self):
        L = self.live
        self.assertEqual(
            L["total"], L["generic"] + L["curated"] + L["distributor"] + L["reports"])
        self.assertEqual(L["default"], L["total"] - L["actions"])


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
