// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { PlanDecisionKind } from '@/types';
import { DecisionBadge } from './DecisionBadge';

afterEach(cleanup);

it.each<[PlanDecisionKind, string, string]>([
  ['keep', 'Maintenue', 'text-success-green'],
  ['ease', 'Allégée', 'text-neon-gold'],
  ['replace_easy', 'Remplacée', 'text-warning-orange'],
  ['rest', 'Repos', 'text-danger-red'],
])('labels %s in French with its own color', (decision, label, tone) => {
  render(<DecisionBadge decision={decision} />);
  expect(screen.getByText(label).className).toContain(tone);
});

it('mutes a reverted decision', () => {
  render(<DecisionBadge decision="rest" reverted />);
  const badge = screen.getByText('Repos');
  expect(badge.className).toContain('line-through');
  expect(badge.className).not.toContain('text-danger-red');
});
