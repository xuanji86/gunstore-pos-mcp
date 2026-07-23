# gunstore-pos-mcp — POS 的 MCP 服务器(Python/uv)

gunstore-pos 平台的 MCP server 源码仓(78 工具 = 10 个通用 Frappe CRUD + 53 个业务工具 + 10 个分销商工具 + 5 个 CPA 报表工具:寄售出库/订单履约/4473/RSR/FastBound/Woo/库存/FFL/财税报表)。工具清单与语义见 `TOOLS.md`。gunstore-pos 仓的 `.mcp.json` 以 `uv run --directory <本仓> gunstore-mcp` 方式引用。

**模式**:`GUNSTORE_MCP_MODE=cpa` 启动只读会计面(恰 18 工具,写面物理不注册 + client 层方法 allowlist + Settings 读 blocklist 三层防御,见 `gunstore_mcp/modes.py`);默认 `full` 全量。未知模式值拒绝启动(fail-closed)。

## 命令
- 测试:`uv run --with pytest pytest`(pytest 不在项目依赖里,用 --with 注入)
- 本地运行:`uv run gunstore-mcp`(需环境变量指向目标 Frappe 站点)

## 关键 gotcha
- **运行实例可能指向 prod POS**。改本仓代码 ≠ 可以拿连接中的 MCP 工具打 prod;联调一律配置指向 `dev.localhost:8000`(gunstore-pos `make dev-up` 起的本地站)。
- 工具行为改动要同步更新 `TOOLS.md`。**工具总数钉在 5 处,改一个就要改全部**:`TOOLS.md` §10 开头 + 文末脚注 / 本文件 / `README.md` / `tests/test_modes.py::test_full_mode_registers_78_tools_including_the_cpa_18`(总数)/ `tests/test_curated.py::test_curated_tool_count_pinned`(curated 桶)。两条测试是硬闸——加一个模块必然先被它们拦下,这是好事。
- 服务端签名以 gunstore-pos 源码为准,落码前逐个核对——MCP 只是薄包装,签名漂移不会在本仓测试里暴露(测试全 mock)。

## 部署政策
交付止于 commit/PR + 本地(dev 站)验证。任何对 prod 的调用/发布由主会话经用户确认执行。
