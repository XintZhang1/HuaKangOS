"""Isolated original-cost arithmetic. Workflow tests follow v3 registration.

This initial section intentionally imports no new ORM models during the frozen
prior-version migration acceptance run.
"""
from itertools import permutations
import pytest
from app.transfer_exception_math import bucket_position, original_portion


def test_partial_physical_returns_and_losses_take_exact_original_tail():
    for sequence in permutations((333, 500, 1000, 1167)):
        done=[]
        for quantity in sequence:
            value=original_portion(3000,100,done,quantity)
            done.append((quantity,value))
        assert sum(value for _,value in done)==100
        assert bucket_position(3000,100,done)=={'handled_milli':3000,'handled_cents':100,'remaining_milli':0,'remaining_cents':0}


def test_rejected_sub_batch_and_partial_return_keep_its_own_original_value():
    accepted=original_portion(3000,100,[],1000)
    rejected=original_portion(3000,100,[(1000,accepted)],1000)
    assert (accepted,rejected)==(33,33)
    first_return=original_portion(1000,rejected,[],333)
    loss=original_portion(1000,rejected,[(333,first_return)],667)
    assert (first_return,loss)==(10,23)
    assert first_return+loss==rejected


def test_zero_cost_is_not_zero_physical_quantity():
    assert original_portion(1000,0,[],333)==0
    assert bucket_position(1000,0,[(333,0)])['remaining_milli']==667


@pytest.mark.parametrize('arguments',[(3000,100,[(1000,34)],1),(3000,100,[(3000,100)],1),(1000,33,[],1001),(1000,33,[],True),(1000,33,[],0)])
def test_unbalanced_stale_over_amount_and_noninteger_portions_are_refused(arguments):
    with pytest.raises(ValueError):original_portion(*arguments)
