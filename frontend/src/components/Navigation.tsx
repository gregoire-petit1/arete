import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  CalendarDays,
  Dumbbell,
  MessageSquare,
  Terminal,
  Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { path: '/', label: 'HUD', icon: LayoutDashboard },
  { path: '/quest-log', label: 'QUEST LOG', icon: CalendarDays },
  { path: '/forge', label: 'FORGE', icon: Dumbbell },
  { path: '/neural-link', label: 'NEURAL LINK', icon: MessageSquare },
  { path: '/matrix', label: 'MATRIX', icon: Terminal },
];

export function Navigation() {
  return (
    <nav aria-label="Main navigation" className="sticky top-0 z-50 bg-void/95 backdrop-blur-sm border-b border-text-muted/20">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          {/* Logo */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center gap-2"
          >
            <span className="text-xl font-bold text-neon-cyan font-mono tracking-wider">
              [ARETE]
            </span>
            <span className="text-text-muted text-xs">════</span>
          </motion.div>

          {/* Nav Links */}
          <div className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
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
                <span className="hidden md:inline">{item.label}</span>
              </NavLink>
            ))}
          </div>

          {/* Settings */}
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                'p-2 rounded transition-all duration-200',
                isActive
                  ? 'text-neon-cyan bg-neon-cyan/10'
                  : 'text-text-muted hover:text-text-primary'
              )
            }
          >
            <Settings className="w-5 h-5" />
          </NavLink>
        </div>
      </div>
    </nav>
  );
}
