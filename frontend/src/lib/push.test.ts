import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { currentState, isSupported, subscribeDevice, unsubscribeDevice, urlBase64ToUint8Array } from './push';

const CHROME_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36';
const IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148';

function fakeSubscription(endpoint = 'https://push.example/abc') {
  return {
    endpoint,
    toJSON: () => ({ endpoint, keys: { p256dh: 'P256', auth: 'AUTH' } }),
    unsubscribe: vi.fn(async () => true),
  };
}

/** A browser with the given push capabilities; returns the spies the tests read. */
function browser({
  ua = CHROME_UA,
  standalone = false,
  push = true,
  permission = 'default' as NotificationPermission,
  grant = 'granted' as NotificationPermission,
  registered = true,
  subscription = null as ReturnType<typeof fakeSubscription> | null,
} = {}) {
  const pushManager = {
    getSubscription: vi.fn(async () => subscription),
    subscribe: vi.fn(async () => fakeSubscription()),
  };
  const reg = registered ? { pushManager } : undefined;
  vi.stubGlobal('navigator', {
    userAgent: ua,
    maxTouchPoints: 0,
    ...(push ? { serviceWorker: { getRegistration: vi.fn(async () => reg) } } : {}),
  });
  const notification = { permission, requestPermission: vi.fn(async () => grant) };
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: standalone }),
    ...(push ? { PushManager: class {}, Notification: notification } : {}),
  });
  vi.stubGlobal('Notification', notification);
  const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  return { pushManager, notification, fetchMock };
}

beforeEach(() => {
  vi.unstubAllGlobals();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('urlBase64ToUint8Array', () => {
  it('decodes URL-safe base64 without padding', () => {
    // "-_-_" is "+/+/" in standard base64.
    expect([...urlBase64ToUint8Array('-_-_')]).toEqual([0xfb, 0xff, 0xbf]);
    expect([...urlBase64ToUint8Array('AQID')]).toEqual([1, 2, 3]);
    expect([...urlBase64ToUint8Array('AQ')]).toEqual([1]);
  });

  it('gives the 65-byte uncompressed P-256 key a VAPID key encodes', () => {
    const key = 'B' + 'A'.repeat(86);
    expect(urlBase64ToUint8Array(key)).toHaveLength(65);
  });
});

describe('currentState', () => {
  it('is unsupported without PushManager', async () => {
    browser({ push: false });
    expect(isSupported()).toBe(false);
    expect(await currentState()).toBe('unsupported');
  });

  it('asks iOS users to install the app first', async () => {
    browser({ ua: IPHONE_UA, push: false });
    expect(await currentState()).toBe('ios-not-installed');
  });

  it('lets the installed iOS app subscribe', async () => {
    browser({ ua: IPHONE_UA, standalone: true });
    expect(await currentState()).toBe('unsubscribed');
  });

  it('reports a refused permission', async () => {
    browser({ permission: 'denied' });
    expect(await currentState()).toBe('denied');
  });

  it('reports a missing service worker instead of waiting for one', async () => {
    browser({ registered: false });
    expect(await currentState()).toBe('no-worker');
  });

  it('reads the existing subscription', async () => {
    browser({ subscription: fakeSubscription() });
    expect(await currentState()).toBe('subscribed');
  });
});

describe('subscribeDevice', () => {
  it('subscribes with the server key and registers the endpoint', async () => {
    const { pushManager, fetchMock } = browser();
    expect(await subscribeDevice('AQID')).toBe('subscribed');

    const options = (pushManager.subscribe.mock.calls[0] as unknown[])[0] as PushSubscriptionOptionsInit;
    expect(options.userVisibleOnly).toBe(true);
    expect([...(options.applicationServerKey as Uint8Array)]).toEqual([1, 2, 3]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/notifications/subscription');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      endpoint: 'https://push.example/abc',
      keys: { p256dh: 'P256', auth: 'AUTH' },
    });
  });

  it('stops when the permission is refused', async () => {
    const { pushManager, fetchMock } = browser({ grant: 'denied' });
    expect(await subscribeDevice('AQID')).toBe('denied');
    expect(pushManager.subscribe).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('undoes the local subscription when the server rejects it', async () => {
    const existing = fakeSubscription();
    const { fetchMock } = browser({ subscription: existing });
    fetchMock.mockResolvedValueOnce(new Response('{"detail":"boom"}', { status: 500 }));
    await expect(subscribeDevice('AQID')).rejects.toThrow('500');
    expect(existing.unsubscribe).toHaveBeenCalled();
  });
});

describe('unsubscribeDevice', () => {
  it('tells the server, then drops the local subscription', async () => {
    const existing = fakeSubscription('https://push.example/xyz');
    const { fetchMock } = browser({ subscription: existing });
    expect(await unsubscribeDevice()).toBe('unsubscribed');
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/notifications/subscription');
    expect(init.method).toBe('DELETE');
    expect(JSON.parse(init.body as string)).toEqual({ endpoint: 'https://push.example/xyz' });
    expect(existing.unsubscribe).toHaveBeenCalled();
  });

  it('is a no-op without a subscription', async () => {
    const { fetchMock } = browser();
    expect(await unsubscribeDevice()).toBe('unsubscribed');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
