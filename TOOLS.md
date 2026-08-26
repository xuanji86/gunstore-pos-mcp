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
| 查某型号在库的每把枪和各自售价 | `available_serials` | 返回 {型号: [{serial, sell_price…}]}，便宜的在前。**默认剔除寄售在外/暂扣的枪**（和 POS 拣枪口径一致）；盘点要完整清单传 `exclude_unavailable=false` |
| 看全部在库枪支清单 | `firearms_in_stock` | 报表：序列号/厂商/型号/口径/仓库/来源 + FastBound 链接；可按仓库或厂商过滤 |
| 看待处理的柜台/经销商订单 | `pending_orders` | Pending Order 队列：还没 dispose、没收够钱、或还没推 ShipStation 的单子。**寄售出库不在这里**——寄售有独立队列，见第 5 节 |
| 看待发货的网店订单 | `pending_web_orders` | 已付款、等 dispose 的 Woo 订单 |
| 看寄售在途/结算队列 | `consignment_queue` / `consignment_dealer_orders` | 寄售全套见第 5 节 |
| 财务/税务报表(销售、总账、三表、税负、AR/AP) | `sales_report` / `gl_entries` / `financial_statement` / `tax_liability` / `ar_ap_summary` | CPA 报表工具包,全模式可用,见第 10 节 |
| 搜 RSR 批发目录（不是本店库存） | `rsr_catalog_search` | 按关键词/UPC/RSR 编号/厂商编号搜 |
| 跑任意报表 | `frappe_run_report` | 报表名：`Sales Report`（营收+毛利；filters 传 `view`="Order"/"Order Detail"/"Product" 切三种视图，默认 Order，返回含 report_summary 卡片）、`Pending 4473 Orders`（卡在 4473 的单）、`Open Special Orders`（特殊订货看板）、`Pending Transfer Pickups`（待取的转入枪） |
| 查任何记录 | `frappe_list_documents` / `frappe_get_document` | 万能查询，见第 9 节 |

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

**传照片**：单张可用 `upload_attachment`（见第 8 节）；**批量传图+描述+建相册请走
firearm-listing-import 技能的脚本**——它会先把图缩到 2000px（原图太大会把 Woo
推送搞超时），MCP 不做 resize。

## 2b. 上架 / 下架（GunBroker —— 第三销售渠道）

固定价 Buy Now，价取 `Serial No.sell_price`。**只按枪操作，没有"整型号推"这回事**——
GunBroker 上一条 listing 就是一把枪。

| 你想… | 工具 | confirm | 说明 |
|---|---|---|---|
| 上架**一把枪** | `gb_push_serial` | ✅ | 守卫拒绝会返回 `{"ok": false, "skipped": ..., "message": ...}`——**这是正常回答不是报错**，照 message 处理，重试不会变 |
| 结束**一把枪**的 listing | `gb_end_listing` | ✅ | **看 `confirmed` 不是看 `ok`**：`confirmed=false` 一定带 `pending_manual` + `gb_url`，意思是**这把枪在 GunBroker 上还能被买走**，要人去站点上手动结束 |
| 看一把枪的上架状态 | `gb_listing_status` | — | 只读；`state` 是 POS 视角（7 态），`remote` 是 GunBroker 当下的说法 |
| 测试 GunBroker 连接 | `gb_test_connection` | — | 只读探活；**回包里的 `sandbox` 字段说明刚才打的是哪个环境** |

**沙盒还是生产，这里选不了**——而且是**真的**选不了，不只是「请不要」：由目标 POS 站点的
`GunBroker Settings.sandbox_mode` 唯一决定，而这个字段**经 MCP 写不了**：
`update_settings("gunbroker", {...})` 只要带上 `enabled` / `sandbox_mode` /
`base_url_override` / `dev_key` / `sandbox_dev_key` / `username` / `password` /
`end_strategy` / `check_deposit_account` / `card_checkout_enabled` 里的任何一个键，
**整个调用直接拒绝**（不是剥掉那个键继续写——半个生效比全不生效更坏）。这些只能在
desk UI 里由人改。工具本身也一律经 POS 的 whitelisted 方法走，MCP 不直连 GunBroker。

**「本地站」不等于「沙盒」**。把 MCP 指向 `dev.localhost:8000`，你拿到的是**那个站点**的
`sandbox_mode`——一个填了生产凭据的本地 dev 站照样能挂出真 listing。唯一可靠的确认方式是
`gb_test_connection` 回包里的 `sandbox` 字段，`gb_push_serial` 之前先看一眼。

