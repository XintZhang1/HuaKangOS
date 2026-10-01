# 维修详情窄屏布局独立审阅

2026-10-02，归属 PATCH-M8-1-REPAIR-DETAIL-MOBILE-GRID-01。审阅者为 closed_writer_audit；本次只做文件字节、来源、原始记录及实际 PNG 审阅，没有执行应用、浏览器、SQL、测试或外置 helper，没有读取私有凭据，也没有修改源码、测试、runner 或自动证据。

结论：实际改动严格限于维修详情顶层布局 class 和两条局部 CSS。repair-mobile18 的原记录与实际截图支持已消除本次原单在 390/768 宽度展开报价历史后整列撑到 876 的缺陷，原宽表仍可在自己的容器内滚动。此结论只属于该显示补丁的定向复查；新生产指纹没有由此取得完整 53/193 验收，business_accepted 继续为 false。

## 精确字节范围与来源

基准为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-business17/source`，新镜像为同外部根的 `repair-mobile18/source`。

| 文件 | full17 SHA256 | 当前及新镜像 SHA256 | 精确差异 |
|---|---|---|---|
| web/repair.js | 91af2e2557ea637f6baab7db35699bfe4576cd63f2a98623014408fec8b51707 | af081eae27b7a26ab21662572cb864136d43ed906c482e76fcef381c6ce3d931 | 第34行唯一顶层 `class="stack"` 增加 `repair-detail`；逆改后整个文件逐字节等于基准 |
| web/simpleui.css | b5b37b59efabac9953d99af6471ab1027118f205de6270c19f592c81dc4018b3 | f951fe50d63eb4b8fe1353ca0a45416213f3240965962bc585418a5555c29347 | 完整基准字节前缀保留；仅第46–47行追加下列两条，均以 LF 结束 |

```css
.repair-detail{grid-template-columns:minmax(0,1fr);min-width:0}
.repair-detail>*{min-width:0}
```

原报价行、KPI 的四个服务器金额、数量、岗位分支、按钮、表单与提交回调字节均保持；`table()` 的 `.tablewrap` 和原 `overflow:auto` 保持。没有全局隐藏页面溢出，也没有修改全部 `.stack`。当前 `index.html` 的 CSS 加载顺序仍以 `simpleui.css` 收尾，局部规则能够覆盖原隐式 auto 网格列。

独立逐文件计算新 provenance 所列 635 个生产文件和 45 个脚本的实 SHA256，全部匹配，清单没有增加或删除路径。与 full17 的清单比较，生产仅上述两路径不同，45 个脚本全部相同。provenance 记录 snapshot_stable=true、before/after 摘要相同、changed_paths 为空。

- 原生产摘要：`76862a922e57832b92d6f9e68ec0804e2182a992da0cd3b150297487532a525b`。
- 新生产摘要：`2e4b6032b69a5296f57d8a1403ac2fc6e1cdae36feb9a22cb0b3e88900c8903f`。
- 脚本摘要保持：`06d17fb81fc97b1d86c753f60602850f9f43dec6359407f8f48affd8323aa5df`。
- 外置 helper `launches/repair-mobile-recheck-v1.py` 实 SHA256 与 provenance 一致：`4d89078ea690be5b7671e5fc8cd9f3afaf06f33ecc86516d5b2016c1f0e05944`；本次只读并解析 AST，没有导入或执行。

manifest 记新外部镜像和独立 runtime，synthetic_copy_lineage 指向已终局 full17 的停止后合成副本，original_53_results_inherited=false。本审不通过读取数据库来增加此声明的证明范围。

## 原定向结果与实际图像

原目录为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/repair-mobile18/evidence`，observations/actions/PNG 位于其中 `repair-mobile-recheck`。原单为 Case222、store1、version19、HKR20261002-6D57FE6748CD。

`repair-display-summary.json` 与原 observations 的六条宽度记录一致：

| 历史状态 | viewport | document | 当前报价表 client/scroll | 历史报价表 client/scroll |
|---|---:|---:|---:|---:|
| closed_history | 390 | 390 | 320/788 | 286/788 |
| closed_history | 768 | 768 | 698/788 | 664/788 |
| closed_history | 1440 | 1440 | 1082/1082 | 1048/1048 |
| expanded_history | 390 | 390 | 320/788 | 286/788 |
| expanded_history | 768 | 768 | 698/788 | 664/788 |
| expanded_history | 1440 | 1440 | 1082/1082 | 1048/1048 |

