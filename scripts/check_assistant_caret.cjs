'use strict';
// 开发用确定性回归：卡片必填项在输入过程中不能被整栏重建，重画也必须把光标放回原位。
// 运行：node --test scripts/check_assistant_caret.cjs
// 不联网、不连数据库、不调用模型；只加载 web/businessassistant.js 在 vm 里跑。
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.resolve(__dirname, '..');

function fakeField(key, value = '') {
    const field = {
        dataset: { baqKey: key }, value, focused: false, selection: null,
        focus() { this.focused = true; }, setSelectionRange(start, end) { this.selection = [start, end]; },
    };
    field.selectionStart = value.length; field.selectionEnd = value.length;
    return field;
}

function env() {
    const listeners = {};
    const state = { route: 'business-assistant', user: { id: 1, role: 'sales', display_name: '合成员工' }, store: '1', stores: [{ id: 1, name: '合成门店' }] };
    const calls = { cards: 0, page: 0 };
    const context = {
        console, AbortController, URLSearchParams, TextDecoder, TextEncoder, setTimeout, clearTimeout, Date, JSON, Promise,
        state, storeContextVersion: 0, toast: () => {}, money: v => (v / 100).toFixed(2), number: v => String(v),
        roleNames: { sales: '销售' }, b: () => '', pill: () => '', empty: () => '', heading: () => '', time: () => '',
        E: v => String(v ?? '').replace(/[&<>"']/g, x => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[x])),
        document: { addEventListener: (name, fn) => { (listeners[name] = listeners[name] || []).push(fn); }, querySelector: () => null, activeElement: null },
        $: selector => (context.elements && context.elements[selector]) || null,
        elements: {},
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(root, 'web/businessassistant.js'), 'utf8'), context);
    const run = code => vm.runInContext(code, context);
    run(`businessAssistantState.context=businessAssistantContext();businessAssistantState.status={ready:true};
         paintBusinessAssistantCards=((original)=>function(){calls.cards++;return original.apply(null,arguments);})(paintBusinessAssistantCards);
         paintBusinessAssistant=((original)=>function(){calls.page++;return original.apply(null,arguments);})(paintBusinessAssistant);`);
    context.calls = calls;
    return { c: context, run, state, calls, listeners, elements: (selector, node) => { context.elements[selector] = node; return node; } };
}

const card = {
    id: 'card-1', turn: 'turn-a', step: '1 订车', step_order: 1, status: 'pending', digest: 'a'.repeat(64),
    label: '新建订单', summary: '合成订单', expires_at: '2099-01-01T00:00:00Z',
    questions: [{ key: 'amount_cents', label: '订单金额', input_type: 'integer', required: true },
                { key: 'values.note', label: '备注', required: false }],
};

test('输入过程中不重建卡片栏：只记值、只更新按钮状态', () => {
    const e = env();
    e.run(`businessAssistantState.session={id:1,proposals:[${JSON.stringify(card)}],messages:[]};`);
    const target = fakeField('amount_cents', '150000');
    const host = { dataset: { baQuestions: 'card-1' }, querySelector: () => null };
    target.closest = selector => (selector === '[data-ba-questions]' ? host : null);
    e.c.document.activeElement = target;
    e.run('businessAssistantQuestionInput')(target, false);
    assert.equal(e.run('businessAssistantState.answers["card-1"].amount_cents'), '150000');
    assert.equal(e.calls.cards, 0, '打字不能整栏重画（重画会把输入框换掉、光标飞出）');
    assert.equal(e.calls.page, 0, '打字也不能重画整页');
});

test('整栏重画后，光标与已输入内容回到原来那一项', () => {
    const e = env();
    e.run(`businessAssistantState.session={id:1,proposals:[${JSON.stringify(card)}],messages:[]};businessAssistantState.answers={"card-1":{amount_cents:"1500"}};`);
    const target = fakeField('amount_cents', '1500');
    target.selectionStart = 4; target.selectionEnd = 4;
    e.c.document.activeElement = target;
    const restored = fakeField('amount_cents', '1500');
    const host = {
        innerHTML: '', dataset: {}, contains: node => node === target,
        querySelector: selector => (String(selector).includes('data-baq-key') ? restored : null),
        querySelectorAll: () => [],
    };
    e.elements('#business-assistant-cards', host);
    assert.equal(e.run('paintBusinessAssistantCards()'), true);
    assert.equal(restored.focused, true, '重画后必须把焦点放回那个输入框');
    assert.deepEqual(restored.selection, [4, 4], '光标位置也要保持');
});

test('整页重画（一轮结束/批量结果）同样把光标放回卡片输入框', () => {
    const e = env();
    e.run(`businessAssistantState.session={id:1,proposals:[${JSON.stringify(card)}],messages:[]};`);
    const target = fakeField('amount_cents', '2500');
    target.selectionStart = 4; target.selectionEnd = 4;
    e.c.document.activeElement = target;
    const restored = fakeField('amount_cents', '2500');
    const main = {
        innerHTML: '', contains: node => node === target,
        querySelector: selector => (String(selector).includes('data-baq-key') ? restored : null),
    };
    e.elements('#main', main);
    e.run('businessAssistantHTML=()=>"<div></div>"');
    e.run('paintBusinessAssistant()');
    assert.equal(restored.focused, true);
    assert.deepEqual(restored.selection, [4, 4]);
});

test('切到别的卡片或换筛选时才允许整栏重画', () => {
    const e = env();
    e.run(`businessAssistantState.session={id:1,proposals:[${JSON.stringify(card)}],messages:[]};`);
    const listener = (e.listeners.change || []).find(fn => String(fn).includes('ba-queue-select'));
    const handler = listener || (e.listeners.change || [])[0];
    assert.ok(handler, '队列选择器的 change 处理器应已注册');
    e.elements('#business-assistant-cards', { innerHTML: '', dataset: {}, contains: () => false, querySelector: () => null, querySelectorAll: () => [] });
    handler({ target: { id: 'ba-queue-select', value: 'card-1' } });
    assert.equal(e.calls.cards, 1, '换卡片是显式操作，可以重画');
});
