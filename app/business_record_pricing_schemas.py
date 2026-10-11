"""Employee-confirmed price publications; model suggestions use the same units."""
from pydantic import Field, model_validator
from .business_records_schemas import Strict, Command, Money, Key


class VehiclePriceInput(Strict):
    family: str = Field(min_length=1, max_length=100)
    series: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=160)
    guide_price_cents: Money
    control_price_cents: Money
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def positive_prices(self):
        if not self.guide_price_cents or not self.control_price_cents:
            raise ValueError('指导价和销售管控价必须明确且大于零')
        if len(self.series + ' ' + self.model) > 160:
            raise ValueError('车系及车型配置合计请勿超过160字')
        return self


class GiftPriceInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    unit_price_cents: Money
    note: str = Field(default='', max_length=2000)


class VehiclePriceImport(Command):
    version: int = Field(ge=0, strict=True)
    file_id: Key
    rows: list[VehiclePriceInput] = Field(min_length=1, max_length=2000)


class GiftPriceImport(Command):
    version: int = Field(ge=0, strict=True)
    file_id: Key
    rows: list[GiftPriceInput] = Field(min_length=1, max_length=2000)


class SellerInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default='', max_length=500)


class StoreProfileInput(Command):
    version: int = Field(ge=0, strict=True)
    brand: str = Field(min_length=1, max_length=100)
    address: str = Field(default='', max_length=500)
    sellers: list[SellerInput] = Field(default_factory=list, max_length=50)
    sales_contacts: dict[str, str] = Field(default_factory=dict, max_length=500)


class VehicleVariantInput(Command):
    version: int = Field(ge=0, strict=True)
    family: str = Field(min_length=1, max_length=100)
    series: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=160)
