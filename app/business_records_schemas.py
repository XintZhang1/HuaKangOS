"""V2 record inputs. Amounts crossing the API are strict integer CNY fen."""
from datetime import date
from decimal import Decimal
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[int, Field(ge=0, le=999999999999, strict=True)]
Key = Annotated[int, Field(gt=0, strict=True)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Command(Strict):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')


class GiftSelection(Strict):
    price_id: Key
    quantity: int = Field(gt=0, le=10000, strict=True)


class ContractSubmission(Strict):
    sales_channel: Literal['retail', 'wholesale'] = 'retail'
    wholesale_channel_id: Key | None = None
    vehicle_invoice_price_cents: Money | None = None
    registration_fee_cents: Money | None = None
    payment_method: Literal['全款', '贷款'] | None = None
    down_payment_cents: Money | None = None
    first_service_count: Annotated[int, Field(ge=0, le=1, strict=True)] | None = None
    nps_participation: Annotated[bool, Field(strict=True)] | None = None
    # Inventory funding is independent of how the customer pays. Old snapshots
    # deliberately remain unknown until an employee explicitly records it.
    is_cash_vehicle: Annotated[bool, Field(strict=True)] | None = None
    installment_fee_cents: Money | None = None
    total_loss_product_cents: Money | None = None
    total_loss_product_description: str = Field(default='', max_length=160)
    trade_in_subsidy_cents: Money | None = None
    used_car_commission_cents: Money | None = None
    finance_excess_cents: Money | None = None
    registration_excess_cents: Money | None = None
    transfer_store: str = Field(default='', max_length=160)
    towing_cost_cents: Money | None = None
    department: str = Field(default='', max_length=160)
    note: str = Field(default='', max_length=4000)


def contract_payment_form(values, payment_method, *, require_deposit=True):
    """Validate stated payment terms, without deriving receipts or other amounts."""
    form = dict(values)
    if payment_method not in {'全款', '贷款'}:
        raise ValueError('请明确选择客户付款方式：全款或贷款')
    form['payment_method'] = payment_method
    if payment_method == '全款':
        for key in ('down_payment', 'payment_bank', 'loan_amount'):
            form[key] = ''
    for key, label, required in (
            ('deposit', '定金', require_deposit),
            ('down_payment', '分期首付', payment_method == '贷款')):
        value = form.get(key, '').strip()
        if not value:
            if required:
                raise ValueError('请填写定金，金额至少2000元' if key == 'deposit' else '请填写分期首付金额；金额为零时请明确填写0')
            continue
        if not re.fullmatch(r'\d+(?:\.\d{1,2})?', value):
            raise ValueError(label + '须为非负金额，最多两位小数')
        amount = Decimal(value)
        if key == 'deposit' and require_deposit and amount < 2000:
            raise ValueError('定金不得低于2000元')
        if amount * 100 > 999999999999:
            raise ValueError(label + '金额超出范围')
        form[key] = format(amount, '.2f')
    return form


def contract_benefits_form(values, submission):
    """Printable projection of independently frozen, non-priced benefits."""
    return {**values, 'standard_benefits_version': '1',
            'first_service_count': str(submission.first_service_count),
            'nps_participation': '1' if submission.nps_participation else '0'}


class ContractInput(Command):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(default='', max_length=40)
    brand: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=160)
    vin: str = Field(min_length=1, max_length=40)
    salesperson_id: Key
    contract_date: date
    sale_price_cents: int = Field(gt=0, le=999999999999, strict=True)
    gift_description: str = Field(default='', max_length=4000)
    form_data: dict[str, str] = Field(default_factory=dict, max_length=50)
    vehicle_price_id: Key | None = None
    inventory_row_id: Key | None = None
    gift_items: list[GiftSelection] = Field(default_factory=list, max_length=100)
    accessory_items: list[GiftSelection] = Field(default_factory=list, max_length=100)
    submission_data: ContractSubmission = Field(default_factory=ContractSubmission)

    @field_validator('form_data')
    @classmethod
    def bounded_fields(cls, values):
        if any(len(key) > 80 or len(value) > 4000 for key, value in values.items()):
            raise ValueError('合同补充字段名称或内容过长')
        if len(values.get('seller_phone', '')) > 40:
            raise ValueError('销售顾问联系电话最多40字')
        if values.get('quantity', '1') != '1':
            raise ValueError('当前每份合同记录一个车架号及一台车辆，数量请填写1')
        return values

    @model_validator(mode='after')
    def explicit_payment_terms(self):
        form = dict(self.form_data)
        if self.vehicle_price_id is not None:
            # The typed submission amount is authoritative for current contracts;
            # form_data keeps only its printable decimal projection.
            payment = self.submission_data.payment_method
            if payment == '全款':
                self.submission_data.down_payment_cents = None
            down = self.submission_data.down_payment_cents
            form['down_payment'] = '' if down is None else format(Decimal(down) / 100, '.2f')
        else:
            payment = form.get('payment_method')
        form = contract_payment_form(form, payment)
        if self.vehicle_price_id is not None or self.submission_data.first_service_count is not None or self.submission_data.nps_participation is not None:
            if self.submission_data.first_service_count is None:
                self.submission_data.first_service_count = 1
            if self.submission_data.nps_participation is None:
                self.submission_data.nps_participation = False
            form = contract_benefits_form(form, self.submission_data)
        self.form_data = form
        return self


class ContractUpdate(ContractInput):
    version: Key


class Action(Command):
    version: Key
    note: str = Field(default='', max_length=2000)


