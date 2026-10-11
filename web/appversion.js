'use strict';
// Updates are opt-in. Never clear cookies, browser storage or business drafts.
(() => {
  const loadedVersion = document.querySelector('meta[name="huakangos-release"]')?.content;
  if (!/^[a-f0-9]{64}$/.test(loadedVersion || '')) return;
  let checking = false, availableVersion = '', pendingWrites = 0, leaving = false;
  const edited = new Set();

  function assistant() {
    return typeof businessAssistantState === 'undefined' ? null : businessAssistantState;
  }
  function busy() {
    const current = assistant();
    return pendingWrites > 0 || !!document.querySelector('[data-submitting="true"]') ||
      !!(current?.busy || current?.files?.busy || current?.runId || current?.session?.busy ||
        window.AssistantWorkspace?.snapshot?.().followupPending);
  }
  function hasUnsaved() {
    const current = assistant();
    if (typeof brState !== 'undefined' && Object.keys(brState.drafts || {}).length) return true;
    if (current?.draft?.trim() || current?.retry || current?.files?.items?.length ||
        Object.values(current?.answers || {}).some(value => Object.keys(value || {}).length)) return true;
    // Previous assistant sessions may hold in-memory answers/file selections.
    if (window.AssistantWorkspace?.hasUnsavedUi?.()) return true;
    if (document.querySelector('dialog[open] form')) return true;
    for (const field of edited) {
      if (!field.isConnected || field.closest('dialog:not([open])')) { edited.delete(field); continue; }
      if (field.type === 'checkbox' || field.type === 'radio') {
        if (field.checked !== field.defaultChecked) return true;
      } else if (field.tagName === 'SELECT') {
        if ([...field.options].some(option => option.selected !== option.defaultSelected)) return true;
      } else if (field.type === 'file' ? field.files.length : field.value !== field.defaultValue) return true;
    }
    return false;
  }
  function rememberInput(event) {
    const field = event.target;
    if (!field.matches('input,textarea,select') || field.type === 'search' ||
        /filter/i.test(field.form?.id || '')) return;
    edited.add(field);
  }
  function message(text) {
    const target = document.getElementById('app-update-message');
    if (target) target.textContent = text;
  }
  function update() {
    if (!availableVersion) return;
    if (busy()) {
      message('正在提交或处理业务，请等结果返回后再更新。');
      return;
    }
    if (hasUnsaved() && !window.confirm('还有未保存或未发送的内容。请取消更新，先保存或处理当前内容。仍要放弃这些内容并更新页面吗？')) return;
    leaving = true;
    // A fresh document gets every script/style URL from the new content hashes.
    // Keep the current deep link, login cookies and selected-store preference.
    location.reload();
  }
  function showUpdate() {
    let notice = document.getElementById('app-update-notice');
    if (!notice) {
      notice = document.createElement('aside');
      notice.id = 'app-update-notice';
      notice.setAttribute('aria-label', '系统更新');
      const text = document.createElement('p');
      text.id = 'app-update-message';
      text.setAttribute('role', 'status');
      const button = document.createElement('button');
      button.id = 'app-update-now';
      button.type = 'button';
      button.textContent = '更新页面';
      button.addEventListener('click', update);
      notice.append(text, button);
      document.body.append(notice);
      message('系统已有更新。请先保存正在填写的内容，再更新页面。');
    }
  }
  async function check() {
    if (checking || document.visibilityState === 'hidden') return;
    checking = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch('/api/app-version', {cache: 'no-store', credentials: 'same-origin', signal: controller.signal});
      if (!response.ok) return;
      const value = await response.json();
      if (!/^[a-f0-9]{64}$/.test(value.version || '')) return;
      if (value.version !== loadedVersion) {
        availableVersion = value.version;
        showUpdate();
      } else {
        availableVersion = '';
        document.getElementById('app-update-notice')?.remove();
      }
    } catch (_) {
      // A restart or offline connection must not interrupt business forms.
    } finally {
      clearTimeout(timeout);
      checking = false;
    }
  }
  window.huakangAppVersion = Object.freeze({
    check,
    beginRequest(method) {
      if (['GET', 'HEAD', 'OPTIONS'].includes(String(method).toUpperCase())) return () => {};
      pendingWrites++;
      let finished = false;
      return () => { if (!finished) { finished = true; pendingWrites--; } };
    }
  });
  document.addEventListener('input', rememberInput);
  document.addEventListener('change', rememberInput);
  window.addEventListener('beforeunload', event => {
    if (!leaving && (busy() || hasUnsaved())) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('visibilitychange', check);
  window.addEventListener('focus', check);
  window.addEventListener('pageshow', check);
  window.addEventListener('online', check);
  setInterval(check, 60000);
  check();
})();
