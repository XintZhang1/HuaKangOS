from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal, Annotated
import re
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, field_validator, model_validator
from .db import today


def money(value):
    if isinstance(value, bool):
        raise ValueError('金额必须是数字，最多两位小数')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('金额格式错误') from exc
    if not number.is_finite() or abs(number) > Decimal('9999999999.99') or number != number.quantize(Decimal('0.01')):
        raise ValueError('金额最多两位小数，且不得超过 9,999,999,999.99 元')
    return number

Money = Annotated[Decimal, BeforeValidator(money), Field(ge=0)]
PositiveMoney = Annotated[Decimal, BeforeValidator(money), Field(gt=0)]
Role = Literal['admin', 'manager', 'sales', 'inventory', 'service', 'finance', 'auditor', 'reception', 'technician', 'customer_service']
StoreRole = Literal['manager', 'sales', 'inventory', 'service', 'finance', 'auditor', 'reception', 'technician', 'customer_service']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class DocumentInput(Strict):
    doc_no: str = Field(min_length=1, max_length=60)
    business_date: date
    note: str = Field(default='', max_length=2000)
    @field_validator('business_date')
    @classmethod
    def valid_day(cls, value):
        if not date(2000, 1, 1) <= value <= today():
            raise ValueError('业务日期必须为 2000 年起且不晚于今天的实际发生日期')
        return value


class CustomerInput(Strict):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(default='', max_length=30, pattern=r'^[0-9+() \-]*$')


class VehicleInput(DocumentInput):
    vin: str = Field(min_length=17, max_length=17, pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    color: str = Field(default='', max_length=40)
    supplier: str = Field(default='', max_length=120)
    location: str = Field(default='', max_length=120)
    purchase_cost: Money
    list_price: Money
    @field_validator('vin', mode='before')
    @classmethod
    def normalize_vin(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class SaleInput(DocumentInput, CustomerInput):
    vehicle_id: int = Field(gt=0)
    salesperson: str = Field(min_length=1, max_length=80)
    sale_stage: Literal['ordered', 'delivered'] = 'ordered'
    delivery_date: date | None = None
    contract_amount: PositiveMoney
    @model_validator(mode='after')
    def check_delivery(self):
        if self.sale_stage == 'ordered' and self.delivery_date is not None:
            raise ValueError('未交车订单不能填写交车日期')
        if self.sale_stage == 'delivered' and (self.delivery_date is None or not self.business_date <= self.delivery_date <= today()):
            raise ValueError('已交车必须填写有效交车日期，且不早于订单日期、不晚于今天')
        return self


class RepairInput(DocumentInput, CustomerInput):
    plate_number: str = Field(min_length=1, max_length=30)
    service_advisor: str = Field(min_length=1, max_length=80)
    repair_type: Literal['maintenance', 'repair', 'insurance'] = 'maintenance'
    repair_stage: Literal['open', 'completed'] = 'open'
    policy_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    completion_date: date | None = None
    labor_amount: Money
    parts_amount: Money
    discount: Money = Decimal('0')
    cost_amount: Money = Decimal('0')
    @model_validator(mode='after')
    def check_repair(self):
        if self.discount > self.labor_amount + self.parts_amount:
            raise ValueError('优惠金额不能超过工时费与配件费合计')
        if self.due_date and self.due_date < self.business_date:
            raise ValueError('预计完工日期不能早于报修日期')
        if self.repair_stage == 'open' and self.completion_date:
            raise ValueError('未完工单不能填写完工日期')
        if self.repair_stage == 'completed' and (self.completion_date is None or not self.business_date <= self.completion_date <= today()):
            raise ValueError('已完工必须填写有效完工日期')
        return self


class PolicyInput(DocumentInput, CustomerInput):
    policy_number: str = Field(min_length=1, max_length=80)
    insurer: str = Field(min_length=1, max_length=100)
    plate_number: str = Field(min_length=1, max_length=30)
    policy_type: Literal['commercial', 'compulsory', 'combined'] = 'commercial'
    start_date: date
    end_date: date
    premium: PositiveMoney
    commission: Money = Decimal('0')
    @model_validator(mode='after')
    def check_policy(self):
        if self.end_date < self.start_date:
            raise ValueError('保险到期日不能早于生效日')
        return self


class CashInput(DocumentInput):
    direction: Literal['in', 'out']
    category: Literal['sale_collection','repair_collection','premium_collection','commission','vehicle_purchase','operating_expense','refund','capital','loan','transfer']
    amount: PositiveMoney
    account: str = Field(min_length=1, max_length=100)
    counter_account: str = Field(default='', max_length=100)
    counterparty: str = Field(default='', max_length=120)
    payment_method: Literal['bank','cash','wechat','alipay','other'] = 'bank'
    voucher_no: str = Field(min_length=1, max_length=100)
    related_type: Literal['none','sales','repairs','policies','vehicles'] = 'none'
    related_id: int | None = Field(default=None, gt=0)
    @model_validator(mode='after')
    def check_category(self):
        expected = {'sale_collection': ('in','sales'), 'repair_collection': ('in','repairs'),
                    'premium_collection': ('in','policies'), 'commission': ('in','policies'),
                    'vehicle_purchase': ('out','vehicles'), 'operating_expense': ('out','none')}
        if self.category in expected and (self.direction, self.related_type) != expected[self.category]:
            raise ValueError('收支方向、分类与关联业务不匹配')
        if (self.related_type == 'none') != (self.related_id is None):
            raise ValueError('关联类型与关联 ID 必须同时填写或同时留空')
        if self.category in {'capital','loan','transfer'} and self.related_type != 'none':
            raise ValueError('资金性往来不能关联销售、维修或保单')
        if self.category == 'refund' and (self.direction != 'out' or self.related_type not in {'sales','repairs','policies'}):
            raise ValueError('退款须为支出并关联销售、维修或保单')
        if self.category == 'transfer':
            if self.direction != 'out' or not self.counter_account or self.counter_account == self.account:
                raise ValueError('内部转账统一录入转出方向，且必须填写不同的转入账户')
        elif self.counter_account:
            raise ValueError('只有内部转账需要填写转入账户')
        return self


INPUTS = {'vehicles': VehicleInput, 'sales': SaleInput, 'repairs': RepairInput, 'policies': PolicyInput, 'cash': CashInput}


class UpdateInput(Strict):
    version: int = Field(gt=0)
    data: dict


class ActionInput(Strict):
    version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)
    effective_date: date | None = None


class LoginInput(Strict):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class PasswordInput(Strict):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class StoreRoleInput(Strict):
    store_id: int = Field(gt=0)
    role: StoreRole


class UserInput(Strict):
    store_ids: list[int] = Field(default_factory=list, max_length=200)
    store_roles: list[StoreRoleInput] | None = Field(default=None, max_length=200)
    can_group_summary: bool = False
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,40}$')
    display_name: str = Field(min_length=1, max_length=80)
    role: Role
    password: str = Field(min_length=12, max_length=128)


