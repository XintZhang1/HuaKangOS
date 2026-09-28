/* 业务助手事项侧栏与两列工作台（M6.3）。
 *
 * 只读服务器授权投影：GET /api/business-assistant/workspace。
 * 本模块不改业务、不推进 Plan/Task/Proposal、不写浏览器持久化、不自动选卡或自动发送。
 * 固定三组顺序：待我处理(attention) → 跟进中(following) → 已结束(finished)，只展示服务器给的项。
 * M6.5 起它同时是唯一的交接入口 requestHandoff：只校验引用与上下文、只预填草稿，
 * entry_context 随员工下一次发送提交；不猜 ID、不把 returnRoute 当工具参数、不自动发送。
 * 唯一出口是 globalThis.AssistantWorkspace：
 *   load({group?,cursor?,limit?}) / mount(root?) / renderSidebar() / openItem(key)
 *   / patchCurrent() / disposeContext() / snapshot()
 *   / requestHandoff(options) / guardHandoff(options) / pendingHandoff() / clearHandoff()
 *   / rememberUi() / restoreUi() / clearUi()
 */
'use strict';
(function () {
  const GROUPS = [['attention', '待我处理'], ['following', '跟进中'], ['finished', '已结束']];
  const KIND_LABEL = { native_task: '业务待办', proposal: '待确认操作', plan: '跟进事项' };
  const DRAWER_WIDTH = 1024;
  const HANDOFF_INTENTS = ['query_status', 'explain_prerequisites', 'prepare_action'];
  // 三种固定中文模板：意图与措辞一一对应，员工可先改再发。
  const HANDOFF_PROMPTS = {
    query_status: '查一下这件事当前的真实状态和下一步，只读取和说明，不准备卡片。',
    explain_prerequisites: '说明这件事还需要哪些资料和前置条件，只读取和说明，不提交。',
    prepare_action: '按这件事的真实原单和资料，准备下一步待确认内容；不要直接提交，等我核对。',
  };
  const HANDOFF_LABEL = { task: '原业务待办', object: '原单', workflow: '业务流程' };
  const uiBySession = new Map();

  function fresh() {
    return { features: null, counts: null, groups: [], cursors: {}, loading: false,
      error: '', selected: null, serial: 0, mounted: false, bound: false, context: '',
      error: '', selected: null, serial: 0, mounted: false, bound: false, context: '',
      drawer: false, notice: '', host: null, toggle: null, handoff: null, handoffLabel: '', handoffPrompt: '' };
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

  // ---- M6.5 交接：唯一入口。只校验引用与上下文，只预填草稿；不发送、不猜 ID、不落浏览器存储。----

  function routeValid(route) {
    const guide = globalThis.WorkflowGuides;
    if (guide && typeof guide.validRoute === 'function') return Boolean(guide.validRoute(route));
    return typeof route === 'string' && route.length < 180
      && /^[a-z][a-z0-9-]*(?:\/[A-Za-z0-9_-]+)*$/.test(route);
  }

  // 只接受服务器 DTO 的三种来源；拒绝任何自报员工/门店/角色或自由文本引用。
  function buildEntryContext(reference, intent) {
    if (!HANDOFF_INTENTS.includes(intent)) return null;
    if (!reference || typeof reference !== 'object') return null;
    const source = reference.source_type;
    if (source === 'task') {
      const taskId = Number(reference.task_id);
      if (!Number.isSafeInteger(taskId) || taskId <= 0) return null;
      return { source_type: 'task', intent: intent, task_id: taskId };
    }
    if (source === 'object') {
      const ref = reference.object_ref;
      if (!ref || typeof ref !== 'object' || typeof ref.type !== 'string' || !ref.type) return null;
      // 与服务器 BusinessObjectRef 相同：report_query 只能引用 WorkItem UUID，其余必须是正整数原单 ID。
      if (ref.type === 'report_query') {
        if (typeof ref.id !== 'string' || !ref.id) return null;
        return { source_type: 'object', intent: intent, object_ref: { type: 'report_query', id: ref.id } };
      }
      if (!Number.isSafeInteger(ref.id) || ref.id <= 0) return null;
      return { source_type: 'object', intent: intent, object_ref: { type: ref.type, id: ref.id } };
    }
    if (source === 'workflow') {
      const workflowId = reference.workflow_id;
      if (typeof workflowId !== 'string' || !workflowId || workflowId.length > 100) return null;
      return { source_type: 'workflow', intent: intent, workflow_id: workflowId };
    }
    return null;
  }

  function guardHandoff() {
    const page = current();
    if (!page) return { ok: false, reason: '助手尚未就绪，请稍后重试。', choice: 'none' };
    const draft = String(page.draft || '');
    // 员工自己写的内容绝不被覆盖；但只是上一次交接预填、尚未改动的草稿允许改交接目标。
    if (draft.trim() && draft !== state.handoffPrompt) {
      return { ok: false, reason: '当前输入还没发送，请先发送或清空，再打开其它事项。', choice: 'none' };
    }
    if (page.retry) {
      return { ok: false, reason: '上一次发送结果还没确认，请先重试或清空，再打开其它事项。', choice: 'none' };
    }
    const cards = (page.session && page.session.proposals) || [];
    const status = (card) => (typeof businessAssistantDisplayStatus === 'function'
      ? businessAssistantDisplayStatus(card) : card.status);
    const waiting = cards.filter((card) => ['pending', 'executing', 'uncertain'].includes(status(card)));
    if (page.runId || page.busy || waiting.length) {
      return { ok: false, choice: 'stay-or-open',
        reason: page.runId || page.busy
          ? '当前事项正在处理中。可以留在当前事项，或保留当前进度并打开目标事项（不会取消运行）。'
          : '当前事项还有 ' + waiting.length + ' 张待确认或在办的卡片。可以留在当前事项，或保留当前进度并打开目标事项。' };
    }
    return { ok: true, reason: '', choice: 'none' };
  }

  function captureUi() {
    const page = current();
    if (!page) return null;
    const answers = {};
    for (const key of Object.keys(page.answers || {})) answers[key] = Object.assign({}, page.answers[key]);
    return { draft: String(page.draft || ''), answers: answers, activeCardId: page.activeCardId,
      queueFilter: page.queueFilter, workPlanId: page.workPlanId,
      files: page.files ? JSON.parse(JSON.stringify(page.files)) : null };
  }

  function uiKey() {
    const page = current();
    return (page && page.session && page.session.id) ? String(page.session.id) : 'new';
  }

  function rememberUi() {
    const snapshot = captureUi();
    if (!snapshot) return false;
    uiBySession.set(uiKey(), snapshot);
    return true;
  }

  function restoreUi() {
    const page = current(), saved = uiBySession.get(uiKey());
    if (!page || !saved) return false;
    page.draft = saved.draft || '';
    if (saved.activeCardId != null) page.activeCardId = saved.activeCardId;
    if (saved.queueFilter) page.queueFilter = saved.queueFilter;
    if (saved.workPlanId != null) page.workPlanId = saved.workPlanId;
    if (saved.files) page.files = JSON.parse(JSON.stringify(saved.files));
    // 只恢复同一 proposal_id 的答案：服务器卡已变时旧答案绝不贴到新卡上。
    const alive = new Set((((page.session && page.session.proposals) || [])).map((card) => String(card.id)));
    page.answers = {};
    for (const key of Object.keys(saved.answers || {})) {
      if (alive.has(String(key))) page.answers[key] = Object.assign({}, saved.answers[key]);
    }
    return true;
  }

  function clearUi() { uiBySession.clear(); return true; }
  function pendingHandoff() { return state.handoff ? Object.assign({}, state.handoff) : null; }
  function clearHandoff() {
    state.handoff = null;
    state.handoffLabel = '';
    if (typeof paintBusinessAssistant === 'function') paintBusinessAssistant();
    return true;
  }

  // 唯一交接入口：{entry_context|reference+intent, prompt?, contextEpoch?, returnRoute?, keepCurrent?}
  function requestHandoff(options) {
    const settings = options || {};
    const intent = settings.intent || (settings.entry_context && settings.entry_context.intent) || 'prepare_action';
    const context = settings.entry_context
      ? buildEntryContext({ source_type: settings.entry_context.source_type,
        task_id: settings.entry_context.task_id, object_ref: settings.entry_context.object_ref,
        workflow_id: settings.entry_context.workflow_id }, intent)
      : buildEntryContext(settings.reference, intent);
    if (!context) return { ok: false, reason: '拿不到明确的原业务引用，请在原页面办理，或从原单页点“交给助手”。' };
    if (settings.contextEpoch != null && String(settings.contextEpoch) !== String(contextKey())) {
      return { ok: false, reason: '页面上下文已变化，这次交接已取消，请重新点一次。' };
    }
    const guard = guardHandoff();
    // 员工明确选择"保留当前事项并打开"时，先把当前编辑状态存进内存再打开目标；否则停留原事项。
    if (!guard.ok && settings.keepCurrent !== true) {
      return { ok: false, reason: guard.reason, needsChoice: guard.choice === 'stay-or-open' };
    }
    const page = current();
    if (!page) return { ok: false, reason: '助手尚未就绪，请稍后重试。' };
    const prompt = typeof settings.prompt === 'string' && settings.prompt.trim()
      ? settings.prompt : HANDOFF_PROMPTS[intent];
    if (settings.keepCurrent === true) {
      rememberUi();          // 草稿、答案、选卡与文件选择留在原事项的内存里，不取消运行
      page.draft = prompt;   // 目标事项显示它自己的交接提示
    }
    state.handoff = { entry_context: context, prompt: prompt,
      returnRoute: (typeof settings.returnRoute === 'string' && routeValid(settings.returnRoute))
        ? settings.returnRoute : '',
      source: HANDOFF_LABEL[context.source_type] || '原业务' };
    state.handoffLabel = state.handoff.source + '：' + (settings.label || prompt.slice(0, 24));
    const draft = String(page.draft || '');
    if (!draft.trim() || draft === state.handoffPrompt) page.draft = prompt;   // 只预填，绝不覆盖员工已写内容
    state.handoffPrompt = prompt;
    state.notice = '';
    if (typeof paintBusinessAssistant === 'function') paintBusinessAssistant({ focus: true });
    return { ok: true, entry_context: state.handoff.entry_context };
  }

  function handoffLabel() { return state.handoffLabel || ''; }

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
        restoreUi();   // 回到旧事项只恢复同一 proposal_id 的答案
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
      // M6.5：所有入口走同一个 requestHandoff；拿不到真实引用时只提示回原页面办理。
      const reference = item.kind === 'native_task' && item.task_id
        ? { source_type: 'task', task_id: item.task_id }
        : item.object_ref ? { source_type: 'object', object_ref: item.object_ref } : null;
      const result = requestHandoff({ reference: reference, intent: 'prepare_action',
        prompt: reference && reference.source_type === 'task'
          ? '处理这项待办：' + (item.title || '待办事项') + '；先读真实原单，再准备待确认内容，不要直接提交。'
          : HANDOFF_PROMPTS.prepare_action,
        label: item.title, returnRoute: item.manual_route, contextEpoch: contextKey() });
      if (!result.ok) {
        state.notice = result.reason;
        renderSidebarInto();
        if (typeof toast === 'function') toast(result.reason, true);
      }
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
    clearUi();          // 切店/退出清空整个内存编辑态与待交接内容
    state = fresh();
    return true;
  }

  globalThis.AssistantWorkspace = {
    load: load, mount: mount, renderSidebar: renderSidebar, openItem: openItem,
    patchCurrent: patchCurrent, disposeContext: disposeContext,
    requestHandoff: requestHandoff, guardHandoff: guardHandoff,
    pendingHandoff: pendingHandoff, clearHandoff: clearHandoff, handoffLabel: handoffLabel,
    rememberUi: rememberUi, restoreUi: restoreUi, clearUi: clearUi,
    snapshot: function () {
      return { groups: state.groups.map((group) => ({ key: group.key, count: (group.items || []).length,
        next_cursor: group.next_cursor || null })),
        counts: state.counts, error: state.error, loading: state.loading,
        selected: state.selected ? state.selected.key : null, drawer: state.drawer,
        handoff: state.handoff ? state.handoff.entry_context : null,
        handoffLabel: state.handoffLabel || '', uiSessions: uiBySession.size };
    },
  };
})();
