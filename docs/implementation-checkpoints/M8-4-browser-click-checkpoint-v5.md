# M8-4 浏览器点击检查点 v5：84项自动业务核对

2026-10-01，当前M8.1的实际增量记录；原实施状态及门禁仍只查实施计划。HEAD基点 `5069b2bcc9f580ebb9d70780769049a14a6de946` 加当前工作树，不是193完整验收或生产放行。

`V/browser-click/automatic-business-20261001-09/evidence/` 完整注册/执行/通过28/28、退出0，scope=full_registered、complete/passed=true。5208动作、2560点击，场景耗时合计773.04秒，页面异常及外部请求尝试0；16次合成模型、真实模型0。白名单镜像前后稳定，生产SHA256 `1597eb7b00be508a8d876f85496c4f20131e07b5377034f19bce0bc50538ff0d`，脚本 `7cc1267dd983682ab5854ca50100a4e4c21ab7e10c5410b1dc13778f5c326d8b`。

完整自动业务check为84项：售前7、采购7、主档15、客服4、销售交付/退订5、报表11、物资9、维修6、系统2、会员5、洗车/快捷/客户直收报销4、交车后四项4、财务5。销售后续HK012/015/016/017在补原Case/Task与实际DOM等待后整场景通过；此前08整场景失败及三个局部诊断原件保留，不继承为本轮成绩。财务HK087/090/091/093/096首次完整通过，实际误录100→90追加更正、预收抵用、非空集中分配和未用预收原账户退款分别核原流水，净现金12000分，预收及两单应收最终0；未借此接受HK088及其他财务项。

原193搜索、111指引、70共用页面和9代表表单仍仅各自UI覆盖；业务人工接受0、full193=false。HK099有限本地车辆来源、HK192/193系统局部、HK124/125会员普通本金局部保持partial。合成外部手续、实物及structure_only文件不替代真实业务条件。

人工domain02是上一轮08源/脚本指纹的维修/接待显示定向复核，六项3/3/3/4/3/3、469表2706行摘要未变；没有将其分数拼成当前84项人工体验。原domain01显示失败及修复范围见v4。当前保险七项及开票/核账两项尚未注册或实际执行，无成绩。

M8.1保持in_progress；M8.4/CP-36保持todo/not_ready。原101/283真实模型、PostgreSQL/Linux、真实故障恢复/附件/员工试用及生产条件保留，四生产开关默认关闭。点击CI更新源码未在远端执行；本轮不推送或部署。

后续保险最小 `business-insurance-20261001-01` selected4/4、33完整自动check退出0，其中七新保险实际120.05秒，源978552f0/脚本a4e18d82，镜像稳定、0合成/0真实模型；全新采购/主档/客服26项为本次真实来源，不与上方84相加成联合成绩。原资金/佣金文件类别接线按真实原UI复验，人工仍pending。该实例结束后原审计页面按AUDIT-FILTER-DISPLAY-01窄修两字段和原键详情，Node及独立短审完成。开票/核账8850917f候选根独立静态短审/AST后注册，当前30；新finance-followon01五场景实际运行中，源91ce1df7/脚本a7d8b2e1，首次两新check结果尚未出。系统两项仍未注册。稳定84增量已本地提交8993ca8，不推送/部署。

后续实际：finance-followon01所选五场景4通过1失败、退出1，23完整check；新核账POST原通用SQLAlchemy409，HK095 failed、097未开始。外置SELECT核批次/核账Case/发票申请均0，未盲重放。唯一server诊断517无请求关联，边界和源原因见RECONCILIATION-TRANSACTION-01；该实例退出后仅两原核账POST认证前复用已评审写事务，AST及独立短审完成。fresh finance-followon02仍同五选择，源a2632178/脚本a7d8b2e1稳定镜像，实际新核账成功并进入票据，尚未记两项终局结果。全部原失败留存，不通过碎片拼联合成绩。

后续02实际结束：所选5场景4通过1失败、退出1，仍23完整check；HK095新批真实创建但未终局，HK097蓝票实际58元/差异复核后红票POST201、新97与旧96 GET均200，截图新红票8元正确。原候选前缀观察接受旧96，DB字段核对失败属于脚本关联缺口，没有计两项通过。进程关闭后仅finance_followon候选按NEW-ENTITY-READ-01绑定真实POST新ID、原GET及URL，保留单次原UI点击；当前脚本b4a200c9经AST/独立只读短审，fresh03同5源a2632178/脚本038879b4稳定镜像运行中。无额外HTTP或未知重放，全部失败原件留存。

后续03实际结束：所选5场景4通过1失败、退出1；HK097完整票据链local passed，但HK095店长复开v3成为prepared_by，又以同人封存被原规则403拒绝。v2此前真实独立封存，v3没有接受成功；整场景仍failed，票据local不拼成完整两项通过。进程结束后按RECONCILIATION-INDEPENDENT-REVIEW-01仅明确第三版由本批原管理员独立复核，保留财务提交/店长复开和原服务守卫；独立审阅发现原Task.role应保持manager，待修正该观察断言。系统及报表冻结短审后仅白名单/注册接线，当前32；两个新的隔离selected实例首次实际运行，结果待出。不得继承局部或静态结论为当前联合成绩。

新增两探针实际结束：system-followon01 selected3为2通过1失败、9完整check；report-followon01 selected6为5通过1失败、41完整check，六报表local使诊断总47，不能拼完整。两源同a2632178/脚本37db0c37稳定镜像、退出1、真实模型0。系统图片实际JPEG与元信息已核，原AuditLog.before_data是JSON `null`，原候选误要求SQL NULL；窄修JSON解码后严格None，经AST/独立短审。报表153显示新两行/五原收退一致、四条原历史purchase缺不可变逐行来源，原complete=false、金额汇总未知/图不显示正确；按PROCUREMENT-HISTORY-SCOPE-01保持153partial/no业务check，完整候选七项、152亦partial，旧单/日期/定义不改。155未开始，首次场景仍failed，无新联合成功或人工接受。

