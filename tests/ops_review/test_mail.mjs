// Run only from the Temp source mirror created by run_isolated.py. This imports
// exports, never the CLI main or its configuration/SMTP credential readers.
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, realpathSync } from 'node:fs';
import { Socket } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { after, test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const sourceRoot = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), '../..'));
const tempRoot = realpathSync(tmpdir());
const inside = (parent, child) => {
  const path = relative(parent, child);
  return path !== '' && !isAbsolute(path) && path !== '..' && !path.startsWith(`..${sep}`);
};
const runtimeInput = process.env.OPS_REVIEW_RUNTIME;
assert.ok(runtimeInput && isAbsolute(runtimeInput), 'OPS_REVIEW_RUNTIME must be an absolute synthetic runtime directory');
assert.ok(inside(tempRoot, sourceRoot), 'Mail checks must run from an external Temp source mirror');
assert.ok(inside(tempRoot, resolve(runtimeInput)), 'Mail runtime must stay under Temp');
mkdirSync(runtimeInput, { recursive: true });
const runtimeRoot = realpathSync(runtimeInput);
assert.ok(inside(tempRoot, runtimeRoot), 'Mail runtime must resolve under Temp');
assert.ok(runtimeRoot !== sourceRoot && !inside(sourceRoot, runtimeRoot), 'Mail runtime must be separate from the source mirror');

// The source import and fake senders cannot silently reach an SMTP provider.
// undici/fetch also opens sockets through this entry point.
const originalConnect = Socket.prototype.connect;
let blockedExternalConnections = 0;
Socket.prototype.connect = function (...args) {
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const options = first && typeof first === 'object' ? first : { port: first, host: typeof args[1] === 'string' ? args[1] : 'localhost' };
  const host = options.host ?? 'localhost';
  if (options.path || !['127.0.0.1', 'localhost', '::1'].includes(host)) {
    blockedExternalConnections += 1;
    throw new Error('Isolated mail checks prohibit non-loopback connections');
  }
  return Reflect.apply(originalConnect, this, args);
};
after(() => {
  assert.equal(blockedExternalConnections, 1, 'Only the deliberate network-denial probe may attempt an external connection');
  Socket.prototype.connect = originalConnect;
});

const { ReviewDelivery, ReviewOutbox, createMailServer } = await import(
  pathToFileURL(join(sourceRoot, 'scripts', 'huakangos_ops_mail.mjs')).href
);
const providerId = `qq-smtp-250-sha256:${'a'.repeat(64)}`;
const databasePath = () => join(mkdtempSync(join(runtimeRoot, 'mail-')), 'synthetic-outbox.sqlite');
const review = (number) => {
  const jobId = `10000000-0000-4000-8000-${String(number).padStart(12, '0')}`;
  return {
    event_id: `huakangos-ops:${jobId}`,
    job_id: jobId,
    title: 'Synthetic isolated review',
    release_id: 'b'.repeat(64),
    base_sha: 'c'.repeat(40),
    report: {
      summary: 'Synthetic candidate, requiring independent review.',
      evidence: [{ path: 'app/ops_worker.py', line: 1, sha256: 'd'.repeat(64) }],
      proposed_changes: ['Independently verify this synthetic candidate.'],
      acceptance_checks: ['Exercise the fake sender only.'],
      risk: 'Synthetic data only.',
      classification: 'review_candidate',
    },
  };
};
const reversedKeys = (value) => Array.isArray(value) ? value.map(reversedKeys)
  : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).reverse().map((key) => [key, reversedKeys(value[key])]))
    : value;

