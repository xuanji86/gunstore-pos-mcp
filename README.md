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
- **Safety**: delete/cancel/submit and destructive methods — including this
  domain's own high-consequence verbs (dispose / push / charge / consolidate /
  ship / return / receive / sold / settle / onboard) —
  require `confirm=true`;
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

> **中文速查手册（按"你想干什么"组织，含安全须知与替代路径）：[TOOLS.md](TOOLS.md)**

67 tools total: 10 generic + 52 curated + 5 CPA reports.

**Modes**: `GUNSTORE_MCP_MODE=cpa` starts a read-only accountant surface —
exactly 18 tools (the write surface is never registered), a per-name read-only
method allowlist at the client layer, and the 7 integration Settings doctypes
blocked from reads. Default (`full`) is the whole surface. Register a second
server entry (e.g. `gunstore-pos-cpa`) with the same command plus
`"env": {"GUNSTORE_MCP_MODE": "cpa"}` to run both side by side.

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
| `get_settings` / `update_settings` | `ffl` \| `fastbound` \| `rsr` \| `payroc` \| `woocommerce` \| `dealer` \| `shipstation` |
| `find_item` / `item_stock` / `available_serials` | typeahead item search / stock per item / in-stock serials + per-gun prices |
| `firearms_in_stock` | the Firearms In Stock report |
| `receive_goods` | Purchase Receipt + FFL acquisitions + FastBound push (`confirm`) |
| `add_stock` / `set_stock` | non-serialized stock add / absolute set (`confirm`) |
| `toggle_service_need` | gunsmith flag on a Serial No (`confirm`) |
| `rsr_catalog_search` / `rsr_sync_catalog` / `rsr_test_connection` | RSR catalog search / full sync / FTPS probe |
| `promote_to_item` / `backfill_from_rsr` | RSR catalog row → sellable Item / backfill Item fields (`confirm`) |
| `fastbound_test_connection` / `push_serial_to_fastbound` / `boundbook_reconcile` | FB probe / per-gun correction push (`confirm`) / bound-book reconcile (apply needs `confirm`) |
| `atf_verify_ffl` / `verify_supplier_ffl` / `reverify_all_ffls` | ATF eZ-Check verifies (`confirm`) |
| `woo_test_connection` / `woo_push_item` / `woo_delist_item` / `woo_reconcile` | store probe / list / delist / reconcile an Item — all take `site: retail\|dealer` (writes need `confirm`) |
| `woo_push_serial` / `woo_delist_serial` | list / delist ONE gun (SKU `item_code::serial`; `site`; `confirm`) |
| `set_serial_title` | per-gun Woo listing title (writes `Serial No.item_name`; takes effect on next push) |
| `pending_orders` / `pending_web_orders` | the Pending Order queue: counter/dealer rows + paid web orders (read-only; consignments live in `consignment_queue`) |
| `dispose_order` / `dispose_web_order` | book the FFL transfer dispositions — stock-out + FastBound push (`confirm`) |
| `record_payment` | Payment Entry against an unpaid submitted invoice; Zelle needs `transaction_number` (`confirm`) |
| `cancel_order` | cancel a submitted counter/dealer order — cascades disposition/stock/FastBound/ShipStation reversal + refund (`confirm` + `reason`) |
| `push_shipment` / `mark_shipped_manually` / `shipstation_test_connection` | ShipStation label push (`confirm`) / no-push escape hatch (`confirm`) / probe |
| `consignment_queue` / `consignment_dealers` / `consignment_serials` / `consignment_dealer_orders` | outbound-consignment reads: At-Dealer queue / shippable FFL dealers / pickable serials / settlement queue |
| `create_consignment_out` / `ship_consignment_out` / `push_consignment_shipment` / `mark_consignment_shipped` | build / dispose+ship / ShipStation push / manual-ship w/ tracking (`confirm`) |
| `retry_consignment_invoice` / `return_consignment_lines` / `cancel_consignment` | settlement-invoice retry / take unsold guns back / cancel line-or-draft (`confirm`; cancel needs `reason`) |
| `start_4473` / `manager_override_4473` / `start_transfer_4473` | 4473 kickoff / stuck-sale manager override / customer transfer (`confirm`) |
| `upload_attachment` | multipart file upload → File doc, optionally attached to a doctype+name / Attach field |

### CPA reports (read-only; registered in both modes)
| Tool | Purpose |
|---|---|
| `sales_report` | the POS Sales Report, payload passed through unchanged (views Order / Order Detail / Product; channel POS/Web/B2B-Manual) |
| `gl_entries` | GL rows for a date range (`is_cancelled=0` always; explicit `truncated:true`) |
| `financial_statement` | P&L / Balance Sheet (Date Range) / Trial Balance (fiscal-year auto-resolved) |
| `tax_liability` | sales-tax liability roll-forward from the GL — accounts resolved from the default sales-tax template, vouchers bucketed fail-closed, cent-exact identity asserted |
| `ar_ap_summary` | aged AR / AP as of a date (Posting Date basis, 30/60/90/120) |

## Security notes

- Uses the key's user (Administrator) = full access. Run **locally only**; keep
  `.env` out of git (it is, by default).
- Credentials never transit the MCP: password-type and credential-named fields are
  stripped from every write. Set secrets in Desk directly.
- All writes are logged by Frappe under the key's user (audit trail).
- To revoke access, regenerate that user's keys in Desk.
