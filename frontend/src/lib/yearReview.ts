import { fetchAPI } from './api';

/** GET /year-review (services/year_review.py). */
export interface YearSession {
  id: number | null;
  date: string;
  sport: string;
  name: string | null;
  duration_sec: number;
  distance_m: number | null;
  ascent_m: number | null;
  tss: number;
}

export interface YearSport {
  sport: string;
  sessions: number;
  duration_sec: number;
  distance_m: number;
  pct_time: number;
}

export interface YearMonth {
  month: number;
  sessions: number;
  duration_sec: number;
  distance_m: number;
  ascent_m: number;
  tss: number;
  strength_volume_kg: number;
}

export interface YearEffort {
  name: string;
  time_sec: number;
  time_display: string;
  date: string;
  activity_name: string;
  activity_id: number;
  previous_best_sec: number | null;
  is_pr: boolean;
}

export interface YearReview {
  year: number;
  start: string;
  end: string;
  complete: boolean;
  years: number[];
  totals: { sessions: number; duration_sec: number; distance_m: number; ascent_m: number; tss: number };
  sports: YearSport[];
  months: YearMonth[];
  consistency: {
    active_days: number;
    days: number;
    active_weeks: number;
    weeks: number;
    longest_day_streak: number;
    longest_week_streak: number;
  };
  highlights: {
    longest_distance: YearSession | null;
    longest_duration: YearSession | null;
    hardest: YearSession | null;
    biggest_climb: YearSession | null;
  };
  best_efforts: YearEffort[];
  pr_count: number;
  fitness: {
    series: { date: string; ctl: number }[];
    peak: { date: string; ctl: number } | null;
    start_ctl: number | null;
    end_ctl: number | null;
  };
  strength: {
    sessions: number;
    working_sets: number;
    volume_kg: number;
    top_exercises: { name: string; volume_kg: number; sets: number; max_weight_kg: number | null }[];
  };
}

export const yearReviewApi = {
  get: (year: number) => fetchAPI<YearReview>(`/year-review?year=${year}`),
};
