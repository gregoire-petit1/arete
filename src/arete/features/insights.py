"""One sentence per analytics card, in French.

Rule-based on purpose: the numbers are already on screen, what is missing is what
they mean. Every function takes what the card computed and returns a short line
plus a tone the UI colours.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Tone = Literal["good", "neutral", "warn", "bad"]


class Insight(TypedDict):
    text: str
    tone: Tone


def _insight(text: str, tone: Tone = "neutral") -> Insight:
    return {"text": text, "tone": tone}


def _pct(value: float) -> str:
    return f"{value:+.0f} %"


# --- Charge ---------------------------------------------------------------
VOLUME_SPIKE_PCT = 25.0
VOLUME_STABLE_PCT = 5.0


def volume_insight(km: float, prev_km: float | None, hours: float) -> Insight:
    if km <= 0:
        return _insight("Aucune séance sur la période.")
    base = f"{km:.0f} km, {hours:.1f} h"
    if not prev_km:
        return _insight(f"{base} sur la période.")
    change = (km - prev_km) / prev_km * 100
    if change > VOLUME_SPIKE_PCT:
        return _insight(
            f"{base}. Volume en forte hausse ({_pct(change)}) : surveille la fatigue.",
            "warn",
        )
    if change < -VOLUME_SPIKE_PCT:
        return _insight(
            f"{base}. Volume en nette baisse ({_pct(change)}) : coupure ou récupération ?",
            "warn",
        )
    if abs(change) <= VOLUME_STABLE_PCT:
        return _insight(f"{base}. Volume stable ({_pct(change)}).", "good")
    return _insight(f"{base}. Progression maîtrisée ({_pct(change)}).", "good")


def pmc_insight(
    ctl: float, tsb: float, acwr: float | None, acwr_zone: str | None
) -> Insight:
    head = f"Forme {ctl:.0f}, fraîcheur {tsb:+.0f}"
    if acwr is not None and acwr > 1.5:
        return _insight(
            f"{head}. Charge aiguë très supérieure à la chronique (ACWR {acwr:.2f}) : risque de blessure.",
            "bad",
        )
    if tsb < -25:
        return _insight(f"{head}. Fatigue lourde : prévois une décharge.", "bad")
    if acwr is not None and acwr > 1.3:
        return _insight(
            f"{head}. Montée de charge rapide (ACWR {acwr:.2f}) : ne rajoute rien cette semaine.",
            "warn",
        )
    if tsb < -10:
        return _insight(f"{head}. La fatigue s'accumule, normal en bloc de charge.")
    if tsb > 25:
        return _insight(
            f"{head}. Très frais : c'est le moment de performer, ou de recharger.",
            "warn",
        )
    zone = f" ({acwr_zone})" if acwr_zone else ""
    return _insight(f"{head}. Charge équilibrée{zone}.", "good")


# --- Intensité ------------------------------------------------------------
POLARIZED_EASY_PCT = 75.0
POLARIZED_HARD_PCT = 20.0
MIN_ZONE_MINUTES = 60


def zones_insight(
    easy_pct: float | None, hard_pct: float | None, total_min: int
) -> Insight:
    if easy_pct is None or total_min < MIN_ZONE_MINUTES:
        return _insight(
            "Pas assez de temps avec une mesure de FC pour juger la répartition."
        )
    hard = hard_pct or 0.0
    if easy_pct >= POLARIZED_EASY_PCT and hard <= POLARIZED_HARD_PCT:
        return _insight(
            f"Répartition polarisée : {easy_pct:.0f} % en Z1-Z2, {hard:.0f} % en Z4-Z5.",
            "good",
        )
    if easy_pct < 60:
        return _insight(
            f"Trop d'intensité moyenne : seulement {easy_pct:.0f} % en Z1-Z2.", "warn"
        )
    return _insight(f"{easy_pct:.0f} % en Z1-Z2, {hard:.0f} % en Z4-Z5 : vise 80/20.")


def sports_insight(
    top_sport: str | None, top_pct: float | None, n_sports: int
) -> Insight:
    if not top_sport or top_pct is None:
        return _insight("Aucune séance sur la période.")
    if n_sports == 1:
        return _insight(f"Uniquement du {top_sport} sur la période.")
    return _insight(
        f"{top_sport} domine avec {top_pct:.0f} % du temps, sur {n_sports} sports."
    )


# --- Économie cardiaque ---------------------------------------------------
DECOUPLING_GOOD_PCT = 5.0
DECOUPLING_OK_PCT = 10.0


def decoupling_insight(avg_pct: float | None, n_runs: int) -> Insight:
    if avg_pct is None or n_runs == 0:
        return _insight(
            "Pas de sortie assez longue (≥ 40 min avec des tours) pour mesurer le découplage."
        )
    tail = f"sur {n_runs} sortie{'s' if n_runs > 1 else ''}"
    if avg_pct < DECOUPLING_GOOD_PCT:
        return _insight(
            f"Découplage moyen {avg_pct:.1f} % {tail} : base aérobie solide.", "good"
        )
    if avg_pct < DECOUPLING_OK_PCT:
        return _insight(
            f"Découplage moyen {avg_pct:.1f} % {tail} : correct, encore de la marge."
        )
    return _insight(
        f"Découplage moyen {avg_pct:.1f} % {tail} : base aérobie à travailler.", "warn"
    )


PACE_TREND_MIN_RUNS = 5
PACE_TREND_SIGNIFICANT = 3.0  # s/km per month


def pace_insight(slope_sec_km_per_month: float | None, n_runs: int) -> Insight:
    if slope_sec_km_per_month is None or n_runs < PACE_TREND_MIN_RUNS:
        return _insight(
            f"Trop peu de sorties ({n_runs}) pour dégager une tendance d'allure."
        )
    if slope_sec_km_per_month <= -PACE_TREND_SIGNIFICANT:
        return _insight(
            f"Allure en progression : {abs(slope_sec_km_per_month):.0f} s/km gagnées par mois.",
            "good",
        )
    if slope_sec_km_per_month >= PACE_TREND_SIGNIFICANT:
        return _insight(
            f"Allure qui se dégrade : {slope_sec_km_per_month:.0f} s/km perdues par mois.",
            "warn",
        )
    return _insight("Allure stable sur la période.")


# --- Récupération ---------------------------------------------------------
def readiness_insight(mean: float | None, prev_mean: float | None) -> Insight:
    if mean is None:
        return _insight("Aucune donnée Garmin sur la période.")
    if prev_mean is None:
        return _insight(f"Préparation moyenne {mean:.0f}/100.")
    delta = mean - prev_mean
    if delta > 5:
        return _insight(
            f"Préparation moyenne {mean:.0f}/100, en hausse ({delta:+.0f}).", "good"
        )
    if delta < -5:
        return _insight(
            f"Préparation moyenne {mean:.0f}/100, en baisse ({delta:+.0f}).", "warn"
        )
    return _insight(f"Préparation moyenne {mean:.0f}/100, stable.")


def hrv_insight(mean: float | None, prev_mean: float | None) -> Insight:
    if mean is None:
        return _insight("Aucune mesure de VFC sur la période.")
    if prev_mean is None or prev_mean == 0:
        return _insight(f"VFC moyenne {mean:.0f} ms.")
    change = (mean - prev_mean) / prev_mean * 100
    if change > 5:
        return _insight(
            f"VFC moyenne {mean:.0f} ms ({_pct(change)}) : bonne adaptation.", "good"
        )
    if change < -10:
        return _insight(
            f"VFC moyenne {mean:.0f} ms ({_pct(change)}) : fatigue ou stress.", "warn"
        )
    return _insight(f"VFC moyenne {mean:.0f} ms, stable.")


SLEEP_SHORT_SEC = 6.5 * 3600
SLEEP_GOOD_SEC = 7.5 * 3600


def sleep_insight(mean_sec: float | None, mean_score: float | None) -> Insight:
    if mean_sec is None:
        return _insight("Aucune donnée de sommeil sur la période.")
    hours = int(mean_sec // 3600)
    minutes = int(round((mean_sec - hours * 3600) / 60))
    duration = f"{hours}h{minutes:02d}"
    score = f", score {mean_score:.0f}/100" if mean_score is not None else ""
    if mean_sec < SLEEP_SHORT_SEC:
        return _insight(f"Sommeil court : {duration} en moyenne{score}.", "warn")
    if mean_sec >= SLEEP_GOOD_SEC:
        return _insight(f"Sommeil suffisant : {duration} en moyenne{score}.", "good")
    return _insight(f"Sommeil moyen : {duration}{score}.")


def resting_hr_insight(mean: float | None, prev_mean: float | None) -> Insight:
    if mean is None:
        return _insight("Aucune mesure de FC de repos sur la période.")
    if prev_mean is None:
        return _insight(f"FC de repos moyenne {mean:.0f} bpm.")
    delta = mean - prev_mean
    if delta > 3:
        return _insight(
            f"FC de repos {mean:.0f} bpm ({delta:+.0f}) : fatigue ou début de maladie ?",
            "warn",
        )
    if delta < -2:
        return _insight(
            f"FC de repos {mean:.0f} bpm ({delta:+.0f}) : bon signe.", "good"
        )
    return _insight(f"FC de repos {mean:.0f} bpm, stable.")
