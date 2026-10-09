import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface SectionDef {
  id: string;
  title: string;
  /** What this section is for, in one sentence. */
  intro: string;
}

export const SECTIONS: SectionDef[] = [
  { id: 'charge', title: 'Charge', intro: "Combien j'ai encaissé, et où en est la forme." },
  { id: 'intensite', title: 'Intensité', intro: 'À quelle intensité, et réparti sur quels sports.' },
  { id: 'efficacite', title: 'Efficacité', intro: 'Ce que le cœur paie pour une allure donnée.' },
  { id: 'terrain', title: 'Terrain & foulée', intro: 'Le dénivelé encaissé et la mécanique de la foulée.' },
  { id: 'recuperation', title: 'Récupération', intro: 'Ce que la montre dit du sommeil et de la fraîcheur.' },
];

/** Sticky jump bar: one click per section. */
export function SectionNav({ active, onJump }: { active: string; onJump: (id: string) => void }) {
  return (
    <nav className="sticky top-0 z-10 -mx-4 px-4 py-2 bg-void/90 backdrop-blur border-b border-text-muted/10">
      <ul className="flex gap-2 flex-wrap">
        {SECTIONS.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onJump(s.id)}
              aria-current={active === s.id ? 'true' : undefined}
              className={cn(
                'px-3 py-1 text-xs font-mono uppercase tracking-wider rounded transition-colors',
                active === s.id
                  ? 'bg-neon-cyan/15 text-neon-cyan'
                  : 'text-text-secondary hover:text-text-primary'
              )}
            >
              {s.title}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function Section({ def, children }: { def: SectionDef; children: ReactNode }) {
  return (
    <section id={def.id} className="scroll-mt-16 space-y-3">
      <header>
        <h2 className="text-lg font-bold font-mono text-text-primary tracking-wider uppercase">{def.title}</h2>
        <p className="text-sm text-text-muted">{def.intro}</p>
      </header>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">{children}</div>
    </section>
  );
}
