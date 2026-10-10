import { createServer, type ServerResponse } from 'node:http';
import { test, expect, type Page } from '@playwright/test';

async function fixture(page: Page, enabled = true) {
  let response: ServerResponse | undefined;
  let requests = 0;
  const server = createServer((request, outgoing) => {
    outgoing.setHeader('Access-Control-Allow-Origin', '*');
    outgoing.setHeader('Access-Control-Allow-Headers', 'content-type');
    if (request.method === 'OPTIONS') { outgoing.writeHead(204); outgoing.end(); return; }
    requests++;
    request.resume();
    outgoing.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
    outgoing.flushHeaders();
    response = outgoing;
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Missing stream fixture port');
  await page.addInitScript(url => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => originalFetch(input === '/api/agent/chat/stream' ? url : input, init);
  }, `http://127.0.0.1:${address.port}/stream`);
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/auth/config')) return route.fulfill({ json: { enabled: false } });
    if (path.endsWith('/settings/gamification')) return route.fulfill({ json: { enabled, opted_in: enabled, available: true, version: 1 } });
    if (path.includes('/settings')) return route.fulfill({ json: {} });
    return route.fulfill({ json: [] });
  });
  return {
    requests: () => requests,
    send(event: object) {
      if (!response) throw new Error('No active stream');
      response.write(`data: ${JSON.stringify(event)}\n\n`);
    },
    async close() {
      response?.end();
      server.closeAllConnections();
      await new Promise<void>(resolve => server.close(() => resolve()));
    },
  };
}

async function openCoach(page: Page) {
  await page.goto('/planning?date=2026-10-10');
  const toggle = page.getByRole('button', { name: 'Ouvrir le coach' }).filter({ visible: true });
  await toggle.click();
  const panel = page.getByRole('complementary', { name: 'Coach IA' });
  await expect(panel).toHaveCSS('opacity', '1');
  return panel;
}

const preview = { text: '{}', truncated: false };

test('Chiron composer: inline file picker, draft removal and reuse before sending', async ({ page }) => {
  const stream = await fixture(page);
  const doc = { id: '11111111-1111-4111-8111-111111111111', name: 'Programme semaine 42.md', size: 18, sha256: '0'.repeat(64), status: 'ready' };
  let uploaded = false;
  let deleted = false;
  await page.route('**/api/agent/threads/*/documents**', route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === 'DELETE') { deleted = true; uploaded = false; return route.fulfill({ json: {} }); }
    if (path.endsWith('/finalize')) { uploaded = true; return route.fulfill({ json: doc }); }
    if (path.includes('/chunks/')) return route.fulfill({ json: { uploaded: true } });
    if (route.request().method() === 'POST') return route.fulfill({ json: doc });
    return route.fulfill({ json: uploaded ? [doc] : [] });
  });
  try {
    const panel = await openCoach(page);
    await page.evaluate(() => document.documentElement.dataset.theme = 'performance');
    const composer = panel.locator('footer');
    const attach = composer.getByRole('button', { name: 'Joindre un fichier', exact: true });
    await expect(attach).toBeVisible();
    await expect(composer.getByRole('button', { name: /Fichiers du fil/ })).toHaveCount(0);
    await composer.getByLabel('Message au coach').fill('Adapte ce programme à ma semaine.');
    await panel.getByRole('button', { name: 'Agrandir la conversation' }).click();
    // The add action must sit beside the text, never in a separate toolbar.
    const expectInlineAttachment = async () => {
      const button = await attach.boundingBox();
      const input = await composer.getByLabel('Message au coach').boundingBox();
      expect(button).not.toBeNull();
      expect(input).not.toBeNull();
      expect(button!.x + button!.width).toBeLessThanOrEqual(input!.x);
      expect(button!.y).toBeGreaterThanOrEqual(input!.y);
      expect(button!.y + button!.height).toBeLessThanOrEqual(input!.y + input!.height + 1);
    };
    await expectInlineAttachment();
    await page.screenshot({ path: '../.context/chiron-composer-desktop.png' });
    await composer.screenshot({ path: '../.context/chiron-composer-detail.png' });
    const picker = page.waitForEvent('filechooser');
    await attach.click();
    await (await picker).setFiles({ name: doc.name, mimeType: 'text/markdown', buffer: Buffer.from('Footing 30 minutes') });
    await expect(composer.getByRole('button', { name: `Consulter ${doc.name}` })).toBeVisible();
    expect(stream.requests()).toBe(0);
    await composer.getByRole('button', { name: `Retirer ${doc.name} du brouillon` }).click();
    await expect(composer.getByLabel('Pièces jointes du brouillon')).toHaveCount(0);
    expect(deleted).toBe(false);
    const library = composer.getByRole('button', { name: 'Fichiers du fil (1)' });
    await library.click();
    await composer.getByRole('checkbox', { name: doc.name }).check();
    await library.click();
    await expect(composer.getByRole('button', { name: `Consulter ${doc.name}` })).toBeVisible();
    await expect(composer.getByLabel('Message au coach')).toHaveValue('Adapte ce programme à ma semaine.');
    for (const theme of ['performance', 'odyssey']) {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
      await expect(attach).toBeInViewport();
      await expect(composer.getByRole('button', { name: 'Envoyer', exact: true })).toBeInViewport();
      expect(await composer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      await expectInlineAttachment();
      await page.screenshot({ path: `../.context/chiron-composer-${theme}-mobile.png` });
    }
    await composer.getByRole('button', { name: 'Envoyer', exact: true }).click();
    await expect.poll(() => stream.requests()).toBe(1);
    await expect(attach).toBeDisabled();
    await expect(panel.getByRole('article', { name: 'Ton message' }).getByText(doc.name)).toBeVisible();
    await composer.getByRole('button', { name: 'Arrêter la réponse' }).click();
    await expect(attach).toBeEnabled();
    await library.click();
    await composer.getByRole('button', { name: `Supprimer définitivement ${doc.name}` }).click();
    await expect(library).toHaveCount(0);
    await expect(composer.getByRole('checkbox')).toHaveCount(0);
    expect(deleted).toBe(true);
  } finally { await stream.close(); }
});

