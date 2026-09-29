"""Aggregate per-page browser evidence into one machine-readable bundle.

The bundle is written from files the browser suite already produced; it never
executes a browser and never contacts a network. It exists so a reviewer can
verify the transport, CSP and page-error facts of a real-browser run without
reading every log, and so an `off` run can never be described as native.
"""
import json
from pathlib import Path


def _load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def collect(evidence, summary, *, mode, expected_tests, source_fingerprint=None,
            suite_fingerprint=None):
    """Build the bundle from the run's own evidence directory."""
    evidence = Path(evidence)
    pages, missing = [], []
    for name in sorted(expected_tests):
        path = evidence / (name + '.json')
        if not path.is_file():
            missing.append(name)
            continue
        record = _load(path)
        if type(record) is not dict:
            raise ValueError('Page evidence must be an object: ' + name)
        requests, errors = record.get('requests'), record.get('page_errors')
        if type(requests) is not list or type(errors) is not list:
            raise ValueError('Page evidence is incomplete: ' + name)
        api = [item for item in requests
               if type(item) is dict and str(item.get('path', '')).startswith('/api/')]
        pages.append({
            'test': name,
            'screenshot': name + '.png' if (evidence / (name + '.png')).is_file() else None,
            'page_errors': errors,
            'api_requests': len(api),
            'api_statuses': sorted({item['status'] for item in api
                                    if type(item.get('status')) is int}),
        })
    if missing:
        raise ValueError('Browser suite produced no evidence for: ' + ', '.join(missing))
    if mode == 'native':
        # The native transport must have reached the isolated service over real
        # HTTP. A fixture run keeps its traffic in the bridge, so a native
        # bundle with no /api requests is a contradiction, not a pass.
        empty = [page['test'] for page in pages if page['api_requests'] < 1]
        if empty:
            raise ValueError('Native pages recorded no original-API traffic: ' + ', '.join(empty))
    environment = evidence / 'browser-environment.json'
    context = _load(environment) if environment.is_file() else {}
    return {
        'schema': 1,
        'mode': mode,
        'native_transport': mode == 'native',
        'real_model_calls': 0,
        'synthetic_data_only': True,
        'page_count': len(pages),
        'page_errors_total': sum(len(page['page_errors']) for page in pages),
        'pages': pages,
        'environment': context,
        'run': {'complete': bool(summary.get('complete')), 'scope': summary.get('scope'),
                'browser_transport': summary.get('browser_transport')},
        'fingerprints': {'source_sha256': source_fingerprint, 'suite_sha256': suite_fingerprint},
    }


def write(evidence, summary, *, mode, expected_tests, source_fingerprint=None,
          suite_fingerprint=None):
    bundle = collect(evidence, summary, mode=mode, expected_tests=expected_tests,
                     source_fingerprint=source_fingerprint, suite_fingerprint=suite_fingerprint)
    target = Path(evidence) / 'browser-evidence.json'
    target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding='utf-8')
    return target