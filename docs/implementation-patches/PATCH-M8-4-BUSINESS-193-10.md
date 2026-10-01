# PATCH-M8-4-BUSINESS-193-10：会员身份、识别卡与本金原款

日期：2026-10-01。按已冻结`docs/architect/tasks/next-business-scope.md`原合同，新增独立未注册`tests/browser_click/membership_business.py`和`docs/architect/tasks/membership-business-click.md`。候选只写本人两文件、静态检查，不启动业务实例。根短审冻结后仅接run白名单、scenarios原注册/汇总、README和进度。

完整check限定HK117/128/118/089/094五项；普通本金充值/退款对HK124/125仅partial，不忽略组合充值与整份退款合同。依赖同次已passed销售明确customer_id及采购HK021原账户ID，重新核本店/本人客户、账户启用、无历史首卡/本金结果；不继承demo会员余额，不从全库挑最新来源。新增身份岗位和fixture成果均为零。

现有本人service原UI核对独立身份/开通会员、首卡、挂失及换补；实际finance明确原账户收10000分，service向该原topup发起退4000分、不同manager批准占额、finance同原账户实际退款。每步核原会员/原单/任务/卡代次/GroupEntry/Cash/GroupSettlementEntry/Receipt与当前member/case/order/CAS及request_id。本金、权益、赠品及内部往来分别保护；旧卡、原现金/充值/流水不可覆盖。无自动到账、业务API/SQL写入或用户管理员绕过。

原任务如默认demo员工，只可manager原UI转交同岗本人；确认、资金与卡状态动作均实际点击。文件为本单不同合成凭据，只称structure-only，不能冒真实款项/银行、ClamAV及员工验收。全原业务snapshot与有限动作/有限原ID旧行守卫沿既有标准，无关/他店/旧钱物权益保持；失败停留证，不重放未知写。人工体验、组合/消费/权益和193完整业务仍pending/false，发现产品缺陷另精确补丁。