**角色不同**：`gb_test_connection` 要 POS 上的 `SYSTEM_ROLES`，另外三个只要 `STOCK_ROLES`。
只有库存类角色的 API 用户会**单单在这个探活工具上吃 403**——而它恰好是文档教你第一个调的，
看到 403 先想这件事，别以为是连接坏了。

**手动重挂**（人工结束过的枪要再上架）不在 MCP 面上：走 Serial No 表单，那里能看见
当初为什么被结束。

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
| **取消一张柜台/经销商转移单** | `cancel_order` | ✅（必须带 reason） | 安全级联：撤 disposition→库存回冲→FastBound 删除排队→ShipStation 作废 + 按实收退款（refund_mode/refund_reference）。别手工逐张撤——这个通道就是为此建的 |
| 测试 ShipStation 连接 | `shipstation_test_connection` | — | 只读探活 |

典型流程：`pending_orders` 看队列 → 差钱先 `record_payment` → `dispose_order` →
`push_shipment`（网店单则 `pending_web_orders` → `dispose_web_order`，不用推单）。

## 5. 寄售出库（Consignment Out —— At Dealer 队列全生命周期）

寄售有自己的队列和流程，**不走第 4 节的 Pending Order**。

| 你想… | 工具 | confirm | 说明 |
|---|---|---|---|
| 看在途寄售队列 | `consignment_queue` | — | 每张寄售单一张卡：经销商可寄性、ShipStation 状态、tracking、枪 pills；`include_closed=true` 连历史一起看 |
| 看能寄给哪些经销商 | `consignment_dealers` | — | 全部 FFL dealer 客户 + shippable/block_reason（FFL 过期会标出来） |
| 看哪些枪能寄出 | `consignment_serials` | — | 在库 Active 序列号 + 结算价/参考价；不可选的枪也返回并附原因 |
| 建一张寄售单 | `create_consignment_out` | ✅ | payload：{dealer, lines:[{item_code, serial, cost, msrp}], dispose_now?}。默认存草稿稍后 dispose；`dispose_now=1` 立即 dispose+推 ShipStation（被 FFL 门拦下会降级保留草稿） |
| **Dispose（发出）寄售单** | `ship_consignment_out` | ✅ | 逐枪登 FFL 转移 disposition + 移库 + 推 FastBound；先验全部行再动任何行，幂等。**动手前核对经销商 FFL 和序列号** |
| 推到 ShipStation 买面单 | `push_consignment_shipment` | ✅ | 已 dispose 的单才能推；幂等、失败不留脏数据 |
| 不走 ShipStation、手工记发货 | `mark_consignment_shipped` | ✅ | 可带 tracking_number/carrier，经销商门户会显示 |
| **改在外寄售枪的价**（At Dealer 行的 Dealer Price/MSRP） | `update_consignment_prices` | ✅ | prices：{行名: {cost 必填>0, msrp 三态——缺键=不动、空=清掉、否则>0}}。只改本张单的行快照，不动 Serial No/Item 主档；结算与门户自动跟随。仅 At Dealer 且未出结算发票的行；整批先验后写。行名从 `consignment_queue` 拿 |
| 看结算队列（卖掉但没收到钱的） | `consignment_dealer_orders` | — | Sold 但结算发票没出/没付清的行，失败的排最前 |
| 结算发票失败重试 | `retry_consignment_invoice` | ✅ | 传 Consignment Out Line 名（从结算队列拿） |
| 收回没卖掉的枪 | `return_consignment_lines` | ✅ | 逐枪登真实 re-acquisition（自动推 FastBound）+ 移库回主仓 |
| 撤销寄售（整单草稿 / 单行误发） | `cancel_consignment` | ✅（必须带 reason） | 不带 `line` 撤整张草稿；带 `line` 撤一行已发的（"枪其实没离店"，仅结算前可用） |

**结算是自动的**：经销商在门户点 Mark Sold 后系统自动出结算发票（失败进结算队列重试）。
**撤结算**：用 `frappe_cancel_document` 取消那张结算 Sales Invoice——取消钩子会对称反开父单（Closed→Shipped），无需也没有专用端点。
**代经销商签收/报售（mark_received / mark_sold）做不了**：那两个方法绑定门户 dealer 会话身份，管理密钥调用会被拒；见第 11 节。

## 6. 4473 / 合规（FastBound、ATF）

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

