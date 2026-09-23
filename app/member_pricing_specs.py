"""Read-only flow catalogue metadata; commands belong to the pricing domain."""

SPEC=dict(label='会员价格规则',module='members',create_roles=[],fields=[],initial='draft',actions=[])


def spec():
    return SPEC
