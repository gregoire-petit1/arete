import { test, expect } from '@playwright/test';

test('connect Garmin with MFA, sync and disconnect from Connections', async ({ page }) => {
  let connected = false;
  let imported = 0;
  const loginBodies: unknown[] = [];
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/auth/config')) return route.fulfill({ json: { enabled: false } });
    if (path.endsWith('/settings/gamification')) return route.fulfill({ json: { available: false, opted_in: false } });
    if (path.endsWith('/garmin/sync/status')) return route.fulfill({ json: { garmin_authenticated: connected, user_email: connected ? 'athlete@garmin.test' : null, activities_synced: imported } });
    if (path.endsWith('/garmin/sync/login')) {
      const body = route.request().postDataJSON();
      loginBodies.push(body);
      connected = body.mfa_code === '123456';
      return route.fulfill({ json: { success: connected, needs_mfa: !connected } });
    }
    if (path.endsWith('/garmin/sync/activities')) {
      expect(connected).toBe(true);
      imported++;
      return route.fulfill({ json: { success: true, activities_synced: 1, errors: [] } });
    }
    if (path.endsWith('/garmin/sync/logout')) {
      connected = false;
      return route.fulfill({ json: { success: true } });
    }
    if (path.includes('/settings')) return route.fulfill({ json: {} });
    if (path.endsWith('/strava/status')) return route.fulfill({ json: { connected: false } });
    return route.fulfill({ json: [] });
  });
  await page.goto('/settings?tab=connections');
  await page.getByRole('button', { name: 'CONNECTER GARMIN' }).click();
  await page.getByLabel('[EMAIL]', { exact: true }).fill('athlete@garmin.test');
  await page.getByLabel('[MOT DE PASSE]', { exact: true }).fill('test-only-password');
  await page.getByRole('button', { name: '[CONNECTER]', exact: true }).click();
  await page.getByLabel('[CODE]', { exact: true }).fill('123456');
  await page.getByRole('button', { name: '[VÉRIFIER]', exact: true }).click();
  await expect(page.getByText('athlete@garmin.test', { exact: true })).toBeVisible();
  expect(loginBodies).toEqual([
    { email: 'athlete@garmin.test', password: 'test-only-password' },
    { email: '', password: '', mfa_code: '123456' },
  ]);
  await page.getByRole('button', { name: 'SYNCHRONISER', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('1 séance(s) importée(s)');
  await page.getByRole('heading', { name: 'SERVICES CONNECTÉS' }).locator('..').screenshot({ path: '../.context/garmin-connected.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Déconnecter Garmin' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../.context/garmin-connected-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Déconnecter Garmin' }).click();
  await expect(page.getByRole('button', { name: 'CONNECTER GARMIN' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('séances importées sont conservées');
  expect(imported).toBe(1);
});
