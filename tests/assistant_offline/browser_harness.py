"""Original Chromium UI in one explicit, non-fallback transport mode.

native: real loopback navigation, browser cookies, fetch and network SSE.
fixture: in-memory page plus explicit HTTP/Cookie/buffered-SSE bridge. This mode
is for environments that prohibit HTTP navigation; it is not native acceptance.
Neither mode contacts a real model. A native navigation failure is a failure,
never a reason to silently switch to the fixture or change browser policy.
"""
import fixture_env
from pathlib import Path
import asyncio,base64,json,re,mimetypes,os
from urllib.parse import urlsplit
import httpx
from playwright.async_api import async_playwright

ORIGIN='http://127.0.0.1:8765'
WEB=fixture_env.ROOT/'web'


def asset_text(path):
    # Front-end assets are UTF-8 by contract; never fall back to the machine's
    # locale codec, which fails outright on a non-UTF-8 Windows host.
    content=path.read_text(encoding='utf-8')
    def image(match):
        absolute=WEB/match.group(2).removeprefix('/static/')
        if not absolute.is_file() or absolute.suffix not in ('.svg','.png','.jpg','.jpeg','.webp','.ico'):return match.group(0)
        mime=mimetypes.guess_type(absolute)[0] or 'application/octet-stream'
        return match.group(1)+'data:'+mime+';base64,'+base64.b64encode(absolute.read_bytes()).decode()+match.group(1)
    return re.sub(r'''(['"])(/static/[^'"<>]+)\1''',image,content)


def frontend_html():
    html=(WEB/'index.html').read_text(encoding='utf-8')
    html=re.sub(r'<link rel="stylesheet" href="/static/([^"]+)">',
                lambda m:'<style>'+asset_text(WEB/m[1])+'</style>',html)
    html=re.sub(r'<script src="/static/([^"]+)" defer></script>',
                lambda m:'<script>'+asset_text(WEB/m[1]).replace('</script','<\\/script')+'</script>',html)
    return html

BRIDGE=r'''
window.__fixtureCookies = '';
Object.defineProperty(document, 'cookie', {configurable:true, get:()=>window.__fixtureCookies});
window.fetch = function(url, options={}) {
  if (options.body && typeof options.body !== 'string') throw new Error('Fixture supports JSON body only');
  return new Promise((resolve,reject)=>{
    const signal=options.signal;
    const abort=()=>reject(new DOMException('Stopped','AbortError'));
    if(signal?.aborted){abort();return;}
    signal?.addEventListener('abort',abort,{once:true});
    window.__fixtureHttp({url:String(url),method:options.method||'GET',headers:Object.fromEntries(new Headers(options.headers||{})),body:options.body||null})
      .then(result=>{
        window.__fixtureCookies=result.cookies;
        if(signal?.aborted)return;
        const bytes=Uint8Array.from(atob(result.content),c=>c.charCodeAt(0));
        resolve(new Response([204,205,304].includes(result.status)?null:bytes,{status:result.status,headers:result.headers}));
      },error=>{if(!signal?.aborted)reject(new TypeError('Fixture HTTP failed: '+error.message));})
      .finally(()=>signal?.removeEventListener('abort',abort));
  });
};
'''

