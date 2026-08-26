# gunstore-pos-mcp — POS 的 MCP 服务器(Python/uv)

gunstore-pos 平台的 MCP server 源码仓(83 工具 = 10 个通用 Frappe CRUD + 57 个业务工具 + 11 个分销商工具 + 5 个 CPA 报表工具:寄售出库/订单履约/4473/RSR/FastBound/Woo/GunBroker/库存/FFL/财税报表;**默认注册 77 个**——4 个分销商队列动作需 `GUNSTORE_MCP_DISTRIBUTOR_ACTIONS=1`、2 个 GunBroker 写动作需 `GUNSTORE_MCP_GUNBROKER_ACTIONS=1` 显式开启,否则物理不注册)。工具清单与语义见 `TOOLS.md`。gunstore-pos 仓的 `.mcp.json` 以 `uv run --directory <本仓> gunstore-mcp` 方式引用。

**模式**:`GUNSTORE_MCP_MODE=cpa` 启动只读会计面(恰 18 工具,写面物理不注册 + client 层方法 allowlist + Settings 读 blocklist 三层防御,见 `gunstore_mcp/modes.py`);默认 `full` 全量。未知模式值拒绝启动(fail-closed)。

**两个动作闸**(互相独立,也都独立于 `GUNSTORE_MCP_MODE`;开任何一个都**不会**给 cpa 面加工具):
- `GUNSTORE_MCP_DISTRIBUTOR_ACTIONS=1` → 那 4 个分销商动作(confirm/cancel/reroute/update_order_ffl)
- `GUNSTORE_MCP_GUNBROKER_ACTIONS=1` → `gb_push_serial` / `gb_end_listing`(**只有写的那两个**;`gb_test_connection` / `gb_listing_status` 永远注册——查看和探活正是你希望人在动手前先做的事)

默认都**物理不注册**——与 cpa 模式同一姿态:"存在但拒绝"挡不住"agent 自认为该确认",而用户级实例真的指向 prod。此处不像 mode 那样对未知值拒绝启动:任何非显式真值都=关,方向天然 fail-closed。

**`gb_push_serial` 为什么够格进这个闸**:它把一把真枪挂上公开拍卖行,买家可以在任何人发现之前拍下,撤下来要人去 GunBroker 站点手动做。`gb_end_listing` 是它的配对项——两者属同一个操作员决定,拆开会造成"能结束不能重挂"。

## 命令
- 测试:`uv run --with pytest pytest`(pytest 不在项目依赖里,用 --with 注入)
- 本地运行:`uv run gunstore-mcp`(需环境变量指向目标 Frappe 站点)

## 关键 gotcha
- **运行实例可能指向 prod POS**。改本仓代码 ≠ 可以拿连接中的 MCP 工具打 prod;联调一律配置指向 `dev.localhost:8000`(gunstore-pos `make dev-up` 起的本地站)。
- 工具行为改动要同步更新 `TOOLS.md`。**工具总数钉在 6 处,改一个就要改全部**:`TOOLS.md` §10 开头 + 文末脚注 / 本文件 / `README.md` / `tests/test_modes.py::test_full_mode_registers_the_whole_surface_including_the_cpa_18`(总数)/ `tests/test_curated.py::test_curated_tool_count_pinned`(curated 桶)/ `tests/test_distributor.py::test_distributor_tool_count_pinned`(分销商桶)。三条测试是硬闸——加一个模块必然先被它们拦下,这是好事。**注意这个数字本身历史上被低估过两次**(先写 3 处、后写 5 处),每次都是"又冒出一处没跟着改";加新桶时请连同本行一起更新计数。**`tests/test_doc_counts.py` 才是真闸**(它自己算 live 计数再逐处比对,上面这份手写清单按其 docstring 的说法必然会烂);新增**注册期开关**时要同时扩 `_count()` / `_live()`,否则默认面的数字会被开发者自己 shell 里的环境变量决定。
- 服务端签名以 gunstore-pos 源码为准,落码前逐个核对——MCP 只是薄包装,签名漂移不会在本仓测试里暴露(测试全 mock)。

## 部署政策
交付止于 commit/PR + 本地(dev 站)验证。任何对 prod 的调用/发布由主会话经用户确认执行。