test('Chiron: real SSE states, one motion cycle, immediate text and an interrupted write without replay', async ({ page }) => {
  const stream = await fixture(page);
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    const panel = await openCoach(page);
    await panel.getByRole('button', { name: 'Agrandir la conversation' }).click();
    await panel.getByLabel('Message au coach').fill('Supprime mon ancien objectif 10 km de mes notes.');
    await panel.getByRole('button', { name: 'Envoyer', exact: true }).click();
    await expect(panel.getByRole('status')).toHaveText('Chiron prépare sa réponse');
    await expect(panel.locator('.coach-activity details')).not.toHaveAttribute('open');
    // Sample the rendered CSS animation over its entire cycle, including the
    // stagger, then resume playback. No screenshot can prove these timings.
    const frames = await panel.locator('.coach-presence').evaluate(element => {
      const dots = Array.from(element.children);
      const animations = dots.map(dot => dot.getAnimations()[0]);
      animations.forEach(animation => animation.pause());
      const result = [240, 520, 800, 1279].map(time => {
        animations.forEach(animation => animation.currentTime = time);
        return dots.map(dot => ({ opacity: Number(getComputedStyle(dot).opacity), transform: getComputedStyle(dot).transform }));
      });
      animations.forEach(animation => animation.play());
      return result;
    });
    for (let i = 0; i < 3; i++) {
      expect(frames[i][i].opacity).toBeGreaterThan(.9);
      expect(frames[i][i].transform).toContain('-3');
    }
    expect(frames[3].every(dot => dot.opacity < .4)).toBe(true);
    await page.screenshot({ path: '../.context/chiron-latency-desktop.png', animations: 'disabled' });
    stream.send({ type: 'tool_start', id: 'read', name: 'read_file', args: preview });
    await expect(panel.getByRole('status')).toHaveText('Lecture de tes notes');
    stream.send({ type: 'tool_end', id: 'read', name: 'read_file', status: 'done', output: preview, elapsed_ms: 40 });
    await expect(panel.getByRole('status')).toHaveText('Notes consultées');
    stream.send({ type: 'token', id: 'answer', text: 'J’ai retrouvé ton ancien objectif.' });
    await expect(panel.getByText('J’ai retrouvé ton ancien objectif.', { exact: true })).toBeVisible({ timeout: 1_000 });
    const prose = await panel.locator('.coach-answer-part').elementHandle();
    stream.send({ type: 'token', id: 'answer', text: ' Je mets les notes à jour.' });
    await expect(panel.locator('.coach-answer-part')).toContainText('Je mets les notes à jour.');
    expect(await prose!.evaluate(node => node === document.querySelector('.coach-answer-part'))).toBe(true);
    const measures = await page.evaluate(() => performance.getEntriesByType('measure').map(entry => entry.name));
    expect(measures.filter(name => name === 'coach:time-to-feedback')).toHaveLength(1);
    expect(measures.filter(name => name === 'coach:time-to-first-text')).toHaveLength(1);
    stream.send({ type: 'tool_start', id: 'edit', name: 'edit_file', args: preview });
    await expect(panel.getByRole('status')).toHaveText('Mise à jour de tes notes');
    await panel.getByLabel('Message au coach').fill('Mon prochain message');
    await panel.getByRole('button', { name: 'Arrêter la réponse' }).click();
    await expect(panel.getByRole('status')).toHaveText('Réponse interrompue');
    await expect(panel.getByText(/Une action a peut-être déjà été effectuée/)).toBeVisible();
    await expect(panel.getByLabel('Message au coach')).toHaveValue('Mon prochain message');
    await expect(panel.getByRole('button', { name: /Réessayer|Regénérer/ })).toHaveCount(0);
    expect(stream.requests()).toBe(1);
  } finally { await stream.close(); }
});

