import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ToolActivity } from './ToolActivity';

it('renders independent expandable calls with honest failure and interruption states', () => {
  const html = renderToStaticMarkup(
    <ToolActivity
      tools={[
        {
          kind: 'tool',
          id: '1',
          name: 'read_file',
          status: 'error',
          args: { text: '{"path":"notes.md"}', truncated: false },
          output: { text: 'Missing file', truncated: false },
          elapsed_ms: 20,
        },
        { kind: 'tool', id: '2', name: 'read_file', status: 'interrupted' },
      ]}
    />
  );
  expect(html.match(/<details/g)).toHaveLength(2);
  expect(html).toContain('Échec');
  expect(html).toContain('Interrompu');
  expect(html).not.toContain('Terminé');
  expect(html).toContain('Missing file');
  expect(html).toContain('notes.md');
});
