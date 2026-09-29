"""Copy the versioned offline suite to a new external directory before importing app."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile

FILES=('fixture_env.py','fake_provider.py','build_base.py','run_validation.py',
       'browser_harness.py','browser_server.py','run_browser.py')

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
    if args.output:
        output=args.output.resolve()
        if output.is_relative_to(source):parser.error('Validation output must be outside the source tree.')
        if output.exists():parser.error('Choose a new output path; existing validation evidence is never overwritten.')
        output.mkdir(parents=True)
    else:
        parent=Path(tempfile.gettempdir()).resolve()
        if parent.is_relative_to(source):parser.error('Temporary directory must be outside the source tree.')
        output=Path(tempfile.mkdtemp(prefix='huakang-assistant-',dir=parent))
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
    env={**os.environ,'HUAKANGOS_SOURCE':str(source),'HUAKANGOS_BROWSER_MODE':args.browser_mode,
         'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'}
    command=[sys.executable,str(output/'run_validation.py'),'--source',str(source)]
    if args.browser_mode=='off':command.append('--skip-browser')
    for suite in args.suite or []:command.extend(['--suite',suite])
    print('Isolated validation: '+str(output),flush=True)
    result=subprocess.run(command,cwd=output,env=env)
    print('Evidence retained: '+str(output/'evidence'),flush=True)
    return result.returncode

if __name__=='__main__':raise SystemExit(main())
