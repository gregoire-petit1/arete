import { NavLink } from 'react-router-dom';
import { BarChart3, CalendarDays, Dumbbell, LayoutDashboard, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/planning', label: 'Planning', icon: CalendarDays },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/log', label: 'Log', icon: Dumbbell },
  { path: '/settings', label: 'Settings', icon: Settings },
];

/**
 * Desktop: sticky top navbar
 * Mobile: fixed bottom tab bar (fitness app pattern)
 */
export function Navigation() {
  return (
    <>
      {/* Desktop top nav — hidden on mobile */}
      <nav
        aria-label="Main navigation"
        className="hidden md:block sticky top-0 z-50 bg-void/95 backdrop-blur-sm border-b border-text-muted/20"
      >
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-2 animate-fade-left">
              <span className="text-xl font-bold text-neon-cyan font-mono tracking-wider">[ARETE]</span>
            </div>

            <div className="flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
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
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>

            {/* Spacer: same width as the logo so the links stay centered */}
            <div className="w-[72px]" />
          </div>
        </div>
      </nav>

      {/* Mobile bottom tab bar — hidden on desktop */}
      <nav
        aria-label="Mobile navigation"
        className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-void/95 backdrop-blur-sm border-t border-text-muted/20"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="flex items-center justify-around h-16 px-2">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                cn(
                  'relative flex flex-col items-center justify-center gap-0.5 py-1 px-3 rounded-lg',
                  'transition-all duration-200 min-w-[56px]',
                  isActive ? 'text-neon-cyan' : 'text-text-muted active:text-text-secondary'
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className={cn('w-5 h-5', isActive && 'drop-shadow-[0_0_6px_rgba(0,240,255,0.5)]')} />
                  <span className="text-[10px] font-mono">{item.label}</span>
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
        </div>
      </nav>
    </>
  );
}
