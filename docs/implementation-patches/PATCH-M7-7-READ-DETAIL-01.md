# PATCH-M7-7-READ-DETAIL-01：补齐权益与套餐原对象读取

日期：2026-09-30。依据：业主要求完成当前剩余任务，M7.7.3/M7.7.5 和 CP-25/26 已登记的读取维度缺口。按 M7.7.3 → M7.7.5 顺序补齐；不同时重开两项。

## 范围及决定

1. M7.7.3：`app/group_benefits_api.py`、`app/group_benefits_service.py` 增加 `GET /api/group/benefits/members/{member_id}`，复用原集团会员详情的当前门店、岗位、销售本人客户责任校验及原权益详情投影。不推测或默选本地 customer_id。`app/assistant_runtime_domains/group_benefit.py` 用新详情实现原会员快照及三条有限存在性事实；`app/assistant_runtime_domains/__init__.py`、`app/business_assistant_capabilities.json` 登记该受控 GET；共享 group_member 对象只由 group_principal 作唯一快照入口，权益按精确 fact key 分派。
2. M7.7.5：`app/repair_package_api.py`、`app/repair_package_service.py` 增加 `GET /api/repair-packages/purchases/{key}`，复用原套餐会员购买列表的本店客户责任、授权门店、发行/状态及字段权限规则；不绕过销售责任或跨店来源授权。返回原购买详情及本店可见的原核销事实，明确资源上限。`app/assistant_runtime_domains/repair_package.py` 用该详情实现快照及发行/核销/实际退款有限事实；同一 registry/capabilities 登记受控 GET 和 package_purchase 唯一快照入口。
3. 只读审查发现其余非 case 对象未设置快照分派的缺口时，逐一核对唯一 provider 后登记精确补充范围；不改变 registry 选择策略，不对共享 case 任意兜底。

套餐结果身份修正同属第 2 项：原 quote 返回维修 Case（不是套餐购买），capture 返回 case_id/金额（没有购买 ID），不得把两者 data.id 当 package_purchase。这两项明确不绑定购买；原购买动作和退款动作仅按规范购买引用绑定。

各项记录、检查点及本轮浏览器夹具/场景可追加。没有迁移、业务写入 API 或金额公式变更。历史 implemented/通过记录保留；本次修补实测前不得套用旧通过数。

## 异常及事实边界

不存在/不可见对象仍拒绝，不从原始表绕过 API 读取；错对象、截断/不完整响应拒绝或明确未知。权益批次、流水或占用存在只证明至少一笔，不等于余额足够或整单结清。套餐发行须有原发行结果，核销须为真实 capture 流水，退款申请/批准不能代替实际支付；零对价组件退回注销明确说明未发生现金退款，不满足 refund_paid。无法看到可靠资金来源时保持未知。原动作可用性不推测。

验证使用仓库外合成数据、原 HTTP 登录权限及新浏览器实际点击路径，不能在工作树导入 app 或访问原预览/公司库。上线和真实模型边界保持原合同。
