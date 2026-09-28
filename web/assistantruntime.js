/* 业务助手 Runtime 浏览器客户端：只读 Run 状态/事件，不确认业务、不创建业务写入。
 *
 * 唯一出口是 globalThis.AssistantRuntime：
 *   submitRun(sessionId, body)        建立一次持久 Run（复用原 Cookie/CSRF/门店守卫）
 *   getRun(runId)                     读取 RunView
 *   subscribeRun(runId, onEvent)      订阅该 Run，返回只关闭本地读取的 unsubscribe
 *   cancelRun(runId, expectedVersion) 显式停止本次准备（只有员工点击才调用）
 *   snapshot(runId?)                  只读本地内存状态（含 succeeded 的固定展示文案）
 *   disposeContext()                  只清本地状态；不发 cancel、不改授权
 *
 * onEvent 收到的事件形状（仅本模块定义，不新增 HTTP 协议）：
 *   {type:'view', view, session?}          当前 RunView；终态时附带读回的一次 session
 *   {type:'event', event}                  服务端 RunEventView（seq 连续应用后）
 *   {type:'connection', state, error?}     'connecting'|'open'|'reconnecting'|'closed'
 *   {type:'unsupported', type_name}        未知事件类型：已重读 RunView 并保留提示
 */
(function () {
  'use strict';
  var API = '/api/business-assistant';
  var RECONNECT_MS = [1000, 2000, 5000];
  var IDLE_MS = 15000;
  var EVENT_CHARS = 2000000;
  var TERMINAL = ['succeeded', 'failed', 'cancelled'];
  var KNOWN_EVENTS = ['run.queued', 'run.started', 'run.progress', 'tool.finished',
    'proposal.prepared', 'plan.updated', 'run.completed', 'run.failed', 'run.cancelled'];
  var records = new Map();
  var visibilityBound = false;

  function contextKey() {
    return typeof businessAssistantContext === 'function' ? businessAssistantContext() : '';
  }

  function sessionState() {
    return typeof businessAssistantState === 'object' && businessAssistantState ? businessAssistantState : null;
  }

  function storeId() {
    return typeof state === 'object' && state ? String(state.store) : '';
  }

  function alive(item) {
    if (item.disposed) return false;
    if (typeof state === 'object' && state && state.storeSwitch) return false;
    if (contextKey() !== item.contextEpoch) return false;
    if (item.sessionState && typeof businessAssistantAlive === 'function'
        && !businessAssistantAlive(item.sessionState, item.generation)) return false;
    return true;
  }

  function notify(item, event) {
    if (!alive(item)) return false;
    for (var handler of Array.from(item.subscribers)) {
      try { handler(event); } catch (error) { /* 订阅方异常不影响其它订阅者与 Run 状态 */ }
    }
    return true;
  }

  function setConnection(item, value, error) {
    item.connectionState = value;
    item.lastError = error ? String(error.message || error) : null;
    notify(item, { type: 'connection', state: value, error: item.lastError });
  }

  function record(runId) {
    var id = String(runId == null ? '' : runId);
    if (!id) throw new Error('执行编号不正确。');
    var item = records.get(id);
    if (!item) {
      var shared = sessionState();
      item = { id: id, view: null, session: null, lastAppliedSeq: 0, displayRevision: -1,
        connectionState: 'idle', controller: null, subscribers: new Set(), contextEpoch: contextKey(),
        sessionState: shared, generation: shared ? shared.generation || 0 : 0,
        attempt: 0, timer: null, paused: false, disposed: false, unsupported: null, lastError: null };
      records.set(id, item);
    }
    return item;
  }

  function terminalText(view) {
    return view && view.status === 'succeeded' ? '本次准备已完成' : null;
  }

  function applyView(item, view, session) {
    if (!view || typeof view !== 'object' || String(view.id) !== item.id) {
      throw new Error('执行状态格式不完整。');
    }
    if (!alive(item)) return view;   // 陈旧门店/账号/会话：只回服务器事实，不改本地状态
    item.view = view;
    var display = view.display || {};
    if (Number.isSafeInteger(display.revision) && display.revision > item.displayRevision) {
      item.displayRevision = display.revision;
    }
    notify(item, { type: 'view', view: view, session: session || null });
    if (TERMINAL.includes(view.status)) close(item, 'closed');
    return view;
  }

  function close(item, value) {
    if (item.timer) { clearTimeout(item.timer); item.timer = null; }
    if (item.controller) { try { item.controller.abort(); } catch (error) { /* 已结束 */ } item.controller = null; }
    if (value) setConnection(item, value);
  }

  function schedule(item) {
    if (!alive(item) || item.paused || !item.subscribers.size) return;
    var delay = item.attempt < RECONNECT_MS.length ? RECONNECT_MS[item.attempt] : IDLE_MS;
    item.attempt += 1;
    if (item.timer) clearTimeout(item.timer);
    item.timer = setTimeout(function () {
      item.timer = null;
      if (!alive(item) || !item.subscribers.size || item.paused) return;
      readOnce(item).catch(function () { schedule(item); });
    }, delay);
  }

  function statusFailure(item, response) {
    if (response.status === 401) {
      if (typeof state === 'object' && state) state.user = null;
      if (typeof loginPage === 'function') loginPage();
      item.disposed = true;
      close(item, 'closed');
      throw Object.assign(new Error('登录已失效，请重新登录。'), { fatal: true, status: 401 });
    }
    if (response.status === 403 || response.status === 404) {
      // 权限或对象已不可读：停止读取，不无限重连，也不伪造 Run 状态。
      item.disposed = true;
      close(item, 'closed');
      throw Object.assign(new Error('此执行当前不可读取，请回原业务页面核对。'),
        { fatal: true, status: response.status });
    }
    if (response.status === 409) {
      // 先读回 RunView 与 session 核对共同 schema 所指原因，不自造 cursor 错误分类。
      throw Object.assign(new Error('执行状态已变化，正在重新读取。'), { conflict: true, status: 409 });
    }
    throw Object.assign(new Error('暂时无法读取执行状态。'), { status: response.status, retry: true });
  }

  async function request(path, options) {
    if (typeof businessAssistantRequest !== 'function') throw new Error('缺少原请求守卫，无法读取执行状态。');
    return businessAssistantRequest(path, options || {});
  }

  async function readSession(item) {
    var sessionId = item.view && item.view.session_id;
    if (!sessionId) return null;
    try {
      var session = await request('/sessions/' + encodeURIComponent(String(sessionId)));
      if (!alive(item) || !session || !Array.isArray(session.messages) || !Array.isArray(session.proposals)) {
        return null;
      }
      item.session = session;
      notify(item, { type: 'view', view: item.view, session: session });
      return session;
    } catch (error) {
      // 终态读回失败只影响这次展示：不改写 Run 状态，也不重发任何业务请求。
      item.lastError = String((error && error.message) || error);
      return null;
    }
  }

  async function getRun(runId) {
    var item = record(runId);
    var view = await request('/runs/' + encodeURIComponent(item.id));
    if (!alive(item)) return view;
    return applyView(item, view, null);
  }

  async function submitRun(sessionId, body) {
    if (!sessionId) throw new Error('请先建立会话。');
    var view = await request('/sessions/' + encodeURIComponent(String(sessionId)) + '/runs',
      { method: 'POST', body: body || {} });
    var item = record(view && view.id);
    if (String((view && view.session_id) || '') !== String(sessionId)) {
      throw new Error('执行状态与会话不一致。');
    }
    return applyView(item, view, null);
  }

  async function cancelRun(runId, expectedVersion) {
    var item = record(runId);
    var version = Number.isSafeInteger(expectedVersion) ? expectedVersion
      : (item.view && Number.isSafeInteger(item.view.version) ? item.view.version : null);
    if (!Number.isSafeInteger(version)) throw new Error('缺少执行版本，请先刷新执行状态。');
    var view = await request('/runs/' + encodeURIComponent(item.id) + '/cancel',
      { method: 'POST', body: { expected_version: version } });
    if (!alive(item)) return view;
    return applyView(item, view, null);
  }

  function parseFrames(pending, onLine) {
    var offset = 0;
    while (offset < pending.length) {
      var index = pending.slice(offset).search(/[\r\n]/);
      if (index < 0) break;
      var end = offset + index;
      var skip = pending[end] === '\r' && pending[end + 1] === '\n' ? 2 : 1;
      onLine(pending.slice(offset, end));
      offset = end + skip;
    }
    return { rest: pending.slice(offset) };
  }

  async function readStream(item, response) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder('utf-8', { fatal: true });
    var pending = '';
    var fields = { event: '', data: [], size: 0 };
    var gap = false;
    var finished = false;
    setConnection(item, 'open');
    item.attempt = 0;

    function dispatch() {
      if (!fields.data.length) { fields = { event: '', data: [], size: 0 }; return; }
      var raw = fields.data.join('\n');
      var current = fields;
      fields = { event: '', data: [], size: 0 };
      var value;
      try { value = JSON.parse(raw); } catch (error) {
        throw new Error('执行事件格式不完整，正在重新读取。');
      }
      if (!alive(item)) return;   // 门店/账号/会话已切换：迟到事件不应用、不改本地序号
      var seq = Number.isSafeInteger(value && value.seq) ? value.seq : null;
      if (seq === null) throw new Error('执行事件缺少序号，正在重新读取。');
      if (seq <= item.lastAppliedSeq) return;                    // 重复/乱序事件忽略
      if (seq !== item.lastAppliedSeq + 1) { gap = true; return; } // 缺口：关闭后按 after_seq 补读
      item.lastAppliedSeq = seq;
      if (String(value.run_id) !== item.id) throw new Error('执行事件与订阅不一致。');
      var type = String(value.type || '');
      if (KNOWN_EVENTS.indexOf(type) < 0) {
        item.unsupported = type || 'unknown';
        notify(item, { type: 'unsupported', type_name: item.unsupported });
        gap = true;
        return;
      }
      if (type === 'run.progress') {
        var display = (value.payload || {}).display || {};
        if (Number.isSafeInteger(display.revision) && display.revision > item.displayRevision) {
          item.displayRevision = display.revision;
        }
      }
      notify(item, { type: 'event', event: value });
      if (type === 'run.completed' || type === 'run.failed' || type === 'run.cancelled') {
        finished = true;
      }
    }

    function line(text) {
      if (!text) { dispatch(); return; }
      if (text[0] === ':') return;
      var split = text.indexOf(':');
      var field = split < 0 ? text : text.slice(0, split);
      var content = split < 0 ? '' : text.slice(split + 1);
      if (content[0] === ' ') content = content.slice(1);
      if (field === 'event') fields.event = content;
      else if (field === 'data') {
        fields.size += content.length;
        if (fields.size > EVENT_CHARS) throw new Error('执行事件过长，正在重新读取。');
        fields.data.push(content);
      }
    }

    try {
      while (!finished && !gap) {
        var chunk = await reader.read();
        if (chunk.done) {
          pending += decoder.decode();
          break;
        }
        pending += decoder.decode(chunk.value, { stream: true });
        if (pending.length > EVENT_CHARS) throw new Error('执行事件过长，正在重新读取。');
        pending = parseFrames(pending, line).rest;
        if (!alive(item)) break;
      }
      if (!gap && !finished && pending) {
        parseFrames(pending + '\n', line);
        line('');
      }
    } finally {
      try { await reader.cancel(); } catch (error) { /* 已结束 */ }
    }
    return { gap: gap, finished: finished };
  }

  async function readOnce(item) {
    if (!alive(item) || !item.subscribers.size) return;
    var controller = new AbortController();
    item.controller = controller;
    setConnection(item, item.attempt ? 'reconnecting' : 'connecting');
    var response;
    try {
      response = await fetch(API + '/runs/' + encodeURIComponent(item.id) + '/events?after_seq='
        + String(item.lastAppliedSeq), {
        method: 'GET', credentials: 'same-origin',
        headers: { 'X-App-Request': '1', 'X-Store-ID': storeId(), 'Accept': 'text/event-stream' },
        signal: controller.signal });
    } catch (error) {
      item.controller = null;
      if (!alive(item)) return;
      setConnection(item, 'reconnecting', error);
      schedule(item);
      return;
    }
    if (!response.ok) {
      item.controller = null;
      var failure;
      try { statusFailure(item, response); failure = null; } catch (error) { failure = error; }
      if (failure && failure.conflict) {
        try { await getRun(item.id); await readSession(item); } catch (error) { /* 保持已知状态 */ }
      }
      if (failure && failure.fatal) return;
      if (failure) setConnection(item, 'reconnecting', failure);
      schedule(item);
      return;
    }
    if (!response.body || typeof response.body.getReader !== 'function'
        || !(response.headers.get('content-type') || '').includes('text/event-stream')) {
      item.controller = null;
      setConnection(item, 'reconnecting', new Error('执行事件通道不可用。'));
      schedule(item);
      return;
    }
    var outcome;
    try {
      outcome = await readStream(item, response);
    } catch (error) {
      item.controller = null;
      if (!alive(item)) return;
      setConnection(item, 'reconnecting', error);
      schedule(item);
      return;
    }
    item.controller = null;
    if (!alive(item)) return;
    if (outcome.gap) { schedule(item); return; }
    // 事件流结束（或已收到终态事件）：读回 RunView 决定终态与后续订阅。
    try {
      var view = await getRun(item.id);
      if (TERMINAL.includes(view.status)) { await readSession(item); return; }
    } catch (error) {
      if (!alive(item)) return;
      setConnection(item, 'reconnecting', error);
    }
    schedule(item);
  }

  function bindVisibility() {
    if (visibilityBound || typeof document === 'undefined' || !document.addEventListener) return;
    visibilityBound = true;
    document.addEventListener('visibilitychange', function () {
      var hidden = document.visibilityState === 'hidden';
      for (var item of Array.from(records.values())) {
        var terminal = TERMINAL.indexOf(item.view && item.view.status) >= 0;
        item.paused = hidden && !terminal;
        if (item.paused) { if (item.timer) { clearTimeout(item.timer); item.timer = null; } continue; }
        if (item.subscribers.size && alive(item) && !item.controller) {
          readOnce(item).catch(function () { schedule(item); });
        }
      }
    });
  }

  function subscribeRun(runId, onEvent) {
    var item = record(runId);
    if (typeof onEvent !== 'function') throw new Error('订阅回调不正确。');
    item.subscribers.add(onEvent);
    bindVisibility();
    if (!item.controller && !item.timer) {
      readOnce(item).catch(function (error) {
        if (alive(item)) { setConnection(item, 'reconnecting', error); schedule(item); }
      });
    }
    return function unsubscribe() {
      item.subscribers.delete(onEvent);
      if (!item.subscribers.size) close(item, 'closed');
    };
  }

  function snapshot(runId) {
    if (runId != null) {
      var item = records.get(String(runId));
      if (!item) return null;
      return { id: item.id, view: item.view, session: item.session, lastAppliedSeq: item.lastAppliedSeq,
        displayRevision: item.displayRevision, connectionState: item.connectionState,
        subscribers: item.subscribers.size, contextEpoch: item.contextEpoch,
        terminalText: terminalText(item.view), lastError: item.lastError, unsupported: item.unsupported };
    }
    return { context: contextKey(), runs: Array.from(records.values()).map(function (item) {
      return { id: item.id, status: item.view ? item.view.status : null,
        lastAppliedSeq: item.lastAppliedSeq, connectionState: item.connectionState,
        subscribers: item.subscribers.size };
    }) };
  }

  function disposeContext() {
    for (var item of Array.from(records.values())) {
      item.disposed = true;
      item.subscribers.clear();
      close(item, 'closed');
    }
    records.clear();
  }

  globalThis.AssistantRuntime = { submitRun: submitRun, getRun: getRun, subscribeRun: subscribeRun,
    cancelRun: cancelRun, disposeContext: disposeContext, snapshot: snapshot };
})();
