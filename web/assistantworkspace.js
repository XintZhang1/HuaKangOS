/* 业务助手事项侧栏与两列工作台（M6.3）。
 *
 * 只读服务器授权投影：GET /api/business-assistant/workspace。
 * 本模块不改业务、不推进 Plan/Task/Proposal、不写浏览器持久化、不自动选卡或自动发送。
 * 固定三组顺序：待我处理(attention) → 跟进中(following) → 已结束(finished)，只展示服务器给的项。
 * 唯一出口是 globalThis.AssistantWorkspace：
 *   load({group?,cursor?,limit?}) / mount(root?) / renderSidebar() / openItem(key)
 *   / patchCurrent() / disposeContext() / snapshot()
 */
'use strict';
(function () {
  const GROUPS = [['attention', '待我处理'], ['following', '跟进中'], ['finished', '已结束']];
  const KIND_LABEL = { native_task: '业务待办', proposal: '待确认操作', plan: '跟进事项' };
  const DRAWER_WIDTH = 1024;

  function fresh() {
    return { features: null, counts: null, groups: [], cursors: {}, loading: false,
      error: '', selected: null, serial: 0, mounted: false, bound: false, context: '',
      drawer: false, notice: '', host: null, toggle: null };
  }
  let state = fresh();

  function escapeText(value) {
    return typeof globalThis.E === 'function' ? globalThis.E(value)
      : String(value == null ? '' : value).replace(/[&<>"']/g, (character) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  }
  function current() { return typeof businessAssistantState === 'object' && businessAssistantState
    ? businessAssistantState : null; }
  function contextKey() {
    return typeof businessAssistantContext === 'function' ? businessAssistantContext() : '';
  }
  function alive() { return state.mounted && state.context === contextKey(); }
  function groupOf(key) { return state.groups.find((group) => group.key === key) || null; }
  function findItem(key) {
    for (const group of state.groups) {
      const item = (group.items || []).find((entry) => entry.key === key);
      if (item) return item;
    }
    return null;
  }
  function countsLine() {
    const counts = state.counts || {}, parts = [];
    if (counts.native_tasks) parts.push('业务待办 ' + counts.native_tasks);
    if (counts.pending_proposals) parts.push('待确认操作 ' + counts.pending_proposals);
    // A failed read must never become a fake zero total; the error line carries that fact.
    return parts.join('、');
  }

  async function load(options) {
    const settings = options || {}, before = state.serial;
    const serial = before + 1;
    state.serial = serial; state.loading = true; state.error = '';
    if (!settings.cursor) state.notice = '';
    renderSidebarInto();
    const query = [];
    if (settings.group) query.push('group=' + encodeURIComponent(settings.group));
    if (settings.cursor) query.push('cursor=' + encodeURIComponent(settings.cursor));
    if (settings.limit) query.push('limit=' + encodeURIComponent(settings.limit));
    let view;
    try {
      view = await businessAssistantRequest('/workspace' + (query.length ? '?' + query.join('&') : ''));
    } catch (error) {
      if (state.serial !== serial) return null;
      state.loading = false;
      state.error = (error && error.message) || '读取待办失败，请稍后重试。';
      renderSidebarInto();
      return null;
    }
    if (state.serial !== serial) return null;  // 迟到的分页结果按序号丢弃，不合并到新上下文
    apply(view, settings);
    return view;
  }

  function apply(view, settings) {
    state.features = (view && view.features) || state.features;
    state.counts = (view && view.counts) || state.counts;
    const incoming = Array.isArray(view && view.groups) ? view.groups : [];
    if (settings && settings.cursor) {
      for (const group of incoming) {
        const target = groupOf(group.key);
        if (!target) { state.groups.push({ key: group.key, items: (group.items || []).slice(),
          next_cursor: group.next_cursor == null ? null : group.next_cursor }); continue; }
        for (const item of group.items || []) {
          // 稳定 key 去重追加：不同客户即使标题相同也各自成项。
          if (!target.items.some((existing) => existing.key === item.key)) target.items.push(item);
        }
        target.next_cursor = group.next_cursor == null ? null : group.next_cursor;
      }
      for (const key of Object.keys(state.cursors)) {
        const group = groupOf(key);
        if (group) state.cursors[key] = group.next_cursor || null;
      }
    } else {
      state.groups = incoming.map((group) => ({ key: group.key, items: (group.items || []).slice(),
        next_cursor: group.next_cursor == null ? null : group.next_cursor }));
      state.cursors = {};
      for (const group of state.groups) state.cursors[group.key] = group.next_cursor || null;
    }
    state.loading = false; state.error = '';
    if (state.selected) {
      const found = findItem(state.selected.key);
      state.selected = found || null;   // 服务器不再返回就清空，不自作主张改选别的项
    }
    renderSidebarInto();
  }

  function itemHTML(item) {
    const selected = state.selected && state.selected.key === item.key;
    const meta = [];
    if (item.waiting_reason) meta.push('等待：' + item.waiting_reason);
    if (item.due_at) meta.push('到期：' + (typeof time === 'function' ? time(item.due_at) : item.due_at));
    const route = item.manual_route
      ? '<a class="ba-record-link" href="#' + escapeText(item.manual_route) + '">打开原业务</a>' : '';
    return '<article class="ba-side-item' + (selected ? ' selected' : '') + '" data-item="' + escapeText(item.key) + '">'
      + '<button type="button" data-baws-action="open" data-key="' + escapeText(item.key) + '" aria-current="' + (selected ? 'true' : 'false') + '">'
      + '<span class="ba-side-kind">' + escapeText(KIND_LABEL[item.kind] || '事项') + '</span>'
      + '<strong>' + escapeText(item.title || '待办事项') + '</strong>'
      + '<span class="ba-side-status">' + escapeText(item.status_label || item.status || '') + '</span></button>'
      + (meta.length ? '<p class="ba-side-meta">' + escapeText(meta.join(' · ')) + '</p>' : '')
      + route + '</article>';
  }

  function renderSidebar() {
    const notice = state.error
      ? '<p class="ba-side-error" role="alert">' + escapeText('待办读取失败：' + state.error) + '</p>'
        + '<p class="ba-side-hint">这不是空列表；原人工入口仍可用，请稍后重试。</p>'
      : '';
    const busy = state.loading && !state.groups.length
      ? '<p class="ba-side-hint">正在读取你的待办…</p>' : '';
    const sections = GROUPS.map(([key, label]) => {
      const group = groupOf(key), items = (group && group.items) || [];
      const badge = Number(((state.counts || {})[key] != null ? state.counts[key] : items.length)) || 0;
      const sub = key === 'attention' ? countsLine() : '';
      const empty = key === 'attention' ? '当前没有待你处理的事项。'
        : key === 'following' ? '没有正在跟进的事项。' : '还没有已结束的事项。';
      const list = items.length ? items.map(itemHTML).join('')
        : '<p class="ba-side-empty">' + escapeText(empty) + '</p>';
      const more = group && group.next_cursor
        ? '<button type="button" class="link" data-baws-action="more" data-group="' + escapeText(key) + '">继续加载</button>' : '';
      return '<section class="ba-side-group" data-group="' + escapeText(key) + '">'
        + '<div class="spread"><h3>' + escapeText(label)
        + ' <span class="ba-side-count" data-count="' + escapeText(key) + '">' + badge + '</span></h3></div>'
        + (sub ? '<p class="ba-side-sub">' + escapeText(sub) + '</p>' : '')
        + '<div class="ba-side-list">' + list + '</div>' + more + '</section>';
    }).join('');
    const noticeLine = state.notice
      ? '<p class="ba-side-notice" role="status">' + escapeText(state.notice) + '</p>' : '';
    return notice + busy + noticeLine + sections;
  }

  function renderSidebarInto() {
    const host = document.getElementById('ba-sidebar-root');
    if (host) host.innerHTML = renderSidebar();
  }

  function headingText() {
    const item = state.selected;
    if (!item) return '还没有选中事项';
    return item.title || '待办事项';
  }
  function planHTML() {
    const item = state.selected, parts = [];
    if (!item) parts.push('<p class="ba-current-hint">左侧选一项待办，或直接在下面说要办的事；助手只读真实数据，不会自动提交。</p>');
    else {
      parts.push('<p class="ba-current-status">' + escapeText(item.status_label || item.status || '') + '</p>');
      if (item.waiting_reason) parts.push('<p class="ba-current-wait">等待：' + escapeText(item.waiting_reason) + '</p>');
      if (item.kind === 'native_task') {
        parts.push('<p class="ba-current-note">这是原业务待办：可直接打开原页面办理，或把这件事交给助手准备。</p>');
        if (item.manual_route) parts.push('<p><a class="ba-record-link" href="#' + escapeText(item.manual_route) + '">打开原业务办理</a>'
          + ' <button type="button" data-baws-action="handoff" data-key="' + escapeText(item.key) + '">交给助手</button></p>');
      }
    }
    return parts.join('');
  }

  function patchCurrent() {
    if (!alive()) return false;
    const heading = document.getElementById('ba-current-heading');
    const plan = document.getElementById('ba-current-plan');
    // 只替换这两个显示节点：消息流、卡片和输入框由助手页面自己维护，不在这里重建。
    if (heading) heading.textContent = headingText();
    if (plan) {
      const work = document.getElementById('business-assistant-workboard');
      const keep = work ? work.outerHTML : '';
      plan.innerHTML = planHTML() + keep;
    }
    const host = document.getElementById('ba-sidebar-root');
    if (host) {
      for (const article of host.querySelectorAll('.ba-side-item')) {
        const selected = state.selected && article.dataset.item === state.selected.key;
        article.classList.toggle('selected', Boolean(selected));
        const button = article.querySelector('[data-baws-action="open"]');
        if (button) button.setAttribute('aria-current', selected ? 'true' : 'false');
      }
    }
    return true;
  }

  function switchGuard(item) {
    const page = current();
    if (!page) return { ok: false, reason: '助手尚未就绪，请稍后重试。' };
    if (item && item.session_id && page.session && page.session.id === item.session_id) {
      return { ok: true, reason: '' };   // 同一事项内部切换不需要守卫
    }
    if (String(page.draft || '').trim()) {
      return { ok: false, reason: '当前输入还没发送，请先发送或清空，再切换到其它事项。' };
    }
    if (page.retry) return { ok: false, reason: '上一次发送结果还没确认，请先重试或清空，再切换事项。' };
    if (page.runId || page.busy) return { ok: false, reason: '当前事项正在处理中，请等待或先停止，再切换事项。' };
    const pending = ((page.session && page.session.proposals) || [])
      .filter((card) => (typeof businessAssistantDisplayStatus === 'function'
        ? businessAssistantDisplayStatus(card) : card.status) === 'pending');
    if (pending.length) return { ok: false, reason: '当前事项还有 ' + pending.length + ' 张待确认卡，请先处理或取消，再切换事项。' };
    return { ok: true, reason: '' };
  }

  async function openItem(key) {
    const item = findItem(key);
    if (!item) return false;
    const guard = switchGuard(item);
    if (!guard.ok) {
      state.notice = guard.reason;
      if (typeof toast === 'function') toast(guard.reason, true);
      renderSidebarInto();
      return false;
    }
    state.notice = '';
    state.selected = item;
    renderSidebarInto();
    patchCurrent();
    if (item.kind === 'native_task') return true;   // 查看原任务不创建会话、不调用模型
    if (item.session_id && typeof businessAssistantChooseSession === 'function') {
      const page = current();
      if (!page || !page.session || page.session.id !== item.session_id) {
        await businessAssistantChooseSession(item.session_id);
      }
      if (typeof businessAssistantRefreshWork === 'function' && item.plan_id) {
        await businessAssistantRefreshWork(undefined, undefined, item.plan_id);
      }
    }
    patchCurrent();
    return true;
  }

  function closeDrawer() {
    state.drawer = false;
    const root = document.querySelector('.ba-runtime-workspace');
    if (root) root.classList.remove('drawer-open');
    const mask = document.querySelector('.ba-side-mask');
    if (mask) mask.classList.remove('shown');
    if (state.toggle && typeof state.toggle.setAttribute === 'function') {
      state.toggle.setAttribute('aria-expanded', 'false');
      if (typeof state.toggle.focus === 'function') state.toggle.focus({ preventScroll: true });
    }
  }

  async function onClick(event) {
    const target = event.target && event.target.closest ? event.target.closest('[data-baws-action]') : null;
    if (!target || !alive()) return;
    const action = target.dataset.bawsAction;
    if (action === 'open') { await openItem(target.dataset.key); return; }
    if (action === 'more') {
      const group = target.dataset.group;
      await load({ group: group, cursor: state.cursors[group] || '' });
      return;
    }
    if (action === 'drawer') {
      state.drawer = !state.drawer;
      state.toggle = target;
      target.setAttribute('aria-expanded', state.drawer ? 'true' : 'false');
      const root = document.querySelector('.ba-runtime-workspace');
      if (root) root.classList.toggle('drawer-open', state.drawer);
      const mask = document.querySelector('.ba-side-mask');
      if (mask) mask.classList.toggle('shown', state.drawer);
      if (state.drawer) {
        const first = document.querySelector('#ba-sidebar-root [data-baws-action="open"]');
        if (first && typeof first.focus === 'function') first.focus({ preventScroll: true });
      }
      return;
    }
    if (action === 'drawer-close') { closeDrawer(); return; }
    if (action === 'handoff') {
      const item = findItem(target.dataset.key) || state.selected;
      if (!item) return;
      const page = current();
      if (!page) return;
      const text = '处理这项待办：' + (item.title || '待办事项')
        + (item.manual_route ? '（原业务入口 ' + item.manual_route + '）' : '')
        + '；先读真实原单，再准备待确认内容，不要直接提交。';
      page.draft = text;   // 只填未发送草稿，等待员工自己发送
      if (typeof paintBusinessAssistant === 'function') paintBusinessAssistant({ focus: true });
    }
  }

  function onKeydown(event) {
    if (event.key !== 'Escape' || !state.drawer) return;
    closeDrawer();
  }

  function mount(root) {
    state.mounted = true;
    state.context = contextKey();
    if (!state.bound) {
      document.addEventListener('click', onClick);
      document.addEventListener('keydown', onKeydown);
      state.bound = true;
    }
    if (root) state.host = root;
    if (!state.groups.length && !state.loading && !state.error) { load(); return true; }
    renderSidebarInto();
    patchCurrent();
    return true;
  }

  function disposeContext() {
    if (state.bound) {
      document.removeEventListener('click', onClick);
      document.removeEventListener('keydown', onKeydown);
    }
    closeDrawer();
    state = fresh();
    return true;
  }

  globalThis.AssistantWorkspace = {
    load: load, mount: mount, renderSidebar: renderSidebar, openItem: openItem,
    patchCurrent: patchCurrent, disposeContext: disposeContext,
    snapshot: function () {
      return { groups: state.groups.map((group) => ({ key: group.key, count: (group.items || []).length,
        next_cursor: group.next_cursor || null })),
        counts: state.counts, error: state.error, loading: state.loading,
        selected: state.selected ? state.selected.key : null, drawer: state.drawer };
    },
  };
})();
