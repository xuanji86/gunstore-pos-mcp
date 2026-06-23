"""GunStore-POS admin MCP server (stdio).

Run: `gunstore-mcp` (console script) or `python -m gunstore_mcp.server`.
Credentials come from mcp/.env (see .env.example)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import curated, generic


def build() -> FastMCP:
    mcp = FastMCP("gunstore-pos")
    generic.register(mcp)
    curated.register(mcp)
    return mcp


mcp = build()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
