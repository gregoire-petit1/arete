import { afterEach, describe, expect, it, vi } from 'vitest';
import { goalsApi, planApi } from './api';

function answer(body: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
}

afterEach(() => vi.unstubAllGlobals());

describe('record endpoints', () => {
  it('pass a record through', async () => {
    answer({ id: 3, name: 'Semi' });
    expect(await goalsApi.next()).toEqual({ id: 3, name: 'Semi' });
  });

  it('read null, an empty list or an object without id as "none"', async () => {
    for (const body of [null, [], {}, { id: '3' }]) {
      answer(body);
      expect(await goalsApi.next()).toBeNull();
      answer(body);
      expect(await planApi.getReview()).toBeNull();
    }
  });

  it('drop a projection without its series', async () => {
    answer({ goal: {}, series: [] });
    expect(await goalsApi.getProjection(1)).not.toBeNull();
    answer([]);
    expect(await goalsApi.getProjection(1)).toBeNull();
  });
});
