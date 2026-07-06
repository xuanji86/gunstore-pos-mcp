# GunStore-POS MCP 工具速查（中文）

> 这份文档按「你想干什么」组织，方便直接对 AI 助手说人话。每个工具标注了
> **读 / 写**、是否需要 `confirm=true`，以及关键参数。英文简表见 README.md。

## ⚠️ 先读我：三件事

1. **这个 MCP 连的是生产环境**（pos.oldsteelarsenal.com + 线上商店）。所有"写"
   都是真实业务操作：上架的枪顾客立刻能买、dispose 会登真实枪支账册。**开发/测试
   一律不用它**，用本地 dev 环境。
2. **confirm 机制**：有后果的操作第一次调用会被拒绝，AI 需要带 `confirm=true` 重调。
   这是给你一个反悔的机会——AI 复述要做的事之后你确认了才会真执行。
3. **凭据永远过不了 MCP**：所有密码/API key 字段写入时自动剥除，读也读不到。
   改密钥去 Desk 后台（My Settings / 各 Settings 页）。

`site` 参数：凡是 Woo 相关工具都可选 `site="retail"`（主店 oldsteelarsenal.com，
默认）或 `site="dealer"`（经销商门户）。

---

## 1. 查东西（全部只读，随便用）

| 你想… | 工具 | 说明 |
|---|---|---|
| 按名字/条码/SKU 找商品 | `find_item` | 输入关键词，返回匹配的 Item |
| 查某商品还剩几个 | `item_stock` | 可一次查多个 item_code |
| 查某型号在库的每把枪和各自售价 | `available_serials` | 返回 {型号: [{serial, sell_price…}]}，便宜的在前 |
| 看全部在库枪支清单 | `firearms_in_stock` | 报表：序列号/厂商/型号/口径/仓库/来源 + FastBound 链接；可按仓库或厂商过滤 |
| 看待处理的柜台/经销商订单 | `pending_orders` | Pending Order 队列：还没 dispose、没收够钱、或还没推 ShipStation 的单子 |
| 看待发货的网店订单 | `pending_web_orders` | 已付款、等 dispose 的 Woo 订单 |
| 搜 RSR 批发目录（不是本店库存） | `rsr_catalog_search` | 按关键词/UPC/RSR 编号/厂商编号搜 |
| 跑任意报表 | `frappe_run_report` | 报表名：`Sales Report`（营收+毛利）、`Pending 4473 Orders`（卡在 4473 的单）、`Open Special Orders`（特殊订货看板）、`Pending Transfer Pickups`（待取的转入枪） |
| 查任何记录 | `frappe_list_documents` / `frappe_get_document` | 万能查询，见第 8 节 |

## 2. 商品上架 / 下架（WooCommerce，主店 + 经销商门户）

| 你想… | 工具 | confirm | 说明 |
|---|---|---|---|
| 上架/更新**一把枪** | `woo_push_serial` | ✅ | 按序列号推，SKU = `型号::序列号`。**只动这一把**——日常首选 |
| 下架**一把枪** | `woo_delist_serial` | ✅ | 商品转草稿 + 库存清零，立刻从店里消失 |
| 上架/更新一个**型号的全部在库枪**（或普通商品） | `woo_push_item` | ✅ | 注意：会把该型号下**每一把** Active 的枪都推一遍 |
| 下架整个型号 | `woo_delist_item` | ✅ | |
| 首次整体上架（型号 + 全部序列号一次推齐） | `woo_reconcile` | ✅ | |
| 给一把枪起独立的商品标题 | `set_serial_title` | — | 写 `Serial No.item_name`；**要再 push 一次才生效** |
| 测试商店连接 | `woo_test_connection` | — | 只读探活 |

以上全部支持 `site="dealer"` 推到经销商门户。

