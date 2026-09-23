/* The bootstrap token lives only in this closure; never local/session storage. */
(() => {
  const setupRequested = location.hash.startsWith('#preview-setup');
  const match = location.hash.match(/^#preview-setup=([A-Za-z0-9_-]{40,100})$/);
  let token = match ? match[1] : '';
  if (setupRequested) history.replaceState(null, '', location.pathname + location.search);
  window.maybeLocalPreviewSetup = async function () {
  if (!setupRequested) return false;
  const unavailable = message => {
    document.getElementById('app').innerHTML = typeof huakangLogin === 'function' ? huakangLogin() : '<main class="loginpage"><section class="loginform"></section></main>';
    const panel = document.querySelector('.loginform');
    panel.innerHTML = '<h1>首次设置暂未完成</h1><p class="formerror" role="alert"></p><p>请重新运行 start-preview.cmd，使用新打开的设置页面。</p><a href="/">返回登录</a>';
    panel.querySelector('.formerror').textContent = message;
    token = ''; return true;
  };
  if (!token) return unavailable('设置链接格式不正确，请重新打开。');
  const mount = document.getElementById('app');
  let status;
  try {
    const response = await fetch('/api/local-preview/status', {cache: 'no-store'});
    if (!response.ok) return unavailable('此设置链接不属于可用的本机预览，请重新运行启动器。');
    status = await response.json();
    if (!status.bootstrap_required) { token = ''; return false; }
  } catch (_) { return unavailable('暂时无法连接本机预览，请确认启动器仍在运行后重试。'); }
  mount.innerHTML = typeof huakangLogin === 'function' ? huakangLogin() : '<main class="loginpage"><section class="loginform"></section></main>';
  mount.querySelector('.loginform').innerHTML = `<div class="eyebrow">HUAKANGOS · LOCAL PREVIEW</div><h1>设置本地预览管理员</h1><p>这是这台电脑上的独立预览，资料保存在仓库之外。请只填写虚构资料。</p><div class="notice warn">尚未建立账号。请自行设置密码；不会覆盖公司账号、灌入业务数据或创建正式经营主体。</div><form id="preview-setup-form" class="stack"><label>管理员账号<input name="username" autocomplete="username" value="admin" minlength="3" maxlength="40" pattern="[A-Za-z0-9_.-]+" required></label><label>密码（12–128 位）<input name="password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><label>再次输入密码<input name="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><div class="formerror" role="alert" aria-live="polite"></div><button class="primary" type="submit">设置管理员并进入</button></form><p class="muted">仅监听 127.0.0.1；本地附件仅做结构校验。设置链接 15 分钟有效，失效后重新运行 start-preview.cmd。</p>`;
  const form = document.getElementById('preview-setup-form');
  let submitting = false;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    const error = form.querySelector('.formerror');
    const button = form.querySelector('button');
    const fields = new FormData(form);
    if (fields.get('password') !== fields.get('confirmation')) { error.textContent = '两次密码不一致，请重新输入。'; return; }
    submitting = true; button.disabled = true; error.textContent = '';
    let configured = false;
    try {
      const body = {username: fields.get('username'), password: fields.get('password')};
      const result = await fetch('/api/local-preview/bootstrap', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-App-Request': '1', 'X-Local-Preview-Token': token}, body: JSON.stringify(body)});
      const data = await result.json();
      if (!result.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '账号或密码格式不正确，请检查后重新提交。');
      configured = true;
      token = '';
      const login = await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-App-Request': '1'}, body: JSON.stringify(body)});
      form.reset();
      // A hash-only replace does not restart the suspended authentication boot.
      history.replaceState(null, '', login.ok ? '/#work' : '/');
      location.reload();
    } catch (failure) {
      if (configured) { form.reset(); unavailable('管理员已设置完成，自动登录暂未成功，请返回登录并使用刚设置的账号。'); }
      else error.textContent = /[\u3400-\u9fff]/.test(failure.message) ? failure.message : '暂时无法连接本机预览，请检查启动器后重试。';
    }
    finally { submitting = false; button.disabled = false; }
  });
  return true;
};

})();
