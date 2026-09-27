'use strict';

// Static allowlist for opening an existing form after navigating to the guide's
// entry.route. The caller must enforce entry.roles and use an enabled, visible
// button in the rendered page. These selectors never submit a form themselves.
// Keep this list independent of model output: do not accept selectors or actions
// returned by the assistant. Every handler below was checked through its modal /
// formDialog boundary; business writes remain in the employee's submit callback.
// Missing prerequisites may make the original handler show its normal error.
globalThis.WORKFLOW_QUICK_FORMS = Object.freeze({
  // app.js createCase('lead') -> customerchoice.js customerChoiceDialog.
  'wf-reception': Object.freeze({label: '新增接待', selector: '[data-act="newcase"][data-kind="lead"]'}),
  // salesquotes.js salesQuoteNew -> salesQuoteForm (no selected lead required).
  'wf-reservation-contract': Object.freeze({label: '新增预订', selector: '[data-act="sales-quote-new"]'}),
  // addonorders.js addonNew: employee selects the source sale inside the form.
  'wf-sale-addon': Object.freeze({label: '新建销售加装', selector: '[data-act="addon-new"]'}),
  // insuranceorders.js insuranceOrderNew: customer/vehicle chosen in the form.
  'wf-insurance-order': Object.freeze({label: '新建保险单', selector: '[data-act="insurance-new"]'}),
  // serviceorders.js serviceOrderNew. Other services require the employee to
  // select “其它客户服务” in the same form; the shortcut does not submit/prefill it.
  'wf-agency-service': Object.freeze({label: '新建客户服务', selector: '[data-act="serviceorder-new"]'}),
  'wf-other-customer-income': Object.freeze({label: '新建客户服务', selector: '[data-act="serviceorder-new"]'}),
  'wf-other-service-income': Object.freeze({label: '新建客户服务', selector: '[data-act="serviceorder-new"]'}),
  // vehicleincome.js vehicleIncomeNew: original sources selected in the form.
  'wf-vehicle-other-income': Object.freeze({label: '新建整车其他收入', selector: '[data-act="vehicle-income-new"]'}),
  // vehicleprocurement.js vpNew; vehicletransfers.js vehicleTransferNew.
  'wf-vehicle-purchase': Object.freeze({label: '新增采购计划', selector: '[data-act="vp-new"]'}),
  'wf-vehicle-transfer': Object.freeze({label: '申请整车调拨', selector: '[data-act="vehicle-transfer-new"]'}),
  // vehicleoperations.js voNew: choose the intended operation in the form.
  'wf-vehicle-local-move': Object.freeze({label: '新增车辆作业', selector: '[data-act="vo-new"]'}),
  'wf-vehicle-other-out': Object.freeze({label: '新增车辆作业', selector: '[data-act="vo-new"]'}),
  // serviceintake.js intakeBook; repair.js repairNew.
  'wf-repair-intake': Object.freeze({label: '登记接待', selector: '[data-act="intake-new"]'}),
  'wf-repair-complete': Object.freeze({label: '新建维修工单', selector: '[data-act="repair-new"]'}),
  // procurement.js procurementNew; transfers.js transferNew.
  'wf-material-purchase': Object.freeze({label: '申请物资采购', selector: '[data-act="procurement-new"]'}),
  'wf-material-transfer': Object.freeze({label: '申请物资调拨', selector: '[data-act="transfer-new"]'}),
  // warehouse.js whNew: only new operations, never original-record returns,
  // capture/post_count, actual receipt/dispatch, or the activate operation.
  'wf-material-other-in': Object.freeze({label: '登记其他物资入库', selector: '[data-act="wh-new"][data-operation="other_in"]'}),
  'wf-consumable-issue-return': Object.freeze({label: '申请耗材领用', selector: '[data-act="wh-new"][data-operation="consumable"]'}),
  'wf-gift-issue-return': Object.freeze({label: '申请礼品发出', selector: '[data-act="wh-new"][data-operation="gift"]'}),
  'wf-material-other-out': Object.freeze({label: '申请其他物资出库', selector: '[data-act="wh-new"][data-operation="disposal"]'}),
  'wf-material-local-move': Object.freeze({label: '申请物资店内移库', selector: '[data-act="wh-new"][data-operation="local_move"]'}),
  'wf-material-stock-count': Object.freeze({label: '新建库位盘点', selector: '[data-act="wh-new"][data-operation="count"]'}),
  // retail.js retailNew; reconciliation.js reconciliationCreate.
  'wf-retail-sale': Object.freeze({label: '新建精品订单', selector: '[data-act="retail-new"]'}),
  'wf-period-close': Object.freeze({label: '新建期间对账', selector: '[data-act="reconcile-new"]'}),
  // app.js masterDialog('customers') -> customerchoice.js; customerservice.js.
  'wf-customer-profile': Object.freeze({label: '新增客户', selector: '[data-act="newmaster"][data-kind="customers"]'}),
  'wf-customer-vehicle': Object.freeze({label: '登记客户车辆', selector: '[data-act="care-vehicle-new"]'}),
  'wf-questionnaire-design-and-answer': Object.freeze({label: '编写问卷题目', selector: '[data-act="care-q-propose"]'}),
  // membership.js membershipCardLookup is a read-only lookup form. Issuing a
  // card, topping up and refunds require first choosing a customer; no shortcut
  // here may select that customer or manufacture an original transaction ID.
  'wf-member-card': Object.freeze({label: '按卡号查会员', selector: '[data-act="membership-card-lookup"]'}),
  // repairpackages.js packageRuleNew; memberpricing.js memberPriceNew.
  'wf-repair-package': Object.freeze({label: '拟定维修套餐', selector: '[data-act="package-rule-new"]'}),
  'wf-customer-repair-package': Object.freeze({label: '拟定维修套餐', selector: '[data-act="package-rule-new"]'}),
  'wf-member-level-rules': Object.freeze({label: '新建会员价格规则', selector: '[data-act="member-price-new"]'}),
  // masters.js masterDataDialog, exact kind keys from master_data.py. A combined
  // guide's label names the specific form being opened, not every covered type.
  'wf-suppliers-and-insurers': Object.freeze({label: '新增供应商', selector: '[data-act="typed-new"][data-kind="suppliers"]'}),
  'wf-workshops-and-jobs': Object.freeze({label: '新增作业项目', selector: '[data-act="typed-new"][data-kind="work_items"]'}),
  'wf-warehouse-location-masters': Object.freeze({label: '新增仓库', selector: '[data-act="typed-new"][data-kind="warehouses"]'}),
  'wf-agency-project-master': Object.freeze({label: '新增代办项目', selector: '[data-act="typed-new"][data-kind="agency_projects"]'}),
  // vehiclecatalog.js catalogEntryDialog (brand, series and model in one form).
  'wf-vehicle-catalog-one-form': Object.freeze({label: '新增车型', selector: '[data-act="catalog-entry"]'}),
  // app.js masterDialog / storeDialog / userDialog / passwordDialog.
  'wf-material-catalog-masters': Object.freeze({label: '新增物资', selector: '[data-act="newmaster"][data-kind="items"]'}),
  'wf-store-management': Object.freeze({label: '新增门店', selector: '[data-act="newstore"]'}),
  'wf-employee-store-roles': Object.freeze({label: '新增员工', selector: '[data-act="newuser"]'}),
  'wf-parameters-password-brand': Object.freeze({label: '修改本人密码', selector: '[data-act="password"]'}),
});

// Intentionally absent: original-record actions (returns/refunds, corrections,
// callbacks, claims, repair rework, invoices, payments, grants), customer/member
// specific actions, and item-specific retail-bundle purchase buttons. Open the
// guide's page so the employee can first choose the right record or rule.
// Also absent: report exports, generated reminders, approvals, execution,
// restore-default buttons and every action that could write without a form.
