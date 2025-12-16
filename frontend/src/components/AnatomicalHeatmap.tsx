import { useState } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

// Detailed muscle groups matching Garmin-style anatomy
export const MUSCLE_GROUPS = {
  // Front upper body
  chest: { id: 'chest', label: 'Chest', aliases: ['pectorals', 'pecs'] },
  front_delts: { id: 'front_delts', label: 'Front Delts', aliases: ['anterior_deltoid', 'shoulders'] },
  side_delts: { id: 'side_delts', label: 'Side Delts', aliases: ['lateral_deltoid', 'shoulders'] },
  biceps: { id: 'biceps', label: 'Biceps', aliases: ['biceps_brachii'] },
  forearms: { id: 'forearms', label: 'Forearms', aliases: ['brachioradialis', 'wrist_flexors'] },
  abs: { id: 'abs', label: 'Abs', aliases: ['rectus_abdominis', 'core'] },
  obliques: { id: 'obliques', label: 'Obliques', aliases: ['external_obliques'] },
  
  // Back upper body
  traps: { id: 'traps', label: 'Traps', aliases: ['trapezius', 'upper_back', 'back'] },
  rear_delts: { id: 'rear_delts', label: 'Rear Delts', aliases: ['posterior_deltoid', 'shoulders'] },
  lats: { id: 'lats', label: 'Lats', aliases: ['latissimus_dorsi', 'back'] },
  rhomboids: { id: 'rhomboids', label: 'Rhomboids', aliases: ['mid_back', 'back'] },
  lower_back: { id: 'lower_back', label: 'Lower Back', aliases: ['erector_spinae', 'spinal_erectors'] },
  triceps: { id: 'triceps', label: 'Triceps', aliases: ['triceps_brachii'] },
  
  // Lower body front
  quads: { id: 'quads', label: 'Quads', aliases: ['quadriceps', 'rectus_femoris', 'vastus'] },
  hip_flexors: { id: 'hip_flexors', label: 'Hip Flexors', aliases: ['iliopsoas'] },
  adductors: { id: 'adductors', label: 'Adductors', aliases: ['inner_thigh'] },
  tibialis: { id: 'tibialis', label: 'Tibialis', aliases: ['tibialis_anterior', 'shins'] },
  
  // Lower body back
  glutes: { id: 'glutes', label: 'Glutes', aliases: ['gluteus_maximus', 'gluteus_medius'] },
  hamstrings: { id: 'hamstrings', label: 'Hamstrings', aliases: ['biceps_femoris', 'semitendinosus'] },
  calves: { id: 'calves', label: 'Calves', aliases: ['gastrocnemius', 'soleus'] },
} as const;

export type MuscleId = keyof typeof MUSCLE_GROUPS;

interface AnatomicalHeatmapProps {
  volumeByMuscle: Record<string, number>;
  className?: string;
  showLabels?: boolean;
  onMuscleClick?: (muscleId: string) => void;
  selectedMuscle?: string | null;
}