## 7. RSR 目录同步

| 你想… | 工具 | confirm |
|---|---|---|
| 立刻全量同步 RSR 目录 | `rsr_sync_catalog` | —（后台跑） |
| 测试 RSR FTPS 连接 | `rsr_test_connection` | — |

（数量增量同步每 15 分钟自动跑；手动触发用
`frappe_run_method` 调 `ffl_integrations.rsr.tasks.sync_quantity_now`。）

## 8. 设置 & 文件

| 你想… | 工具 | 说明 |
|---|---|---|
| 看某个集成的配置 | `get_settings` | `ffl` \| `fastbound` \| `rsr` \| `payroc` \| `woocommerce` \| `dealer` \| `shipstation` |
| 改配置（非密钥字段） | `update_settings` | 密码/密钥字段自动剥除，去 Desk 改 |
| 上传一个本地文件到 POS | `upload_attachment` | 可顺带挂到某条记录（doctype+name）或写进附件字段。默认私有；**要给 Woo 用的商品图必须 `is_private=false`**。批量图片走技能脚本（先 resize） |

## 9. 万能后门（`frappe_*` 通用工具）

上面没有的操作，AI 可以用通用工具直达任何数据和白名单方法——**新功能上线当天就能用，
不用等 MCP 更新**：

- `frappe_list_documents` / `frappe_get_document` / `frappe_describe_doctype` — 查任何 doctype（先 describe 看字段名）
- `frappe_create_document` / `frappe_update_document` — 建/改任何记录（凭据字段自动剥除）
- `frappe_delete_document` / `frappe_submit_document` / `frappe_cancel_document` — 删/提交/作废（都要 confirm）
- `frappe_run_method` — 按点路径调任何白名单方法；方法名含 delete/cancel/refund/**dispose/push/charge/consolidate/ship/return/receive/sold/settle/onboard** 等危险动词时要 confirm。另有一批**无危险动词但高后果**的方法走显式精确名单(`_ALWAYS_CONFIRM_METHODS`:update_order / update_consignment_line_prices / create_consignment_out / record_payment / create_consignment_invoice_now / add_stock / set_stock / set_customer_tax_exempt),裸调同样要 confirm——收录判据:记钱、动库存、改合规/税务状态
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
| **编辑**一张 pending 柜台单（取消重建式，仅限未 dispose/未推单） | `ffl_core.api.manual_order.update_order`（要 confirm——已列入显式高后果名单 `_ALWAYS_CONFIRM_METHODS`，"update" 虽不在危险动词表，裸调也会被要求确认）内部是 cancel+rebuild 级联——慎用，动手前先复述要改什么 |
| 查/设客户免税状态 | `ffl_core.api.manual_order.get_customer_tax_status` / `set_customer_tax_exempt` |
| Woo 部分退款对账（Woo 退了款、POS 侧对齐） | `ffl_woo_sync.woocommerce.refunds.reconcile_web_order_refund`（要 confirm） |
| 清理指向已删 Woo 商品的 dangling ID | `ffl_woo_sync.woocommerce.dangling.woo_audit_dangling_ids`（`fix=0` 干跑只报告） |
| 经销商开户（FFL 查询 → 建 Customer+门户账号） | `ffl_core.api.dealer_onboarding.lookup_ffl` → `onboard_dealer`（要 confirm） |
| 网单收入发票失败重试 | `ffl_woo_sync.woocommerce.revenue.create_web_invoice_now` |
| 撤销一笔寄售结算 | `frappe_cancel_document` 取消那张结算 Sales Invoice（钩子自动反开父单） |

## 9b. 分销商直发（RSR Direct Connect）— `distributor_*` 11 个（只读 7 + 动作 4）

只读 7 + 确认队列动作 4。**不含**直接下单(place)、Settings 写、以及 metabox 清单以外的任何变更面。

| 工具 | 服务端方法 | 说明 |
|---|---|---|
| `distributor_orders` | `distributor.api.list_orders` | 列 Distributor Order,可按 status/分销商筛 |
| `distributor_route_queue` | `distributor.router.route_queue` | **确认队列**:待确认的 Draft 单 + 被拦下的网单(未付款/买家 FFL 缺失或过期/地址不全)及原因、目的 FFL 到期日。确认任何单之前先读这个 |
| `distributor_catalog_search` | `distributor.api.search` | 目录 typeahead(本地同步的目录,不是实时库存) |
| `distributor_quote` | `distributor.api.quote` | 单品成本/MAP/MSRP/建议价/受限州/封锁旗标;qty 是**缓存目录量**,不保证新鲜度 |
| `distributor_check_availability` | `distributor.api.check_availability` | **实时**量价二次确认(会打 RSR HTTP,只读) |
| `distributor_precheck_fds` | `distributor.router.precheck_fds` | 问分销商是否接受发往该 transfer dealer 的 FDS(会打 HTTP,只读) |
| `distributor_fulfillment_options` | `distributor.options.fulfillment_options_for_order` | 单张网单的**决策面板**:逐行候选分销商(最便宜在前)+ 本地库存对比行 + 裁决。只读。**读返回值前先看下面的三态说明** |
| `distributor_confirm_order` | `distributor.api.confirm_order` | ⚠ **要 confirm**。Draft→Queued 并启动下单 worker = **真实采购不可逆**;RSR 无取消 API。柜台来源单还要求发票全款结清 |
| `distributor_cancel_order` | `distributor.api.cancel_order` | 要 confirm + **要 reason**。仅在下单前(Draft/Queued)是安全的;已下单的会被标记并告警运营,退货是人工流程 |
| `distributor_reroute` | `distributor.router.reroute` | 要 confirm。修好拦截原因后重跑路由,**只建 Draft**、幂等 |
| `distributor_update_order_ffl` | `distributor.router.update_order_ffl` | 要 confirm。FDS Hold 的标准解法;新执照先过与柜台同一条 canonical 校验链(未过期+完整地址)才调 RSR |

### `distributor_fulfillment_options` 的返回值契约(容易读错,单列)

**两个字段是三态,`if not x` 在它们身上是错的**——`null` 的意思是"还判不了",不是"没问题":

| 字段 | 取值 | `null` 的含义 |
|---|---|---|
| `verdict.fulfillable` | `true` / `false` / `null` | 判不了,看同级 `reason`:`unknown_destination`(目的州还没捕获——订单停在 Pending Route 或买家 FFL 未上传时**这是常态**)或 `stale_feed`(唯一够量的候选来自过期 feed) |
| `restricted_state` | `true` / `false` / `null` | 同上,受限州判定尚无法做出 |

遇到 `null` 一律当 **HOLD**:如实说"未判定"并引用 `reason`,**不要说这行可以发货**。受限商品 + 未解析目的地正是这里绝不能放行的情形——POS 侧刚修掉的就是这个 fail-open,消费端读成 falsy 等于在自己这边重新打开它。

**候选行旗标**:`not_carried` = 该分销商目录里没有这个商品(**列出来**而不是丢掉,以免被误读成缺货);`blocked` = 有货但不可买(分销商封锁 / 需厂商批准);`stale` = 数量来自过期 feed。不可买的行一律**沉到最后**,所以第一条候选是**最可能可执行**的那条——但以该行的 `verdict` 与旗标为准,排序本身不是许可。

**金额**:`unit_landed` 是**单件**、且**只含货款**。运费在下单前不存在,故 `shipping` 为 `null` 且 `shipping_known` 为 `false`。不要把 `unit_landed` 说成到岸价,也不要乘以数量当成最终成本。

## 10. CPA 模式（只读会计面）+ 报表工具包

**模式开关**：启动环境变量 `GUNSTORE_MCP_MODE=cpa`（默认 `full` = 全部 83 工具中默认注册 79（4 个分销商队列动作需显式开启），行为与以前完全一致；未知值直接拒绝启动，不会静默降级成可写）。cpa 模式给会计/CPA 用：**写面在工具列表里物理不存在**，不是"存在但会拒绝"。三层防御，缺一层其余仍兜底：

1. **注册层**：tools/list 恰好 = 下面 18 个名字（集合相等，测试钉死）；
2. **客户端层**：一切写方法 + 未逐一列名的点路径方法（`frappe_run_method` 整个不注册）→ `CpaModeRefused`；只读点路径 allowlist 逐一列名，禁通配；
3. **Settings 层**：7 个集成 Settings doctype 的 get/list 读也被挡（配置面对会计无用，密码遮蔽是框架行为不是本仓保证）。

**cpa 模式的 18 个工具**：
- 通用查（4）：`frappe_list_documents` / `frappe_get_document` / `frappe_describe_doctype` / `frappe_run_report`
- 业务只读（9）：`find_item` / `item_stock` / `firearms_in_stock` / `pending_orders` / `pending_web_orders` / `consignment_queue` / `consignment_dealers` / `consignment_serials` / `consignment_dealer_orders`
- 报表工具包（5，见下；**full 模式同样可用**）

注意 cpa 模式**没有** `available_serials`（其默认剔除寄售/暂扣枪，在盘点语境会漏枪——盘点用 `firearms_in_stock`）。

**报表工具包**（口径权威 = run 2026-07-16-mcp-cpa-mode/cpa-review.md §2/§3）：

| 你想… | 工具 | 说明 |
|---|---|---|
| 看期间营收+毛利（报税视图） | `sales_report(from_date, to_date, view="Product", channel?, product_type?)` | Sales Report 原样透传（含 report_summary 卡片）；view: Order / Order Detail / Product；channel: POS / Web / B2B-Manual |
| 追总账明细 | `gl_entries(from_date, to_date, account?, party?, voucher_no?, voucher_type?, limit=500)` | 恒定 `is_cancelled=0`（cancel+amend 被撤单自动出列）；**截断显式** `truncated:true`，绝不静默截断；limit 夹 1..5000（0/空按 500），更多行用日期范围分页；单公司口径——多公司化需补 company filter |
| 跑三大财务报表 | `financial_statement(statement, from_date, to_date, periodicity="Monthly")` | statement: `pnl` / `balance_sheet` / `trial_balance`；P&L/BS 走 Date Range;Trial Balance 需日期落在同一 Fiscal Year（自动解析,跨年拒绝） |
| 查期间销售税负债滚动表 | `tax_liability(from_date, to_date)` | opening/collected/remitted/closing 按 voucher 分列,非常规 voucher fail-closed 单列;科目动态解析自默认销售税模板;**注意发票的 "Total Taxes and Charges" 含运费,不是销售税** |
| 查应收/应付账龄 | `ar_ap_summary(kind, as_on_date)` | kind: `ar` / `ap`;Posting Date 基准,30/60/90/120 账龄桶;寄售结算应收在 AR 里按经销商列示 |

**月结/报税常用标准报表**（`frappe_run_report` 直跑,键名已核对 ERPNext v16 源码）：

| 报表名 | 关键 filter 键 |
|---|---|
| `Sales Register` | company, from_date, to_date, customer, warehouse, mode_of_payment, item_group |
| `General Ledger` | company, from_date, to_date, account, party_type+party, voucher_no, categorize_by |
| `Stock Balance` | company, from_date, to_date, item_code, item_group, warehouse |
| `Accounts Receivable` / `Accounts Payable` | company, report_date, ageing_based_on("Posting Date"/"Due Date"), range("30, 60, 90, 120") |
| `Trial Balance` | company, **fiscal_year(必填)**, from_date, to_date |

（缓建备忘：`stock_valuation` 专用工具——年终存货 tie-out 直接 `frappe_run_report("Stock Balance", …)` 即可。）

## 11. 这个 MCP **做不了**的事（别硬试，走别的路）

| 做不了 | 替代路径 |
|---|---|
| 改密码/API 密钥类字段 | Desk 后台直接改（设计如此，防泄露） |
| 批量传枪支照片并建相册 | firearm-listing-import 技能的脚本（自动 resize + 建 gallery） |
| 改 doctype 结构/权限/角色 | 走代码和迁移，MCP 写入黑名单挡着 |
| Payroc 刷卡/退款 | POS 收银界面操作（真实资金，未包装成工具） |
| 在 FastBound 填 4473 表格本身 | FastBound 网页 UI（表格只能在它家填） |
| 代经销商在门户签收/报售（mark_received / mark_sold） | 那两个方法绑定门户 dealer 会话身份，管理密钥调用会被拒；让经销商自己在门户点，或等 staff 端代操作方法上线 |
| 手动触发 ShipStation tracking 轮询 | 每 10 分钟 cron 自动跑（poll_consignment_tracking 非白名单方法）；急查去 ShipStation 后台 |
| 给 dev/测试环境做操作 | 本地 `bench --site dev.localhost` + 本地 WC 克隆 |

---

*工具总数 83（10 个通用 + 57 个专用 + 11 个分销商 + 5 个报表），默认注册 79（4 个分销商队列动作需 `GUNSTORE_MCP_DISTRIBUTOR_ACTIONS=1`）；`GUNSTORE_MCP_MODE=cpa` 只读模式恰注册其中 18 个。对应版本 v0.4.1；工具行为以 README.md
和源码 `gunstore_mcp/tools/` 为准。*