for (const theme of ['odyssey', 'performance']) {
  test(`mobile ${theme}: reduced motion, stable layout and confirmed result`, async ({ page }) => {
    const stream = await fixture(page);
    try {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const panel = await openCoach(page);
      await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
      await panel.getByLabel('Message au coach').fill('Mets à jour mes notes.');
      await panel.getByRole('button', { name: 'Envoyer', exact: true }).click();
      await expect(panel.getByRole('status')).toHaveText('Chiron prépare sa réponse');
      const animations = await panel.locator('.coach-presence > span').evaluateAll(dots => dots.map(dot => getComputedStyle(dot).animationName));
      expect(animations).toEqual(['none', 'none', 'none']);
      stream.send({ type: 'tool_start', id: 'edit', name: 'edit_file', args: preview });
      stream.send({ type: 'tool_end', id: 'edit', name: 'edit_file', status: 'done', output: preview, elapsed_ms: 40 });
      await expect(panel.getByRole('status')).toHaveText('Notes mises à jour');
      await expect(panel.locator('.coach-confirmation')).toHaveCSS('animation-name', 'none');
      stream.send({ type: 'token', id: 'answer', text: 'Tes notes sont à jour.' });
      stream.send({ type: 'done', message: { role: 'assistant', content: 'Tes notes sont à jour.' } });
      await expect(panel.getByText('Tes notes sont à jour.', { exact: true })).toBeVisible();
      await expect(panel.getByRole('button', { name: 'Envoyer', exact: true })).toBeVisible();
      const overflowing = await panel.evaluate(element => Array.from(element.querySelectorAll('.coach-activity, .coach-answer-part, textarea, footer')).filter(child => {
        const bounds = child.getBoundingClientRect();
        return bounds.left < 0 || bounds.right > innerWidth || child.scrollWidth > child.clientWidth + 1;
      }).map(child => child.className));
      expect(overflowing).toEqual([]);
      await expect(panel.getByRole('img')).toHaveCount(0); // Decorative portrait remains hidden to screen readers.
      const portrait = panel.locator('header img');
      expect(await portrait.evaluate(image => ({ width: image.clientWidth, height: image.clientHeight, loaded: (image as HTMLImageElement).naturalWidth > 0 }))).toEqual({ width: 36, height: 36, loaded: true });
      await page.screenshot({ path: `../.context/chiron-latency-${theme}-mobile.png`, animations: 'disabled' });
      expect(stream.requests()).toBe(1);
    } finally { await stream.close(); }
  });
}

test('the existing opt-out keeps the original coach interface', async ({ page }) => {
  const stream = await fixture(page, false);
  try {
    const panel = await openCoach(page);
    await expect(panel.getByRole('heading', { name: 'Coach Arete', exact: true })).toBeVisible();
    await panel.getByLabel('Message au coach').fill('Ma forme ?');
    await panel.getByRole('button', { name: 'Envoyer', exact: true }).click();
    await expect(panel.locator('.coach-presence')).toHaveCount(0);
    await expect(panel.getByText('Voir l’activité')).toHaveCount(0);
    await expect(panel.getByRole('button', { name: 'Arrêter la réponse' })).toBeVisible();
  } finally { await stream.close(); }
});
