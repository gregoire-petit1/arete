// @vitest-environment jsdom
import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MessageFeedback } from './MessageFeedback';
import { readFeedback, writeFeedback, type MessageFeedback as Feedback } from '@/lib/agentFeedback';

vi.mock('@/lib/agentFeedback', async original => ({
  ...await original<typeof import('@/lib/agentFeedback')>(),
  writeFeedback: vi.fn(), readFeedback: vi.fn(),
}));
const trace = { trace_id: '12345678-1234-4123-8123-123456789012', feedback_token: 'a'.repeat(64) };
function Harness() {
  const [feedback, setFeedback] = useState<Feedback>();
  return <MessageFeedback trace={trace} threadId="thread-a" feedback={feedback} onChange={setFeedback} />;
}
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('waits for acknowledgement, prevents double clicks, toggles and changes votes', async () => {
  let resolve!: () => void;
  vi.mocked(writeFeedback).mockReturnValueOnce(new Promise<void>(r => { resolve = r; }));
  render(<Harness />);
  const up = screen.getByRole('button', { name: 'Réponse utile' });
  fireEvent.click(up);
  fireEvent.click(up);
  expect(writeFeedback).toHaveBeenCalledTimes(1);
  expect(up.getAttribute('aria-pressed')).toBe('false');
  expect(screen.getByRole('status').textContent).toBe('Envoi…');
  await act(async () => resolve());
  expect(up.getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('status').textContent).toBe('Enregistré');
  fireEvent.click(screen.getByRole('button', { name: 'Réponse peu utile' }));
  await waitFor(() => expect(writeFeedback).toHaveBeenLastCalledWith(trace, 'thread-a', 'user_score', 0));
  fireEvent.click(screen.getByRole('button', { name: 'Réponse peu utile' }));
  await waitFor(() => expect(writeFeedback).toHaveBeenLastCalledWith(trace, 'thread-a', 'user_score', null));
});

it('supports arbitrary composed emojis and keeps votes independent from reactions', async () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Choisir une réaction' }));
  const input = screen.getByRole('textbox', { name: 'Ou colle ton emoji' });
  fireEvent.change(input, { target: { value: 'bad' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ajouter la réaction' }));
  expect(screen.getByRole('alert').textContent).toBe('Choisis un seul emoji.');
  expect(writeFeedback).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '👩🏽‍💻' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ajouter la réaction' }));
  await screen.findByRole('button', { name: 'Retirer la réaction 👩🏽‍💻' });
  expect(writeFeedback).toHaveBeenLastCalledWith(trace, 'thread-a', 'reaction', '👩🏽‍💻');
  expect(screen.getByRole('button', { name: 'Réponse utile' }).getAttribute('aria-pressed')).toBe('false');
});

it('requires an explicit read to resolve an ambiguous write without replaying it', async () => {
  vi.mocked(writeFeedback).mockRejectedValueOnce(new Error('network lost'));
  vi.mocked(readFeedback).mockResolvedValueOnce({ user_score: 1, reaction: '🎯' });
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Réponse utile' }));
  await screen.findByRole('alert');
  expect((screen.getByRole('button', { name: 'Réponse peu utile' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Vérifier le retour enregistré' }));
  await screen.findByRole('button', { name: 'Retirer la réaction 🎯' });
  expect(screen.getByRole('button', { name: 'Réponse utile' }).getAttribute('aria-pressed')).toBe('true');
  expect(writeFeedback).toHaveBeenCalledOnce();
  expect(readFeedback).toHaveBeenCalledWith(trace, 'thread-a');
});
