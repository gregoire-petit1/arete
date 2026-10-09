// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { athleteFactsApi } from '@/lib/api';
import type { AthleteFact } from '@/types';
import { AthleteFactsPanel, FactList } from './AthleteFactsPanel';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const fact = (id: number, over: Partial<AthleteFact> = {}): AthleteFact => ({
  id,
  kind: 'injury',
  text: `Fait ${id}`,
  since: '2026-09-01',
  status: 'active',
  source: 'coach',
  updated_at: '2026-09-01T08:00:00',
  ...over,
});

const facts = [
  fact(1, { status: 'resolved', kind: 'preference', source: 'athlete' }),
  fact(2, { kind: 'constraint' }),
];

function renderList(over: Partial<Parameters<typeof FactList>[0]> = {}) {
  const actions = { onSave: vi.fn(), onToggle: vi.fn(), onDelete: vi.fn() };
  render(<FactList facts={facts} busyId={null} {...actions} {...over} />);
  return actions;
}

it('lists active facts first and dims resolved ones', () => {
  renderList();
  const rows = screen.getAllByRole('listitem');
  expect(rows.map((r) => r.dataset.status)).toEqual(['active', 'resolved']);
  expect(rows[0].className).not.toContain('opacity-50');
  expect(rows[1].className).toContain('opacity-50');
  expect(within(rows[0]).getByText('contrainte')).toBeTruthy();
  expect(within(rows[0]).getByText('coach')).toBeTruthy();
  expect(within(rows[1]).getByText('préférence')).toBeTruthy();
  expect(within(rows[1]).getByText('toi')).toBeTruthy();
});

it('resolves an active fact and reactivates a resolved one', () => {
  const { onToggle, onDelete } = renderList();
  fireEvent.click(screen.getByRole('button', { name: 'Résolu' }));
  expect(onToggle).toHaveBeenLastCalledWith(facts[1]);
  fireEvent.click(screen.getByRole('button', { name: 'Réactiver' }));
  expect(onToggle).toHaveBeenLastCalledWith(facts[0]);
  fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer le fait' })[0]);
  expect(onDelete).toHaveBeenCalledWith(facts[1]);
});

it('edits a fact in place and only saves a changed text', () => {
  const { onSave } = renderList();
  const row = screen.getAllByRole('listitem')[0];
  fireEvent.click(within(row).getByRole('button', { name: /Modifier/ }));
  fireEvent.click(within(row).getByRole('button', { name: 'Enregistrer le fait' }));
  expect(onSave).not.toHaveBeenCalled();
  fireEvent.click(within(row).getByRole('button', { name: /Modifier/ }));
  fireEvent.change(within(row).getByLabelText('Texte du fait'), { target: { value: '  Pas de côtes  ' } });
  fireEvent.click(within(row).getByRole('button', { name: 'Enregistrer le fait' }));
  expect(onSave).toHaveBeenCalledWith(facts[1], 'Pas de côtes');
  expect(within(row).getByText('Fait 2')).toBeTruthy();
});

it('writes changes at once, without the settings save button', async () => {
  vi.spyOn(athleteFactsApi, 'list').mockResolvedValue(facts);
  const update = vi.spyOn(athleteFactsApi, 'update').mockResolvedValue({ ...facts[1], status: 'resolved' });
  const create = vi.spyOn(athleteFactsApi, 'create').mockResolvedValue(fact(3));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AthleteFactsPanel />
    </QueryClientProvider>
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Résolu' }));
  await waitFor(() => expect(update).toHaveBeenCalledWith(2, { status: 'resolved' }));
  fireEvent.change(screen.getByLabelText('Type de fait'), { target: { value: 'goal' } });
  fireEvent.change(screen.getByLabelText('Nouveau fait'), { target: { value: 'Sub 1h45 au semi' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ajouter' }));
  await waitFor(() => expect(create).toHaveBeenCalledWith({ kind: 'goal', text: 'Sub 1h45 au semi' }));
  client.clear();
});
