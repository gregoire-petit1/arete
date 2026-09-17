import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Period } from '@/types';
import { analyticsApi } from '@/lib/api';
import { CHART, COLORS } from '@/lib/chartTheme';
import {
  EfficiencyCard,
  LoadCard,
  PaceCard,
  PeriodSelector,
  PREVIOUS_LABEL,
  RecordsCard,
  RecoveryCard,
  SECTIONS,
  Section,
  SectionNav,
  SportsCard,
  VolumeCard,
  ZonesCard,
} from './analytics/index';

/** Highlight the section currently on screen. */
function useActiveSection(): string {
  const [active, setActive] = useState(SECTIONS[0].id);
  const observed = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    observed.current?.disconnect();
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length) setActive(visible[0].target.id);
      },
      { rootMargin: '-15% 0px -70% 0px' }
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    observed.current = observer;
    return () => observer.disconnect();
  }, []);

  return active;
}

export function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>('30d');
  const active = useActiveSection();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['analytics', 'overview', period],
    queryFn: () => analyticsApi.getOverview(period),
    staleTime: 60 * 1000,
  });

  const cards = data?.cards;
  const bucket = data?.bucket ?? 'day';
  const previousLabel = PREVIOUS_LABEL[period];
  const state = { loading: isLoading, error: isError, bucket, previousLabel };

  const jump = (id: string) =>
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold font-mono text-neon-cyan tracking-wider uppercase">Analyses</h1>
          {data && (
            <p className="text-xs text-text-muted font-mono mt-1">
              Du {new Date(`${data.start}T00:00:00`).toLocaleDateString('fr-FR')} au{' '}
              {new Date(`${data.end}T00:00:00`).toLocaleDateString('fr-FR')}
              {data.prev_start && ` · comparé ${previousLabel}`}
            </p>
          )}
        </div>
        <PeriodSelector period={period} onChange={setPeriod} />
      </div>

      <SectionNav active={active} onJump={jump} />

      <Section def={SECTIONS[0]}>
        <VolumeCard card={cards?.volume} {...state} />
        <LoadCard card={cards?.pmc} {...state} />
      </Section>

      <Section def={SECTIONS[1]}>
        <ZonesCard card={cards?.zones} model={data?.hr_zone_model} {...state} />
        <SportsCard card={cards?.sports} previousLabel={previousLabel} loading={isLoading} error={isError} />
      </Section>

      <Section def={SECTIONS[2]}>
        <EfficiencyCard card={cards?.decoupling} {...state} />
        <PaceCard card={cards?.pace} {...state} />
        <RecordsCard />
      </Section>

      <Section def={SECTIONS[3]}>
        <RecoveryCard
          title="Préparation"
          question="La montre dit-elle que le corps est prêt ?"
          card={cards?.readiness}
          color={COLORS.neonCyan}
          unit="/100"
          {...state}
        />
        <RecoveryCard
          title="VFC"
          question="La variabilité cardiaque tient-elle la charge ?"
          card={cards?.hrv}
          color={CHART.purple}
          unit="ms"
          {...state}
        />
        <RecoveryCard
          title="Sommeil"
          question="Assez de sommeil pour encaisser ?"
          card={cards?.sleep}
          color={COLORS.infoBlue}
          unit=""
          {...state}
        />
        <RecoveryCard
          title="FC de repos"
          question="La fréquence de repos dérive-t-elle ?"
          card={cards?.resting_hr}
          color={CHART.red}
          unit="bpm"
          {...state}
        />
      </Section>
    </div>
  );
}
