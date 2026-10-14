"""Explicit uploader mappings; no cross-store target or inferred financial status."""
from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from .business_records_schemas import Strict, Command, Key


class InventoryOverride(Strict):
    source_row: Key
    production_on: date | None = None
    exterior_color: str | None = Field(default=None, max_length=100)
    interior_color: str | None = Field(default=None, max_length=100)
    vehicle_price_id: Key | None = None


class InventoryMapping(Strict):
    sheet: str = Field(min_length=1, max_length=100)
    header_row: int = Field(ge=1, le=20, strict=True)
    columns: dict[str, str] = Field(max_length=20)
    as_of_date: date
    source_owners: list[str] = Field(min_length=1, max_length=200)
    funding_map: dict[str, Literal['cash', 'third_party', 'unknown']] = Field(default_factory=dict, max_length=200)
    configuration_contains_colors: bool = False
    overrides: list[InventoryOverride] = Field(default_factory=list, max_length=10000)

    @model_validator(mode='after')
    def unique_rows(self):
        if len({r.source_row for r in self.overrides}) != len(self.overrides):
            raise ValueError('同一来源行只能有一份核对结果')
        if len(set(self.source_owners)) != len(self.source_owners):
            raise ValueError('来源所属店请勿重复选择')
        return self


class InventoryPreview(InventoryMapping):
    # The initial field preview discovers the original ownership labels. It
    # cannot publish until the uploader explicitly selects their store scope.
    source_owners: list[str] = Field(default_factory=list, max_length=200)


class InventoryPublish(Command):
    version: int = Field(ge=0, strict=True)
    mapping: InventoryMapping
    confirmed: Literal[True]
    confirmed_brand: str = Field(min_length=1, max_length=100)
    confirmed_store_id: Key