class BatchUserRow(Strict):
    """One pasted staff row. Row-level rules live in the handler so the error names the line."""
    username: str = Field(max_length=40)
    display_name: str = Field(max_length=80)
    role: str = Field(max_length=40)


class BatchUserInput(Strict):
    # Staff only: a second system administrator still goes through the single form.
    store_id: int = Field(gt=0)
    password: str = Field(min_length=12, max_length=128)
    rows: list[BatchUserRow] = Field(min_length=1, max_length=50)


class UserUpdate(Strict):
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    access_version: int = Field(gt=0, strict=True)
    store_ids: list[int] | None = Field(default=None, max_length=200)
    store_roles: list[StoreRoleInput] | None = Field(default=None, max_length=200)
    can_group_summary: bool | None = None
    role: Role
    display_name: str = Field(min_length=1, max_length=80)
    active: bool


class ResetPasswordInput(Strict):
    password: str = Field(min_length=12, max_length=128)
    reason: str = Field(min_length=3, max_length=1000)


class ReviewInput(Strict):
    version: int = Field(gt=0)
    status: Literal['open','reviewing','confirmed','dismissed','resolved']
    note: str = Field(min_length=5, max_length=2000)


class ReportInput(Strict):
    business_date: date
    use_ai: bool = False
    retry_ai: bool = False
    @field_validator('business_date')
    @classmethod
    def report_date(cls, value):
        if not date(2000,1,1) <= value <= today():
            raise ValueError('不能生成未来日期的日报')
        return value


class AIReview(Strict):
    ref: str = Field(max_length=50)
    reason: str = Field(min_length=1, max_length=600)
    action: str = Field(min_length=1, max_length=600)


class AIResult(Strict):
    summary: str = Field(min_length=1, max_length=2000)
    highlights: list[str] = Field(max_length=10)
    reviews: list[AIReview] = Field(max_length=30)
    limitations: str = Field(max_length=1500)
    @field_validator('highlights')
    @classmethod
    def bounded_highlights(cls, values):
        if any(len(v) > 600 for v in values):
            raise ValueError('Highlights too long')
        return values


class StoreInput(Strict):
    code: str = Field(min_length=1, max_length=30, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=100)
    active: bool = True


class FeedbackInput(Strict):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=12000)
    category: Literal['bug','improvement','feature'] = 'improvement'
    consent_code_review: bool = False
