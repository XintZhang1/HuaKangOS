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

  // 等待文案只用服务器给出的固定中文标签。内部状态机标识（如 employee_continue）
  // 不再直接显示给员工；确实没有文案时整条等待信息不显示。
  function waitingText(item) {
    if (!item || typeof item !== 'object') return '';
    return typeof item.waiting_label === 'string' ? item.waiting_label : '';
  }

  function fresh() {
    return { features: null, counts: null, groups: [], cursors: {}, loading: false, loaded: false,
      error: '', selected: null, serial: 0, mounted: false, bound: false, context: '',
      drawer: false, notice: '', host: null, toggle: null, handoff: null, handoffLabel: '', handoffPrompt: '',
      plan: null, planError: '', planLoading: false, planSerial: 0, followupPending: '', followupToken: null, revokeArmed: false,
      notices: [], noticeUnread: 0, noticeCursor: null, noticeOpen: false, noticeError: '',
      noticeSerial: 0, noticeLoading: false, noticePoll: null, noticeSeen: null, noticeReadPending: '', noticeBound: false,
      receipts: {} };
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
  // Serial counters restart on disposal; identity plus context prevents ABA responses.
  function requestGuard() {
    const owner = state, epoch = contextKey();
    return () => owner === state && epoch === contextKey();
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
    const valid = requestGuard();
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
      if (!valid() || state.serial !== serial) return null;
      state.loading = false;
      state.error = (error && error.message) || '读取待办失败，请稍后重试。';
      renderSidebarInto();
      return null;
    }
    if (!valid() || state.serial !== serial) return null;  // 迟到的分页结果按序号丢弃，不合并到新上下文
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
    state.loading = false; state.loaded = true; state.error = '';
    if (state.selected) {
      const found = findItem(state.selected.key);
      state.selected = found || null;   // 服务器不再返回就清空，不自作主张改选别的项
    }
    renderSidebarInto();
    if (state.mounted) startNotifications();
    patchCurrent();
  }

  function itemHTML(item) {
    const selected = state.selected && state.selected.key === item.key;
    const meta = [];
    // 只显示服务器给出的固定中文等待文案；没有文案时不显示内部状态机标识。
    const waiting = waitingText(item);
    if (waiting) meta.push('等待：' + waiting);
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
        + '<button type="button" class="link" data-baws-action="retry-sidebar">重试</button>'
      : '';
    const busy = state.loading && !state.loaded
      ? '<p class="ba-side-hint">正在读取你的待办…</p>' : '';
    // Before a successful read, unknown totals are not an empty work queue.
    if (!state.loaded) return notice + busy;
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
    if (!item) return current()?.session?.title || '新对话';
    return item.title || '待办事项';
  }
  function planHTML() {
    const item = state.selected, parts = [];
    parts.push(notificationPanelHTML());
    parts.push(planHeaderHTML());
    if (item) {
      parts.push('<p class="ba-current-status">' + escapeText(item.status_label || item.status || '') + '</p>');
      const currentWait = waitingText(item);
      if (currentWait) parts.push('<p class="ba-current-wait">等待：' + escapeText(currentWait) + '</p>');
      if (item.kind === 'native_task') {
        parts.push('<p class="ba-current-note">这是原业务待办，可打开原页面办理；需要助手帮助时，在对话中输入事项和原单信息。</p>');
        if (item.manual_route) parts.push('<p><a class="ba-record-link" href="#' + escapeText(item.manual_route) + '">打开原业务办理</a></p>');
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
    if (!context) return { ok: false, reason: '拿不到明确的原业务引用，请在原页面办理，或在业务助手中输入事项和原单信息。' };
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

  function parseRef(ref) {
    const parts = String(ref || '').split(':');
    if (parts[0] === 'task' && parts.length === 2 && /^[0-9]+$/.test(parts[1])) {
      return { source_type: 'task', task_id: Number(parts[1]) };
    }
    if (parts[0] === 'object' && parts.length === 3 && parts[1] && parts[2]) {
      return { source_type: 'object', object_ref: { type: parts[1],
        id: /^[0-9]+$/.test(parts[2]) ? Number(parts[2]) : parts[2] } };
    }
    if (parts[0] === 'workflow' && parts.length === 2 && parts[1]) {
      return { source_type: 'workflow', workflow_id: parts[1] };
    }
    return null;
  }

  // 保留各原页面的调用接口；员工统一在业务助手中输入，不再显示独立交接按钮。
  function handoffButton(options) {
    return '';
  }

  // ---- M6.6 持续跟进：只读 PlanView、只在员工明确点击时提交一次动作；不做本地授权判定。----
  const PLAN_STATUS_TEXT = { active: '进行中', paused: '已暂停', completed: '已完成', cancelled: '已取消' };
  const GRANT_STATUS_TEXT = { active: '持续跟进中', paused: '已暂停跟进', revoked: '已结束跟进' };
  const FOLLOWUP_LABELS = { enable: '开启此事项持续跟进', pause: '暂停跟进', resume: '恢复跟进', revoke: '结束这件事' };

  function planStatusText(status) { return PLAN_STATUS_TEXT[status] || '状态待核对'; }
  function grantStatusText(grant) {
    if (!grant || !grant.status) return '尚未开启持续跟进';
    return GRANT_STATUS_TEXT[grant.status] || '跟进状态待核对';
  }
  function followupAllowed(action) {
    const plan = state.plan;
    if (!plan || !Array.isArray(plan.allowed_actions)) return false;
    const features = state.features || {};
    if (features.followup !== true) return false;   // 开关关闭：只显示状态，不给可操作按钮
    return plan.allowed_actions.includes(action);
  }

  async function loadPlan(planId) {
    const valid = requestGuard();
    const previous = state.plan, armed = state.revokeArmed === true;
    if (!planId || state.plan?.id !== planId) {
      state.plan = null; state.revokeArmed = false; state.followupPending = ''; state.followupToken = null;
    }
    const serial = (state.planSerial || 0) + 1;
    state.planSerial = serial; state.planLoading = true; state.planError = '';
    if (!planId) { state.plan = null; state.planLoading = false; patchCurrent(); return null; }
    patchCurrent();
    let view;
    try {
      view = await businessAssistantRequest('/plans/' + encodeURIComponent(String(planId)));
    } catch (error) {
      if (!valid() || state.planSerial !== serial) return null;
      state.planLoading = false;
      state.plan = null;
      state.revokeArmed = false;
      state.planError = (error && error.message) || '读取事项进度失败，请稍后重试。';
      patchCurrent();
      return null;
    }
    if (!valid() || state.planSerial !== serial) return null;
    state.plan = view || null;
    state.planLoading = false;
    state.revokeArmed = !!(armed && state.revokeArmed === true && previous && view && previous.id === view.id
      && Number.isSafeInteger(previous.goal_version) && view.goal_version === previous.goal_version
      && view.status === previous.status && JSON.stringify(view.grant) === JSON.stringify(previous.grant)
      && Array.isArray(view.allowed_actions) && view.allowed_actions.includes('revoke'));
    patchCurrent();
    return state.plan;
  }

  // 只提交当前 plan.id 与当前 version；不重放、不自造版本、不改本地授权快照。
  async function setFollowup(action) {
    const validContext = requestGuard();
    if (state.followupPending || state.planLoading) return { ok: false, reason: '正在核对，请稍后再操作。' };
    const plan = state.plan;
    if (!plan || !plan.id) return { ok: false, reason: '还没有可跟进的事项，请先选一件事项。' };
    if (!FOLLOWUP_LABELS[action]) return { ok: false, reason: '不支持的跟进操作。' };
    if (!followupAllowed(action)) return { ok: false, reason: '当前事项不允许这个操作，请刷新后核对。' };
    if (action === 'revoke' && state.revokeArmed !== true) {
      state.revokeArmed = true;          // 二次确认：明确说明不取消原业务
      patchCurrent();
      return { ok: false, reason: '再点一次“结束这件事”确认；已生成的卡片和已提交的原业务都不会被取消。', needsConfirm: true };
    }
    const version = plan.version;
    if (!Number.isSafeInteger(version)) return { ok: false, reason: '事项版本未知，请刷新后重试。' };
    const token = {};
    state.followupToken = token; state.followupPending = action; state.planSerial++;
    const valid = () => validContext() && state.followupToken === token && state.plan?.id === plan.id;
    patchCurrent();
    try {
      // 后台进度会推进 version；核对同一授权范围后只提交一次服务器当前版本。
      const current = await businessAssistantRequest('/plans/' + encodeURIComponent(String(plan.id)));
      if (!valid()) return { ok: false, reason: '当前事项已切换。' };
      if (!current || current.id !== plan.id || !Number.isSafeInteger(current.version)
          || !Number.isSafeInteger(plan.goal_version) || current.goal_version !== plan.goal_version
          || JSON.stringify(current.grant) !== JSON.stringify(plan.grant)
          || !Array.isArray(current.allowed_actions) || !current.allowed_actions.includes(action)) {
        state.plan = current && current.id === plan.id ? current : null;
        state.revokeArmed = false;
        state.planError = '事项已变化，请核对后再操作。';
        return { ok: false, reason: state.planError };
      }
      state.plan = current;
      const updated = await businessAssistantRequest(
        '/plans/' + encodeURIComponent(String(plan.id)) + '/followup',
        { method: 'POST', body: { action: action, expected_version: current.version } });
      if (!valid()) return { ok: false, reason: '当前事项已切换。' };
      state.planSerial++; state.planLoading = false;
      if (state.plan && state.plan.id === plan.id && (!Number.isSafeInteger(updated?.version) || updated.version >= state.plan.version)) {
        state.plan = Object.assign({}, state.plan, updated || {});
        state.planError = '';
      }
      state.revokeArmed = false;
      return { ok: true, plan: updated };
    } catch (error) {
      if (!valid()) return { ok: false, reason: '当前事项已切换。' };
      state.revokeArmed = false;
      const status = error && error.status;
      if (status === 409) {
        // 版本冲突：不重放动作，读回当前 Plan 让员工重新核对；提示在读回之后仍然可见。
        const changed = '事项已变化，请核对后再操作。';
        await loadPlan(plan.id);
        if (!valid()) return { ok: false, reason: '当前事项已切换。' };
        state.planError = changed;
        patchCurrent();
        return { ok: false, reason: changed };
      } else if (status === 403 || status === 404) {
        state.plan = null;
        state.planError = status === 403
          ? '当前账号或门店已没有这件事项的权限，写控制已收起。原业务仍可在原页面办理。'
          : '这件事项已不存在或不可读，写控制已收起。';
      } else {
        state.planError = (error && error.message) || '跟进操作没有完成，请稍后重试。';
      }
      patchCurrent();
      return { ok: false, reason: state.planError };
    } finally {
      if (validContext() && state.followupToken === token) {
        state.followupPending = ''; state.followupToken = null; patchCurrent();
      }
    }
  }

  function planHeaderHTML() {
    const plan = state.plan, features = state.features || {};
    if (state.planLoading && !plan) return '<p class="ba-plan-hint">正在读取这件事的进度…</p>';
    const lines = [];
    if (state.planError) lines.push('<p class="ba-plan-error" role="alert">' + escapeText(state.planError) + '</p>');
    if (!plan) {
      return lines.join('');
    }
    lines.push('<p class="ba-plan-goal">目标：' + escapeText(plan.goal || '当前事项') + ' · '
      + escapeText(planStatusText(plan.status)) + '</p>');
    const grant = plan.grant || {};
    lines.push('<p class="ba-plan-grant">' + escapeText(grantStatusText(grant))
      + (grant.stop_reason ? '（' + escapeText(grant.stop_reason) + '）' : '') + '</p>');
    const waiting = (plan.steps || []).filter((step) => step && typeof step.waiting_label === 'string' && step.waiting_label);
    if (waiting.length) {
      lines.push('<ul class="ba-plan-waits">' + waiting.slice(0, 3).map((step) => '<li>'
        + escapeText(step.title || '步骤') + '：' + escapeText(step.waiting_label) + '</li>').join('') + '</ul>');
    }
    if (features.followup !== true) {
      lines.push('<p class="ba-plan-hint">当前版本未开启持续跟进开关，只显示已有状态。</p>');
      return lines.join('');
    }
    if (!grant.enabled && followupAllowed('enable')) {
      // 开启前把范围讲清楚：目标、门店、本人、只查询与准备、退出后继续、暂停与结束入口。
      const storeName = typeof businessAssistantStoreName === 'function' ? businessAssistantStoreName() : '当前门店';
      lines.push('<p class="ba-plan-scope">以你在' + escapeText(storeName)
        + '的权限查询和准备此事项，办理仍需逐张确认。退出登录后继续跟进，可随时暂停或结束。</p>');
    }
    const buttons = ['enable', 'resume', 'pause', 'revoke'].filter(followupAllowed).map((action) => {
      const label = action === 'revoke' && state.revokeArmed ? '确认结束这件事' : FOLLOWUP_LABELS[action];
      const busy = state.followupPending || state.planLoading ? ' disabled' : '';
      return '<button type="button" class="ba-plan-action' + (action === 'revoke' ? ' danger' : '')
        + '" data-baws-action="followup" data-baws-followup="' + action + '"' + busy + '>'
        + escapeText(label) + '</button>';
    });
    if (buttons.length) lines.push('<div class="row ba-plan-actions">' + buttons.join('') + '</div>');
    return lines.join('');
  }

  // ---- M6.7 站内通知：只读服务器通知投影；点击先打开目标再显式标记已读。----
  const RECEIPT_TEXT = {
    confirmed_success: '已找到原业务成功回执，请按原单核对结果。',
    not_found: '还没找到原业务结果，保持“待核对”，不要重复提交。',
    unsupported: '这类业务暂不支持助手核对，请到原页面核对。',
    inaccessible: '当前权限看不到原业务结果，请核对岗位或门店权限。',
    mismatch: '原业务结果与本次提交不一致，请先核对原单。',
  };

  function noticeSeen() {
    if (!(state.noticeSeen instanceof Set)) state.noticeSeen = new Set();
    return state.noticeSeen;
  }

  async function loadNotifications(options) {
    const valid = requestGuard();
    const settings = options || {};
    if (!notificationsOn() && !settings.force) return null;   // 未开启时连读取都不做
    const serial = (state.noticeSerial || 0) + 1;
    state.noticeSerial = serial; state.noticeLoading = true;
    const query = [];
    if (settings.cursor) query.push('cursor=' + encodeURIComponent(settings.cursor));
    if (settings.limit) query.push('limit=' + encodeURIComponent(settings.limit));
    let view;
    try {
      view = await businessAssistantRequest('/notifications' + (query.length ? '?' + query.join('&') : ''));
    } catch (error) {
      if (!valid() || state.noticeSerial !== serial) return null;
      state.noticeLoading = false;
      state.noticeError = (error && error.message) || '读取通知失败，请稍后重试。';
      patchCurrent();
      return null;
    }
    if (!valid() || state.noticeSerial !== serial) return null;
    const items = Array.isArray(view && view.items) ? view.items : [];
    if (settings.cursor) {
      for (const item of items) {
        if (item && item.id && !state.notices.some((existing) => existing.id === item.id)) state.notices.push(item);
      }
    } else {
      state.notices = items.slice();
    }
    state.noticeCursor = (view && view.next_cursor) || null;   // 原样透传给下一页，不自行拼装
    state.noticeUnread = Number((view && view.unread_count) || 0) || 0;
    state.noticeLoading = false;
    state.noticeError = '';
    // 只在新通知 ID 首次出现时轻提示一次；同页刷新不重复。
    const seen = noticeSeen();
    const fresh = state.notices.filter((item) => item && item.id && item.status === 'unread' && !seen.has(item.id));
    for (const item of state.notices) if (item && item.id) seen.add(item.id);
    if (fresh.length && !settings.silent && typeof toast === 'function') {
      toast('有 ' + fresh.length + ' 条新的业务助手通知。');
    }
    patchCurrent();
    return view;
  }

  function startNotifications() {
    if (!notificationsOn()) { stopNotifications(); return false; }
    if (state.noticeBound) return true;   // 未开启通知时不轮询
    if (typeof document === 'undefined' || !document.addEventListener) return false;
    state.noticeBound = true;
    document.addEventListener('visibilitychange', onVisibility);
    if (typeof window !== 'undefined' && window.addEventListener) window.addEventListener('focus', onVisibility);
    if (document.visibilityState !== 'hidden') {
      if (!state.noticeLoading) void loadNotifications({ silent: true });
      state.noticePoll = setTimeout(pollTick, 30000);
    }
    return true;
  }

  function stopNotifications() {
    state.noticeBound = false;
    if (state.noticePoll) { clearTimeout(state.noticePoll); state.noticePoll = null; }
    if (typeof document !== 'undefined' && document.removeEventListener) {
      document.removeEventListener('visibilitychange', onVisibility);
    }
    if (typeof window !== 'undefined' && window.removeEventListener) window.removeEventListener('focus', onVisibility);
    return true;
  }

  function pollTick() {
    state.noticePoll = null;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    const valid = requestGuard();
    loadNotifications({ silent: true }).then(() => {
      if (valid() && notificationsOn() && !state.noticePoll && state.mounted && typeof document !== 'undefined' && document.visibilityState !== 'hidden') {
        state.noticePoll = setTimeout(pollTick, 30000);
      }
    });
  }

  function onVisibility() {
    if (!state.mounted || !notificationsOn()) return;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      if (state.noticePoll) { clearTimeout(state.noticePoll); state.noticePoll = null; }
      return;   // 隐藏标签停止轮询
    }
    loadNotifications({ silent: true });   // 回到前台立即读取一次
    if (!state.noticePoll) state.noticePoll = setTimeout(pollTick, 30000);
  }

  function invalidateNotifications() {
    // 既有运行事件只用来触发一次合并读取；不新增事件类型。
    if (!notificationsOn() || state.noticeLoading) return false;
    loadNotifications({ silent: true });
    return true;
  }

  async function openNotification(id) {
    const valid = requestGuard();
    const item = state.notices.find((notice) => notice && notice.id === id);
    if (!item || state.noticeReadPending) return false;
    // Latch the whole open/read sequence; a double click must not decrement twice.
    state.noticeReadPending = item.id;
    let opened = false;
    try {
      if (item.task_id) {
        opened = await openTaskReference(item.task_id, item.safe_summary);
      } else if (item.session_id) {
        const page = current();
        if (page?.session?.id === item.session_id) {
          opened = typeof businessAssistantRefreshCurrentSession === 'function'
            && await businessAssistantRefreshCurrentSession();
        } else {
          const guard = switchGuard(item);
          if (!guard.ok) { if (typeof toast === 'function') toast(guard.reason, true); return false; }
          opened = typeof businessAssistantChooseSession === 'function'
            && await businessAssistantChooseSession(item.session_id);
        }
        if (opened && valid() && item.plan_id && typeof businessAssistantRefreshWork === 'function') {
          await businessAssistantRefreshWork(undefined, undefined, item.plan_id);
        }
        if (opened && valid() && item.proposal_id) {
          const active = current(), card = active?.session?.proposals?.find(p => p.id === item.proposal_id);
          if (card) {
            active.activeCardId = card.id;
            active.queueFilter = typeof businessAssistantBucket === 'function' ? businessAssistantBucket(card) : 'pending';
            active.mobilePane = 'cards';
            if (typeof paintBusinessAssistant === 'function') paintBusinessAssistant();
          }
        }
      } else if (item.manual_route && typeof go === 'function') {
        go(item.manual_route); opened = true;
      }
      if (!valid() || !opened) return false;
      if (item.status === 'unread') {
        const serial = ++state.noticeSerial; // Invalidate polls started before this read.
        const updated = await businessAssistantRequest('/notifications/' + encodeURIComponent(String(item.id)) + '/read',
          { method: 'POST' });
        if (!valid()) return false;
        const latest = state.notices.find(notice => notice.id === item.id);
        state.notices = state.notices.map(notice => notice.id === item.id
          ? Object.assign({}, notice, updated || {}, { status: updated?.status || 'read' }) : notice);
        if (latest?.status === 'unread') state.noticeUnread = Math.max(0, Number(state.noticeUnread || 0) - 1);
        // A concurrent poll has its own exact server count; re-read instead of guessing.
        if (state.noticeSerial !== serial) void loadNotifications({ silent: true });
        else state.noticeLoading = false;
      }
      return true;
    } catch (error) {
      if (valid()) state.noticeError = opened ? '已打开，已读状态未更新，请稍后刷新。' : '未能打开，请稍后刷新。';
      return opened && valid();
    } finally {
      if (valid()) { state.noticeReadPending = ''; patchCurrent(); }
    }
  }

  async function openTaskReference(taskId, label) {
    const guard = guardHandoff();
    if (!guard.ok && !(guard.choice === 'stay-or-open' && guard.keepCurrent === true)) {
      if (typeof toast === 'function') toast(guard.reason, true);
      return false;   // 守卫拒绝时不假称已读
    }
    const result = requestHandoff({ reference: { source_type: 'task', task_id: taskId },
      intent: 'query_status', label: label });
    if (!result.ok) {
      if (typeof toast === 'function') toast(result.reason, true);
      return false;
    }
    return true;
  }

  async function checkReceipt(sessionId, proposalId) {
    const contextValid = requestGuard(), page = current(), generation = page && page.generation;
    const valid = () => contextValid() && page && current() === page && page.generation === generation
      && String(page.session && page.session.id || '') === String(sessionId);
    if (!sessionId || !proposalId || !valid()) return null;
    const key = String(proposalId);
    try {
      const view = await businessAssistantRequest('/sessions/' + encodeURIComponent(String(sessionId))
        + '/proposals/' + encodeURIComponent(key) + '/execution-result');
      if (!valid()) return null;
      state.receipts[key] = view || null;
    } catch (error) {
      if (!valid()) return null;
      state.receipts[key] = { status: 'unavailable', reason: (error && error.message) || '核对失败，请稍后重试。' };
    }
    patchCurrent();
    return state.receipts[key];
  }

  function receiptText(view) {
    if (!view) return '';
    const primary = RECEIPT_TEXT[view.status];
    if (primary) return primary;
    return '核对未完成：' + ((view && view.reason) || '请稍后重试。');
  }

  function notificationsOn() {
    const features = state.features || {};
    return features.notifications === true;
  }

  function notificationPanelHTML() {
    if (!notificationsOn()) return '';   // 开关关闭：隐藏通知交互，不改任何业务状态
    const unread = Number(state.noticeUnread || 0) || 0;
    const entry = '<button type="button" class="ba-notice-entry" data-baws-action="notices" aria-expanded="'
      + (state.noticeOpen ? 'true' : 'false') + '">通知' + (unread ? ' <span class="ba-notice-badge">' + unread + '</span>' : '') + '</button>';
    if (!state.noticeOpen) return '<div class="ba-notice-bar">' + entry + '</div>';
    const rows = state.notices.length ? state.notices.map((item) => {
      const when = item.created_at && typeof time === 'function' ? time(item.created_at) : '';
      const readable = Boolean(item.task_id || item.session_id || item.manual_route);
      return '<li class="ba-notice' + (item.status === 'unread' ? ' unread' : '') + '" data-notice="' + escapeText(item.id) + '">'
        + '<button type="button" data-baws-action="notice-open" data-notice-id="' + escapeText(item.id) + '"'
        + (readable ? '' : ' disabled') + '>' + escapeText(item.safe_summary || '业务助手通知') + '</button>'
        + '<p class="ba-notice-meta">' + escapeText(when) + (item.status === 'unread' ? ' · 未读' : '') + '</p></li>';
    }).join('') : '<li class="ba-notice-empty">还没有通知。</li>';
    const more = state.noticeCursor
      ? '<button type="button" class="link" data-baws-action="notices-more">继续加载</button>' : '';
    return '<div class="ba-notice-bar">' + entry + '</div><div class="ba-notice-panel">'
      + (state.noticeError ? '<p class="ba-notice-error" role="alert">' + escapeText(state.noticeError) + '</p>' : '')
      + '<ul class="ba-notice-list">' + rows + '</ul>' + more + '</div>';
  }

  function receiptButtonHTML(sessionId, proposalId) {
    if (!sessionId || !proposalId) return '';
    return '<button type="button" data-baws-action="receipt" data-session="' + escapeText(sessionId)
      + '" data-proposal="' + escapeText(proposalId) + '">核对办理结果</button>';
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
    const validContext = requestGuard();
    const valid = () => validContext() && state.selected === item;
    state.notice = '';
    state.selected = item;
    renderSidebarInto();
    patchCurrent();
    if (item.kind === 'native_task') {
      await loadPlan(null);   // Viewing a native task never creates a session or calls a model.
      return valid();
    }
    await loadPlan(item.plan_id || null);
    if (!valid()) return false;
    if (item.session_id && typeof businessAssistantChooseSession === 'function') {
      const page = current();
      if (!page || !page.session || page.session.id !== item.session_id) {
        const opened = await businessAssistantChooseSession(item.session_id);
        if (!valid() || !opened) return false;
        restoreUi();   // Restore answers only for the same proposal in the chosen session.
      }
      if (typeof businessAssistantRefreshWork === 'function' && item.plan_id) {
        await businessAssistantRefreshWork(undefined, undefined, item.plan_id);
        if (!valid()) return false;
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
    if (action === 'retry-sidebar') {
      if (!state.loading) await load();
      return;
    }
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
    if (action === 'notices') { state.noticeOpen = !state.noticeOpen; patchCurrent(); if (state.noticeOpen) await loadNotifications({ silent: true }); return; }
    if (action === 'notices-more') { await loadNotifications({ cursor: state.noticeCursor || '' }); return; }
    if (action === 'notice-open') { await openNotification(String(target.dataset.noticeId || '')); return; }
    if (action === 'receipt') {
      const page = current(), generation = page && page.generation, sessionId = target.dataset.session;
      const view = await checkReceipt(sessionId, target.dataset.proposal);
      if (view && alive() && current() === page && page.generation === generation
          && String(page.session && page.session.id || '') === String(sessionId)
          && typeof toast === 'function') toast(receiptText(view), view.status !== 'confirmed_success');
      return;
    }
    if (action === 'followup') {
      const result = await setFollowup(String(target.dataset.bawsFollowup || ''));
      if (!result.ok && typeof toast === 'function') toast(result.reason, true);
      return;
    }
    if (action === 'handoff') {
      // 原页面按钮带 data-baws-ref；侧栏项用 data-key 查当前投影。
      if (target.dataset.bawsRef) {
        const label = target.dataset.bawsLabel || '';
        const result = requestHandoff({ reference: parseRef(target.dataset.bawsRef),
          intent: 'prepare_action', label: label || undefined });
        if (!result.ok && typeof toast === 'function') toast(result.reason, true);
        if (result.ok && typeof go === 'function' && globalThis.state
            && globalThis.state.route !== 'business-assistant') {
          go('business-assistant');   // 交接成功后回到助手页：草稿已预填，仍未发送
        }
        return;
      }
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
    const features = current()?.status?.features;
    if (features && ['home', 'runtime', 'followup', 'notifications'].every(key => typeof features[key] === 'boolean')) state.features = features;
    if (!state.bound) {
      document.addEventListener('click', onClick);
      document.addEventListener('keydown', onKeydown);
      state.bound = true;
    }
    if (root) state.host = root;
    startNotifications();
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
    stopNotifications();
    clearUi();
    // 退出/切店只清前端：绝不在这里调用 followup pause/revoke。
    state.plan = null; state.planError = ''; state.planSerial = 0; state.followupPending = ''; state.revokeArmed = false;          // 切店/退出清空整个内存编辑态与待交接内容
    state = fresh();
    return true;
  }

  globalThis.AssistantWorkspace = {
    load: load, mount: mount, renderSidebar: renderSidebar, openItem: openItem,
    patchCurrent: patchCurrent, disposeContext: disposeContext,
    requestHandoff: requestHandoff, guardHandoff: guardHandoff,
    handoffButton: handoffButton, parseRef: parseRef,
    notificationsOn: notificationsOn,
    loadNotifications: loadNotifications, startNotifications: startNotifications,
    stopNotifications: stopNotifications, invalidateNotifications: invalidateNotifications,
    openNotification: openNotification, checkReceipt: checkReceipt, receiptText: receiptText,
    notificationPanelHTML: notificationPanelHTML, receiptButtonHTML: receiptButtonHTML,
    loadPlan: loadPlan, setFollowup: setFollowup, planStatusText: planStatusText,
    grantStatusText: grantStatusText, followupAllowed: followupAllowed, waitingText: waitingText,
    pendingHandoff: pendingHandoff, clearHandoff: clearHandoff, handoffLabel: handoffLabel,
    rememberUi: rememberUi, restoreUi: restoreUi, clearUi: clearUi,
    snapshot: function () {
      return { groups: state.groups.map((group) => ({ key: group.key, count: (group.items || []).length,
        next_cursor: group.next_cursor || null })),
        counts: state.counts, error: state.error, loading: state.loading,
        selected: state.selected ? state.selected.key : null, drawer: state.drawer,
        handoff: state.handoff ? state.handoff.entry_context : null,
        plan: state.plan ? { id: state.plan.id, status: state.plan.status, version: state.plan.version,
          grant: (state.plan.grant && state.plan.grant.status) || null, revokeArmed: state.revokeArmed } : null,
        planError: state.planError || '',
        planLoading: state.planLoading, followupPending: !!state.followupPending,
        notificationsOn: notificationsOn(),
        noticeUnread: Number(state.noticeUnread || 0) || 0,
        noticeIds: state.notices.map((item) => item && item.id).filter(Boolean),
        noticeCursor: state.noticeCursor, noticeOpen: state.noticeOpen,
        noticeError: state.noticeError || '', receipts: Object.keys(state.receipts || {}),
        handoffLabel: state.handoffLabel || '', uiSessions: uiBySession.size };
    },
  };
})();