原 observation `native_horizontal_table_scroll` 记录实际 mouse.wheel 后：390 下两个表的 scrollLeft 为 468/502，768 下为 90/124，均恰好到对应表的 scrollWidth-clientWidth；没有通过改表列、缩小业务内容或写 scrollLeft 值伪造滚动。外置 helper 第105–112行对原 `.tablewrap` hover 后调用 mouse.wheel，再读实际 scrollLeft 并要求大于0。

本审通过 view_image(original) 实际查看以下三张新原件；其余 PNG 只核宽度及 SHA，不声称已逐张人工阅图：

| PNG | 实像素 | SHA256 | 实际可见事实 |
|---|---|---|---|
| 12-expanded_history-390.png | 390×5402 | d86901da017c589cdb30315f5c20db858e577e56efa2d8b504a2d09f102cc513 | KPI与后续卡片收在屏内；展开报价历史仍可见；宽表当前显示左侧项目列 |
| 17-native-table-horizontal-scroll-390.png | 390×5402 | da0c290470dba83407ba40289500350f8939fee67fd143f134d7cca5ec9e8362 | 页面整体宽度保持390；两个原报价表滚至右侧，单价/分摊优惠/金额列真实可见 |
| 14-expanded_history-768.png | 768×4990 | 573176206cdcd0195e4dce35a8c5920239c224b2fed995c735d426bfb96b2dce | KPI/客户工位/报修/当前及历史报价/款项/凭据/交接卡片均收在768内，表格保持局部宽内容 |

三张实际图的 KPI 均为当前授权30.00、外部承担20.00、客户尚欠15.00、全部尚欠15.00；原客户已到账5.00及内部承担10.00仍分开展示，待结算交接与待办保持。helper 第81–86行绑定本次原 GET 响应的 Case ID/version，再以 amount_cents、revenue_cents、customer_due_cents、receivable_cents 比较四个实际 KPI 文本，不在客户端重新计算业务净额。本审没有另发 HTTP 或自行查询数据库；backend 结论只引用原定向自动证据及此静态断言范围。

observations 中登录后的基线、原维修读取前后及显示复查结束的业务摘要均为 `5eef46fa664cd8b0c62fbb9ef1b063b3fea1e2bed3127262cf75de7724f5fedb`。登录前摘要不同由原登录系统动作另记；本审不把登录描述为零写入，也不将该变化扩大为维修写入。27个原 action 连续记录，原 summary 为5次点击、12次键盘动作、protected_conflicts=[]、forbidden=[]。局部 wheel 另由 observation 记录，本审不把它虚计入 action 点击数。

## 终态与证据边界

原 `repair-display-summary.json` 的 complete/passed/normal_stop 为 true、original_server_exit_code=0；provider 的 synthetic_requests/real_model_calls/blocked_external_attempts 均为0，server.log为空。根任务报告本次 helper CLI0；本审没有重跑或把自己的静态审阅计为另一次执行。

原 summary 明确 scope=targeted_repair_display_recheck，business_accepted=false、full_registered_suite_complete=false、full193_business_acceptance=false、parent_full53_results_inherited=false，保持原53和193原件的独立归属。此证据属于桌面浏览器390/768/1440 viewport 的定向展示与局部滚动复查，不代表物理手机、员工试用、所有维修状态、完整193人工评分、故障恢复、PostgreSQL/Linux、真实外部业务、真实模型或生产门槛通过。四生产开关与原里程碑状态未由本审更改。

原件 SHA256：provenance `cd1a34c2f2565931a9f52653319516c4b0eadf756497cc3b8ab630384b5a069c`；summary `92f9469693bff1dd4f8a11493bebd67754d035e23a0a11a20351837c93bb94d0`；observations `8de6a2f184f9bb25b0dec3ffb063a4bc3f912f9fd5e119024a5615ff6cdea9cf`；actions `9839708623b4c07db0c8486291d364ed9022f87b0c42113a6b64a0e149d3ca2b`；原 display-recheck-result `bae109a2bfd4a9f089ba8a0c4d3616ed67568bebcb24e4383a0066a7b96093cc`。
