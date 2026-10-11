"""V2 record inputs. Amounts crossing the API are strict integer CNY fen."""
from datetime import date
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
    vehicle_invoice_price_cents: Money | None = None
    registration_fee_cents: Money | None = None
    payment_method: Literal['全款', '贷款'] = '全款'
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
    gift_items: list[GiftSelection] = Field(default_factory=list, max_length=100)
    submission_data: ContractSubmission = Field(default_factory=ContractSubmission)

    @field_validator('form_data')
    @classmethod
    def bounded_fields(cls, values):
        if any(len(key) > 80 or len(value) > 4000 for key, value in values.items()):
            raise ValueError('合同补充字段名称或内容过长')
        if values.get('quantity', '1') != '1':
            raise ValueError('当前每份合同记录一个车架号及一台车辆，数量请填写1')
        return values


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


class ReceiptInput(Action):
    actual_amount_cents: int = Field(gt=0, le=999999999999, strict=True)
    received_on: date


class OfficeReview(Action):
    report_key: Literal['vehicle_details', 'hail_vehicle_details', 'secondary_vehicle_details', 'vehicle_details_sheet2'] = 'vehicle_details'
    period: date | None = None
    values: dict = Field(default_factory=dict, max_length=150)
    expected_amount_cents: Money | None = None
    cost_cents: Money | None = None
    profit_cents: int | None = Field(default=None, ge=-999999999999, le=999999999999, strict=True)
    gift_cost_cents: Money | None = None
    cash_consumption_cents: Money | None = None


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
