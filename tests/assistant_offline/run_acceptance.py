"""One verdict per milestone, from the evidence the same folder already produced.

This is the workspace-local acceptance gate. It never runs a test itself and
never talks to the network: it re-checks the artefacts of a finished run
(`run-summary.json`, `browser-evidence.json`, `source-and-suite.json`) against
the assertions in `acceptance_milestones.json`, then writes one verdict file.

It deliberately refuses to invent a pass. A missing suite, a lower count than
registered, a transport other than the one registered for the milestone, a page
error, or a reported real model call all make the verdict false.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'acceptance_milestones.json'


def fail(message):
    print('ACCEPTANCE REFUSED: ' + message, file=sys.stderr)
    return 2


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def evaluate(name, rule, evidence, provenance):
    """Return (problems, facts). Every problem is a concrete contradiction."""
    problems = []
    summary = load_json(evidence / 'run-summary.json')
    counts = summary.get('counts') or {}
    total = sum(value for value in counts.values() if type(value) is int)
    facts = {'total': total, 'suites': len(counts),
             'browser_transport': summary.get('browser_transport'),
             'complete': summary.get('complete'), 'scope': summary.get('scope'),
             'real_model_calls': summary.get('real_model_calls')}
    if summary.get('complete') is not True:
        problems.append('the run did not complete')
    if rule.get('scope') and summary.get('scope') != rule['scope']:
        problems.append('scope is ' + str(summary.get('scope')))
    if total < int(rule.get('minimum_total', 0)):
        problems.append('only ' + str(total) + ' cases, registered minimum is '
                        + str(rule.get('minimum_total')))
    if summary.get('real_model_calls'):
        problems.append('the run reported real model calls')
    if rule.get('browser_mode') and summary.get('browser_transport') != rule['browser_mode']:
        problems.append('transport is ' + str(summary.get('browser_transport'))
                        + ', registered as ' + rule['browser_mode'])
    for suite, expected in sorted((rule.get('required_suites') or {}).items()):
        actual = counts.get(suite)
        if actual is None:
            problems.append('suite missing: ' + suite)
        elif actual < int(expected):
            problems.append(suite + ' ran ' + str(actual) + ', registered minimum is ' + str(expected))
    bundle_path = evidence / 'browser-evidence.json'
    if bundle_path.is_file():
        bundle = load_json(bundle_path)
        facts['pages'] = bundle.get('page_count')
        facts['page_errors'] = bundle.get('page_errors_total')
        facts['browser_version'] = (bundle.get('environment') or {}).get('browser_version')
        if rule.get('require_page_errors_zero') and bundle.get('page_errors_total'):
            problems.append('pages reported errors: ' + str(bundle.get('page_errors_total')))
        if not bundle.get('page_count'):
            problems.append('no browser page evidence')
    else:
        problems.append('no browser evidence bundle')
    if provenance:
        facts['source_sha256'] = provenance.get('source_sha256')
        facts['suite_sha256'] = provenance.get('suite_sha256')
    return problems, facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--milestone', required=True)
    parser.add_argument('--evidence', required=True, type=Path,
                        help='the evidence directory of a finished run')
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    config = load_json(args.config)
    rule = (config.get('milestones') or {}).get(args.milestone)
    if rule is None:
        return fail('unknown milestone: ' + args.milestone)
    evidence = args.evidence.resolve()
    if not evidence.is_dir():
        return fail('evidence directory does not exist: ' + str(evidence))
    for required in ('run-summary.json',):
        if not (evidence / required).is_file():
            return fail('evidence is incomplete: ' + required + ' is missing')
    provenance_path = evidence / 'source-and-suite.json'
    provenance = load_json(provenance_path) if provenance_path.is_file() else {}
    problems, facts = evaluate(args.milestone, rule, evidence, provenance)
    verdict = {
        'schema': 1,
        'milestone': args.milestone,
        'title': rule.get('title'),
        'accepted': not problems,
        'problems': problems,
        'checked_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'evidence': str(evidence),
        'rule': {'minimum_total': rule.get('minimum_total'),
                 'browser_mode': rule.get('browser_mode'), 'scope': rule.get('scope'),
                 'required_suites': rule.get('required_suites')},
        'facts': facts,
        'release_accepted': False,
    }
    target = evidence / ('acceptance-' + args.milestone + '.json')
    target.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    if problems:
        print('ACCEPTANCE FAILED: ' + '; '.join(problems), file=sys.stderr)
        return 1
    print('ACCEPTANCE PASSED: ' + args.milestone + ' -> ' + str(target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())