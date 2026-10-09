import type { ReactNode } from 'react';
import { Spinner } from '@/components/ui/Spinner';

/** Full-page frame for what the gate shows in place of the app. */
export function GateScreen({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-void flex items-center justify-center p-6">{children}</div>
  );
}

/** The gate is still deciding: the config, Clerk or the account is loading. */
export function GateSpinner() {
  return (
    <GateScreen>
      <span role="status" aria-label="Chargement…">
        <Spinner className="text-neon-cyan" />
      </span>
    </GateScreen>
  );
}
