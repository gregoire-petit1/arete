import type { MouseEvent } from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  Bot,
  CalendarDays,
  Dumbbell,
  LayoutDashboard,
  Loader2,
  PanelRightClose,
  Settings,
} from 'lucide-react';
import { useGamePreference } from '@/lib/gamification';
import { ChironPortrait } from './ChironPortrait';
import { User } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { path: '/', label: 'Tableau de bord', icon: LayoutDashboard },
  { path: '/planning', label: 'Planning', icon: CalendarDays },
  { path: '/analytics', label: 'Analyses', icon: BarChart3 },
  { path: '/log', label: 'Journal', icon: Dumbbell },
  { path: '/settings', label: 'Réglages', icon: Settings },
];

/**
 * Desktop: sticky top navbar
 * Mobile: fixed bottom tab bar (fitness app pattern)
 */
export function Navigation({
  agentOpen,
  agentBusy,
  onToggleAgent,
}: {
  agentOpen: boolean;
  agentBusy: boolean;
  onToggleAgent: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  const { data: preference } = useGamePreference();
  const rpg = preference?.enabled === true;
  const profile = { path: '/profile', label: 'Profil', icon: User };
  const desktopItems = rpg ? [...navItems.slice(0, 4), profile, navItems[4]] : navItems;
  const mobileItems = rpg ? [...navItems.slice(0, 4), profile] : navItems;
  return (
    <>
      {/* Desktop top nav — hidden on mobile */}
      <nav
        aria-label="Navigation principale"
        className="hidden md:block sticky top-0 z-50 bg-void/95 backdrop-blur-sm border-b border-text-muted/20"
      >
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-2 animate-fade-left">
              <span className="text-xl font-bold text-neon-cyan font-mono tracking-wider">
                [ARETE]
              </span>
            </div>

            <div className="flex items-center gap-1">
              {desktopItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  aria-label={item.label}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 px-3 py-2 rounded text-sm font-mono',
                      'transition-all duration-200',
                      isActive
                        ? 'text-neon-cyan bg-neon-cyan/10 border border-neon-cyan/30'
                        : 'text-text-secondary hover:text-text-primary hover:bg-abyss'
                    )
                  }
                >
                  <item.icon className="w-4 h-4" />
                  <span className="hidden lg:inline">{item.label}</span>
                </NavLink>
              ))}
            </div>

            <button
              onClick={onToggleAgent}
              aria-controls="coach-panel"
              aria-expanded={agentOpen}
              aria-label={agentOpen ? 'Masquer le coach' : 'Ouvrir le coach'}
              className={cn(
                'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors',
                agentOpen
                  ? 'border-neon-cyan/30 bg-neon-cyan/10 text-neon-cyan'
                  : 'border-text-muted/20 text-text-secondary hover:border-neon-cyan/30 hover:text-neon-cyan'
              )}
            >
              {agentBusy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : agentOpen ? (
                <PanelRightClose className="size-4" />
              ) : (
                rpg ? <ChironPortrait size={24} /> : <Bot className="size-4" />
              )}
              <span>{rpg ? 'Chiron' : 'Coach'}</span>
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile bottom tab bar — hidden on desktop */}
      <nav
        aria-label="Navigation mobile"
        className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-void/95 backdrop-blur-sm border-t border-text-muted/20"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="flex items-center justify-around h-16 px-2">
          {mobileItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              aria-label={item.label}
              end={item.path === '/'}
              className={({ isActive }) =>
                cn(
                  'relative flex flex-1 flex-col items-center justify-center gap-0.5 py-1 px-1 rounded-lg',
                  'transition-all duration-200 min-w-0',
                  isActive
                    ? 'text-neon-cyan'
                    : 'text-text-muted active:text-text-secondary'
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    className={cn(
                      'w-5 h-5',
                      isActive && 'drop-shadow-[0_0_6px_rgba(0,240,255,0.5)]'
                    )}
                  />
                  <span className="text-[9px] font-mono">
                    {item.path === '/' ? 'Accueil' : item.label}
                  </span>
                  {/* Active indicator; the NavLink is `relative` so it sits on this tab */}
                  <span
                    aria-hidden
                    className={cn(
                      'absolute -top-px left-2 right-2 h-0.5 bg-neon-cyan rounded-full transition-opacity duration-200',
                      isActive ? 'opacity-100' : 'opacity-0'
                    )}
                  />
                </>
              )}
            </NavLink>
          ))}
          <button
            onClick={onToggleAgent}
            aria-controls="coach-panel"
            aria-expanded={agentOpen}
            aria-label={agentOpen ? 'Masquer le coach' : 'Ouvrir le coach'}
            className={cn(
              'flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-lg px-1 py-1',
              agentOpen ? 'bg-neon-cyan/10 text-neon-cyan' : 'text-text-muted'
            )}
          >
            {agentBusy ? (
              <Loader2 className="size-5 animate-spin" />
            ) : agentOpen ? (
              <PanelRightClose className="size-5" />
            ) : (
              rpg ? <ChironPortrait size={24} /> : <Bot className="size-5" />
            )}
            <span className="text-[9px] font-mono">{rpg ? 'Chiron' : 'Coach'}</span>
          </button>
        </div>
      </nav>
    </>
  );
}
