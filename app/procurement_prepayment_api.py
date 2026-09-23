"""Strict schemas mounted by the existing procurement router."""
from datetime import date
from pydantic import BaseModel,ConfigDict,Field,model_validator


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Request(Reason,Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    valid_until:date
class Ref(Strict):
    funds_request_id:int=Field(gt=0,strict=True)
    funds_version:int=Field(gt=0,strict=True)
class Decision(Ref,Reason,Evidence):pass
class End(Ref,Reason):pass
class Pay(Ref,Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
    confirmed:bool=Field(strict=True)
    @model_validator(mode='after')
    def actual(self):
        if not self.confirmed:raise ValueError('必须明确确认已实际付款')
        return self


SCHEMAS={'prepay_request':Request,'prepay_approve':Decision,'prepay_reject':Decision,'prepay_cancel':End,'prepay_expire':End,'prepay_pay':Pay}
