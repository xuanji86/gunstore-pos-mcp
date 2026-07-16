# gunstore-pos-mcp — POS 的 MCP 服务器(Python/uv)

gunstore-pos 平台的 MCP server 源码仓(62 工具 = 10 个通用 Frappe CRUD + 52 个业务工具:寄售出库/订单履约/4473/RSR/FastBound/Woo/库存/FFL)。工具清单与语义见 `TOOLS.md`。gunstore-pos 仓的 `.mcp.json` 以 `uv run --directory <本仓> gunstore-mcp` 方式引用。

## 命令
- 测试:`uv run --with pytest pytest`(pytest 不在项目依赖里,用 --with 注入)
- 本地运行:`uv run gunstore-mcp`(需环境变量指向目标 Frappe 站点)

## 关键 gotcha
- **运行实例可能指向 prod POS**。改本仓代码 ≠ 可以拿连接中的 MCP 工具打 prod;联调一律配置指向 `dev.localhost:8000`(gunstore-pos `make dev-up` 起的本地站)。
- 工具行为改动要同步更新 `TOOLS.md`(工具总数三处要一致:TOOLS.md 脚注 / 本文件 / README;测试里 test_curated_tool_count_pinned 钉住计数)。
- 服务端签名以 gunstore-pos 源码为准,落码前逐个核对——MCP 只是薄包装,签名漂移不会在本仓测试里暴露(测试全 mock)。

## 部署政策
交付止于 commit/PR + 本地(dev 站)验证。任何对 prod 的调用/发布由主会话经用户确认执行。
