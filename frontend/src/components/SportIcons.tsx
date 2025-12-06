import { cn } from '@/lib/utils';

interface SportIconProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
};

// Running - stylized runner silhouette
export function RunIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <circle cx="12" cy="5" r="2" />
      <path d="M7 20l3-6 3 3 4-8" />
      <path d="M18 12l-2 4-3-3-2 4" />
    </svg>
  );
}

// Rowing - oar motion
export function RowIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M4 18l8-8 8 8" />
      <path d="M4 14h16" />
      <circle cx="12" cy="6" r="2" />
    </svg>
  );
}

// Strength - dumbbell
export function StrengthIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M6 7v10" />
      <path d="M18 7v10" />
      <path d="M4 9v6" />
      <path d="M20 9v6" />
      <path d="M6 12h12" />
      <rect x="2" y="10" width="4" height="4" rx="0.5" />
      <rect x="18" y="10" width="4" height="4" rx="0.5" />
    </svg>
  );
}

// Cycling - wheel/bike
export function CycleIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <circle cx="6" cy="16" r="4" />
      <circle cx="18" cy="16" r="4" />
      <path d="M6 16l6-8 6 8" />
      <path d="M12 8v4" />
    </svg>
  );
}

// Swimming - wave pattern
export function SwimIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M2 12c2-2 4-2 6 0s4 2 6 0 4-2 6 0" />
      <path d="M2 17c2-2 4-2 6 0s4 2 6 0 4-2 6 0" />
      <circle cx="8" cy="6" r="2" />
      <path d="M10 6l4 3" />
    </svg>
  );
}

// Yoga/Mobility - person in pose
export function YogaIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <circle cx="12" cy="5" r="2" />
      <path d="M12 7v6" />
      <path d="M8 10l4 3 4-3" />
      <path d="M8 19l4-6 4 6" />
    </svg>
  );
}

// Hiking - mountain/trail
export function HikeIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M4 20l6-10 4 6 6-12" />
      <circle cx="10" cy="6" r="1.5" />
    </svg>
  );
}

// Walking - footsteps
export function WalkIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <ellipse cx="8" cy="8" rx="2" ry="3" />
      <ellipse cx="16" cy="14" rx="2" ry="3" />
      <path d="M8 11v2" />
      <path d="M16 17v2" />
    </svg>
  );
}

// Rest/Recovery - moon/sleep
export function RestIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M12 3a9 9 0 1 0 9 9c0-1.5-.4-3-1-4a6 6 0 0 1-8-8c-1 .6-2.5 1-4 1" />
    </svg>
  );
}

// Other/Default - lightning bolt
export function OtherIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  );
}

// Flame - for streaks (keeping emoji-like style)
export function FlameIcon({ className, size = 'md' }: SportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className={cn(sizeClasses[size], className)}
    >
      <path d="M12 2c-3 4-6 6-6 11a6 6 0 0 0 12 0c0-5-3-7-6-11zm0 15a2.5 2.5 0 0 1-2.5-2.5c0-1.5 1-2.5 2.5-4 1.5 1.5 2.5 2.5 2.5 4A2.5 2.5 0 0 1 12 17z" />
    </svg>
  );
}

// Map sport string to icon component
export function getSportIconComponent(sport: string): React.ComponentType<SportIconProps> {
  const sportLower = sport.toLowerCase();
  
  if (sportLower.includes('run') || sportLower.includes('running')) return RunIcon;
  if (sportLower.includes('row') || sportLower.includes('rowing')) return RowIcon;
  if (sportLower.includes('strength') || sportLower.includes('weight') || sportLower.includes('gym')) return StrengthIcon;
  if (sportLower.includes('cycl') || sportLower.includes('bike')) return CycleIcon;
  if (sportLower.includes('swim')) return SwimIcon;
  if (sportLower.includes('yoga') || sportLower.includes('mobil') || sportLower.includes('stretch')) return YogaIcon;
  if (sportLower.includes('hik')) return HikeIcon;
  if (sportLower.includes('walk')) return WalkIcon;
  if (sportLower.includes('rest') || sportLower.includes('recovery')) return RestIcon;
  
  return OtherIcon;
}

// Get color for sport type
export function getSportColor(sport: string): string {
  const sportLower = sport.toLowerCase();
  
  if (sportLower.includes('run') || sportLower.includes('running')) return 'text-neon-cyan';
  if (sportLower.includes('row') || sportLower.includes('rowing')) return 'text-neon-purple';
  if (sportLower.includes('strength') || sportLower.includes('weight') || sportLower.includes('gym')) return 'text-warning-orange';
  if (sportLower.includes('cycl') || sportLower.includes('bike')) return 'text-success-green';
  if (sportLower.includes('swim')) return 'text-neon-cyan';
  if (sportLower.includes('yoga') || sportLower.includes('mobil')) return 'text-neon-purple';
  if (sportLower.includes('hik')) return 'text-success-green';
  if (sportLower.includes('walk')) return 'text-text-secondary';
  if (sportLower.includes('rest')) return 'text-text-muted';
  
  return 'text-neon-gold';
}
