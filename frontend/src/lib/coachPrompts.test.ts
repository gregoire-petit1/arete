import { describe, expect, it } from 'vitest';
import { starters } from './coachPrompts';

describe('coach prompts', () => {
  it('opens on questions about the page', () => {
    expect(starters('planning')[0]).toContain('semaine');
  });

  it('falls back to general questions on an unknown page', () => {
    expect(starters('admin')).toContain('Que peux-tu faire pour moi ?');
  });

});
