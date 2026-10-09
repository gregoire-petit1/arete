import { describe, expect, it } from 'vitest';
import { followUps, starters } from './coachPrompts';

describe('coach prompts', () => {
  it('opens on questions about the page', () => {
    expect(starters('planning')[0]).toContain('semaine');
  });

  it('falls back to general questions on an unknown page', () => {
    expect(starters('admin')).toContain('Que peux-tu faire pour moi ?');
  });

  it('never offers a question already asked', () => {
    const asked = ["que dois-je faire aujourd'hui ?"];
    const offered = followUps('dashboard', asked);
    expect(offered).toHaveLength(3);
    expect(offered).not.toContain("Que dois-je faire aujourd'hui ?");
  });
});
