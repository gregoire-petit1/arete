import assert from 'node:assert/strict';
import { setTimeout as sleep } from 'node:timers/promises';

const ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions';
const RETRY_STATUSES = new Set([408, 429, 500, 502, 503, 504]);
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
const MAX_RESPONSE_CHUNKS = 8192;

export const LIMITS = Object.freeze({
  intervalMs: 6000,
  attempts: 4,
  requestTimeoutMs: 120000,
  runTimeoutMs: 23 * 60 * 1000,
  requests: 120,
  pending: 4,
  maxWaitMs: 180000,
  backoffMs: 30000,
  jitterMs: 5000,
});

// Buffer only this non-streaming endpoint so body disconnects/timeouts stay
// inside the retry boundary, before OpenWiki can execute any returned tools.
async function readBody(response) {
  if (!response.body) return '';
  const reader = response.body.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    for (let i = 0; i < MAX_RESPONSE_CHUNKS; i += 1) {
      const { done, value } = await reader.read();
      if (done) return Buffer.concat(chunks, bytes).toString('utf8');
      bytes += value.byteLength;
      assert(bytes <= MAX_RESPONSE_BYTES, 'OpenWiki response exceeds 2 MiB');
      chunks.push(value);
    }
    assert.fail('OpenWiki response exceeds chunk limit');
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}

export function retryDelay(headers, now) {
  const hints = [];
  const after = headers.get('retry-after');
  if (after !== null && after.trim() !== '') {
    const seconds = Number(after);
    hints.push(Number.isFinite(seconds) && seconds >= 0
      ? seconds * 1000 : Date.parse(after) - now);
  }
  const reset = headers.get('x-ratelimit-reset');
  if (reset !== null && reset.trim() !== '') {
    const epoch = Number(reset);
    hints.push(Number.isFinite(epoch)
      ? epoch * (epoch < 1e12 ? 1000 : 1) - now : Date.parse(reset) - now);
  }
  return Math.max(0, ...hints.filter(Number.isFinite));
}

function transientProvider404(status, body) {
  if (status !== 404) return false;
  let error;
  try {
    error = JSON.parse(body)?.error;
  } catch (cause) {
    if (!(cause instanceof SyntaxError)) throw cause;
    return false; // An unstructured 404 is a permanent endpoint error.
  }
  // Preserve the pinned OpenWiki client's narrow provider-404 workaround;
  // unknown models and genuinely missing endpoints remain terminal.
  return error?.message === 'Provider returned error' &&
    error.metadata?.raw === '' && typeof error.metadata?.provider_name === 'string';
}

export function createTransport({
  fetch: baseFetch,
  limits = LIMITS,
  now = Date.now,
  wait = (ms, signal) => sleep(ms, undefined, { signal }),
  random = Math.random,
  log = console.error,
}) {
  for (const name of Object.keys(LIMITS)) {
    const value = limits[name];
    assert(Number.isSafeInteger(value) && value > 0, `Invalid limit: ${name}`);
  }
  let tail = Promise.resolve();
  let pending = 0;
  let requests = 0;
  let nextStart = 0;
  let deadline;
  let stopped;

  function stop(message, cause) {
    // AbortError tells the SDK to stop too; its retries must not multiply ours.
    stopped ??= Object.assign(new Error(`OpenWiki transport: ${message}`, { cause }), {
      name: 'AbortError',
    });
    return stopped;
  }

  return async function fetchOpenRouter(input, init) {
    const url = input instanceof Request ? input.url : String(input);
    if (url !== ENDPOINT) return baseFetch(input, init);
    if (stopped) throw stopped;
    assert.equal(init?.method, 'POST');
    assert.equal(typeof init.body, 'string', 'Retries require a reusable JSON body');
    const payload = JSON.parse(init.body);
    assert.equal(payload.model, 'openrouter/free', 'Only free routing is authorized');
    assert.equal(payload.stream, false, 'Only non-streaming inference is supported');
    if (pending >= limits.pending) throw stop('concurrency queue limit reached');
    pending += 1;
    const previous = tail;
    let release;
    tail = new Promise((resolve) => { release = resolve; });
    const signal = init.signal ?? (input instanceof Request ? input.signal : undefined);
    deadline ??= now() + limits.runTimeoutMs;
    try {
      await previous;
      for (let attempt = 0; attempt < limits.attempts; attempt += 1) {
        if (stopped) throw stopped;
        signal?.throwIfAborted();
        if (requests >= limits.requests) throw stop('total HTTP request budget exhausted');
        const delay = Math.max(0, nextStart - now());
        if (delay > limits.maxWaitMs || now() + delay >= deadline) {
          throw stop('provider cooldown exceeds the remaining run budget');
        }
        if (delay > 0) await wait(delay, signal);
        signal?.throwIfAborted();
        const remaining = deadline - now();
        if (remaining <= 0) throw stop('run deadline exceeded');
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), Math.min(limits.requestTimeoutMs, remaining));
        const requestSignal = signal
          ? AbortSignal.any([signal, controller.signal]) : controller.signal;
        let response;
        let body;
        let networkError;
        requests += 1;
        nextStart = now() + limits.intervalMs;
        try {
          response = await baseFetch(input, { ...init, signal: requestSignal });
          body = await readBody(response);
        } catch (error) {
          signal?.throwIfAborted();
          // Programmer/contract errors are not transient network failures.
          if (error?.code === 'ERR_ASSERTION') throw error;
          if (!(error instanceof TypeError) && error?.name !== 'AbortError' && error?.name !== 'TimeoutError') {
            throw error;
          }
          networkError = error;
        } finally {
          clearTimeout(timer);
        }
        log(`OpenWiki HTTP ${requests}/${limits.requests}: attempt ${attempt + 1}/${limits.attempts}, ${networkError ? 'network failure' : response.status}`);
        if (now() >= deadline) throw stop('run deadline exceeded');
        if (!networkError && response.ok) {
          return new Response(body, { status: response.status, headers: response.headers });
        }
        const dailyQuota = response?.status === 429 &&
          /free-models-per-day|daily[^\n]{0,80}(?:limit|quota)|insufficient_quota|quota[^\n]{0,40}exhausted/i.test(body ?? '');
        if (dailyQuota) throw stop('daily free-model quota exhausted; wait for its reset');
        if (!networkError && !RETRY_STATUSES.has(response.status) &&
            !transientProvider404(response.status, body)) {
          throw stop(`non-retryable HTTP ${response.status}; check credentials, quota or request configuration`);
        }
        if (attempt + 1 === limits.attempts) {
          throw stop(`transient failure persisted after ${limits.attempts} attempts (${networkError ? 'network' : response.status})`, networkError);
        }
        const backoff = Math.max(response?.status === 429 ? 60000 : 0,
          limits.backoffMs * 2 ** attempt) + Math.floor(random() * limits.jitterMs);
        const cooldown = Math.max(backoff, response ? retryDelay(response.headers, now()) : 0);
        nextStart = Math.max(nextStart, now() + cooldown);
      }
      assert.fail('Retry loop must return or throw');
    } catch (error) {
      throw stop(error.message, error);
    } finally {
      pending -= 1;
      release();
    }
  };
}