class ManagerApproval(Action):
    gift_excess_cents: Money = 0
    submission_data: ContractSubmission | None = None
    # Required for v30 by the route; optional here keeps historical v29 commands valid.
    minimum_sale_price_cents: Money | None = None
    gift_limit_cents: Money | None = None
    offered_gift_value_cents: Money | None = None
    approval_basis: str | None = Field(default=None, min_length=1, max_length=2000)


class PriceReview(Action):
    expected_amount_cents: Money
    cost_cents: Money
    profit_cents: int = Field(ge=-999999999999, le=999999999999, strict=True)
    gift_cost_cents: Money


class Reject(Action):
    note: str = Field(min_length=1, max_length=2000)


class CorrectionRequest(Action):
    target_user_id: Key
    target_role: Literal['sales', 'manager']
    note: str = Field(min_length=1, max_length=2000)


class CorrectionSubmit(ContractInput):
    version: Key
    gift_excess_cents: Money = 0
    note: str = Field(default='', max_length=2000)


class CorrectionManagerApproval(Action):
    gift_excess_cents: Money = 0


class ReceiptInput(Action):
    actual_amount_cents: int = Field(gt=0, le=999999999999, strict=True)
    received_on: date


class OfficeExtensionFacts(Strict):
    total_loss_count: Annotated[int, Field(ge=0, le=10000, strict=True)] | None = None
    product_count: Annotated[int, Field(ge=0, le=10000, strict=True)] | None = None
    trade_in_count: Annotated[int, Field(ge=0, le=10000, strict=True)] | None = None
    accessory_sales_income_cents: Money | None = None
    accessory_sales_cost_cents: Money | None = None
    # Clerk-confirmed actual cost is separate from the contract's frozen quote.
    accessory_sales_actual_cost_cents: Money | None = None
    total_loss_commission_cents: Money | None = None
    product_commission_cents: Money | None = None
    decoration_count: Annotated[int, Field(ge=0, le=10000, strict=True)] | None = None
    accessory_sales_verified: Annotated[bool, Field(strict=True)] = False
    accessory_sales_file_id: Key | None = None


class OfficeReview(Action):
    report_key: Literal['vehicle_details', 'hail_vehicle_details', 'secondary_vehicle_details', 'vehicle_details_sheet2'] = 'vehicle_details'
    period: date | None = None
    values: dict = Field(default_factory=dict, max_length=150)
    expected_amount_cents: Money | None = None
    cost_cents: Money | None = None
    profit_cents: int | None = Field(default=None, ge=-999999999999, le=999999999999, strict=True)
    gift_cost_cents: Money | None = None
    cash_consumption_cents: Money | None = None
    extension_data: OfficeExtensionFacts = Field(default_factory=OfficeExtensionFacts)


class StandardPriceInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    version: Key | None = None
    sale_price_cents: Money | None = None
    cost_cents: Money | None = None
    note: str = Field(default='', max_length=2000)


class StandardPriceImport(Command):
    rows: list[StandardPriceInput] = Field(min_length=1, max_length=500)


class StandardPriceItem(Strict):
    price_id: Key
    quantity: int = Field(gt=0, le=10000, strict=True)


class StandardPriceEstimate(Strict):
    items: list[StandardPriceItem] = Field(min_length=1, max_length=100)


class CustomerInput(Command):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(default='', max_length=40)
    note: str = Field(default='', max_length=4000)


class AfterSalesInput(Command):
    service_type: Literal['repair', 'maintenance', 'accident', 'renewal', 'extended_warranty', 'accessories']
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(default='', max_length=40)
    vehicle: str = Field(min_length=1, max_length=160)
    brand: str = Field(default='', max_length=100)
    service_items: str = Field(min_length=1, max_length=4000)
    materials_cents: Money = 0
    labor_cents: Money = 0
    cost_cents: Money | None = None
    handler_name: str = Field(min_length=1, max_length=100)
    business_date: date


class ManualReportInput(Command):
    report_key: str = Field(min_length=1, max_length=80)
    period: date
    brand: str = Field(default='', max_length=100)
    salesperson_id: Key | None = None
    values: dict = Field(max_length=150)
    contract_id: Key | None = None
    contract_version: Key | None = None
    entry_mode: Literal['snapshot', 'detail', 'final'] = 'snapshot'
    supersedes_id: Key | None = None
    supersedes_version: Key | None = None
    note: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def paired_source_versions(self):
        if (self.contract_id is None) != (self.contract_version is None):
            raise ValueError('关联的合同与合同版本须一同提供，请重新选择合同')
        if (self.supersedes_id is None) != (self.supersedes_version is None):
            raise ValueError('更正记录与原记录版本须一同提供')
        if self.contract_id is not None and self.entry_mode != 'detail':
            raise ValueError('合同关联统计按单笔明细记录')
        return self


class SettingsInput(Command):
    version: int = Field(ge=0, strict=True)
    approval_mode: Literal['all', 'fixed', 'ratio'] = 'all'
    threshold_amount_cents: Money | None = None
    threshold_basis_points: int | None = Field(default=None, ge=0, le=10000, strict=True)

    @model_validator(mode='after')
    def threshold_required(self):
        if self.approval_mode == 'fixed' and self.threshold_amount_cents is None:
            raise ValueError('固定金额模式须填写赠品成本阈值')
        if self.approval_mode == 'ratio' and self.threshold_basis_points is None:
            raise ValueError('车价比例模式须填写比例基点，100基点为1%')
        return self
