"""GunStore-POS admin MCP server (stdio).

Run: `gunstore-mcp` (console script) or `python -m gunstore_mcp.server`.
Credentials come from mcp/.env (see .env.example).

Modes (GUNSTORE_MCP_MODE): "full" (default) = the whole surface; "cpa" = the
read-only accountant surface (exactly the 19 tools in modes.CPA_TOOL_NAMES; the
write tools are never registered).

GUNSTORE_MCP_DISTRIBUTOR_ACTIONS=1 additionally opts into the 4 distributor queue
actions, which are NOT registered otherwise. Sizes are asserted in tests rather
than restated here — this docstring is where the last stale count lived."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import __version__
from .modes import CPA_MODE, CPA_TOOL_NAMES, FULL_MODE, FilteredMCP, get_mode
from .tools import curated, distributor, generic, reports


def register_tools(mcp, mode: str | None = None) -> None:
    """Register the tool surface for `mode` (default: env GUNSTORE_MCP_MODE).

    cpa mode routes every registration through FilteredMCP so only the
    18 allowlisted tools ever reach tools/list."""
    mode = mode or get_mode()
    if mode not in (FULL_MODE, CPA_MODE):
        raise RuntimeError(f"Unknown server mode {mode!r}.")
    target = mcp if mode == FULL_MODE else FilteredMCP(mcp, CPA_TOOL_NAMES)
    generic.register(target)
    curated.register(target)
    distributor.register(target)
    reports.register(target)


def build() -> FastMCP:
    mode = get_mode()
    mcp = FastMCP("gunstore-pos" if mode == FULL_MODE else "gunstore-pos-cpa")
    # FastMCP takes no version; without this serverInfo reports the mcp SDK's
    # version, so clients can't tell which build of ours they're talking to.
    mcp._mcp_server.version = __version__
    register_tools(mcp, mode)
    return mcp


mcp = build()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
