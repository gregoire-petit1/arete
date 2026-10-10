import type { ReactNode } from 'react';

/** Keep the identity still; only the bounded waiting orbit moves. */
export function ActivityIndicator({ active = true, size = 32, children }: {
  active?: boolean;
  size?: number;
  children: ReactNode;
}) {
  return (
    <span className="activity-presence" style={{ width: size, height: size }} aria-hidden="true">
      {active && <span className="activity-orbit" />}
      {children}
    </span>
  );
}