**传照片**：单张可用 `upload_attachment`（见第 7 节）；**批量传图+描述+建相册请走
firearm-listing-import 技能的脚本**——它会先把图缩到 2000px（原图太大会把 Woo
推送搞超时），MCP 不做 resize。

## 3. 收货入库 / 库存调整

| 你想… | 工具 | confirm | 说明 |
|---|---|---|---|
| 正式收货（含枪支） | `receive_goods` | ✅ | 建并提交 Purchase Receipt；枪支自动逐把建 FFL Acquisition 并推 FastBound。枪**必须**走这个，不能用 add_stock |
| 给普通商品加库存 | `add_stock` | ✅ | 弹药/配件等非序列号商品 |
| 盘点后把数量改成实数 | `set_stock` | ✅ | 会留盘点原因的审计记录 |
| 标记/取消"待枪匠维修" | `toggle_service_need` | ✅ | 同步开/关枪匠 ToDo |
| RSR 目录商品转成本店在售 Item | `promote_to_item` | ✅ | 厂商/型号/口径/图自动带入 |
| 用 RSR 数据补全已有 Item 的空字段 | `backfill_from_rsr` | ✅ | 只填空，不覆盖已有值 |

## 4. 订单 → 收款 → 发货（Pending Order 队列的全部动作）

| 你想… | 工具 | confirm | 说明 |
|---|---|---|---|
| 给没付清的单子记一笔收款 | `record_payment` | ✅ | 不填金额=收清尾款；Zelle 必须带 transaction_number |
| **Dispose** 柜台/经销商订单的枪 | `dispose_order` | ✅ | 逐把登转出 disposition：出库存 + 推 FastBound。没付清或收货方 FFL 无效会被服务器拦下。**动手前先核对 FFL 和序列号** |
| **Dispose** 网店订单的枪 | `dispose_web_order` | ✅ | 网店单不推 ShipStation（店里的 Woo 插件自己发货） |
| 把订单推到 ShipStation 买面单 | `push_shipment` | ✅ | 幂等；FFL 无效/没付清会失败保护 |
| 不走 ShipStation、直接标记已发货 | `mark_shipped_manually` | ✅ | 兜底：面单在别处买的/集成关了。枪没 dispose 完会拒绝 |
| 测试 ShipStation 连接 | `shipstation_test_connection` | — | 只读探活 |

典型流程：`pending_orders` 看队列 → 差钱先 `record_payment` → `dispose_order` →
`push_shipment`（网店单则 `pending_web_orders` → `dispose_web_order`，不用推单）。

## 5. 4473 / 合规（FastBound、ATF）

| 你想… | 工具 | confirm | 说明 |
|---|---|---|---|
| 给柜台枪支销售发起 4473 | `start_4473` | ✅ | 发票挂起，去 FastBound 填表；参数是 {发票行: 序列号} 映射 |
| **解卡**：4473 在 FastBound 明明完成了但单子卡住 | `manager_override_4473` | ✅ | 经理权限 + 必须写原因；补出 Retail Sale disposition（标 manual_override 可审计）。**不回推 FastBound**，账册要另行核对 |
| 发起客户转入枪的 4473（收转移费） | `start_transfer_4473` | ✅ | 服务器端建 $0 枪行 + 转移费行的 POS 发票；费率用 `frappe_run_method` 调 `ffl_core.firearm.get_transfer_config` 查 |
| 核验一个 FFL 号（eZ-Check） | `atf_verify_ffl` | ✅ | 在线验证并存/更新 ATF FFL Record |
| 核验某供应商的 FFL | `verify_supplier_ffl` | ✅ | 顺带更新供应商上的核验状态 |
| 把所有 FFL 供应商重验一遍 | `reverify_all_ffls` | ✅ | 批量 |
| 修正已入册枪支的厂商/进口商 | `push_serial_to_fastbound` | ✅ | 原地改 FastBound 账册条目 |
| 对账：FastBound 已 dispose 但本店还显示在库 | `boundbook_reconcile` | 干跑不用；`apply=true` 才要 ✅ | 默认只报告不动库存 |
| 测试 FastBound 连接 | `fastbound_test_connection` | — | 只读 |

