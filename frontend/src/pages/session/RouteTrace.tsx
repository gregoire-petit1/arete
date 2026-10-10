import { projectRoute } from '@/lib/activity';
import { COLORS } from '@/lib/chartTheme';

const WIDTH = 320;
const HEIGHT = 220;

/**
 * The GPS trace as an SVG line: no map tiles, no map library, nothing fetched
 * from a third party. North is up; the dot marks the start, the square the finish.
 */
export function RouteTrace({ route }: { route: [number, number][] }) {
  const projected = projectRoute(route, WIDTH, HEIGHT, 12);
  if (!projected) return null;
  const [sx, sy] = projected.start;
  const [ex, ey] = projected.end;
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="w-full h-auto max-h-80 rounded bg-abyss border border-text-muted/20"
      role="img"
      aria-label="Tracé GPS de la séance, départ en rond, arrivée en carré"
    >
      <polyline
        points={projected.points}
        fill="none"
        stroke={COLORS.neonCyan}
        strokeWidth={2.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={sx} cy={sy} r={5} fill={COLORS.successGreen} stroke={COLORS.void} strokeWidth={2} />
      <rect x={ex - 5} y={ey - 5} width={10} height={10} fill={COLORS.dangerRed} stroke={COLORS.void} strokeWidth={2} />
    </svg>
  );
}
