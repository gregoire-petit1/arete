import { useState } from 'react';
import { cn } from '@/lib/utils';

// Detailed muscle groups matching Garmin-style anatomy.
// Ids mirror MUSCLES in src/arete/data/exercises_catalog.py (backend volume keys).
export const MUSCLE_GROUPS = {
  chest: { label: 'Chest', aliases: ['pectorals', 'pecs'] },
  front_delts: { label: 'Front Delts', aliases: ['anterior_deltoid', 'shoulders'] },
  side_delts: { label: 'Side Delts', aliases: ['lateral_deltoid', 'shoulders'] },
  biceps: { label: 'Biceps', aliases: ['biceps_brachii'] },
  forearms: { label: 'Forearms', aliases: ['brachioradialis', 'wrist_flexors'] },
  abs: { label: 'Abs', aliases: ['rectus_abdominis', 'core'] },
  obliques: { label: 'Obliques', aliases: ['external_obliques'] },
  traps: { label: 'Traps', aliases: ['trapezius', 'upper_back', 'back'] },
  rear_delts: { label: 'Rear Delts', aliases: ['posterior_deltoid', 'shoulders'] },
  lats: { label: 'Lats', aliases: ['latissimus_dorsi', 'back'] },
  rhomboids: { label: 'Rhomboids', aliases: ['mid_back', 'back'] },
  lower_back: { label: 'Lower Back', aliases: ['erector_spinae', 'spinal_erectors'] },
  triceps: { label: 'Triceps', aliases: ['triceps_brachii'] },
  quads: { label: 'Quads', aliases: ['quadriceps', 'rectus_femoris', 'vastus'] },
  hip_flexors: { label: 'Hip Flexors', aliases: ['iliopsoas'] },
  adductors: { label: 'Adductors', aliases: ['inner_thigh'] },
  tibialis: { label: 'Tibialis', aliases: ['tibialis_anterior', 'shins'] },
  glutes: { label: 'Glutes', aliases: ['gluteus_maximus', 'gluteus_medius'] },
  hamstrings: { label: 'Hamstrings', aliases: ['biceps_femoris', 'semitendinosus'] },
  calves: { label: 'Calves', aliases: ['gastrocnemius', 'soleus'] },
} as const;

export type MuscleId = keyof typeof MUSCLE_GROUPS;

type View = 'front' | 'back';

type Shape =
  | { id: MuscleId; view: View; el: 'ellipse'; cx: number; cy: number; rx: number; ry: number }
  | { id: MuscleId; view: View; el: 'rect'; x: number; y: number; w: number; h: number; rx?: number }
  | { id: MuscleId; view: View; el: 'path'; d: string };

/** Left/right mirrored ellipse pair around the body axis (x = 60). */
const pair = (id: MuscleId, view: View, cx: number, cy: number, rx: number, ry: number): Shape[] => [
  { id, view, el: 'ellipse', cx, cy, rx, ry },
  { id, view, el: 'ellipse', cx: 120 - cx, cy, rx, ry },
];

// Draw order matters: later shapes paint over earlier ones.
const MUSCLE_SHAPES: Shape[] = [
  // ── front ──
  { id: 'traps', view: 'front', el: 'path', d: 'M 48 36 Q 60 32 72 36 L 68 42 Q 60 40 52 42 Z' },
  ...pair('side_delts', 'front', 31, 45, 6, 6), // outer shoulder, partly covered by front_delts
  ...pair('front_delts', 'front', 38, 44, 8, 6),
  ...pair('chest', 'front', 48, 54, 10, 8),
  ...pair('biceps', 'front', 28, 58, 5, 12),
  ...pair('forearms', 'front', 24, 78, 4, 10),
  { id: 'abs', view: 'front', el: 'rect', x: 52, y: 66, w: 16, h: 28, rx: 3 },
  { id: 'obliques', view: 'front', el: 'path', d: 'M 40 68 Q 38 80 42 94 L 50 92 L 50 68 Z' },
  { id: 'obliques', view: 'front', el: 'path', d: 'M 80 68 Q 82 80 78 94 L 70 92 L 70 68 Z' },
  ...pair('hip_flexors', 'front', 48, 100, 6, 4),
  ...pair('adductors', 'front', 54, 118, 4, 14),
  ...pair('quads', 'front', 46, 125, 8, 22),
  ...pair('tibialis', 'front', 44, 165, 4, 14),
  // ── back ──
  { id: 'traps', view: 'back', el: 'path', d: 'M 48 36 Q 60 30 72 36 L 72 48 Q 60 52 48 48 Z' },
  ...pair('rear_delts', 'back', 36, 44, 6, 5),
  { id: 'rhomboids', view: 'back', el: 'path', d: 'M 48 48 L 52 48 L 52 62 L 48 66 Z' },
  { id: 'rhomboids', view: 'back', el: 'path', d: 'M 72 48 L 68 48 L 68 62 L 72 66 Z' },
  { id: 'lats', view: 'back', el: 'path', d: 'M 38 50 Q 32 62 36 80 L 48 80 L 52 62 L 48 50 Z' },
  { id: 'lats', view: 'back', el: 'path', d: 'M 82 50 Q 88 62 84 80 L 72 80 L 68 62 L 72 50 Z' },
  ...pair('triceps', 'back', 28, 58, 5, 12),
  ...pair('forearms', 'back', 24, 78, 4, 10),
  { id: 'lower_back', view: 'back', el: 'path', d: 'M 52 66 L 56 66 L 58 92 L 56 96 L 52 96 Z' },
  { id: 'lower_back', view: 'back', el: 'path', d: 'M 68 66 L 64 66 L 62 92 L 64 96 L 68 96 Z' },
  ...pair('glutes', 'back', 48, 108, 10, 8),
  ...pair('hamstrings', 'back', 46, 135, 7, 18),
  ...pair('calves', 'back', 46, 168, 5, 14),
];

