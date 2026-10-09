import portrait from '@/assets/rpg/chiron.svg';

/** Exact vector portrait from the approved Figma component 59:1301. */
export function ChironPortrait({ size = 24 }: { size?: number }) {
  return (
    <img
      src={portrait}
      alt=""
      aria-hidden
      width={size}
      height={size}
      className="shrink-0 object-contain"
    />
  );
}
