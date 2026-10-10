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
