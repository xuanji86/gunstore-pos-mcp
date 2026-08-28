# gunstore-pos —— Claude Code 插件

GunStore-POS(Frappe/ERPNext)MCP 服务器。包内含完整 Python 包源码、`pyproject.toml`
与 `uv.lock`;依赖由 **uv** 在首次启动时自动解好(首启多几秒,之后走缓存)。
前提:机器上有 `uv`。

一个插件注册**两个 server**:

| server | 说明 |
|---|---|
| `gunstore-pos` | 完整工具面(含写操作) |
| `gunstore-pos-cpa` | 只读会计视角,写工具在代码层就没注册 |

装好后用 `/mcp` 看各自的实际工具清单。

## 安装

- **组织分发**:在 claude.ai 组织设置的插件页上传本 zip。
- **本机试用**:`claude --plugin-dir /路径/gunstore-pos.zip`(也可指向解压后的目录)。

## 配置密钥(二选一)

包内**不含任何密钥**,格式见同目录 `.env.example`。

**A. 指向一个 .env 文件(推荐)** —— `~/.claude/settings.json`:

```json
{ "env": { "GUNSTORE_ENV_FILE": "/绝对路径/gunstore.env" } }
```

**B. 直接写进 settings.json 的 `env` 块**:`FRAPPE_BASE_URL`、`FRAPPE_API_KEY`、
`FRAPPE_API_SECRET`(可选 `FRAPPE_TIMEOUT`、`FRAPPE_WRITE_DENYLIST`)。

## 注意

- 工具名带插件前缀:`mcp__plugin_gunstore-pos_gunstore-pos__*` 与
  `…_gunstore-pos-cpa__*`。写死旧名 `mcp__gunstore-pos__*` 的地方需同步改。
- 装上后把 `~/.claude.json` 里原来的 `mcpServers.gunstore-pos` / `gunstore-pos-cpa` 删掉。
- `FRAPPE_BASE_URL` 指向 prod 时,所有写工具直接落生产库。
