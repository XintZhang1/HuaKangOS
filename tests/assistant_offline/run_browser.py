"""Launch only the external, synthetic browser fixture; always stop the server."""
import fixture_env
import httpx,os,signal,subprocess,sys,time
from pathlib import Path
root=fixture_env.VALIDATION
# Refuse to silently reuse an unrelated loopback process/database. A refused
# connection reports ConnectError and a filtered/hanging loopback reports
# ConnectTimeout; both mean "nothing of ours is listening", while any HTTP
# answer means the port is genuinely occupied.
try:
    httpx.get('http://127.0.0.1:8765/api/auth/me',trust_env=False,timeout=.5)
except (httpx.ConnectError,httpx.ConnectTimeout):pass
else:raise SystemExit('Port 8765 is already in use. Stop the existing test server first.')
log=(root/'evidence/browser-server-final.log').open('w')
server=subprocess.Popen([sys.executable,'browser_server.py'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
try:
    for _ in range(150):
        if server.poll() is not None:raise RuntimeError('Fixture server exited; inspect its log')
        try:
            r=httpx.get('http://127.0.0.1:8765/api/auth/me',trust_env=False,timeout=.5)
            if r.status_code==401:break
        except (httpx.ConnectError,httpx.ConnectTimeout,httpx.ReadTimeout):pass
        time.sleep(.2)
    else:raise TimeoutError('Fixture server not ready')
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_browser_ui.py','-v']+sys.argv[1:],cwd=root,timeout=300)
finally:
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    log.close()
sys.exit(result.returncode)
