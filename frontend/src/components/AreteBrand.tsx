import { ActivityIndicator } from './ui/ActivityIndicator';

/** The approved Figma laurel is shared by Arete and its AI coach. */
export function AreteMark({ size = 24, className = '' }: { size?: number; className?: string }) {
  return <span className={`arete-mark ${className}`} style={{ width: size, height: size }} aria-hidden="true" />;
}

export function AreteWordmark() {
  return <span className="arete-wordmark"><AreteMark size={32} /><span>ARETE</span></span>;
}

/** Only the orbit moves: the brand stays readable while real work is pending. */
export function AretePresence({ active = true, size = 32 }: { active?: boolean; size?: number }) {
  return (
    <ActivityIndicator active={active} size={size}>
      <AreteMark size={size * 0.64} />
    </ActivityIndicator>
  );
}
