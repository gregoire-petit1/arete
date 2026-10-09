// @vitest-environment jsdom
import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { StreamEvent } from '@/lib/agentStream';
import { AgentSidePanel } from './AgentSidePanel';
import { Navigation } from './Navigation';

const stream = vi.hoisted(() => ({
  emit: null as ((event: StreamEvent) => void) | null,
  resolve: null as (() => void) | null,
  signal: null as AbortSignal | null,
}));
vi.mock('@/lib/agentStream', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/agentStream')>()),
  runAgentStream: vi.fn(
    (_history, _context, emit, signal) =>
      new Promise<void>((resolve, reject) => {
        stream.emit = emit;
        stream.resolve = resolve;
        stream.signal = signal;
        signal.addEventListener(
          'abort',
          () => reject(new DOMException('Stopped', 'AbortError')),
          { once: true }
        );
      })
  ),
}));
function Harness() {
  const [open, setOpen] = useState(false);
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Navigation
          agentOpen={open}
          agentBusy={false}
          onToggleAgent={() => setOpen((v) => !v)}
        />
        <AgentSidePanel open={open} onClose={() => setOpen(false)} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  localStorage.clear();
  Element.prototype.scrollTo = vi.fn();
});
afterEach(cleanup);

it('toggles the coach from navigation and hides it with Escape', () => {
  render(<Harness />);
  expect(screen.queryByRole('complementary')).toBeNull();
  const toggle = screen.getAllByRole('button', { name: 'Ouvrir le coach' })[0];
  fireEvent.click(toggle);
  expect(screen.getByRole('complementary')).toBeTruthy();
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(toggle);
  expect(screen.queryByRole('complementary')).toBeNull();
  fireEvent.click(toggle);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('complementary')).toBeNull();
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
});

it('creates a thread without erasing the old one and retains a stream when hidden', async () => {
  render(<Harness />);
  const toggle = screen.getAllByRole('button', { name: 'Ouvrir le coach' })[0];
  fireEvent.click(toggle);
  fireEvent.change(screen.getByRole('textbox', { name: 'Message au coach' }), {
    target: { value: 'Préparer mon trail' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));
  fireEvent.click(
    screen.getByRole('button', { name: 'Nouvelle conversation' })
  );
  expect(screen.queryByLabelText('Ton message')).toBeNull();
  expect(screen.getByText('Le coach répond dans un autre fil.')).toBeTruthy();
  fireEvent.change(screen.getByRole('textbox', { name: 'Message au coach' }), {
    target: { value: 'Brouillon du deuxième fil' },
  });
  fireEvent.click(
    within(screen.getByRole('complementary')).getByRole('button', {
      name: 'Masquer le coach',
    })
  );
  expect(stream.signal?.aborted).toBe(false);
  await act(async () => {
    stream.emit?.({ type: 'message', id: 'm1', text: '**Réponse au trail**' });
    stream.emit?.({
      type: 'done',
      message: { role: 'assistant', content: '**Réponse au trail**' },
    });
    stream.resolve?.();
  });
  fireEvent.click(toggle);
  expect(
    (
      screen.getByRole('textbox', {
        name: 'Message au coach',
      }) as HTMLTextAreaElement
    ).value
  ).toBe('Brouillon du deuxième fil');
  fireEvent.click(
    screen.getByRole('button', { name: 'Historique des conversations' })
  );
  fireEvent.click(screen.getByRole('button', { name: /^Préparer mon trail/ }));
  expect(screen.getByLabelText('Ton message').textContent).toBe(
    'Préparer mon trail'
  );
  expect(screen.getByText('Réponse au trail').tagName).toBe('STRONG');
});

it('offers page follow-ups only once the answer is done, and sends one', async () => {
  render(<Harness />);
  fireEvent.click(screen.getAllByRole('button', { name: 'Ouvrir le coach' })[0]);
  fireEvent.change(screen.getByRole('textbox', { name: 'Message au coach' }), {
    target: { value: 'Ma forme ?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));
  expect(screen.queryByRole('group', { name: 'Suggestions de suivi' })).toBeNull();
  expect(screen.queryByLabelText('Suggestions de suivi')).toBeNull();
  await act(async () => {
    stream.emit?.({ type: 'done', message: { role: 'assistant', content: 'Repos aujourd’hui.' } });
    stream.resolve?.();
  });
  const followUps = screen.getByLabelText('Suggestions de suivi');
  const [first] = within(followUps).getAllByRole('button');
  const question = first.textContent ?? '';
  fireEvent.click(first);
  expect(screen.getAllByText(question).length).toBeGreaterThan(0);
});

it('asks the same question again on retry, without the failed answer', async () => {
  render(<Harness />);
  fireEvent.click(screen.getAllByRole('button', { name: 'Ouvrir le coach' })[0]);
  fireEvent.change(screen.getByRole('textbox', { name: 'Message au coach' }), {
    target: { value: 'Ma forme ?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));
  await act(async () => {
    stream.emit?.({ type: 'error', detail: 'Le coach est indisponible.' });
    stream.resolve?.();
  });
  fireEvent.click(screen.getByRole('button', { name: /Réessayer/ }));
  // The thread title also reads the question: count the messages, not the text.
  expect(screen.getAllByRole('article', { name: 'Ton message' })).toHaveLength(1);
  expect(screen.queryByText('Le coach est indisponible.')).toBeNull();
});

it('gathers every tool of an answer in one activity card', async () => {
  render(<Harness />);
  fireEvent.click(screen.getAllByRole('button', { name: 'Ouvrir le coach' })[0]);
  fireEvent.change(screen.getByRole('textbox', { name: 'Message au coach' }), {
    target: { value: 'Ma semaine ?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));
  const preview = { text: '{}', truncated: false };
  await act(async () => {
    stream.emit?.({ type: 'tool_start', id: 't1', name: 'get_workload', args: preview });
    stream.emit?.({ type: 'tool_end', id: 't1', name: 'get_workload', status: 'done', output: preview, elapsed_ms: 5 });
    stream.emit?.({ type: 'token', id: 'm1', text: 'Je regarde ton planning.' });
    stream.emit?.({ type: 'tool_start', id: 't2', name: 'list_planned', args: preview });
    stream.emit?.({ type: 'tool_end', id: 't2', name: 'list_planned', status: 'done', output: preview, elapsed_ms: 5 });
    stream.emit?.({ type: 'done', message: { role: 'assistant', content: 'Semaine équilibrée.' } });
    stream.resolve?.();
  });
  const cards = screen.getAllByLabelText('Activité des outils');
  expect(cards).toHaveLength(1);
  expect(within(cards[0]).getByText(/2 outils/)).toBeTruthy();
});