test('outbox canonical deduplication, conflict and concurrent send once', async () => {
  const outbox = new ReviewOutbox(databasePath());
  let sends = 0;
  let accept;
  const gate = new Promise((resolveGate) => { accept = resolveGate; });
  const delivery = new ReviewDelivery(outbox, {
    async send(envelope) {
      sends += 1;
      assert.equal(envelope.recipient, 'xintperfect@gmail.com');
      await gate;
      return { provider_id: providerId };
    },
  });
  const input = review(1);
  try {
    const pending = Array.from({ length: 8 }, (_, index) => delivery.enqueue(index % 2 ? reversedKeys(input) : input));
    assert.equal(sends, 1);
    const active = outbox.get(input.event_id, true);
    assert.equal(active.status, 'uncertain');
    assert.equal(active.delivery_in_progress, true);
    accept();
    for (const result of await Promise.all(pending)) {
      assert.equal(result.status, 'sent');
      assert.equal(result.provider_message_id, providerId);
    }
    assert.equal((await delivery.enqueue(reversedKeys(input))).status, 'sent');
    assert.equal(sends, 1);
    assert.equal(outbox.list().reviews.length, 1);
    const conflicting = structuredClone(input);
    conflicting.report.summary = 'Different synthetic content under the same event ID.';
    assert.throws(() => outbox.enqueue(conflicting), (error) => error.code === 'event_payload_conflict' && error.status === 409);
    assert.deepEqual(outbox.get(input.event_id, true).review, input);
    assert.equal(sends, 1);
  } finally {
    accept();
    await delivery.close();
    outbox.close();
  }
});

test('failed/uncertain deliveries never retry and sending recovers after restart', async () => {
  const path = databasePath();
  let outbox = new ReviewOutbox(path);
  let sends = 0;
  let delivery = new ReviewDelivery(outbox, {
    async send(envelope) {
      sends += 1;
      if (envelope.event_id === review(2).event_id) {
        throw Object.assign(new Error('synthetic refusal'), { outcome: 'not_sent', code: 'synthetic_refusal' });
      }
      if (envelope.event_id === review(3).event_id) throw new Error('synthetic unknown result');
      return {}; // A response without verifiable provider acceptance is uncertain.
    },
  });
  const outcomes = [[2, 'failed', 'synthetic_refusal'], [3, 'uncertain', 'smtp_outcome_unknown'], [4, 'uncertain', 'smtp_acceptance_unknown']];
  try {
    for (const [number, status, errorCode] of outcomes) {
      const result = await delivery.enqueue(review(number));
      assert.equal(result.status, status);
      assert.equal(result.error_code, errorCode);
      assert.equal((await delivery.enqueue(review(number))).status, status);
    }
    assert.equal(sends, 3);
    outbox.enqueue(review(5));
    assert.equal(outbox.claim(review(5).event_id).delivery_in_progress, true);
    outbox.enqueue(review(6)); // Held rows are not scanned/sent on startup.
    await delivery.close();
    outbox.close();
    outbox = new ReviewOutbox(path);
    let restartedSends = 0;
    delivery = new ReviewDelivery(outbox, {
      async send() { restartedSends += 1; return { provider_id: providerId }; },
    });
    const recovered = outbox.get(review(5).event_id, true);
    assert.equal(recovered.status, 'uncertain');
    assert.equal(recovered.error_code, 'interrupted_delivery');
    assert.equal(recovered.delivery_in_progress, undefined);
    assert.equal(outbox.get(review(6).event_id).status, 'held');
    for (const [number, status] of outcomes) assert.equal((await delivery.enqueue(review(number))).status, status);
    assert.equal((await delivery.enqueue(review(5))).status, 'uncertain');
    assert.equal(restartedSends, 0);
    assert.equal(outbox.list({ status: 'uncertain' }).reviews.length, 3);
  } finally {
    await delivery.close();
    outbox.close();
  }
});

