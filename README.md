# GunStore-POS Admin MCP

A local [MCP](https://modelcontextprotocol.io) server that wraps the GunStore-POS
Frappe REST API, so you can read and change **production** settings/content from
Claude or Codex — toggle integration config, edit item pricing/listing, fix
records, trigger RSR/FastBound/ATF operations, run the Firearms-In-Stock report.

> **Companion repo:** [`firearm-listing-import`](https://github.com/xuanji86/firearm-listing-import) —
> a Claude Code / Codex skill that uses this MCP (per-gun photos + descriptions → Serial No →
> WooCommerce). Extracted from the gunstore-pos app as a standalone, separately distributable package.

## How it works

- A small **generic backbone** (`frappe_*` tools) covers every doctype and every
  whitelisted method — present and future. A **curated layer** makes the frequent
  settings/sync/report ops one call.
- Talks to Frappe over HTTPS with token auth (`Authorization: token key:secret`).
- **Safety**: delete/cancel/submit and destructive methods require `confirm=true`;
  password/credential fields are never transmitted (set those in Desk);
  schema/permission doctypes are read-only.

## Setup

### 1. Generate a Frappe API key
In Desk as the user you want to act as (Administrator): top-right avatar →
**My Settings** → **API Access** → **Generate Keys**. Copy the **API Key** and
**API Secret** (the secret is shown only once).

### 2. Configure credentials
```bash
cp .env.example .env
# edit .env: FRAPPE_BASE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET
```
`.env` is git-ignored. Point at dev first (`http://dev.localhost:8000`) to test,
then switch to prod (`https://pos.oldsteelarsenal.com`).

### 3. Install
```bash
uv sync          # creates .venv and installs deps
```

### 4. Register with your agent

`/path/to/gunstore-pos-mcp` below is wherever you cloned this repo (the package is
at the repo root). The server loads `.env` by its own file path, so credentials
never go in the agent config.

**Claude Code** — add to `.mcp.json` (project) or run `claude mcp add`:
```json
{
  "mcpServers": {
    "gunstore-pos": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/gunstore-pos-mcp", "gunstore-mcp"]
    }
  }
}
```
**Claude Desktop** — the same block in `claude_desktop_config.json`.

**Codex** — add to `~/.codex/config.toml`, then **restart Codex** (it reads MCP
servers at startup):
```toml
[mcp_servers.gunstore-pos]
command = "uv"            # or an absolute path to uv if it isn't on Codex's PATH
args = ["run", "--directory", "/path/to/gunstore-pos-mcp", "gunstore-mcp"]
startup_timeout_sec = 120
```
Verify with a quick stdio handshake (`initialize` + `tools/list`) or just list
tools from within Codex.

Secrets stay in `.env` (loaded by the server), not in the agent config.

## Tools

### Generic backbone
| Tool | Purpose |
|---|---|
| `frappe_list_documents` | list any doctype (filters / fields / limit; `limit=0` = all) |
| `frappe_get_document` | fetch one doc (Single: `name == doctype`) |
| `frappe_describe_doctype` | fields incl. custom fields; flags password fields |
| `frappe_create_document` | create (credential fields stripped) |
| `frappe_update_document` | update (credential fields stripped) |
| `frappe_delete_document` | delete — needs `confirm=true` |
| `frappe_submit_document` | submit a draft — needs `confirm=true` |
| `frappe_cancel_document` | cancel a submitted doc — needs `confirm=true` |
| `frappe_run_method` | call any whitelisted method by dotted path |
| `frappe_run_report` | run a Script/Query report |

### Curated
| Tool | Purpose |
|---|---|
| `get_settings` / `update_settings` | `ffl` \| `fastbound` \| `rsr` \| `payroc` |
| `rsr_sync_catalog` / `rsr_test_connection` | RSR catalog sync / FTPS probe |
| `fastbound_test_connection` | FastBound API probe |
| `atf_verify_ffl` | EZ Check verify + upsert record (needs `confirm=true`) |
| `firearms_in_stock` | the Firearms In Stock report |
| `find_item` | typeahead item search |
| `woo_test_connection` | WooCommerce API probe |
| `woo_push_item` / `woo_delist_item` / `woo_reconcile` | list / delist / reconcile an Item on Woo (need `confirm=true`) |
| `set_serial_title` | set a per-gun Woo listing title (writes `Serial No.item_name`; takes effect on next push) |

## Security notes

- Uses the key's user (Administrator) = full access. Run **locally only**; keep
  `.env` out of git (it is, by default).
- Credentials never transit the MCP: password-type and credential-named fields are
  stripped from every write. Set secrets in Desk directly.
- All writes are logged by Frappe under the key's user (audit trail).
- To revoke access, regenerate that user's keys in Desk.
