"""Copy the versioned offline suite to a fresh per-run directory before importing app."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,time

FILES=('fixture_env.py','fake_provider.py','build_base.py','run_validation.py',
       'browser_harness.py','browser_server.py','run_browser.py','browser_evidence.py',
       'run_browser_pipeline.py')

def main():
    bundled=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=bundled.parents[1])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--browser-mode',choices=('off','fixture','native'),default='off')
    available=sorted(p.name for p in (bundled/'tests').glob('test_*.py') if p.name!='test_browser_ui.py')
    parser.add_argument('--suite',action='append',choices=available,help='Target one backend suite (repeatable); not a full regression.')
    args=parser.parse_args();source=args.source.resolve()
    if args.suite and len(args.suite)!=len(set(args.suite)):parser.error('Duplicate suite selections are not allowed.')
    if not (source/'app/main.py').is_file() or (source/'.env').exists():
        parser.error('Use a disposable source checkout without .env; no database is read from the environment.')
    # Every run gets its own directory because evidence is never overwritten.
    # The default keeps runs inside this test folder so one place holds the
    # suites, the run record and the evidence. That folder is ignored by git,
    # and the runtime it creates still sits outside the application source that
    # runs are executed against.
    if args.output:
        output=args.output.resolve()
        if output==source or output.is_relative_to(source/'app') or output.is_relative_to(source/'web') or output.is_relative_to(source/'migrations'):
            parser.error('Validation output must not sit inside the application source.')
        if output.exists():parser.error('Choose a new output path; existing validation evidence is never overwritten.')
        output.mkdir(parents=True)
    else:
        stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
        output=(bundled/'evidence'/('off-'+stamp)).resolve()
        if output.exists():parser.error('Choose a new output path; existing validation evidence is never overwritten.')
        output.mkdir(parents=True)
    files=[bundled/name for name in FILES]
    files+=sorted((bundled/'tests').glob('test_*.py'))+sorted((bundled/'tests').glob('*.test.cjs'))
    if not files or any(not p.is_file() for p in files):parser.error('Offline test sources are incomplete.')
    for path in files:
        target=output/path.relative_to(bundled);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    (output/'evidence').mkdir()
    source_files=sorted(p for folder in ('app','web','migrations') for p in (source/folder).rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    source_files+=[source/f for f in ('requirements.txt','alembic.ini')]
    inventory={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    suite_inventory={str(p.relative_to(bundled)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    suite_inventory['run_isolated.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    provenance={'source_sha256':digest(inventory),'suite_sha256':digest(suite_inventory),'files':inventory,
                'suite_files':suite_inventory,'python':sys.version,'browser_mode':args.browser_mode,
                'scope':'targeted' if args.suite else 'full','selected_suites':args.suite or available}
    (output/'evidence/source-and-suite.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2))
    # The synthetic database, the random password and the synthetic config must
    # stay outside the checkout: the application refuses to read an assistant
    # config from inside its own tree, and a real database must never be opened.
    # The run itself and its evidence stay in this test folder.
    runtime_root=Path(os.environ.get('HUAKANGOS_RUNTIME_ROOT')
                      or (bundled.parents[1].parent/'HuaKangOS-validation'/'runtime')).resolve()
    if runtime_root.is_relative_to(source):parser.error('Synthetic runtime must stay outside the source checkout.')
    runtime=runtime_root/output.name
    if runtime.exists():parser.error('Choose a new output path; its synthetic runtime already exists.')
    runtime.mkdir(parents=True)
    env={**os.environ,'HUAKANGOS_SOURCE':str(source),'HUAKANGOS_RUNTIME':str(runtime),
         'HUAKANGOS_BROWSER_MODE':args.browser_mode,
         'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'}
    command=[sys.executable,str(output/'run_validation.py'),'--source',str(source)]
    if args.browser_mode=='off':command.append('--skip-browser')
    for suite in args.suite or []:command.extend(['--suite',suite])
    print('Isolated validation: '+str(output),flush=True)
    result=subprocess.run(command,cwd=output,env=env)
    print('Evidence retained: '+str(output/'evidence'),flush=True)
    return result.returncode

if __name__=='__main__':raise SystemExit(main())
