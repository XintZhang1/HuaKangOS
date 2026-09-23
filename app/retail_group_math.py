"""Integer allocation primitives for frozen retail tenders and original returns.

These functions neither move goods nor alter wallets. A return consumes the
remaining original allocation, so repeated partial returns cannot manufacture a
fen or force a negative adjustment to an earlier accepted return.
"""
from dataclasses import dataclass
from fastapi import HTTPException


def integer(value, label, minimum=0, maximum=1_000_000_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise HTTPException(422, label + '须为允许范围内的整数分')
    return value


def distribute(amount, weights):
    """Hamilton allocation of ONE actual posting over remaining capacities."""
    integer(amount, '分摊金额')
    if not weights or len(weights) > 1000:
        raise HTTPException(422, '原分摊清单须有 1 至 1000 项')
    weights = [integer(w, '原剩余额度') for w in weights]
    total = sum(weights)
    if amount > total:
        raise HTTPException(409, '本次退回金额超过原行尚未退回的额度')
    if total == 0:
        return [0] * len(weights)
    values = [amount * w // total for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i))
    for i in order[:amount - sum(values)]:
        values[i] += 1
    return values


def portion(total, amount, remaining):
    integer(total, '剩余原价值'); integer(amount, '本次抵扣额度'); integer(remaining, '剩余抵扣额度')
    if amount > remaining or not remaining:
        raise HTTPException(409, '原抵扣剩余额度不足')
    return total if amount == remaining else (2 * total * amount + remaining) // (2 * remaining)


@dataclass(frozen=True)
class Value:
    """Face C, actual issuance consideration P, and internal settlement S."""
    face: int
    consideration: int
    settlement: int

    def __post_init__(self):
        integer(self.face, '抵扣额度'); integer(self.consideration, '原发行实款分摊'); integer(self.settlement, '内部结算')
        if self.consideration > self.face or self.settlement > self.face:
            raise HTTPException(409, '原发行实款或内部结算不能超过冻结抵扣额度')

    def subtract(self, prior):
        if prior.face > self.face or prior.consideration > self.consideration or prior.settlement > self.settlement:
            raise HTTPException(409, '原核销已被超额退回')
        return Value(self.face-prior.face, self.consideration-prior.consideration, self.settlement-prior.settlement)

    def slice(self, face):
        if not face:
            return Value(0, 0, 0)
        return Value(face, portion(self.consideration, face, self.face), portion(self.settlement, face, self.face))

    def fields(self):
        return dict(credit_cents=self.face, consideration_cents=self.consideration, settlement_cents=self.settlement)


def allocate_unit(value, weights):
    """Freeze each original unit's C/P/S over explicitly eligible components."""
    faces = distribute(value.face, weights)
    # P and S cannot use distribute(): their denominator is allocated C rather
    # than the original (possibly larger) component capacity.
    def scaled(amount):
        if not value.face:
            return [0]*len(faces)
        values = [amount*f//value.face for f in faces]
        order = sorted(range(len(faces)), key=lambda i: (-(amount*faces[i]%value.face), i))
        for i in order[:amount-sum(values)]: values[i] += 1
        return values
    prices, internal = scaled(value.consideration), scaled(value.settlement)
    return [Value(c,p,s) for c,p,s in zip(faces,prices,internal)]


def allocate_return(amount, remaining):
    """Return one original component over its remaining original tender cells."""
    return [v.slice(c) for v,c in zip(remaining,distribute(amount,[v.face for v in remaining]))]


def summarize_pending(kind, original, returned, restored):
    remaining = original.subtract(returned)
    pending = returned.subtract(restored)
    if kind in {'coupon','package'} and restored.face not in {0,original.face}:
        raise HTTPException(409, '券和套餐只能恢复原核销的完整整数份')
    if kind in {'coupon','package'} and restored.face and remaining.face:
        raise HTTPException(409, '原单位对应的退回额度尚未凑整')
    return {**pending.fields(), 'spendable_credit_cents':0,
            'restorable':bool(pending.face and (kind not in {'coupon','package'} or not remaining.face)),
            'pending_original_unit':kind in {'coupon','package'} and bool(pending.face and remaining.face)}
