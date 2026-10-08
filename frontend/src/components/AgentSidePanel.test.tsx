// @vitest-environment jsdom
import { useState } from 'react';
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
  return (
    <MemoryRouter>
      <Navigation
        agentOpen={open}
        agentBusy={false}
        onToggleAgent={() => setOpen((v) => !v)}
      />
      <AgentSidePanel open={open} onClose={() => setOpen(false)} />
    </MemoryRouter>
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