## 6. RSR 目录同步

| 你想… | 工具 | confirm |
|---|---|---|
| 立刻全量同步 RSR 目录 | `rsr_sync_catalog` | —（后台跑） |
| 测试 RSR FTPS 连接 | `rsr_test_connection` | — |

（数量增量同步每 15 分钟自动跑；手动触发用
`frappe_run_method` 调 `ffl_integrations.rsr.tasks.sync_quantity_now`。）

## 7. 设置 & 文件

| 你想… | 工具 | 说明 |
|---|---|---|
| 看某个集成的配置 | `get_settings` | `ffl` \| `fastbound` \| `rsr` \| `payroc` \| `woocommerce` \| `dealer` \| `shipstation` |
| 改配置（非密钥字段） | `update_settings` | 密码/密钥字段自动剥除，去 Desk 改 |
| 上传一个本地文件到 POS | `upload_attachment` | 可顺带挂到某条记录（doctype+name）或写进附件字段。默认私有；**要给 Woo 用的商品图必须 `is_private=false`**。批量图片走技能脚本（先 resize） |

## 8. 万能后门（`frappe_*` 通用工具）

上面没有的操作，AI 可以用通用工具直达任何数据和白名单方法——**新功能上线当天就能用，
不用等 MCP 更新**：

- `frappe_list_documents` / `frappe_get_document` / `frappe_describe_doctype` — 查任何 doctype（先 describe 看字段名）
- `frappe_create_document` / `frappe_update_document` — 建/改任何记录（凭据字段自动剥除）
- `frappe_delete_document` / `frappe_submit_document` / `frappe_cancel_document` — 删/提交/作废（都要 confirm）
- `frappe_run_method` — 按点路径调任何白名单方法；方法名含 delete/cancel/refund/**dispose/push/charge/consolidate** 等危险动词时要 confirm
- `frappe_run_report` — 跑任何报表

**尚无专用工具、常用点路径备忘**（都走 `frappe_run_method`）：

| 场景 | 点路径 |
|---|---|
| 手动合并卡住的 POS 发票（枪不出库存时的解药） | `ffl_core.api.pos_consolidate.consolidate_pos_invoice_now`（要 confirm） |
| 核验**客户**的 FFL | `ffl_integrations.atf.ez_check_api.verify_customer_ffl` |
| 单枪与 FastBound 的字段差异对账 | `ffl_integrations.fastbound.reconcile.compute_serial_fb_diff`（只读）等 reconcile 套件 |
| 特殊订货 / 定金 | `ffl_core.api.special_order.*` |
| 个人 trade-in 收枪 | `ffl_core.api.trade_in.create_trade_in_intake` |
| 安全删除 Item（保留枪支审计链） | `ffl_core.api.item_admin.preview_delete` → `force_delete`（要 confirm） |

## 9. 这个 MCP **做不了**的事（别硬试，走别的路）

| 做不了 | 替代路径 |
|---|---|
| 改密码/API 密钥类字段 | Desk 后台直接改（设计如此，防泄露） |
| 批量传枪支照片并建相册 | firearm-listing-import 技能的脚本（自动 resize + 建 gallery） |
| 改 doctype 结构/权限/角色 | 走代码和迁移，MCP 写入黑名单挡着 |
| Payroc 刷卡/退款 | POS 收银界面操作（真实资金，未包装成工具） |
| 在 FastBound 填 4473 表格本身 | FastBound 网页 UI（表格只能在它家填） |
| 给 dev/测试环境做操作 | 本地 `bench --site dev.localhost` + 本地 WC 克隆 |

---

*工具总数 50（10 个通用 + 40 个专用）。对应版本 v0.2.0；工具行为以 README.md
和源码 `gunstore_mcp/tools/` 为准。*
