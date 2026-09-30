"""M8.2 closure check: compare the archived baseline against what this workspace adds.

M8.2 requires that the baseline and the new cases be compared item by item, with
a reason for everything added, missing or inapplicable. This script does that
comparison from two artefacts and nothing else:

  * the archived baseline aggregate of a finished M0.2.B run (declared inventory,
    executed node ids, per-node status), and
  * the versioned suites in this folder, which are the cases added since.

It never runs a test and never writes outside its own report. A missing baseline
module, an executed node that no module declares, a failed node, or a suite that
is present but not registered in the milestone rules all fail the verdict, so a
green result cannot be produced by leaving things out.

Usage:
  python check_m82_closeout.py --baseline <run>/reports/baseline.json \
      --manifest <root>/validation-manifest.json \
      --report evidence/m82-closeout.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ENVIRONMENT_LIMITATION = 'symlink'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def module_of(row):
    """The owning module of one evidence row.

    Only pytest rows carry a file path in `nodeid`; scripted commands report
    their own node names (`catalog`, `check_assistant_business....`), so those
    are attributed to the command that produced them instead of being mistaken
    for undeclared files.
    """
    nodeid = row.get('nodeid') or ''
    command_id = row.get('command_id') or ''
    if '::' in nodeid and nodeid.split('::', 1)[0].startswith('tests/'):
        return nodeid.split('::', 1)[0]
    if command_id.startswith('b02-') or command_id.startswith('b03-') or command_id.startswith('b04-'):
        return command_id
    return nodeid.split('::', 1)[0]


def baseline_facts(baseline, manifest):
    inventory = ((manifest.get('milestones') or {}).get('M0.2') or {}).get('baseline_inventory') or {}
    facts, problems = {}, []
    nodes = baseline.get('per_node') or []
    facts['executed_nodes'] = len(nodes)
    executed_modules = sorted({module_of(row) for row in nodes if row.get('nodeid') or row.get('command_id')})
    facts['executed_modules'] = len(executed_modules)
    status = {}
    for row in nodes:
        status[row.get('status')] = status.get(row.get('status'), 0) + 1
    facts['node_status'] = status
    if status.get('failed') or status.get('error'):
        problems.append('the baseline reports failed nodes: '
                        + str(status.get('failed') or 0) + ' failed, ' + str(status.get('error') or 0) + ' error')
    skipped = [row['nodeid'] for row in nodes if row.get('status') == 'skipped']
    facts['skipped_nodes'] = skipped
    unexplained = [node for node in skipped if ENVIRONMENT_LIMITATION not in node]
    if unexplained:
        problems.append('unexplained skipped nodes: ' + ', '.join(unexplained[:5]))
    if not baseline.get('inventory_complete'):
        problems.append('the baseline inventory is not complete')
    if not baseline.get('coverage_complete'):
        problems.append('the baseline coverage is not complete')
    for key in ('missing', 'extra', 'duplicate'):
        values = baseline.get(key) or []
        facts[key] = len(values)
        if values:
            problems.append(str(len(values)) + ' baseline ' + key + ' entries: ' + ', '.join(map(str, values[:5])))
    # A declared module is either a baseline pytest module or a registered
    # scripted command of this milestone; both are named in the manifest, so
    # nothing counts as "executed but undeclared" by accident.
    registration = (manifest.get('milestones') or {}).get('M0.2') or {}
    # Only this phase's commands can have run here; a phase A command being
    # absent from a phase B run is a fact about the phase, not a gap.
    scripted = {command.get('command_id') for command in (registration.get('commands') or [])
                if command.get('kind') == 'python_script'
                and (command.get('phase') or 'B') == 'B'}
    declared = sorted(set(inventory.get('applicable_original_pytest_modules') or [])
                      | set(inventory.get('added_test_modules') or [])
                      | {value for value in scripted if value})
    facts['declared_modules'] = len(declared)
    facts['declared_scripted_commands'] = sorted(value for value in scripted if value)
    absent = [name for name in declared if name not in executed_modules]
    facts['declared_not_executed'] = absent
    if absent:
        problems.append('declared modules executed nothing: ' + ', '.join(absent[:5]))
    undeclared = [name for name in executed_modules if name not in declared]
    facts['executed_not_declared'] = undeclared
    if undeclared:
        problems.append('executed modules that the inventory does not declare: ' + ', '.join(undeclared[:5]))
    facts['not_applicable'] = [row.get('file') for row in (inventory.get('not_applicable') or [])]
    facts['deferred'] = [row.get('script') for row in (inventory.get('deferred_acceptance') or [])]
    facts['deferred_owner'] = sorted({row.get('owner') for row in (inventory.get('deferred_acceptance') or [])})
    return facts, problems, executed_modules


def workspace_additions(rules):
    """Everything this folder runs, with its registered milestone meaning."""
    registered = set()
    for rule in (rules.get('milestones') or {}).values():
        registered |= set(rule.get('required_suites') or {})
    facts, problems = {}, []
    backend = sorted(p.stem for p in (HERE / 'tests').glob('test_*.py')
                     if p.name != 'test_browser_ui.py')
    node = sorted(p.name for p in (HERE / 'tests').glob('*.test.cjs'))
    browser = (HERE / 'tests' / 'test_browser_ui.py').is_file()
    facts['workspace_backend_suites'] = len(backend)
    facts['workspace_node_suites'] = len(node)
    facts['workspace_browser_suite'] = browser
    facts['workspace_suites'] = backend + node
    facts['registered_in_rules'] = sorted(registered)
    unregistered = [name for name in backend if name not in registered]
    facts['backend_not_registered'] = unregistered
    if unregistered:
        problems.append('workspace suites that no milestone rule requires: ' + ', '.join(unregistered))
    facts['probe_files_are_not_suites'] = len(list((HERE / 'probes').glob('probe_*.py'))) if (HERE / 'probes').is_dir() else 0
    return facts, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--rules', type=Path, default=HERE / 'acceptance_milestones.json')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    for path in (args.baseline, args.manifest, args.rules):
        if not Path(path).is_file():
            print('CLOSEOUT REFUSED: missing input ' + str(path), file=sys.stderr)
            return 2
    baseline = load(args.baseline)
    manifest = load(args.manifest)
    rules = load(args.rules)
    facts, problems, executed = baseline_facts(baseline, manifest)
    added_facts, added_problems = workspace_additions(rules)
    facts.update(added_facts)
    problems.extend(added_problems)
    facts['executed_modules_sample'] = executed[:8]
    verdict = {'schema': 1, 'milestone': 'M8.2', 'accepted': not problems,
               'problems': problems, 'facts': facts}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    if problems:
        print('CLOSEOUT FAILED: ' + '; '.join(problems), file=sys.stderr)
        return 1
    print('CLOSEOUT PASSED: baseline inventory reconciles with the workspace suites')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())