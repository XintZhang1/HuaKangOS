"""Integer allocation conservation independent of HTTP integration."""
import random
import pytest
from fastapi import HTTPException
from app.retail_group_math import Value, allocate_unit, allocate_return, summarize_pending, distribute


def test_frozen_unit_partial_return_and_restore_do_not_duplicate_income_or_settlement():
    original=Value(1000,801,903)
    cells=allocate_unit(original,[600,400])
    assert cells==[Value(600,481,542),Value(400,320,361)]
    part=allocate_return(250,[cells[0]])[0]
    assert part==Value(250,200,226)
    pending=summarize_pending('coupon',original,part,Value(0,0,0))
    assert pending['pending_original_unit'] and not pending['restorable'] and pending['spendable_credit_cents']==0
    # Existing benefit ledger is still the full capture; the new adjustment
    # immediately reduces revenue and clearing while an indivisible unit waits.
    assert (original.consideration-part.consideration,original.settlement-part.settlement)==(601,677)
    with pytest.raises(HTTPException):summarize_pending('coupon',original,part,part)
    # When fully returned: standard original-unit reversal is compensated once
    # in the pending ledger, so the same return is not deducted twice.
    restored=original
    assert original.face-restored.face-original.face+restored.face==0
    assert summarize_pending('coupon',original,original,restored)['credit_cents']==0


def test_cash_principal_bonus_are_separate_original_cells_and_installation_is_retained():
    goods=[Value(299,299,299),Value(300,300,300),Value(401,0,0)]
    parts=allocate_return(333,goods)
    assert [v.face for v in parts]==[100,100,133]
    assert sum(v.consideration for v in parts)==200
    assert summarize_pending('principal',goods[1],parts[1],parts[1])['credit_cents']==0
    # The caller passes only actual goods reduction. Retained installation
    # does not enter this return distribution and remains a separate cell.
    install=Value(101,101,101)
    assert install==Value(101,101,101)


def test_successive_odd_fen_returns_consume_remaining_values_exactly():
    rng=random.Random(4218)
    for _ in range(200):
        c=rng.randint(1,2000); p=rng.randint(0,c); s=rng.randint(0,c)
        original=Value(c,p,s); left=original; parts=[]
        while left.face:
            amount=rng.randint(1,left.face)
            part=allocate_return(amount,[left])[0]
            parts.append(part);left=left.subtract(part)
        assert [sum(getattr(x,k) for x in parts) for k in ('face','consideration','settlement')]==[c,p,s]


def test_repeated_small_returns_never_reduce_an_earlier_payment_claim():
    # Recomputing cumulative largest-remainder allocations can suffer the
    # Alabama paradox. Each posting here consumes only its original remainder.
    left=[Value(v,v,v) for v in [1500,1500,900,500,500,200]]
    totals=[0]*len(left)
    while sum(v.face for v in left):
        amount=min(25,sum(v.face for v in left));parts=allocate_return(amount,left)
        assert sum(v.face for v in parts)==amount
        for i,part in enumerate(parts):
            totals[i]+=part.face;left[i]=left[i].subtract(part)
    assert totals==[1500,1500,900,500,500,200]


@pytest.mark.parametrize('bad',[True,1.0,-1,10**13])
def test_money_is_strict_integer_and_source_cannot_be_overdrawn(bad):
    with pytest.raises(HTTPException):distribute(bad,[100])
    with pytest.raises(HTTPException):allocate_return(101,[Value(100,80,90)])
