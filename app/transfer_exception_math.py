"""Integer original-batch arithmetic, independent of any database or state change."""


def bucket_position(quantity_milli, value_cents, handled):
    """Return remaining quantity/value after chronological original-batch facts.

    `handled` contains completed normal dispositions and confirmed losses, never
    mere observations or claims. Each tuple is (quantity_milli, value_cents).
    Cumulative floor allocation gives the last physical/loss portion the exact
    original remainder, including a zero-value but nonzero-quantity batch.
    """
    if type(quantity_milli) is not int or type(value_cents) is not int or quantity_milli <= 0 or value_cents < 0:
        raise ValueError('原调拨批次数量或价值无效')
    done_quantity = done_value = 0
    for quantity, value in handled:
        if type(quantity) is not int or type(value) is not int or quantity <= 0 or value < 0:
            raise ValueError('原批次处理数量或价值无效')
        done_quantity += quantity
        done_value += value
    if done_quantity > quantity_milli or done_value != done_quantity * value_cents // quantity_milli:
        raise ValueError('原批次处理量或累计原成本不守恒')
    return {'handled_milli': done_quantity, 'handled_cents': done_value,
            'remaining_milli': quantity_milli-done_quantity, 'remaining_cents': value_cents-done_value}


def original_portion(quantity_milli, value_cents, handled, requested_milli):
    position = bucket_position(quantity_milli, value_cents, handled)
    if type(requested_milli) is not int or requested_milli <= 0 or requested_milli > position['remaining_milli']:
        raise ValueError('本次数量超过原批次剩余数量')
    return (position['handled_milli']+requested_milli)*value_cents//quantity_milli-position['handled_cents']
