# GunStore-POS Admin MCP

A local [MCP](https://modelcontextprotocol.io) server that wraps the GunStore-POS
Frappe REST API, so you can read and change **production** settings/content from
Claude — toggle integration config, edit item pricing/listing, fix records,
trigger RSR/FastBound/ATF operations, run the Firearms-In-Stock report.

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
cd mcp
cp .env.example .env
# edit .env: FRAPPE_BASE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET
```
`.env` is git-ignored. Point at dev first (`http://dev.localhost:8000`) to test,
then switch to prod (`https://pos.oldsteelarsenal.com`).

### 3. Install
```bash
uv sync          # creates .venv and installs deps
```

### 4. Register with Claude
**Claude Code** — add to `.mcp.json` (project) or run `claude mcp add`:
```json
{
  "mcpServers": {
    "gunstore-pos": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/Anji/Desktop/GunStore-POS/mcp", "gunstore-mcp"]
    }
  }
}
```
**Claude Desktop** — the same block in `claude_desktop_config.json`.
Secrets stay in `mcp/.env` (loaded by the server), not in the Claude config.

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

## Security notes

- Uses the key's user (Administrator) = full access. Run **locally only**; keep
  `.env` out of git (it is, by default).
- Credentials never transit the MCP: password-type and credential-named fields are
  stripped from every write. Set secrets in Desk directly.
- All writes are logged by Frappe under the key's user (audit trail).
- To revoke access, regenerate that user's keys in Desk.