const OUTLINE = [
  'M 36 36 L 32 44 L 30 70 L 38 96 L 42 106 L 46 106 L 50 96 L 60 96 L 70 96 L 74 106 L 78 106 L 82 96 L 90 70 L 88 44 L 84 36',
  'M 32 44 L 22 46 L 18 78 L 20 92 L 28 92 L 32 78 L 32 58',
  'M 88 44 L 98 46 L 102 78 L 100 92 L 92 92 L 88 78 L 88 58',
  'M 42 106 L 38 150 L 36 185 L 44 190 L 52 185 L 54 150 L 54 106',
  'M 78 106 L 82 150 L 84 185 L 76 190 L 68 185 L 66 150 L 66 106',
];

const HEAT_FILL = ['fill-heat-none', 'fill-heat-low', 'fill-heat-mid', 'fill-heat-high'] as const;

const heatLevel = (volume: number): 0 | 1 | 2 | 3 =>
  volume >= 2000 ? 3 : volume >= 1000 ? 2 : volume > 0 ? 1 : 0;

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
  const [hoveredMuscle, setHoveredMuscle] = useState<MuscleId | null>(null);

  // Sum the muscle's own volume with its aliases
  const volumeOf = (id: MuscleId): number =>
    (volumeByMuscle[id] || 0) +
    MUSCLE_GROUPS[id].aliases.reduce((sum, alias) => sum + (volumeByMuscle[alias] || 0), 0);

  const shapeClass = (id: MuscleId) =>
    cn(
      HEAT_FILL[heatLevel(volumeOf(id))],
      hoveredMuscle === id && 'brightness-125',
      selectedMuscle === id && 'stroke-neon-cyan stroke-2',
      'transition-all duration-200 cursor-pointer'
    );

  const renderShape = (shape: Shape, i: number) => {
    const common = {
      key: i,
      className: shapeClass(shape.id),
      onMouseEnter: () => setHoveredMuscle(shape.id),
      onMouseLeave: () => setHoveredMuscle(null),
      onClick: () => onMuscleClick?.(shape.id),
    };
    switch (shape.el) {
      case 'ellipse':
        return <ellipse {...common} cx={shape.cx} cy={shape.cy} rx={shape.rx} ry={shape.ry} />;
      case 'rect':
        return <rect {...common} x={shape.x} y={shape.y} width={shape.w} height={shape.h} rx={shape.rx} />;
      case 'path':
        return <path {...common} d={shape.d} />;
    }
  };

  const renderBody = (view: View) => (
    <div className="flex flex-col items-center">
      <span className="text-[10px] font-mono text-text-muted mb-2 uppercase tracking-wider">
        {view.toUpperCase()}
      </span>
      <svg viewBox="0 0 120 200" className="w-[140px] h-[220px]">
        <g className="stroke-outline-dim fill-none stroke-[0.5]">
          <ellipse cx="60" cy="15" rx="12" ry="14" />
          <rect x="54" y="28" width="12" height="8" />
        </g>
        {MUSCLE_SHAPES.filter((s) => s.view === view).map(renderShape)}
        <g className="stroke-outline fill-none stroke-[1] pointer-events-none">
          {OUTLINE.map((d) => (
            <path key={d} d={d} />
          ))}
        </g>
      </svg>
    </div>
  );

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="flex justify-center items-start gap-4">
        {renderBody('front')}
        {renderBody('back')}
      </div>

      {hoveredMuscle && (
        <div className="text-center mt-2 animate-fade-up">
          <span className="text-xs font-mono text-text-primary uppercase">{MUSCLE_GROUPS[hoveredMuscle].label}</span>
          <span className="text-xs font-mono text-text-muted ml-2">
            {(volumeOf(hoveredMuscle) / 1000).toFixed(1)}k kg
          </span>
        </div>
      )}

      {showLabels && (
        <div className="flex justify-center gap-4 mt-4 text-[10px] font-mono">
          <LegendSwatch color="bg-heat-high" label="Primary" />
          <LegendSwatch color="bg-heat-low" label="Secondary" />
          <LegendSwatch color="bg-heat-none" label="Untargeted" />
        </div>
      )}
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('w-3 h-3 rounded-sm', color)} />
      <span className="text-text-muted">{label}</span>
    </span>
  );
}
