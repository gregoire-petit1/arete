import { describe, expect, it } from 'vitest';
import { applyEvent, consumeStream, type ChatMessage } from './agentStream';
import { restoreConversation } from './agentConversation';
import { isWorkoutUpdate, mergeWorkout, type WorkoutUpdate } from './workouts';

const update: WorkoutUpdate = {
  type: 'workout_update', id: 'call', thread_id: 'thread', sequence: 100,
  session: { id: 4, revision: 1, date: '2027-01-12', sport: 'running', description: 'Fractionné', status: 'pending', summary: '6 × 400 m' },
  export: { session_id: 4, operation_id: 'op', updated_at: '2027-01-10T12:00:00', state: 'working', phase: 'creating', error: null, deleted: false, workout_id: null, schedule_id: null },
};
describe('workout event contract', () => {
  it('preserves cards through browser storage and rejects stale events', () => {
    const message: ChatMessage = { role: 'assistant', content: '', pending: true };
    const next = applyEvent(message, update);
    expect(next.workouts).toHaveLength(1);
    expect(applyEvent(next, { ...update, sequence: 99, session: { ...update.session, description: 'Old' } })).toEqual(next);
    const restored = restoreConversation(JSON.stringify([next]));
    expect(restored[0].workouts).toEqual([update]);
    expect(restored[0].pending).toBe(false);
    expect(restored[0].interrupted).toBe(true);
  });
  it('does not let a stale query overwrite a newer revision or operation', () => {
    const latest = { ...update, session: { ...update.session, revision: 2 }, export: { ...update.export!, state: 'scheduled', updated_at: '2027-01-10T12:01:00' } };
    expect(mergeWorkout(latest, update)).toEqual(latest);
    expect(mergeWorkout(latest, { ...update, session: latest.session }).export?.state).toBe('scheduled');
  });
  it('rejects corrupt events and saved cards explicitly', () => {
    expect(isWorkoutUpdate({ ...update, session: { ...update.session, id: -1 } })).toBe(false);
    expect(isWorkoutUpdate({ ...update, export: { ...update.export, session_id: 9 } })).toBe(false);
    expect(() => restoreConversation(JSON.stringify([{ role: 'assistant', content: '', workouts: [{}] }]))).toThrow('Séances sauvegardées invalides');
  });
  it('delivers a card from fragmented SSE before the final response exists', async () => {
    const encoder = new TextEncoder();
    const seen: string[] = [];
    let finish!: () => void;
    const barrier = new Promise<void>(resolve => { finish = resolve; });
    const body = new ReadableStream<Uint8Array>({ async start(controller) {
      const event = `data: ${JSON.stringify(update)}\n\n`;
      controller.enqueue(encoder.encode(event.slice(0, 17)));
      controller.enqueue(encoder.encode(event.slice(17)));
      await barrier;
      controller.enqueue(encoder.encode('data: {"type":"done","message":{"role":"assistant","content":"Programmé"}}\n\n'));
    } });
    const consuming = consumeStream(body, event => { seen.push(event.type); if (event.type === 'workout_update') { expect(seen).toEqual(['workout_update']); finish(); } });
    await consuming;
    expect(seen).toEqual(['workout_update', 'done']);
  });
});
