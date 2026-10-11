"""Focused target semantics; run only from the external synthetic source mirror.

HTTP tenancy, idempotency, append-only revisions and browser interaction belong
to the accompanying isolated integration run, not to these pure projections.
"""
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.business_record_targets import MonthlyTargetInput, target_values, can_manage_targets
from app.business_record_reports import CATALOG_BY_KEY
from app.business_record_report_generation import (
    aggregate_rows, latest_snapshots, effective_records, contract_statistics, _overlap)


class MonthlyTargetSemantics(unittest.TestCase):
    def body(self, **changes):
        return MonthlyTargetInput(request_id='synthetic-target-request', month='2026-10',
                                  brand='合成品牌', series='合成系列', **changes)

    def test_blank_slash_and_zero_have_different_input_meanings(self):
        body = self.body(sales_units=0, mechanical_cents='/', accident_cents=None)
        self.assertEqual(target_values(body), {
            'c01': '合成系列', 'c02': '0', 'c03': '/', 'c04': None, 'c05': None})

    def test_precision_and_invalid_types_are_rejected(self):
        for field, value in [('sales_units', 1.5), ('sales_units', True),
                             ('mechanical_cents', 1.1), ('mechanical_cents', '123'),
                             ('mechanical_cents', -1), ('accident_cents', False),
                             ('after_sales_cents', float('nan'))]:
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                self.body(**{field: value})
        with self.assertRaises(ValidationError):
            MonthlyTargetInput(request_id='synthetic-target-request', month='0000-01', series='合成系列')

    def test_money_is_exact_and_total_is_not_invented(self):
        values = target_values(self.body(mechanical_cents=999999999999,
                                        accident_cents=1, after_sales_cents=None))
        self.assertEqual(values['c03'], '9999999999.99')
        self.assertEqual(values['c04'], '0.01')
        self.assertIsNone(values['c05'])
        self.assertEqual(target_values(self.body(after_sales_cents=200))['c05'], '2.00')

    def test_revision_identifiers_must_be_paired(self):
        for changes in [{'supersedes_id': 1}, {'supersedes_version': 1}]:
            with self.assertRaises(ValidationError):
                self.body(**changes)

    def test_manager_permission_uses_current_store_role_and_aggregate_is_read_only(self):
        for role in ['admin', 'manager', 'general_manager', 'chairman', 'group_deputy_manager']:
            self.assertTrue(can_manage_targets(SimpleNamespace(role=role)))
            self.assertFalse(can_manage_targets(SimpleNamespace(role=role, _aggregate_scope=True)))
        for role in ['clerk', 'sales', 'finance', 'service']:
            self.assertFalse(can_manage_targets(SimpleNamespace(role=role)))

    def test_target_snapshot_does_not_displace_actual_snapshot(self):
        base = dict(period='2026-10-01', store_id=1, brand='合成品牌', salesperson_id=None, c01='合成系列')
        target = dict(base, id=1, entry_mode='target', c02='10')
        actual = dict(base, id=2, period='2026-10-10', entry_mode='snapshot', c06='3')
        latest_target = dict(base, id=3, entry_mode='target', c02='12')
        rows = latest_snapshots([target, actual, latest_target], CATALOG_BY_KEY['sales_targets'])
        self.assertEqual({row['id'] for row in rows}, {2, 3})
        self.assertEqual({row['id'] for row in effective_records([
            target, dict(latest_target, supersedes_id=1)])}, {3})

    def test_targets_and_actuals_do_not_make_each_other_unknown(self):
        target = {'c02': '10', 'c03': None, 'c04': None, 'c05': '200.00',
                  '_applicable_fields': {'c02', 'c03', 'c04', 'c05'}}
        actual = {'c06': '2', 'c09': '100.00', '_applicable_fields': {'c06', 'c09'}}
        total = aggregate_rows([target, actual], CATALOG_BY_KEY['sales_targets'], '合成范围')
        self.assertEqual(total['c02'], '10')
        self.assertEqual(total['c06'], '2')
        self.assertEqual(total['c10'], '20.000000')
        self.assertEqual(total['c11'], '50.000000')
        self.assertIsNone(total['c03'])

    def test_missing_target_in_one_series_does_not_become_zero_in_total(self):
        rows = [{'c02': '10', '_applicable_fields': {'c02'}},
                {'c02': None, '_applicable_fields': {'c02'}}]
        total = aggregate_rows(rows, CATALOG_BY_KEY['sales_targets'], '合成范围')
        self.assertIsNone(total['c02'])
        self.assertIsNone(total['c10'])

    def test_series_comes_from_confirmed_source_and_is_not_guessed_from_model(self):
        contract = SimpleNamespace(profit_cents=None, cost_cents=None, model='不能猜成系列')
        receipt = SimpleNamespace(actual_amount_cents=1)
        definition = CATALOG_BY_KEY['sales_targets']
        source = SimpleNamespace(report_key='vehicle_details', values={'c03': '已确认系列'})
        known = contract_statistics('sales_targets', contract, receipt, '', source, definition)
        self.assertEqual(known, {'c01': '已确认系列', 'c06': '1'})
        unknown = contract_statistics('sales_targets', contract, receipt, '', None, definition)
        self.assertEqual(unknown, {'c06': '1'})

    def test_unclassified_business_does_not_replace_a_named_series_actual(self):
        scope = dict(period='2026-10-01', store_id=1, brand='合成品牌', salesperson_id=None)
        named = dict(scope, c01='已确认系列', c06='3')
        unclassified = dict(scope, c06='1')
        definition = CATALOG_BY_KEY['sales_targets']
        self.assertFalse(_overlap(named, unclassified, definition))
        self.assertFalse(_overlap(named, dict(unclassified, c01='其他系列'), definition))
        self.assertTrue(_overlap(named, dict(unclassified, c01='已确认系列'), definition))

    def test_legacy_store_goal_and_series_goal_are_not_summed(self):
        scope = dict(period='2026-10-01', store_id=1, brand='合成品牌', salesperson_id=None)
        old = dict(scope, entry_mode='snapshot', c01='', c02='100', _applicable_fields={'c02'})
        target = dict(scope, entry_mode='target', c01='合成系列', c02='10', _applicable_fields={'c02'})
        total = aggregate_rows([old, target], CATALOG_BY_KEY['sales_targets'], '合成范围')
        self.assertIsNone(total['c02'])
        self.assertTrue(total['aggregation_warnings'])
        self.assertEqual(aggregate_rows([target], CATALOG_BY_KEY['sales_targets'], '合成系列')['c02'], '10')

    def test_unclassified_actual_and_named_manual_actual_total_stays_unknown(self):
        scope = dict(period='2026-10-01', store_id=1, brand='合成品牌', salesperson_id=None)
        old = dict(scope, entry_mode='snapshot', c01='合成系列', c06='3', c10='30',
                   _applicable_fields={'c06', 'c10'})
        generated = dict(scope, entry_mode='generated', c06='1', _applicable_fields={'c06'})
        target = dict(scope, entry_mode='target', c01='合成系列', c02='10', _applicable_fields={'c02'})
        total = aggregate_rows([old, generated, target], CATALOG_BY_KEY['sales_targets'], '合成范围')
        self.assertIsNone(total['c06'])
        self.assertIsNone(total['c10'])
        self.assertTrue(total['aggregation_warnings'])


if __name__ == '__main__':
    unittest.main()
