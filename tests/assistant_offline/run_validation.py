"""Reproduce this checkpoint, using only disposable data outside the source tree."""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def selected_suites(root, requested=None):
    """Default discovery cannot silently omit a newly versioned backend suite."""
    available=sorted(p.name for p in (root/'tests').glob('test_*.py') if p.name!='test_browser_ui.py')
    if not available:raise ValueError('No backend test suites were found.')
    if requested:
        if len(requested)!=len(set(requested)):raise ValueError('Duplicate suite selections are not allowed.')
        if any(name not in available for name in requested):raise ValueError('Unknown backend suite selection.')
        return list(requested)
    return available


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--skip-browser',action='store_true')
    parser.add_argument('--suite',action='append')
    args=parser.parse_args();source=args.source.resolve()
    if not (source/'app/main.py').is_file() or (source/'.env').exists():
        parser.error('Use a disposable source checkout without a .env file.')
    if ROOT.is_relative_to(source):parser.error('Extract validation outside the source checkout.')
    try:suites=selected_suites(ROOT,args.suite)
    except ValueError as exc:parser.error(str(exc))
    scope='targeted' if args.suite else 'full'
    # Every child writes UTF-8 bytes into a log we open as UTF-8. Without this
    # a non-UTF-8 host (for example GBK Windows) makes Python encode its own
    # diagnostics in the locale codec, so the log cannot be read back.
    env={**os.environ,'HUAKANGOS_SOURCE':str(source),'PYTHONIOENCODING':'utf-8',
         'PYTHONUTF8':'1'}
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    steps=[]
    def run(name,command,cwd=ROOT,timeout=420):
        started=time.monotonic()
        with (evidence/(name+'.log')).open('w',encoding='utf-8') as stream:
            try:
                result=subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
                code=result.returncode
            except (OSError,subprocess.TimeoutExpired) as exc:
                stream.write(type(exc).__name__+': '+str(exc)+'\n');code=124 if isinstance(exc,subprocess.TimeoutExpired) else 127
        steps.append({'name':name,'command':command,'exit_code':code,'elapsed_seconds':round(time.monotonic()-started,3),'log':name+'.log'})
        (evidence/'run-summary.json').write_text(json.dumps({'steps':steps,'complete':False,'selected_complete':False,'scope':scope,'selected_suites':suites,
            'real_model_calls':0,'release_accepted':False},ensure_ascii=False,indent=2))
        if code:raise RuntimeError(name+' failed; inspect '+str(evidence/(name+'.log')))
    if not (ROOT/'runtime/seed-base.sqlite').exists():run('fresh-migration-seed',[sys.executable,'build_base.py'])
    run('python-syntax',[sys.executable,'-m','compileall','-q','app','migrations'],source)
    js_files=sorted((source/'web').glob('*.js'))
    run('javascript-syntax',[sys.executable,'-c',
        'import subprocess,sys; [subprocess.run(["node","--check",p],check=True) for p in sys.argv[1:]]; print("Checked",len(sys.argv)-1,"JavaScript files")',
        *map(str,js_files)])
    run('frontend-final',['node','--test',*map(str,sorted((ROOT/'tests').glob('*.test.cjs')))])
    for suite in suites:
        run(suite.removesuffix('.py'),[sys.executable,'-m','unittest','discover','-s','tests','-p',suite,'-v'])
    if not args.skip_browser:run('browser-final',[sys.executable,'run_browser.py'])
    counts={}
    # Node's test summary marker changed from '#' to 'ℹ' across major versions;
    # accept either marker rather than silently treating a green run as uncounted.
    for name,pattern in [('frontend-final',r'^[#\u2139] tests (\d+)$'),*[(s.removesuffix('.py'),r'^Ran (\d+) tests? in') for s in suites],('browser-final',r'^Ran (\d+) tests? in')]:
        if name=='browser-final' and args.skip_browser:continue
        log=(evidence/(name+'.log')).read_text(encoding='utf-8',errors='replace')
        match=re.search(pattern,log,re.M)
        if not match or int(match[1])<1:raise RuntimeError('Missing/nonpositive executed test count: '+name)
        counts[name]=int(match[1])
        if name=='frontend-final':
            failed=re.search(r'^[#\u2139] fail (\d+)$',log,re.M)
            if not failed:raise RuntimeError('Missing frontend failure count: '+name)
            if int(failed[1]):raise RuntimeError('Frontend tests reported failures: '+name)
    result={'complete':not bool(args.suite),'selected_complete':True,'scope':scope,'selected_suites':suites,'steps':steps,'counts':counts,'real_model_calls':0,'browser_transport':env.get('HUAKANGOS_BROWSER_MODE','fixture') if not args.skip_browser else 'not_run','release_accepted':False}
    (evidence/'run-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if not args.skip_browser:
        # Fail closed before writing the bundle: the browser log must not be
        # interpreted more loosely than the count guard above.
        write_browser_bundle(evidence,result,env.get('HUAKANGOS_BROWSER_MODE','fixture'),counts['browser-final'])
    print(json.dumps(result,ensure_ascii=False,indent=2))


def write_browser_bundle(evidence,result,mode,executed):
    """Summarise the browser pages from their own evidence files."""
    import browser_evidence
    provenance=json.loads((evidence/'source-and-suite.json').read_text(encoding='utf-8'))
    bundle=browser_evidence.collect(evidence,result,mode=mode,
        expected_tests=expected_browser_tests(evidence),
        source_fingerprint=provenance.get('source_sha256'),suite_fingerprint=provenance.get('suite_sha256'))
    if bundle['page_count']!=executed:
        raise RuntimeError('Browser evidence pages do not match the executed tests: '
                           +str(bundle['page_count'])+' != '+str(executed))
    if mode=='native' and bundle['page_errors_total']:
        raise RuntimeError('Native browser pages reported page errors: '+str(bundle['page_errors_total']))
    (evidence/'browser-evidence.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')


def expected_browser_tests(evidence):
    """Page evidence names come from the suite's own files, not a hand list."""
    names=sorted(path.stem for path in evidence.glob('test_*.json'))
    if not names:raise RuntimeError('No browser page evidence was produced.')
    return names

if __name__=='__main__':main()
