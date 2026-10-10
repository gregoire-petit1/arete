// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { GarminSyncProgress } from './GarminSyncProgress';

afterEach(cleanup);
const progress = { stage: 'fit' as const, completed: 2, total: 4, activity_name: 'Sortie longue' };
const result = { success: true, activities_synced: 3, activities_merged: 0, activities_matched: 0, activities_skipped: 1, errors: [], last_activity_date: null };

it('shows real work and reserves 100% for the final result', () => {
  const { rerender } = render(<GarminSyncProgress progress={progress} isPending error={null} />);
  expect(screen.getByRole('status').textContent).toContain('Récupération du fichier FIT');
  expect(screen.getByText('2 / 4 activités traitées')).toBeTruthy();
  expect(screen.getByText('Sortie longue')).toBeTruthy();
  expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeLessThan(100);
  rerender(<GarminSyncProgress progress={{ ...progress, stage: 'finalizing' }} isPending error={null} />);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('95');
  rerender(<GarminSyncProgress progress={progress} isPending={false} result={result} error={null} />);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100');
  expect(screen.getByText('3 importées · 0 fusionnées · 1 déjà présentes')).toBeTruthy();
});

it('keeps partial errors and interruptions visible', () => {
  const { rerender } = render(<GarminSyncProgress progress={progress} isPending={false} result={{ ...result, errors: ['FIT indisponible'] }} error={null} />);
  expect(screen.getByRole('status').textContent).toContain('avec des erreurs');
  expect(screen.getByText('FIT indisponible')).toBeTruthy();
  rerender(<GarminSyncProgress progress={progress} isPending={false} error={new Error('Suivi interrompu')} />);
  expect(screen.getByRole('alert').textContent).toBe('Suivi interrompu');
  expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeLessThan(100);
});
