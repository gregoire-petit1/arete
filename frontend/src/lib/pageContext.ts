import { useLocation } from 'react-router-dom';

/**
 * The page the user is currently viewing, stamped into every agent request as
 * `panel_context`. The "page" is a React Router route, so context
 * comes from `useLocation`.
 */
export interface PanelPageContext {
  page: string;
  path: string;
  params: Record<string, string>;
}

/** Route basename → canonical page name sent to POST /agent/chat. */
export function pageFromPath(pathname: string): string {
  const first = pathname.split('/').filter(Boolean)[0] ?? '';
  switch (first) {
    case '':
      return 'dashboard';
    case 'planning':
      return 'planning';
    case 'analytics':
      return 'analytics';
    case 'log':
      return 'log';
    case 'profile':
      return 'profile';
    case 'settings':
      return 'settings';
    default:
      // Legacy redirects (/forge, /quest-log…) never settle here — they
      // immediately <Navigate> to a canonical route.
      return 'dashboard';
  }
}

export function usePanelContext(): PanelPageContext {
  const location = useLocation();
  return {
    page: pageFromPath(location.pathname),
    path: location.pathname,
    params: Object.fromEntries(new URLSearchParams(location.search)),
  };
}
