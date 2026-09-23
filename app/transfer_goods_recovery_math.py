"""Integer allocation for a separately recorded recovery of written-off goods."""


def allocation(loss_quantity, loss_value, destination_burden, found_done, restored_done,
               value_done, destination_done, quantity, usable):
    values=(loss_quantity,loss_value,destination_burden,found_done,restored_done,value_done,destination_done,quantity)
    if any(type(x) is not int for x in values) or type(usable) is not bool:
        raise ValueError('数量与金额必须是整数，复验结果必须明确')
    if loss_quantity<=0 or quantity<=0 or min(values[1:])<0 or destination_burden>loss_value:
        raise ValueError('原损失数量、成本或承担无效')
    if not 0<=restored_done<=found_done<=loss_quantity or found_done+quantity>loss_quantity:
        raise ValueError('本次找回超过原损失尚未处理数量')
    if value_done!=loss_value*restored_done//loss_quantity:
        raise ValueError('已恢复价值不符合原损失累计尾差')
    expected_destination=destination_burden*value_done//loss_value if loss_value else 0
    if destination_done!=expected_destination:
        raise ValueError('已恢复承担不符合原成本累计分摊')
    restored=quantity if usable else 0
    total_value=loss_value*(restored_done+restored)//loss_quantity
    value=total_value-value_done
    destination=(destination_burden*total_value//loss_value if loss_value else 0)-destination_done
    return dict(found_quantity_milli=quantity,restored_quantity_milli=restored,
                value_cents=value,source_reverse_cents=value-destination,destination_reverse_cents=destination)