后续三探针均已退出，源a2632178622d952c4dd10fba6d8b7b4a87ba993c1307b7b5dfe132e2d221216a／脚本6d03251f69ddd3a9b57146b34270f025cfd3443014f46036239976664003e596稳定。report-followon02 selected6/6、退出0、48完整自动check，本批146/147/148/149/150/151/155七项均passed，152/153分别partial，不计193完整；页面异常/外部尝试0，真实模型0。finance-followon04 selected5为4过1、退出1、23完整check，admin前置要求user_stores行与原tenancy有效管理员投影不符，零动作失败；system-followon02 selected3为2过1、退出1、9完整check，图片恢复/本人改密已实际发生，旧会话Page被错误绑定为登录事实dict，HK192整体failed、193未开始。原件与局部全部保留，不继承为两新项通过。

三关联实例退出后，ADMIN-SCOPE-01仅财务候选改核有效admin/有效店，并在每次原登录响应核真实一店本人投影，非admin逐店行仍严格；SYSTEM-PAGE-01仅系统候选取原Page返回值。AST通过，分别e1fb54bbc57f20d812fcc270d65fce9477a140cf15f6340429238439e4d83e07／d30c0d8744cfa9ca9de509e71adcf9b35da1b02410c894d2990ef8b2d36de653。INSURANCE-FACTS-ENTRY-01原销售统计仅追加已有实际出保表预览及原完整明细按钮，web/app.js指纹abe031f0a934107df2d7df4fa8cc2905cd6fc2104f6c712b56ef9cf036da2dba，Node通过；三增量独立短审及新镜像待做。完整联合成功仍28/84，未注册会员/财务报表/车辆候选无实测成绩。

随后三增量独立短审完成，没有确定误配或权限放宽；automatic-business-20261001-10完整32注册联合已启动，源0ce46e44efb63370e6fb2f3439aeda115c069e1dec4ee983c73bcd5acd1b7a29／脚本a55c795a850d5dac8fc361f3aa05fbc88c6b2b5b5774a5e66ee2e0711926eee5初始镜像稳定。结果待出；当前未注册会员、财务报表和车辆候选不进入白名单，允许仅owned候选/文档继续，不能修改运行中的注册源码。

联合10终局：完整32注册/执行，31passed/1failed、退出1、complete=true/passed=false、scope=full_registered；100完整自动check、diagnostic=100，6335动作/3081点击/1072.99秒，0页面异常/外部尝试，17合成/0真实模型，源0ce46e44…/脚本a55c795a…前后稳定。保险7、系统2、报表7同次整场通过，152/153仍partial；财务后继0.09秒/0动作，在读取users时漏白名单登记而前置failed，没有办理095/097。整次不记成功联合，也不继承旧84或局部到新112；原件完整外置留存。

所有关联实例结束后，READ-REFERENCES-01只追加users/stores为只读参考表、原可写Guard不变；e2c5123c1149d75326d24fdc90e94094c0f87c1aff14f2c90b4546698cb4dc8b经AST/独立短审。冻结会员6的2c8777cf经独立金额/权限/旧行合同审阅，财务四报表1a536320经根原API/七表/冻结CSV/58表字段静态审阅；按PATCH18/19仅白名单/固定顺序接线，当前34/27文件。两候选未实际运行，不写新check成绩；原业务人工接受0/full193=false与原外部/生产门槛保持。


联合11终局：automatic-business-20261001-11完整34注册/执行，33passed/1failed、退出1、scope=full_registered、complete=true/passed=false，108完整自动check/111局部诊断；7709动作/3663点击/1299.56秒，0页面异常/外部尝试，17合成/0真实模型，源0ce46e44efb63370e6fb2f3439aeda115c069e1dec4ee983c73bcd5acd1b7a29、脚本63e28f37bd9c42d0a3b6bdbd2c2fefec0418e18f470986efa2eea6005f19b6a3前后稳定。会员六项与财务后继两项本次整场通过；141/161/162仅局部，163在原现金136,000.00与候选136000.00的格式观察失败，未计完整四项。历史成功联合28/84不与局部拼成绩。

manual-finance-system-20261001-01的七原UI前序通过；IAB同源三宽度实际查封存版本3、取消复开、核凭据/待办、日志筛选重置详情、参数密码取消。核账金额被五段版本介绍推到手机首屏外，手机审计说明逐字换行/详情超出表容器，人工未通过；469表2687行5cab276a5d1459a5ed4e8fcc8e4b36b97409059aa23ea29226eb5859c59969a3原业务摘要不变，失败截图/评分原件保留。所有关联验证进程均正常退出后，根才按RECONCILIATION-COPY-01/AUDIT-MOBILE-LAYOUT-01/FROZEN-SOURCE-UI-FORMAT-01修展示与严格格式观察；Node/AST/差异检查完成，独立短审待结论。车辆六项811c59e0和仓储八项1d1372b0静态审阅后按PATCH20/21只接白名单/注册，当前36/29、源ea75c0d50c1bb2f75b81206af478620988d788c9bc688434cd5e756377e5bf4d、脚本69f5db44b8f6096424fcb0054532e3887cfeb9dd59258ddda5c45fe131528fb7；新镜像尚未执行。193与全部业务人工false/0，M8.1唯一in_progress，M8.4/CP-36与原环境/生产门槛不变。