test('loopback HTTP MCP enforces authentication, bounded tools and fixed recipient', async () => {
  const outbox = new ReviewOutbox(databasePath());
  const envelopes = [];
  const delivery = new ReviewDelivery(outbox, {
    async send(envelope) { envelopes.push(envelope); return { provider_id: providerId }; },
  });
  const token = 'synthetic-mail-test-token-0000000000000000';
  const app = createMailServer({ token, port: 0 }, delivery);
  let requestId = 0;
  try {
    const deniedSocket = new Socket();
    assert.throws(() => deniedSocket.connect({ host: 'synthetic.invalid', port: 465 }), /prohibit non-loopback/);
    deniedSocket.destroy();
    const address = await app.start();
    assert.equal(address.address, '127.0.0.1');
    const url = `http://127.0.0.1:${address.port}/mcp`;
    const request = async (message, headers = {}) => {
      const response = await fetch(url, {
        method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
        headers: {
          authorization: `Bearer ${token}`,
          accept: 'application/json, text/event-stream',
          'content-type': 'application/json',
          'mcp-protocol-version': '2025-11-25',
          ...headers,
        },
        body: JSON.stringify(message),
      });
      return { status: response.status, body: await response.json() };
    };
    const rpc = (method, params = {}, headers) => request({ jsonrpc: '2.0', id: ++requestId, method, params }, headers);
    const call = (name, args) => rpc('tools/call', { name, arguments: args });
    const toolError = async (name, args, code) => {
      const result = await call(name, args);
      assert.equal(result.status, 200); // MCP tool errors are in the RPC result.
      assert.equal(result.body.result.isError, true);
      assert.equal(result.body.result.structuredContent.error_code, code);
    };

    const noToken = await rpc('ping', {}, { authorization: '' });
    assert.equal(noToken.status, 401);
    assert.equal(noToken.body.error_code, 'unauthorized');
    assert.equal((await rpc('ping', {}, { authorization: 'Bearer synthetic-wrong-token' })).status, 401);
    assert.equal((await rpc('ping', {}, { origin: 'https://synthetic.invalid' })).status, 403);
    assert.equal((await rpc('ping', {}, { accept: 'application/json' })).status, 406);
    assert.equal((await rpc('ping', {}, { 'content-type': 'text/plain' })).status, 415);
    assert.equal((await rpc('ping', {}, { 'mcp-protocol-version': 'synthetic-unsupported' })).status, 400);
    const initialized = await rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'synthetic-review', version: '1' } });
    assert.equal(initialized.body.result.protocolVersion, '2025-11-25');
    const tools = await rpc('tools/list');
    assert.deepEqual(tools.body.result.tools.map((item) => item.name), ['enqueue_change_review', 'get_change_review', 'list_change_reviews']);
    for (const tool of tools.body.result.tools) assert.equal(tool.inputSchema.additionalProperties, false);
    await toolError('send_email', { to: 'nobody@synthetic.invalid' }, 'unknown_tool');
    const input = review(7);
    for (const field of ['recipient', 'subject', 'text', 'command']) {
      await toolError('enqueue_change_review', { ...input, [field]: 'synthetic caller override' }, 'invalid_fields');
    }
    await toolError('get_change_review', { event_id: input.event_id, command: 'synthetic forbidden' }, 'invalid_fields');
    const outsideEvidence = structuredClone(input);
    outsideEvidence.report.evidence[0].path = '../outside';
    await toolError('enqueue_change_review', outsideEvidence, 'invalid_evidence');
    const headerInjection = { ...input, title: 'Synthetic\r\nBcc: nobody@synthetic.invalid' };
    await toolError('enqueue_change_review', headerInjection, 'invalid_text');
    assert.equal(envelopes.length, 0);
    assert.equal((await call('get_change_review', { event_id: input.event_id })).body.result.structuredContent.status, 'not_found');

    const sent = await call('enqueue_change_review', input);
    assert.equal(sent.body.result.isError, false);
    assert.equal(sent.body.result.structuredContent.status, 'sent');
    assert.equal(envelopes.length, 1);
    const envelope = envelopes[0];
    assert.equal(envelope.recipient, 'xintperfect@gmail.com');
    assert.match(envelope.subject, /^\[Codex-Cutie\] /);
    for (const field of ['event_id', 'job_id', 'release_id', 'base_sha']) assert.ok(envelope.text.includes(`${field}: ${input[field]}`));
    assert.match(envelope.message_id, /^<[0-9a-f]{64}@codex-cutie\.local>$/);
    assert.equal((await call('enqueue_change_review', reversedKeys(input))).body.result.structuredContent.status, 'sent');
    const conflict = { ...input, title: 'Changed synthetic review title' };
    await toolError('enqueue_change_review', conflict, 'event_payload_conflict');
    const stored = (await call('get_change_review', { event_id: input.event_id })).body.result.structuredContent;
    assert.deepEqual(stored.review, input);
    assert.match(stored.payload_sha256, /^[0-9a-f]{64}$/);
    const listed = (await call('list_change_reviews', { status: 'sent', limit: 1 })).body.result.structuredContent.reviews;
    assert.equal(listed.length, 1);
    assert.equal(listed[0].event_id, input.event_id);
    assert.equal(listed[0].review, undefined);
    assert.equal(envelopes.length, 1);
  } finally {
    await app.close();
    outbox.close();
  }
});
