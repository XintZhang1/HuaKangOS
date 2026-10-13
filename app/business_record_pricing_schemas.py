"""Employee-confirmed price publications; model suggestions use the same units."""
from typing import Literal
from pydantic import Field, model_validator
from .business_records_schemas import Strict, Command, Money, Key, GiftSelection


class GiftPolicyInput(Strict):
    text: str = Field(default='', max_length=3000)
    standard_gift_note: str = Field(default='', max_length=3000)
    cost_limit_cents: Money | None
    # These are employee-selected catalog identities, never parsed from prose.
    standard_gifts: list[GiftSelection] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique_standard_gifts(self):
        if len({item.price_id for item in self.standard_gifts}) != len(self.standard_gifts):
            raise ValueError('标准赠品请合并同一项目的数量，不要重复选择')
        return self


class VehiclePriceInput(Strict):
    family: str = Field(min_length=1, max_length=100)
    series: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=160)
    guide_price_cents: Money
    control_price_cents: Money
    note: str = Field(default='', max_length=2000)
    gift_policy: GiftPolicyInput | None

    @model_validator(mode='after')
    def positive_prices(self):
        if not self.guide_price_cents or not self.control_price_cents:
            raise ValueError('指导价和销售管控价必须明确且大于零')
        if len(self.series + ' ' + self.model) > 160:
            raise ValueError('车系及车型配置合计请勿超过160字')
        return self


class GiftPriceInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    unit_price_cents: Money | None = None
    unit_cost_cents: Money | None = None
    brand: str = Field(default='', max_length=100)
    unit: str = Field(default='', max_length=40)
    applicable_models: str = Field(default='', max_length=300)
    source_ref: str = Field(default='', max_length=300)
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def known_amount(self):
        if self.unit_price_cents is None and self.unit_cost_cents is None:
            raise ValueError('赠品成本或售价至少须有一项已核定，空白不可当作零')
        return self


class VehiclePriceImport(Command):
    sales_channel: Literal['retail', 'wholesale'] = 'retail'
    version: int = Field(ge=0, strict=True)
    brand_version: int = Field(ge=0, strict=True)
    brand: str = Field(min_length=1, max_length=100)
    file_id: Key
    rows: list[VehiclePriceInput] = Field(min_length=1, max_length=2000)
    policy_confirmed: bool = Field(strict=True)

    @model_validator(mode='after')
    def reviewed_policy(self):
        if self.policy_confirmed is not True:
            raise ValueError('请逐行核对赠品政策及成本额度，或明确无金额限制后勾选确认')
        return self


class GiftPolicyCheck(Strict):
    sales_channel: Literal['retail', 'wholesale'] = 'retail'
    vehicle_price_id: Key
    gift_items: list[GiftSelection] = Field(default_factory=list, max_length=100)
    contract_id: Key | None = None


class GiftPriceImport(Command):
    version: int = Field(ge=0, strict=True)
    brand_version: int = Field(ge=0, strict=True)
    file_id: Key
    brand: str = Field(min_length=1, max_length=100)
    rows: list[GiftPriceInput] = Field(min_length=1, max_length=2000)


class SellerInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default='', max_length=500)


class StoreProfileInput(Command):
    version: int = Field(ge=0, strict=True)
    brand: str | None = Field(default=None, max_length=100)
    address: str = Field(default='', max_length=500)
    sellers: list[SellerInput] = Field(default_factory=list, max_length=50)
    sales_contacts: dict[str, str] = Field(default_factory=dict, max_length=500)


class VehicleVariantInput(Command):
    version: int = Field(ge=0, strict=True)
    brand_version: int = Field(ge=0, strict=True)
    brand: str = Field(min_length=1, max_length=100)
    family: str = Field(min_length=1, max_length=100)
    series: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=160)
