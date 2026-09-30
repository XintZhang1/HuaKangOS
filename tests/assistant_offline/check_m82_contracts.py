"""M8.2 contract checks that belong to the repository, not to a test fixture.

Three things are proved here, all from versioned files and without a network:
the published workflow-guide artifacts are current for their source, the 193
requirements and 111 workflows still reconcile against each other in both
directions, and every one of the ten original business modules still carries
requirements. A failure prints the exact contradiction, so the verdict cannot be
mistaken for a style complaint.

The generators are run in check mode only; --draft is never used, so a
hand-edited or stale artifact is reported instead of silently rewritten.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / 'docs/requirements.json'
COVERAGE = ROOT / 'docs/workflow-source/coverage.json'
GUIDES = ROOT / 'web/workflow-guides.json'
HANDBOOK = ROOT / 'web/workflow-handbook.html'
FULL_HANDBOOK = ROOT / 'docs/全量工作流手册.html'
GENERATOR = ROOT / 'scripts/build_workflow_guides.py'
MODULES = 10


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def check_generator(problems, facts):
    """The published artifacts must be reproducible from the source."""
    if not GENERATOR.is_file():
        problems.append('workflow generator is missing: scripts/build_workflow_guides.py')
        return
    result = subprocess.run([sys.executable, str(GENERATOR), '--check'],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    facts['generator_exit'] = result.returncode
    if result.returncode:
        tail = (result.stdout + result.stderr).strip().splitlines()[-6:]
        problems.append('workflow generator --check failed: ' + ' | '.join(tail))


def check_requirements(problems, facts):
    document = load(REQUIREMENTS)
    items = document.get('requirements') or []
    facts['requirements'] = len(items)
    if len(items) != 193:
        problems.append('requirements.json holds ' + str(len(items)) + ', expected 193')
    identifiers = [item.get('id') for item in items]
    if any(not isinstance(value, str) or not value for value in identifiers):
        problems.append('a requirement has no id')
    if len(set(identifiers)) != len(identifiers):
        problems.append('requirement ids are not unique')
    modules = sorted({item.get('module') for item in items})
    facts['modules'] = modules
    if len(modules) != MODULES:
        problems.append('requirements cover ' + str(len(modules)) + ' modules, expected ' + str(MODULES))
    for item in items:
        if not item.get('title') or not item.get('module') or not item.get('group'):
            problems.append('requirement ' + str(item.get('id')) + ' lacks title/module/group')
            break
        if not item.get('implementation_refs'):
            problems.append('requirement ' + str(item.get('id')) + ' has no implementation reference')
            break
        if not item.get('test_refs') and not item.get('validation'):
            problems.append('requirement ' + str(item.get('id')) + ' has no test or validation reference')
            break
    return items


def check_workflows(problems, facts):
    coverage = load(COVERAGE)
    guides = load(GUIDES)
    for name, path in (('coverage', COVERAGE), ('guides', GUIDES),
                       ('handbook', HANDBOOK), ('full handbook', FULL_HANDBOOK)):
        if not Path(path).is_file():
            problems.append('published artifact missing: ' + name)
    workflows = guides.get('workflows') or []
    facts['workflows'] = len(workflows)
    linked = guides.get('requirements') or []
    facts['linked_requirements'] = len(linked)
    if len(workflows) != 111:
        problems.append('workflow-guides.json holds ' + str(len(workflows)) + ' workflows, expected 111')
    if coverage.get('workflows') != len(workflows):
        problems.append('coverage declares ' + str(coverage.get('workflows'))
                        + ' workflows but the artifact holds ' + str(len(workflows)))
    if coverage.get('requirements') != 193 or len(linked) != 193:
        problems.append('coverage requirements ' + str(coverage.get('requirements'))
                        + ' / linked ' + str(len(linked)) + ', expected 193 both')
    source = coverage.get('source_sha256')
    facts['source_sha256'] = source
    if not source:
        problems.append('coverage has no source fingerprint')
    elif guides.get('source_sha256') != source:
        problems.append('the published guides were built from a different workflow source')
    identifiers = [row.get('id') for row in workflows]
    if len(set(identifiers)) != len(identifiers):
        problems.append('workflow ids are not unique')
    known = set(identifiers)
    mapping = coverage.get('mapping') or []
    facts['mapping'] = len(mapping)
    if len(mapping) != 193:
        problems.append('coverage mapping holds ' + str(len(mapping)) + ' entries, expected 193')
    seen = set()
    for row in mapping:
        identifier = row.get('id')
        if identifier in seen:
            problems.append('coverage maps requirement ' + str(identifier) + ' twice')
            break
        seen.add(identifier)
        unknown = [value for value in (row.get('workflow_ids') or []) if value not in known]
        if unknown:
            problems.append('requirement ' + str(identifier) + ' maps to unknown workflows ' + str(unknown[:3]))
            break
        if not row.get('workflow_ids'):
            problems.append('requirement ' + str(identifier) + ' maps to no workflow')
            break
    # Both directions: every workflow must cite requirements, and every cited
    # requirement must exist in the frozen requirement set.
    requirement_ids = {item.get('id') for item in (load(REQUIREMENTS).get('requirements') or [])}
    for row in workflows:
        cited = row.get('requirement_ids') or []
        if not cited:
            problems.append('workflow ' + str(row.get('id')) + ' cites no requirement')
            break
        missing = [value for value in cited if value not in requirement_ids]
        if missing:
            problems.append('workflow ' + str(row.get('id')) + ' cites unknown requirements ' + str(missing[:3]))
            break
    return workflows, mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-generator', action='store_true',
                        help='only reconcile the published artifacts')
    parser.add_argument('--report', type=Path, help='write the verdict as JSON here')
    args = parser.parse_args()
    problems, facts = [], {}
    if not args.skip_generator:
        check_generator(problems, facts)
    check_requirements(problems, facts)
    check_workflows(problems, facts)
    verdict = {'schema': 1, 'milestone': 'M8.2', 'accepted': not problems,
               'problems': problems, 'facts': facts}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    if problems:
        print('CONTRACTS FAILED: ' + '; '.join(problems), file=sys.stderr)
        return 1
    print('CONTRACTS PASSED: 193 requirements / 111 workflows reconcile')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())