class BrowserHarness:
    async def start(self,width=1440,height=1000):
        self.playwright=await async_playwright().start()
        self.mode=os.environ.get('HUAKANGOS_BROWSER_MODE','fixture')
        if self.mode not in {'fixture','native'}:raise ValueError('Unknown browser mode')
        executable=os.environ.get('HUAKANGOS_CHROMIUM')
        if executable is None and Path('/usr/bin/chromium').exists():executable='/usr/bin/chromium'
        self.browser=await self.playwright.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
        # The reviewer needs the exact browser that produced the pages. Record
        # which executable was used (bundled or an explicitly supplied one) and
        # never let a missing version silently become an unnamed browser.
        self.browser_version=self.browser.version
        self.browser_executable=executable or 'playwright-bundled'
        self.csp=''
        self.current_test='unknown'
        self.context=await self.browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
        self.page=await self.context.new_page()
        self.page.set_default_timeout(8000)
        self.http=httpx.AsyncClient(base_url=ORIGIN,trust_env=False,timeout=30,follow_redirects=False)
        self.errors=[];self.requests=[];self.console_errors=[]
        self.page.on('console',lambda msg:self.console_errors.append(msg.text) if msg.type=='error' else None)
        self.page.on('pageerror',lambda err:self.errors.append(str(err)))
        self.page.on('request',self.record_request)
        if self.mode=='fixture':
            await self.page.expose_function('__fixtureHttp',self.request)
        else:
            async def local_only(route):
                if urlsplit(route.request.url).netloc==urlsplit(ORIGIN).netloc:await route.continue_()
                else:await route.abort()
            await self.context.route('**/*',local_only)
            def record(response):
                url=response.url
                if url.startswith(ORIGIN+'/api/'):
                    for item in reversed(self.requests):
                        if item['status'] is None and item['path']==url[len(ORIGIN):]:
                            item['status']=response.status
                            break
            self.page.on('response',record)
        try:
            await self.load()
        except BaseException:
            await self.close()
            raise
        return self
    async def request(self,data):
        url=data['url']
        if (not url.startswith('/api/') and url!='/static/workflow-guides.json') or '..' in url:raise AssertionError('Only original local routes allowed')
        headers={k:v for k,v in data['headers'].items() if k.lower() not in ('cookie','host','origin')}
        headers['Origin']=ORIGIN
        result=await self.http.request(data['method'],url,headers=headers,content=data['body'])
        self.requests.append({'method':data['method'],'path':url,'status':result.status_code})
        # Only the browser-visible CSRF cookie is mirrored. The login cookie stays in httpx's jar.
        csrf=self.http.cookies.get('dealer_csrf','')
        return {'status':result.status_code,'content':base64.b64encode(result.content).decode(),
                'headers':{k:v for k,v in result.headers.items() if k.lower() not in ('set-cookie','content-encoding','content-length')},
                'cookies':'dealer_csrf='+csrf if csrf else ''}
    async def load(self):
        if self.mode=='native':
            response = await self.page.goto(ORIGIN,wait_until='domcontentloaded')
            self.csp = response.headers.get('content-security-policy', '') if response else ''
            return
        # A new about:blank document avoids the denied-navigation error page.
        await self.page.set_content('<html><head></head><body></body></html>')
        await self.page.add_script_tag(content=BRIDGE)
        csrf=self.http.cookies.get('dealer_csrf','')
        await self.page.evaluate('(v)=>window.__fixtureCookies=v','dealer_csrf='+csrf if csrf else '')
        # document.write replacement keeps bridge bindings in this same global.
        await self.page.set_content(frontend_html(),wait_until='domcontentloaded')
    async def login(self):
        await self.page.locator('input[name="username"]').fill('offline_admin')
        await self.page.locator('input[name="password"]').fill(fixture_env.PASSWORD.read_text())
        await self.page.get_by_role('button',name='登录',exact=True).click()
        # The navigation renders after the login response, so wait for the entry
        # to exist instead of racing it with a click. This only synchronises with
        # the application's own render; it asserts nothing on its behalf.
        entry=self.page.locator('a[href="#business-assistant"]')
        await entry.wait_for(state='attached',timeout=30000)
        await entry.scroll_into_view_if_needed()
        await entry.click()
        await self.page.locator('#business-assistant-input').wait_for(timeout=15000)
        if self.mode=='native':
            # Only out-of-page fixture setup uses this jar. Page fetch, login,
            # CSRF and SSE remain unmodified native Chromium throughout.
            for cookie in await self.context.cookies():
                self.http.cookies.set(cookie['name'],cookie['value'])
    def record_request(self,request):
        # Real network requests only; the fixture bridge reports its own calls
        # through the HTTP client and must never be counted as native traffic.
        url=request.url
        if url.startswith(ORIGIN):
            self.requests.append({'method':request.method,'path':url[len(ORIGIN):],'status':None})
    async def close(self):
        self.write_environment()
        await self.context.close();await self.browser.close();await self.playwright.stop();await self.http.aclose()
    def write_environment(self):
        # One authoritative record per test, so an aggregator never has to guess
        # which browser, transport or policy produced the page evidence.
        target=fixture_env.VALIDATION/'evidence'/'browser-environment.json'
        try:payload=json.loads(target.read_text(encoding='utf-8')) if target.is_file() else {'schema':1,'tests':{}}
        except (OSError,ValueError):payload={'schema':1,'tests':{}}
        payload.update({'schema':1,'mode':self.mode,'native_transport':self.mode=='native',
            'real_model_calls':0,'origin':ORIGIN,'browser_version':self.browser_version,
            'browser_executable':self.browser_executable,'csp':self.csp,
            'csp_script_src_self':"script-src 'self'" in self.csp,
            'csp_unsafe_eval':"unsafe-eval" in self.csp})
        payload.setdefault('tests',{})[self.current_test]={
            'page_errors':len(self.errors),'console_errors':len(self.console_errors),
            'api_requests':len([r for r in self.requests if r['path'].startswith('/api/')])}
        target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

async def smoke():
    h=await BrowserHarness().start()
    try:
        await h.page.wait_for_timeout(500)
        print('INITIAL',await h.page.locator('body').inner_text())
        await h.login()
        print('AFTER LOGIN', (await h.page.locator('body').inner_text())[:7000])
        print('ERRORS',h.errors)
        await h.page.screenshot(path=str(fixture_env.VALIDATION/'evidence/browser-assistant-start.png'),full_page=True)
    finally:await h.close()

if __name__=='__main__':asyncio.run(smoke())