export function AnatomicalHeatmap({
  volumeByMuscle,
  className,
  showLabels = true,
  onMuscleClick,
  selectedMuscle,
}: AnatomicalHeatmapProps) {
  const [hoveredMuscle, setHoveredMuscle] = useState<string | null>(null);

  // Normalize muscle names and sum volumes for aliases
  const getNormalizedVolume = (muscleId: string): number => {
    const group = MUSCLE_GROUPS[muscleId as MuscleId];
    if (!group) return volumeByMuscle[muscleId] || 0;

    let total = volumeByMuscle[muscleId] || 0;
    group.aliases.forEach((alias) => {
      total += volumeByMuscle[alias] || 0;
    });
    return total;
  };

  // Get heat color based on volume (0-3 scale for intensity)
  const getHeatLevel = (volume: number): 0 | 1 | 2 | 3 => {
    if (volume >= 2000) return 3; // High
    if (volume >= 1000) return 2; // Medium
    if (volume > 0) return 1; // Low
    return 0; // None
  };

  const getHeatColor = (muscleId: string, _view: 'front' | 'back' = 'front') => {
    const volume = getNormalizedVolume(muscleId);
    const level = getHeatLevel(volume);
    const isHovered = hoveredMuscle === muscleId;
    const isSelected = selectedMuscle === muscleId;

    // Base colors matching Garmin style
    const colors = {
      0: 'fill-slate-700', // Untargeted - gray
      1: 'fill-amber-500', // Secondary - yellow/gold
      2: 'fill-orange-500', // Medium - orange
      3: 'fill-red-500', // Primary - red
    };

    const baseColor = colors[level];
    const extraClasses = cn(
      baseColor,
      isHovered && 'brightness-125',
      isSelected && 'stroke-neon-cyan stroke-2',
      'transition-all duration-200 cursor-pointer'
    );

    return extraClasses;
  };

  const handleMuscleInteraction = (muscleId: string) => {
    if (onMuscleClick) {
      onMuscleClick(muscleId);
    }
  };

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Bodies Container */}
      <div className="flex justify-center items-start gap-4">
        {/* Front View */}
        <div className="flex flex-col items-center">
          <span className="text-[10px] font-mono text-text-muted mb-2 uppercase tracking-wider">FRONT</span>
          <svg viewBox="0 0 120 200" className="w-[140px] h-[220px]">
            {/* Body outline */}
            <g className="stroke-slate-600 fill-none stroke-[0.5]">
              {/* Head */}
              <ellipse cx="60" cy="15" rx="12" ry="14" />
              {/* Neck */}
              <rect x="54" y="28" width="12" height="8" />
            </g>

            {/* === FRONT MUSCLES === */}
            
            {/* Traps (front visible) */}
            <path
              d="M 48 36 Q 60 32 72 36 L 68 42 Q 60 40 52 42 Z"
              className={getHeatColor('traps')}
              onMouseEnter={() => setHoveredMuscle('traps')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('traps')}
            />

            {/* Front Delts - Left */}
            <ellipse
              cx="38" cy="44"
              rx="8" ry="6"
              className={getHeatColor('front_delts')}
              onMouseEnter={() => setHoveredMuscle('front_delts')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('front_delts')}
            />
            {/* Front Delts - Right */}
            <ellipse
              cx="82" cy="44"
              rx="8" ry="6"
              className={getHeatColor('front_delts')}
              onMouseEnter={() => setHoveredMuscle('front_delts')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('front_delts')}
            />

            {/* Chest - Left */}
            <ellipse
              cx="48" cy="54"
              rx="10" ry="8"
              className={getHeatColor('chest')}
              onMouseEnter={() => setHoveredMuscle('chest')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('chest')}
            />
            {/* Chest - Right */}
            <ellipse
              cx="72" cy="54"
              rx="10" ry="8"
              className={getHeatColor('chest')}
              onMouseEnter={() => setHoveredMuscle('chest')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('chest')}
            />

            {/* Biceps - Left */}
            <ellipse
              cx="28" cy="58"
              rx="5" ry="12"
              className={getHeatColor('biceps')}
              onMouseEnter={() => setHoveredMuscle('biceps')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('biceps')}
            />
            {/* Biceps - Right */}
            <ellipse
              cx="92" cy="58"
              rx="5" ry="12"
              className={getHeatColor('biceps')}
              onMouseEnter={() => setHoveredMuscle('biceps')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('biceps')}
            />

            {/* Forearms - Left */}
            <ellipse
              cx="24" cy="78"
              rx="4" ry="10"
              className={getHeatColor('forearms')}
              onMouseEnter={() => setHoveredMuscle('forearms')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('forearms')}
            />
            {/* Forearms - Right */}
            <ellipse
              cx="96" cy="78"
              rx="4" ry="10"
              className={getHeatColor('forearms')}
              onMouseEnter={() => setHoveredMuscle('forearms')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('forearms')}
            />

            {/* Abs */}
            <rect
              x="52" y="66"
              width="16" height="28"
              rx="3"
              className={getHeatColor('abs')}
              onMouseEnter={() => setHoveredMuscle('abs')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('abs')}
            />

            {/* Obliques - Left */}
            <path
              d="M 40 68 Q 38 80 42 94 L 50 92 L 50 68 Z"
              className={getHeatColor('obliques')}
              onMouseEnter={() => setHoveredMuscle('obliques')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('obliques')}
            />
            {/* Obliques - Right */}
            <path
              d="M 80 68 Q 82 80 78 94 L 70 92 L 70 68 Z"
              className={getHeatColor('obliques')}
              onMouseEnter={() => setHoveredMuscle('obliques')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('obliques')}
            />

            {/* Hip Flexors - Left */}
            <ellipse
              cx="48" cy="100"
              rx="6" ry="4"
              className={getHeatColor('hip_flexors')}
              onMouseEnter={() => setHoveredMuscle('hip_flexors')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('hip_flexors')}
            />
            {/* Hip Flexors - Right */}
            <ellipse
              cx="72" cy="100"
              rx="6" ry="4"
              className={getHeatColor('hip_flexors')}
              onMouseEnter={() => setHoveredMuscle('hip_flexors')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('hip_flexors')}
            />

            {/* Adductors - Left */}
            <ellipse
              cx="54" cy="118"
              rx="4" ry="14"
              className={getHeatColor('adductors')}
              onMouseEnter={() => setHoveredMuscle('adductors')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('adductors')}
            />
            {/* Adductors - Right */}
            <ellipse
              cx="66" cy="118"
              rx="4" ry="14"
              className={getHeatColor('adductors')}
              onMouseEnter={() => setHoveredMuscle('adductors')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('adductors')}
            />

            {/* Quads - Left */}
            <ellipse
              cx="46" cy="125"
              rx="8" ry="22"
              className={getHeatColor('quads')}
              onMouseEnter={() => setHoveredMuscle('quads')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('quads')}
            />
            {/* Quads - Right */}
            <ellipse
              cx="74" cy="125"
              rx="8" ry="22"
              className={getHeatColor('quads')}
              onMouseEnter={() => setHoveredMuscle('quads')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('quads')}
            />

            {/* Tibialis - Left */}
            <ellipse
              cx="44" cy="165"
              rx="4" ry="14"
              className={getHeatColor('tibialis')}
              onMouseEnter={() => setHoveredMuscle('tibialis')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('tibialis')}
            />
            {/* Tibialis - Right */}
            <ellipse
              cx="76" cy="165"
              rx="4" ry="14"
              className={getHeatColor('tibialis')}
              onMouseEnter={() => setHoveredMuscle('tibialis')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('tibialis')}
            />

            {/* Body outline overlay */}
            <g className="stroke-slate-500 fill-none stroke-[1] pointer-events-none">
              {/* Torso */}
              <path d="M 36 36 L 32 44 L 30 70 L 38 96 L 42 106 L 46 106 L 50 96 L 60 96 L 70 96 L 74 106 L 78 106 L 82 96 L 90 70 L 88 44 L 84 36" />
              {/* Arms */}
              <path d="M 32 44 L 22 46 L 18 78 L 20 92 L 28 92 L 32 78 L 32 58" />
              <path d="M 88 44 L 98 46 L 102 78 L 100 92 L 92 92 L 88 78 L 88 58" />
              {/* Legs */}
              <path d="M 42 106 L 38 150 L 36 185 L 44 190 L 52 185 L 54 150 L 54 106" />
              <path d="M 78 106 L 82 150 L 84 185 L 76 190 L 68 185 L 66 150 L 66 106" />
            </g>
          </svg>
        </div>

        {/* Back View */}
        <div className="flex flex-col items-center">
          <span className="text-[10px] font-mono text-text-muted mb-2 uppercase tracking-wider">BACK</span>
          <svg viewBox="0 0 120 200" className="w-[140px] h-[220px]">
            {/* Body outline */}
            <g className="stroke-slate-600 fill-none stroke-[0.5]">
              {/* Head */}
              <ellipse cx="60" cy="15" rx="12" ry="14" />
              {/* Neck */}
              <rect x="54" y="28" width="12" height="8" />
            </g>

            {/* === BACK MUSCLES === */}

            {/* Traps (upper) */}
            <path
              d="M 48 36 Q 60 30 72 36 L 72 48 Q 60 52 48 48 Z"
              className={getHeatColor('traps', 'back')}
              onMouseEnter={() => setHoveredMuscle('traps')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('traps')}
            />

            {/* Rear Delts - Left */}
            <ellipse
              cx="36" cy="44"
              rx="6" ry="5"
              className={getHeatColor('rear_delts', 'back')}
              onMouseEnter={() => setHoveredMuscle('rear_delts')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('rear_delts')}
            />
            {/* Rear Delts - Right */}
            <ellipse
              cx="84" cy="44"
              rx="6" ry="5"
              className={getHeatColor('rear_delts', 'back')}
              onMouseEnter={() => setHoveredMuscle('rear_delts')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('rear_delts')}
            />

            {/* Rhomboids */}
            <path
              d="M 48 48 L 52 48 L 52 62 L 48 66 Z"
              className={getHeatColor('rhomboids', 'back')}
              onMouseEnter={() => setHoveredMuscle('rhomboids')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('rhomboids')}
            />
            <path
              d="M 72 48 L 68 48 L 68 62 L 72 66 Z"
              className={getHeatColor('rhomboids', 'back')}
              onMouseEnter={() => setHoveredMuscle('rhomboids')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('rhomboids')}
            />

            {/* Lats - Left */}
            <path
              d="M 38 50 Q 32 62 36 80 L 48 80 L 52 62 L 48 50 Z"
              className={getHeatColor('lats', 'back')}
              onMouseEnter={() => setHoveredMuscle('lats')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('lats')}
            />
            {/* Lats - Right */}
            <path
              d="M 82 50 Q 88 62 84 80 L 72 80 L 68 62 L 72 50 Z"
              className={getHeatColor('lats', 'back')}
              onMouseEnter={() => setHoveredMuscle('lats')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('lats')}
            />

            {/* Triceps - Left */}
            <ellipse
              cx="28" cy="58"
              rx="5" ry="12"
              className={getHeatColor('triceps', 'back')}
              onMouseEnter={() => setHoveredMuscle('triceps')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('triceps')}
            />
            {/* Triceps - Right */}
            <ellipse
              cx="92" cy="58"
              rx="5" ry="12"
              className={getHeatColor('triceps', 'back')}
              onMouseEnter={() => setHoveredMuscle('triceps')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('triceps')}
            />

            {/* Forearms - Left */}
            <ellipse
              cx="24" cy="78"
              rx="4" ry="10"
              className={getHeatColor('forearms', 'back')}
              onMouseEnter={() => setHoveredMuscle('forearms')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('forearms')}
            />
            {/* Forearms - Right */}
            <ellipse
              cx="96" cy="78"
              rx="4" ry="10"
              className={getHeatColor('forearms', 'back')}
              onMouseEnter={() => setHoveredMuscle('forearms')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('forearms')}
            />

            {/* Lower Back / Erectors */}
            <path
              d="M 52 66 L 56 66 L 58 92 L 56 96 L 52 96 Z"
              className={getHeatColor('lower_back', 'back')}
              onMouseEnter={() => setHoveredMuscle('lower_back')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('lower_back')}
            />
            <path
              d="M 68 66 L 64 66 L 62 92 L 64 96 L 68 96 Z"
              className={getHeatColor('lower_back', 'back')}
              onMouseEnter={() => setHoveredMuscle('lower_back')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('lower_back')}
            />

            {/* Glutes - Left */}
            <ellipse
              cx="48" cy="108"
              rx="10" ry="8"
              className={getHeatColor('glutes', 'back')}
              onMouseEnter={() => setHoveredMuscle('glutes')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('glutes')}
            />
            {/* Glutes - Right */}
            <ellipse
              cx="72" cy="108"
              rx="10" ry="8"
              className={getHeatColor('glutes', 'back')}
              onMouseEnter={() => setHoveredMuscle('glutes')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('glutes')}
            />

            {/* Hamstrings - Left */}
            <ellipse
              cx="46" cy="135"
              rx="7" ry="18"
              className={getHeatColor('hamstrings', 'back')}
              onMouseEnter={() => setHoveredMuscle('hamstrings')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('hamstrings')}
            />
            {/* Hamstrings - Right */}
            <ellipse
              cx="74" cy="135"
              rx="7" ry="18"
              className={getHeatColor('hamstrings', 'back')}
              onMouseEnter={() => setHoveredMuscle('hamstrings')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('hamstrings')}
            />

            {/* Calves - Left */}
            <ellipse
              cx="46" cy="168"
              rx="5" ry="14"
              className={getHeatColor('calves', 'back')}
              onMouseEnter={() => setHoveredMuscle('calves')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('calves')}
            />
            {/* Calves - Right */}
            <ellipse
              cx="74" cy="168"
              rx="5" ry="14"
              className={getHeatColor('calves', 'back')}
              onMouseEnter={() => setHoveredMuscle('calves')}
              onMouseLeave={() => setHoveredMuscle(null)}
              onClick={() => handleMuscleInteraction('calves')}
            />

            {/* Body outline overlay */}
            <g className="stroke-slate-500 fill-none stroke-[1] pointer-events-none">
              {/* Torso */}
              <path d="M 36 36 L 32 44 L 30 70 L 38 96 L 42 106 L 46 106 L 50 96 L 60 96 L 70 96 L 74 106 L 78 106 L 82 96 L 90 70 L 88 44 L 84 36" />
              {/* Arms */}
              <path d="M 32 44 L 22 46 L 18 78 L 20 92 L 28 92 L 32 78 L 32 58" />
              <path d="M 88 44 L 98 46 L 102 78 L 100 92 L 92 92 L 88 78 L 88 58" />
              {/* Legs */}
              <path d="M 42 106 L 38 150 L 36 185 L 44 190 L 52 185 L 54 150 L 54 106" />
              <path d="M 78 106 L 82 150 L 84 185 L 76 190 L 68 185 L 66 150 L 66 106" />
            </g>
          </svg>
        </div>
      </div>

      {/* Hover Info */}
      {hoveredMuscle && (
        <motion.div
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mt-2"
        >
          <span className="text-xs font-mono text-text-primary uppercase">
            {MUSCLE_GROUPS[hoveredMuscle as MuscleId]?.label || hoveredMuscle}
          </span>
          <span className="text-xs font-mono text-text-muted ml-2">
            {(getNormalizedVolume(hoveredMuscle) / 1000).toFixed(1)}k kg
          </span>
        </motion.div>
      )}

      {/* Legend */}
      {showLabels && (
        <div className="flex justify-center gap-4 mt-4 text-[10px] font-mono">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-red-500" />
            <span className="text-text-muted">Primary</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-amber-500" />
            <span className="text-text-muted">Secondary</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-slate-700" />
            <span className="text-text-muted">Untargeted</span>
          </span>
        </div>
      )}
    </div>
  );
}

// Compact version for smaller spaces
export function AnatomicalHeatmapCompact({
  volumeByMuscle,
  className,
}: {
  volumeByMuscle: Record<string, number>;
  className?: string;
}) {
  return (
    <AnatomicalHeatmap
      volumeByMuscle={volumeByMuscle}
      className={className}
      showLabels={false}
    />
  );
}
