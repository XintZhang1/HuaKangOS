"""Pinned image entrypoint. No dependencies are installed from the candidate."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
# The read-only source is copied into disposable tmpfs; never mount host data.
# Git is needed only by hermetic regression tests using throw-away local repos.
import shutil
root=Path(tempfile.mkdtemp(prefix='candidate-'))
shutil.copytree('/source',root,dirs_exist_ok=True)
os.chdir(root)
env=os.environ.copy();env['PYTHONPATH']=str(root);env['APP_ENV']='test';env['SCHEDULER_ENABLED']='false'
env['ALLOW_AI_EXTERNAL']='false';env['MAINTENANCE_ENABLED']='false';env['ALLOW_CODE_EXTERNAL']='false'
for key in list(env):
    if any(x in key for x in ('API_KEY','SECRET','TOKEN')): env.pop(key,None)
for cmd in (["node","--check","web/app.js"],[sys.executable,"-m","pytest","-q","-p","no:cacheprovider"]):
    completed=subprocess.run(cmd,env=env,timeout=230)
    if completed.returncode: raise SystemExit(completed.returncode)
