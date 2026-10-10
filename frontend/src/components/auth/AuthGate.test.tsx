// @vitest-environment jsdom
import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { authHeaders, setTokenGetter } from '@/lib/auth';
import { AuthGate } from './AuthGate';

const clerk = vi.hoisted(() => ({
  /** Called when the mocked SDK module is first evaluated, i.e. when the gate loads it. */
  loaded: vi.fn(),
  signedIn: false,
  getToken: vi.fn(async () => 'jeton'),
  signOut: vi.fn(async (then?: () => Promise<void>) => {
    await then?.();
  }),
}));

vi.mock('@clerk/react', () => {
  clerk.loaded();
  return {
    ClerkProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    SignIn: () => <div>Formulaire Clerk</div>,
    UserButton: () => <div>Compte</div>,
    useAuth: () => ({
      isLoaded: true,
      isSignedIn: clerk.signedIn,
      sessionId: clerk.signedIn ? 'sess_1' : null,
      getToken: clerk.getToken,
      signOut: clerk.signOut,
    }),
    useUser: () => ({ user: null }),
  };
});
vi.mock('@clerk/localizations/fr-FR', () => ({ frFR: {} }));

interface Me {
  email: string;
  name: string | null;
  athlete_id: number | null;
  is_owner: boolean;
}

/** Answers the two gate endpoints and records every request. */
function server(config: unknown, me?: Me) {
  const requests: { url: string; headers: Headers }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, headers: new Headers(init?.headers) });
      if (url === '/api/auth/config') {
        if (config instanceof Error) throw config;
        return new Response(JSON.stringify(config), { status: 200 });
      }
      if (url === '/api/auth/me') {
        return me
          ? new Response(JSON.stringify(me), { status: 200 })
          : new Response('{"detail":"Non authentifié"}', { status: 401 });
      }
      throw new Error(`unexpected request: ${url}`);
    })
  );
  return requests;
}

const enabled = { enabled: true, publishable_key: 'pk_test_x' };
const disabled = { enabled: false, publishable_key: null };

function mount() {
  return render(
    <AuthGate>
      <p>Tableau de bord</p>
    </AuthGate>
  );
}

afterEach(() => {
  cleanup();
  setTokenGetter(null);
  clerk.signedIn = false;
  vi.unstubAllGlobals();
});

// Runs first on purpose: the SDK module is loaded once per file, by the first gate that needs it.
it('renders the app as before, without the Clerk SDK, when sign-in is off', async () => {
  const requests = server(disabled);
  mount();
  expect(await screen.findByText('Tableau de bord')).toBeTruthy();
  expect(clerk.loaded).not.toHaveBeenCalled();
  expect(requests.map((r) => r.url)).toEqual(['/api/auth/config']);
  expect(requests[0].headers.has('Authorization')).toBe(false);
  expect(await authHeaders()).toEqual({});
});

it('offers a retry, never the app, when the config cannot be fetched', async () => {
  server(new Error('réseau'));
  mount();
  expect(await screen.findByText('SERVEUR INJOIGNABLE')).toBeTruthy();
  expect(screen.queryByText('Tableau de bord')).toBeNull();
  server(disabled);
  fireEvent.click(screen.getByRole('button', { name: 'RÉESSAYER' }));
  expect(await screen.findByText('Tableau de bord')).toBeTruthy();
});

it('shows the sign-in page when signed out', async () => {
  const requests = server(enabled);
  mount();
  expect(await screen.findByText('Formulaire Clerk')).toBeTruthy();
  expect(screen.getByRole('heading', { name: '[ARETE]' })).toBeTruthy();
  expect(screen.queryByText('Tableau de bord')).toBeNull();
  expect(requests.map((r) => r.url)).toEqual(['/api/auth/config']);
});

it('shows the waiting page with the email while no athlete is attached', async () => {
  clerk.signedIn = true;
  const requests = server(enabled, {
    email: 'ana@exemple.fr',
    name: null,
    athlete_id: null,
    is_owner: false,
  });
  mount();
  expect(await screen.findByText(/aucun athlète ne lui est encore associé/)).toBeTruthy();
  expect(screen.getByText('ana@exemple.fr')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Se déconnecter' })).toBeTruthy();
  expect(screen.queryByText('Tableau de bord')).toBeNull();
  const me = requests.find((r) => r.url === '/api/auth/me');
  expect(me?.headers.get('Authorization')).toBe('Bearer jeton');
});

it('renders the app once an athlete is attached', async () => {
  clerk.signedIn = true;
  server(enabled, { email: 'ana@exemple.fr', name: 'Ana', athlete_id: 1, is_owner: true });
  mount();
  expect(await screen.findByText('Tableau de bord')).toBeTruthy();
  expect(await authHeaders()).toEqual({ Authorization: 'Bearer jeton' });
});
