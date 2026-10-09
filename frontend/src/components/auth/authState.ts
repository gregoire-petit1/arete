import { createContext, useContext } from 'react';

/** What the app knows about the signed-in account. */
export interface AuthState {
  /** Whether the server requires sign-in; false keeps the app exactly as before. */
  enabled: boolean;
  email: string | null;
  isOwner: boolean;
  /** Ends the session, drops the cached API answers and reloads; a no-op when sign-in is off. */
  signOut: () => Promise<void>;
}

export const AUTH_DISABLED: AuthState = {
  enabled: false,
  email: null,
  isOwner: false,
  signOut: async () => {},
};

/** Provided by the auth gate; components rendered without one see sign-in as off. */
export const AuthStateContext = createContext<AuthState>(AUTH_DISABLED);

export function useAuthState(): AuthState {
  return useContext(AuthStateContext);
}
