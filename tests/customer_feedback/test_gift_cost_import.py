"""Run only from the external source mirror with synthetic inputs."""
import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from app.business_record_gift_import import preview_gift_file, canonical_brand
from app.business_record_pricing_schemas import GiftPriceInput


class GiftCostImportChecks(unittest.TestCase):
    def test_separate_cost_sale_blank_and_zero(self):
        source = ('名称,品牌,成本（元）,售价（元）,单位,适用车型\n'
                  '脚垫,阿维塔,68.25,,套,12\n'
                  '礼盒,腾势,0,180.50,套,\n').encode('utf-8-sig')
        result = preview_gift_file(source, 'text/csv; charset=utf-8', '阿维塔')
        rows = result['rows']
        self.assertEqual((rows[0]['unit_cost_cents'], rows[0]['unit_price_cents']), (6825, None))
        self.assertEqual((rows[1]['unit_cost_cents'], rows[1]['unit_price_cents']), (0, 18050))
        self.assertEqual(rows[1]['brand'], '腾势')  # Mismatch remains explicit for the API guard.
        self.assertEqual(rows[0]['source_ref'], 'CSV:2')

    def test_invalid_or_ambiguous_amounts_never_become_zero(self):
        for value in ('1.001', '-1', 'NaN', '无货', '建议100'):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                preview_gift_file(('名称,成本\n脚垫,' + value).encode(), 'text/csv; charset=utf-8', '阿维塔')
        with self.assertRaises(HTTPException):
            preview_gift_file('名称,单价\n脚垫,100'.encode(), 'text/csv; charset=utf-8', '阿维塔')

    def test_input_preserves_unknown_and_requires_one_fact(self):
        cost_only = GiftPriceInput(name='脚垫', unit_cost_cents=6825)
        self.assertIsNone(cost_only.unit_price_cents)
        with self.assertRaises(ValidationError):
            GiftPriceInput(name='脚垫')
        with self.assertRaises(ValidationError):
            GiftPriceInput(name='脚垫', unit_cost_cents=1.1)

    def test_only_reviewed_brand_aliases(self):
        self.assertEqual(canonical_brand('启源'), '长安启源')
        self.assertEqual(canonical_brand('长安凯程'), '凯程')
        self.assertEqual(canonical_brand('深蓝'), '深蓝汽车')
        self.assertEqual(canonical_brand('BYD'), '比亚迪')
        self.assertEqual(canonical_brand('默认门店'), '默认门店')


if __name__ == '__main__':
    unittest.main()
