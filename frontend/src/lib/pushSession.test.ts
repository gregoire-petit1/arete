// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { claimPushDevice } from './pushSession';

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

it('revokes the previous device channel and displayed notifications before switching', async () => {
  localStorage.setItem('arete.push.athlete', '1');
  const unsubscribe = vi.fn(async () => true);
  const close = vi.fn();
  vi.stubGlobal('navigator', {
    serviceWorker: {
      getRegistration: async () => ({
        pushManager: { getSubscription: async () => ({ unsubscribe }) },
        getNotifications: async () => [{ close }],
      }),
    },
  });
  await claimPushDevice(2);
  expect(unsubscribe).toHaveBeenCalledOnce();
  expect(close).toHaveBeenCalledOnce();
  expect(localStorage.getItem('arete.push.athlete')).toBe('2');
  await claimPushDevice(2);
  expect(unsubscribe).toHaveBeenCalledOnce();
});

it('refuses a switch when the previous channel cannot be revoked', async () => {
  localStorage.setItem('arete.push.athlete', '1');
  vi.stubGlobal('navigator', {
    serviceWorker: {
      getRegistration: async () => ({
        pushManager: { getSubscription: async () => ({ unsubscribe: async () => false }) },
      }),
    },
  });
  await expect(claimPushDevice(2)).rejects.toThrow('notifications');
  expect(localStorage.getItem('arete.push.athlete')).toBe('1');
});
